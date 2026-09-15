"""Linha digitável do boleto: 47 dígitos, e o código de barras de 44.

Os 47 dígitos são 43 de dados mais 4 verificadores, distribuídos em cinco campos:

- Campo 1 (10): banco (3) + moeda (1) + posições 20-24 do código de barras (5)
  + DV por módulo 10.
- Campo 2 (11): posições 25-34 do código de barras + DV por módulo 10.
- Campo 3 (11): posições 35-44 do código de barras + DV por módulo 10.
- Campo 4 (1): DV geral do código de barras, por módulo 11.
- Campo 5 (14): fator de vencimento (4) + valor em centavos (10), sem formatação.

**FATOR DE VENCIMENTO — a melhor armadilha de falha silenciosa do projeto.**
A data-base original era 07/10/1997. O fator atingiu o limite 9999 em 21/02/2025 e
foi reiniciado para 1000 em 22/02/2025, seguindo o incremento diário.

Um agente que use a data-base antiga para decodificar o fator 1569 responde
23/01/2002 para um boleto que vence em 14/09/2026: erra por cerca de 24 anos, com
confiança total e sem sinal nenhum. Rótulo: `usou_data_base_antiga_1997`.

O erro é indetectável por dígito verificador, porque o fator não mudou — mudou o
que ele significa. Os quatro DVs aprovam a linha inteira; só quem conhece a data
do reinício sabe que a resposta está 9.000 dias fora do lugar. Ver
`fator_para_data_pela_base_antiga`, que existe para **fabricar** essa resposta
errada e registrá-la em `silent_failure_if`.

**AS DUAS CONVENÇÕES DO MÓDULO 11, que não são a mesma.**
`base.modulo11` implementa a convenção de CPF, CNPJ e chave da NF-e: resto menor
que 2 produz dígito 0. O DV geral do código de barras usa a convenção da
FEBRABAN, que é **outra**: dígito 0, 10 ou 11 vira 1. Nunca vira 0.

Dois efeitos, os dois úteis:

1. Um agente que aprendeu "o módulo 11 brasileiro" como regra única erra o DV do
   boleto em cerca de 18% dos casos — os restos 0, 1 e 10 de 11 possíveis — e
   acerta nos outros 82%, o que é pior do que errar sempre, porque parece
   funcionar.
2. Nenhum boleto válido tem 0 no campo 4. É um invariante de graça, e o teste
   `test_o_dv_geral_nunca_e_zero` o fixa.

Por isso `modulo11_febraban` mora aqui, com nome próprio, em vez de virar um
parâmetro de `base.modulo11`. Uma função com dois comportamentos convida a passar
o parâmetro errado; duas funções com nomes diferentes, não.

Fontes conferidas em set/2026: layout de cobrança por código de barras do
Santander (v34) para os dois algoritmos, e a documentação da FEBRABAN sobre o
reinício do fator. A aritmética do reinício foi verificada nos dois sentidos:
07/10/1997 + 9999 dias = 21/02/2025, e 22/02/2025 - 1000 dias = 29/05/2022.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Final, NamedTuple, assert_never

from curupira.core.enums import Corrupcao
from curupira.formatos.base import (
    Gerado,
    incrementar_digito,
    modulo10,
    rng_de,
    transpor_detectavel,
    trocar_caractere,
)

TAMANHO_DA_LINHA: Final = 47
TAMANHO_DO_BARRAS: Final = 44
TAMANHO_DO_BANCO: Final = 3

MOEDA_REAL: Final = "9"
"""Codigo da moeda no codigo de barras. Real e 9; nao ha outro em uso."""

TAMANHO_DO_FATOR: Final = 4
TAMANHO_DO_VALOR: Final = 10
TAMANHO_DO_CAMPO_LIVRE: Final = 25

DATA_BASE_ANTIGA: Final = date(1997, 10, 7)
"""Data-base original. Mantida aqui para GERAR a resposta errada rotulada."""

DATA_BASE_NOVA: Final = date(2025, 2, 22)
"""Data em que o fator foi reiniciado para 1000."""

FATOR_NO_REINICIO: Final = 1000
FATOR_MAXIMO: Final = 9999
FATOR_SEM_VENCIMENTO: Final = 0
"""Fator `0000`: boleto sem data de vencimento. E valido e nao vira data."""

PRIMEIRA_DATA: Final = DATA_BASE_NOVA
ULTIMA_DATA: Final = DATA_BASE_NOVA + timedelta(days=FATOR_MAXIMO - FATOR_NO_REINICIO)
"""Faixa representavel pela regra vigente: 22/02/2025 a 13/10/2049."""

VALOR_MAXIMO_CENTAVOS: Final = 10**TAMANHO_DO_VALOR - 1

_PESO_INICIAL: Final = 2
_PESO_FINAL: Final = 9
_MODULO: Final = 11
_DVS_QUE_VIRAM_UM: Final = frozenset({0, 10, 11})
"""Convencao FEBRABAN do DV geral. Note que 0 NAO esta entre os resultados."""

_NUA: Final = re.compile(r"^\d{47}$")
_MASCARADA: Final = re.compile(r"^\d{5}\.\d{5} \d{5}\.\d{6} \d{5}\.\d{6} \d \d{14}$")

# Fatias da linha digitavel, declaradas em vez de espalhadas pelo codigo.
_CAMPO1_DADOS: Final = slice(0, 9)
_CAMPO1_DV: Final = 9
_CAMPO2_DADOS: Final = slice(10, 20)
_CAMPO2_DV: Final = 20
_CAMPO3_DADOS: Final = slice(21, 31)
_CAMPO3_DV: Final = 31
_CAMPO4_DV_GERAL: Final = 32
_CAMPO5: Final = slice(33, 47)


class Boleto(NamedTuple):
    """As partes de um boleto, antes de qualquer dígito verificador.

    Existe para que `gerar` e `corromper` montem a linha pelo mesmo caminho: toda
    corrupção que recalcula os DVs passa por aqui, e nenhuma monta a linha à mão.
    """

    banco: str
    """Tres digitos."""

    moeda: str
    """Um digito. `MOEDA_REAL` em qualquer boleto real."""

    fator: str
    """Quatro digitos."""

    valor: str
    """Dez digitos, em centavos, com zeros a esquerda."""

    livre: str
    """Vinte e cinco digitos, de uso livre do banco emissor."""


def modulo11_febraban(digitos: str) -> int:
    """Calcula o DV geral do código de barras pela convenção da FEBRABAN.

    Pesos de 2 a 9, ciclando, aplicados da direita para a esquerda. O dígito é
    `11 - (soma % 11)`, e **0, 10 ou 11 viram 1**.

    Essa última regra é o que separa esta função de `base.modulo11`, que faz o
    oposto: lá, resultado fora da faixa vira 0. Ver a nota no topo do módulo.

    Args:
        digitos: os 43 dígitos do código de barras, sem a posição do próprio DV.

    Returns:
        O dígito verificador, de 1 a 9. Nunca 0.

    Raises:
        ValueError: se a entrada estiver vazia ou tiver algo que não seja dígito.
    """
    if not digitos or not digitos.isdigit():
        msg = f"modulo11_febraban espera digitos, recebeu {digitos!r}"
        raise ValueError(msg)
    soma = 0
    peso = _PESO_INICIAL
    for caractere in reversed(digitos):
        soma += int(caractere) * peso
        peso = _PESO_INICIAL if peso == _PESO_FINAL else peso + 1
    dv = _MODULO - soma % _MODULO
    return 1 if dv in _DVS_QUE_VIRAM_UM else dv


def fator_para_data(fator: int) -> date:
    """Converte um fator de vencimento em data, pela regra vigente.

    Args:
        fator: o fator de 4 dígitos.

    Returns:
        A data de vencimento.

    Raises:
        ValueError: se o fator estiver fora de 1000 a 9999. `0000` significa
            "sem vencimento" e não tem data; converter seria inventar uma.
    """
    if not FATOR_NO_REINICIO <= fator <= FATOR_MAXIMO:
        msg = (
            f"fator {fator} fora da faixa representavel "
            f"({FATOR_NO_REINICIO} a {FATOR_MAXIMO}); "
            f"{FATOR_SEM_VENCIMENTO} significa boleto sem vencimento"
        )
        raise ValueError(msg)
    return DATA_BASE_NOVA + timedelta(days=fator - FATOR_NO_REINICIO)


def fator_para_data_pela_base_antiga(fator: int) -> date:
    """Converte um fator pela data-base de 1997, **que não vale mais**.

    Esta função existe para produzir a resposta errada, não a certa. O dataset
    precisa saber exatamente qual data um agente desatualizado responderia, para
    registrá-la em `silent_failure_if` com o rótulo `usou_data_base_antiga_1997`.
    Sem isso, o benchmark saberia que o agente errou, mas não *como* — e é o como
    que vira gráfico no artigo.

    Args:
        fator: o fator de 4 dígitos.

    Returns:
        A data que a base de 07/10/1997 produziria — cerca de 24 anos e meio
        antes da correta, para qualquer fator da era vigente.

    Raises:
        ValueError: se o fator estiver fora de 1000 a 9999.
    """
    if not FATOR_NO_REINICIO <= fator <= FATOR_MAXIMO:
        msg = f"fator {fator} fora da faixa representavel"
        raise ValueError(msg)
    return DATA_BASE_ANTIGA + timedelta(days=fator)


def data_para_fator(vencimento: date) -> int:
    """Converte uma data de vencimento em fator, pela regra vigente.

    Args:
        vencimento: a data.

    Returns:
        O fator de 4 dígitos.

    Raises:
        ValueError: se a data cair fora da faixa representável.
    """
    if not PRIMEIRA_DATA <= vencimento <= ULTIMA_DATA:
        msg = (
            f"{vencimento.isoformat()} fora da faixa representavel pela regra "
            f"vigente ({PRIMEIRA_DATA.isoformat()} a {ULTIMA_DATA.isoformat()})"
        )
        raise ValueError(msg)
    return FATOR_NO_REINICIO + (vencimento - DATA_BASE_NOVA).days


def _digitos(linha: str) -> str | None:
    """Extrai os 47 dígitos, se a grafia for uma das duas aceitas.

    Duas grafias, e só elas: 47 dígitos nus, ou a grafia usual impressa no
    boleto. A rigidez é o que torna `MASCARA_ERRADA` detectável.
    """
    if _NUA.match(linha):
        return linha
    if _MASCARADA.match(linha):
        return linha.replace(".", "").replace(" ", "")
    return None


def _dvs_de_campo(nua: str) -> tuple[int, int, int]:
    """Calcula os três DVs de campo por módulo 10, a partir dos dados da linha."""
    return (
        modulo10([int(c) for c in nua[_CAMPO1_DADOS]]),
        modulo10([int(c) for c in nua[_CAMPO2_DADOS]]),
        modulo10([int(c) for c in nua[_CAMPO3_DADOS]]),
    )


def codigo_de_barras(linha: str) -> str:
    """Reconstrói o código de barras de 44 posições a partir da linha digitável.

    A linha digitável **não** é o código de barras com pontinhos: ela reordena os
    campos e acrescenta três DVs que o código de barras não tem. Quem trata as
    duas grafias como a mesma coisa erra por construção.

    Args:
        linha: a linha digitável, com ou sem máscara.

    Returns:
        Os 44 dígitos do código de barras.

    Raises:
        ValueError: se a grafia da linha não for aceita.
    """
    nua = _digitos(linha)
    if nua is None:
        msg = f"grafia de linha digitavel nao reconhecida: {linha!r}"
        raise ValueError(msg)
    return (
        nua[0:4]
        + nua[_CAMPO4_DV_GERAL]
        + nua[_CAMPO5]
        + nua[4:9]
        + nua[_CAMPO2_DADOS]
        + nua[_CAMPO3_DADOS]
    )


def _linha_de(boleto: Boleto) -> str:
    """Monta a linha digitável nua de 47 dígitos, calculando os quatro DVs."""
    sem_dv_geral = boleto.banco + boleto.moeda + boleto.fator + boleto.valor + boleto.livre
    dv_geral = modulo11_febraban(sem_dv_geral)

    campo1 = boleto.banco + boleto.moeda + boleto.livre[0:5]
    campo2 = boleto.livre[5:15]
    campo3 = boleto.livre[15:25]
    dv1, dv2, dv3 = _dvs_de_campo(f"{campo1}0{campo2}0{campo3}0")

    return f"{campo1}{dv1}{campo2}{dv2}{campo3}{dv3}{dv_geral}{boleto.fator}{boleto.valor}"


def partes_de(linha: str) -> Boleto:
    """Decompõe uma linha digitável nas partes que a originaram.

    Args:
        linha: a linha digitável, com ou sem máscara.

    Returns:
        As partes, sem nenhum dígito verificador.

    Raises:
        ValueError: se a grafia da linha não for aceita.
    """
    barras = codigo_de_barras(linha)
    return Boleto(
        banco=barras[0:3],
        moeda=barras[3],
        fator=barras[5:9],
        valor=barras[9:19],
        livre=barras[19:TAMANHO_DO_BARRAS],
    )


def _fatiar(linha: str) -> str:
    """Aplica o layout da grafia usual a 47 caracteres quaisquer.

    Separada de `mascarar` porque `corromper` precisa preservar a grafia de uma
    linha mascarada mesmo quando o resultado já não é composto só de dígitos —
    um `X` no meio de uma linha impressa é justamente o que se quer mostrar ao
    agente. `mascarar` valida antes; esta só fatia.
    """
    return (
        f"{linha[0:5]}.{linha[5:10]} {linha[10:15]}.{linha[15:21]} "
        f"{linha[21:26]}.{linha[26:32]} {linha[32]} {linha[33:47]}"
    )


def mascarar(nua: str) -> str:
    """Aplica a grafia usual impressa no boleto.

    Args:
        nua: os 47 dígitos.

    Returns:
        A linha no formato `00000.00000 00000.000000 00000.000000 0 00000000000000`.

    Raises:
        ValueError: se não forem 47 dígitos.
    """
    if not _NUA.match(nua):
        msg = f"mascarar espera {TAMANHO_DA_LINHA} digitos, recebeu {nua!r}"
        raise ValueError(msg)
    return _fatiar(nua)


def _fator_na_faixa(fator: str) -> bool:
    """Diz se o fator é `0000` (sem vencimento) ou está na faixa 1000-9999."""
    numero = int(fator)
    return numero == FATOR_SEM_VENCIMENTO or FATOR_NO_REINICIO <= numero <= FATOR_MAXIMO


def validar(linha: str) -> bool:
    """Valida uma linha digitável de 47 dígitos.

    Confere, nesta ordem: grafia, os três DVs de campo (módulo 10), o DV geral
    (módulo 11 da FEBRABAN, reconstruindo o código de barras) e a faixa dos
    campos estruturais — moeda e fator de vencimento.

    **As camadas não são redundantes, e nenhuma cobre a outra.** Um agente que
    confira só os DVs de campo aprova uma linha cujo código de barras é
    inconsistente; um que confira só o DV geral aprova uma linha que nenhum caixa
    eletrônico aceitaria digitada. E nenhum dos dois pega fator fora de faixa,
    porque ali a aritmética está perfeita — o número é que é impossível.

    Args:
        linha: a linha digitável, com ou sem máscara.

    Returns:
        `True` se as quatro camadas aprovam.
    """
    nua = _digitos(linha)
    if nua is None:
        return False

    dv1, dv2, dv3 = _dvs_de_campo(nua)
    if (nua[_CAMPO1_DV], nua[_CAMPO2_DV], nua[_CAMPO3_DV]) != (str(dv1), str(dv2), str(dv3)):
        return False

    barras = codigo_de_barras(nua)
    if barras[4] != str(modulo11_febraban(barras[0:4] + barras[5:TAMANHO_DO_BARRAS])):
        return False

    return barras[3] == MOEDA_REAL and _fator_na_faixa(barras[5:9])


def gerar(
    rng_seed: int,
    *,
    vencimento: date,
    valor_centavos: int,
    banco: str = "001",
    com_mascara: bool = False,
) -> Gerado:
    """Gera uma linha digitável válida.

    Args:
        rng_seed: a seed.
        vencimento: a data de vencimento.
        valor_centavos: o valor, em centavos, sem formatação.
        banco: código do banco, 3 dígitos.
        com_mascara: se verdadeiro, aplica pontos e espaços da grafia usual.

    Returns:
        A linha digitável gerada.

    Raises:
        ValueError: se o banco não tiver 3 dígitos, se o valor não couber em 10
            dígitos ou for negativo, ou se o vencimento cair fora da faixa
            representável.
    """
    if len(banco) != TAMANHO_DO_BANCO or not banco.isdigit():
        msg = f"banco espera {TAMANHO_DO_BANCO} digitos, recebeu {banco!r}"
        raise ValueError(msg)
    if not 0 <= valor_centavos <= VALOR_MAXIMO_CENTAVOS:
        msg = f"valor_centavos fora de 0 a {VALOR_MAXIMO_CENTAVOS}: {valor_centavos}"
        raise ValueError(msg)

    rng = rng_de(rng_seed)
    boleto = Boleto(
        banco=banco,
        moeda=MOEDA_REAL,
        fator=f"{data_para_fator(vencimento):0{TAMANHO_DO_FATOR}d}",
        valor=f"{valor_centavos:0{TAMANHO_DO_VALOR}d}",
        livre="".join(str(rng.randrange(10)) for _ in range(TAMANHO_DO_CAMPO_LIVRE)),
    )
    nua = _linha_de(boleto)
    return Gerado(
        valor=mascarar(nua) if com_mascara else nua,
        valido=True,
        corrupcao=None,
        seed=rng_seed,
    )


def _com_fator_fora_da_faixa(nua: str, rng_seed: int) -> str:
    """Refaz a linha com um fator de 1 a 999, recalculando os quatro DVs.

    É a corrupção mais valiosa deste módulo porque **a aritmética continua
    perfeita**. Os quatro dígitos verificadores conferem; o que não existe é o
    número. Um validador que só some e divida aprova a linha, e o boleto é
    irrecebível.
    """
    rng = rng_de(rng_seed)
    fora = rng.randrange(1, FATOR_NO_REINICIO)
    partes = partes_de(nua)._replace(fator=f"{fora:0{TAMANHO_DO_FATOR}d}")
    return _linha_de(partes)


def _transpor(nua: str, rng_seed: int) -> str:
    """Troca dois dígitos vizinhos de forma verificadamente detectável.

    A transposição dentro de um campo protegido por módulo 10 **nem sempre é
    detectada por aquele DV** — é a fraqueza conhecida do módulo 10, e o motivo
    de o código de barras carregar um módulo 11 por cima. Mas as duas camadas
    juntas ainda deixam casos passar, e a fronteira entre um campo e o seu
    próprio DV nem sequer corresponde a dígitos vizinhos no código de barras.

    Deduzir qual troca é segura daria errado de vez em quando, e "de vez em
    quando" aqui significa uma tarefa com gabarito errado no dataset. Então
    verifica-se, como em CPF e CNPJ.
    """
    candidato = transpor_detectavel(nua, TAMANHO_DA_LINHA, validar, rng_seed)
    if candidato is not None:
        return candidato
    return trocar_caractere(nua, _CAMPO4_DV_GERAL, incrementar_digito(nua[_CAMPO4_DV_GERAL]))


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe uma linha digitável pelo modo pedido.

    `TRANSPOSICAO` é deliberadamente escolhido: o módulo 10 dos campos não
    detecta todas as trocas de vizinhos, e um agente que confia no DV de campo
    passa direto — por isso a troca é **verificada** contra o validador inteiro.

    `FAIXA_INVALIDA` é o modo mais valioso: refaz a linha com um fator de
    vencimento impossível e **recalcula os quatro DVs**, de modo que só quem
    conhece a faixa reprova.

    A grafia de entrada é preservada: uma linha mascarada sai mascarada, inclusive
    quando o resultado já não é composto só de dígitos. A exceção é
    `MASCARA_ERRADA`, cujo produto **é** uma grafia diferente, e
    `TAMANHO_ERRADO`, que destrói o layout. Sem isso, corromper uma linha
    impressa mudaria dois atributos de uma vez e o gabarito mentiria sobre qual
    deles o agente deveria ter percebido.

    Args:
        valor: uma linha digitável válida.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        A linha corrompida, que `validar` reprova.

    Raises:
        ValueError: se `valor` não for válido, ou se o modo não se aplicar à
            linha digitável.
    """
    nua = _digitos(valor)
    if nua is None or not validar(nua):
        msg = f"corromper espera uma linha digitavel valida, recebeu {valor!r}"
        raise ValueError(msg)

    rng = rng_de(rng_seed)
    mascarada = "." in valor

    if modo is Corrupcao.MASCARA_ERRADA:
        # Sai por aqui porque o resultado NAO deve ser remascarado no fim.
        return Gerado(
            valor=f"{nua[0:10]}.{nua[10:21]}.{nua[21:32]}-{nua[32:]}",
            valido=False,
            corrupcao=modo,
            seed=rng_seed,
        )

    if modo is Corrupcao.DV_TROCADO:
        corrompida = trocar_caractere(
            nua, _CAMPO4_DV_GERAL, incrementar_digito(nua[_CAMPO4_DV_GERAL])
        )
    elif modo is Corrupcao.TRANSPOSICAO:
        corrompida = _transpor(nua, rng_seed)
    elif modo is Corrupcao.FAIXA_INVALIDA:
        corrompida = _com_fator_fora_da_faixa(nua, rng_seed)
    elif modo is Corrupcao.TAMANHO_ERRADO:
        corrompida = nua[: rng.randrange(1, TAMANHO_DA_LINHA)]
    elif modo is Corrupcao.CARACTERE_INVALIDO:
        corrompida = trocar_caractere(nua, rng.randrange(TAMANHO_DA_LINHA), "X")
    elif modo is Corrupcao.SEQUENCIA_REPETIDA:
        # 47 zeros passa nos TRES DVs de campo (modulo 10 de zeros e zero) e e
        # reprovada so pelo DV geral, que pela convencao da FEBRABAN nunca e 0.
        # Melhor contraexemplo possivel para a intuicao de que "conferir o
        # digito verificador" e uma coisa so.
        corrompida = "0" * TAMANHO_DA_LINHA
    else:
        # `assert_never` em vez de `raise ValueError`: o mypy prova aqui, em tempo
        # de checagem, que TODO modo de `Corrupcao` esta tratado acima. No dia em
        # que alguem acrescentar um modo ao enum e esquecer deste modulo, o erro
        # aparece no portao — nao meses depois, numa tarefa que usou o modo novo.
        assert_never(modo)

    if mascarada and len(corrompida) == TAMANHO_DA_LINHA:
        corrompida = _fatiar(corrompida)
    return Gerado(valor=corrompida, valido=False, corrupcao=modo, seed=rng_seed)
