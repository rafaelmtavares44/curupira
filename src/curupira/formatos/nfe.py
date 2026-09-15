"""Chave de acesso da NF-e: 44 posições.

Composição: cUF (2) + AAMM (4) + CNPJ (14) + modelo (2) + série (3) + número (9)
+ tipo de emissão (1) + código numérico (8) + DV (1).

O DV usa módulo 11 com pesos de 2 a 9, aplicados da direita para a esquerda sobre
as 43 primeiras posições; resto 0 ou 1 resulta em dígito 0 — a mesma convenção de
CPF e CNPJ, e **a oposta** da que o boleto usa no DV do código de barras. Ver a
nota no topo de `curupira.formatos.boleto`, onde a divergência está medida.

**PENDÊNCIA RESOLVIDA (era: "a Nota Técnica ainda NÃO foi lida").**
A NT 2025.001 foi lida. A chave deixou de ser exclusivamente numérica: a
expressão regular oficial passou a ser `[0-9]{6}[A-Z0-9]{12}[0-9]{26}`, ou seja,
as 12 posições da raiz e da ordem do CNPJ aceitam letras maiúsculas, e os 2
dígitos verificadores do CNPJ continuam numéricos — soma 44. O cálculo do DV da
chave "deverá aplicar a mesma lógica da validação do CNPJ Alfa, trocando todos os
caracteres pelos números correspondentes da tabela ASCII subtraindo 48".

Duas ambiguidades do texto oficial, declaradas em vez de escondidas
---------------------------------------------------------------
1. A NT diz "todos os caracteres (44) que compõe a chave" e em seguida manda
   aplicar o módulo 11 — mas o DV *é* a 44ª posição, e não pode entrar no cálculo
   de si mesmo. Implementamos sobre as 43 primeiras, que é a única leitura
   aritmeticamente possível e a que reproduz o vetor de referência publicado.
2. A conversão `ASCII - 48` é idêntica para dígitos e letras, então uma
   implementação correta do formato numérico já estava correta para o
   alfanumérico. Isso é conveniente e é também a razão de tanta gente achar que
   "não mudou nada": mudou o espaço de entrada, não a aritmética.

**HERDADO DO CNPJ: o DV da chave alfanumérica é mais fraco contra transposição.**
Os 43 pares de caracteres cujos valores diferem em múltiplo de 11 (ver
`cnpj.transposicoes_indetectaveis`) valem aqui pelo mesmo motivo, agora numa
chave que identifica um documento fiscal. Por isso `_transpor` **verifica** com o
validador em vez de confiar no raciocínio.

O buraco do cUF, e o buraco do tpEmis
-------------------------------------
Os códigos do IBGE não são contínuos: entre RJ (33) e SP (35) não existe 34. Um
modelo que "complete a sequência" produz 34 e fabrica uma chave que passa em
qualquer verificação de dígito verificador e não existe. Mesma família de
armadilha do CEP de Roraima dentro do Amazonas.

O tpEmis é o caso oposto, e vale registrar a diferença: as tabelas publicadas
listam de 1 a 7 e o 9, sem mencionar o 8. **Não encontramos fonte que declare o 8
proibido**, apenas fontes que não o listam. Ausência de menção não é proibição,
então `validar` recusa somente o 0 e documenta a lacuna. Inventar uma regra
fecharia o validador contra chave legítima — erro pior que o que evitaria.

Fontes conferidas em set/2026: NT 2025.001 (CNPJ alfanumérico na chave), tabela
de código de UF do IBGE, e um exemplo numérico publicado do cálculo do DV, que a
implementação reproduz dígito a dígito.
"""

from __future__ import annotations

import re
import string
from typing import Final, assert_never

from curupira.core.enums import Corrupcao
from curupira.formatos import cnpj as mod_cnpj
from curupira.formatos.base import (
    Gerado,
    apenas_alfanumericos,
    incrementar_digito,
    modulo11,
    rng_de,
    transpor_detectavel,
    trocar_caractere,
)

TAMANHO: Final = 44
_TAMANHO_DA_BASE: Final = 43

MODELO_NFE: Final = "55"
MODELO_NFCE: Final = "65"
MODELOS: Final = frozenset({MODELO_NFE, MODELO_NFCE})
"""Modelos que este modulo trata. CT-e (57) e MDF-e (58) usam a mesma estrutura
de chave e outro conjunto de regras de negocio; aceita-los aqui seria prometer
uma validacao que este modulo nao faz."""

CUF_POR_UF: Final = {
    "RO": 11, "AC": 12, "AM": 13, "RR": 14, "PA": 15, "AP": 16, "TO": 17,
    "MA": 21, "PI": 22, "CE": 23, "RN": 24, "PB": 25, "PE": 26, "AL": 27,
    "SE": 28, "BA": 29,
    "MG": 31, "ES": 32, "RJ": 33, "SP": 35,
    "PR": 41, "SC": 42, "RS": 43,
    "MS": 50, "MT": 51, "GO": 52, "DF": 53,
}  # fmt: skip
"""Os 27 codigos do IBGE. Fonte: tabela de codigo de UF do IBGE, set/2026."""

CUFS_VALIDOS: Final = frozenset(CUF_POR_UF.values())

CUFS_INEXISTENTES: Final = tuple(codigo for codigo in range(10, 100) if codigo not in CUFS_VALIDOS)
"""Codigos de dois digitos que nao pertencem a UF nenhuma. O 34 e o mais util:
mora exatamente entre RJ (33) e SP (35) e parece a continuacao da sequencia."""

MES_MINIMO: Final = 1
MES_MAXIMO: Final = 12
TPEMIS_INVALIDO: Final = "0"

_PESO_INICIAL: Final = 2
_QUANTIDADE_DE_PESOS: Final = 8
PESOS_DV: Final = tuple(
    _PESO_INICIAL + ((_TAMANHO_DA_BASE - 1 - i) % _QUANTIDADE_DE_PESOS)
    for i in range(_TAMANHO_DA_BASE)
)
"""Pesos ja alinhados da esquerda para a direita, para casar com `base.modulo11`.

A especificacao descreve "2 a 9 da direita para a esquerda". Traduzir isso em
indices na hora do uso e onde uma implementacao erra por um; aqui a traducao
acontece uma vez so, e o teste `test_os_pesos_batem_com_a_especificacao` fixa
as duas pontas da tupla."""

_NUA: Final = re.compile(r"^[0-9]{6}[0-9A-Z]{12}[0-9]{26}$")
"""A expressao regular da NT 2025.001, literalmente: 6 + 12 + 26 = 44."""

_AGRUPADA: Final = re.compile(r"^[0-9]{4}(?: [0-9A-Z]{4}){10}$")
"""Grafia impressa no DANFE: onze grupos de quatro, separados por espaco."""

REPETIDOS: Final = frozenset(c * TAMANHO for c in string.digits)
"""Passam no digito verificador e mesmo assim nao sao chave de documento nenhum.

`"0" * 44` e o exemplar interessante: as 43 primeiras posicoes somam zero, o
resto e 0, a regra "resto menor que 2 vira 0" produz exatamente o 0 que esta
la, e o DV **aprova**. Quem reprova e a faixa do cUF. E o espelho do caso do
boleto, onde os tres DVs de campo aprovam 47 zeros e o DV geral reprova."""

# Fatias da chave, declaradas em vez de espalhadas pelo codigo.
_CUF: Final = slice(0, 2)
_ANO: Final = slice(2, 4)
_MES: Final = slice(4, 6)
_CNPJ: Final = slice(6, 20)
_MODELO: Final = slice(20, 22)
_SERIE: Final = slice(22, 25)
_NUMERO: Final = slice(25, 34)
_TPEMIS: Final = 34
_CODIGO: Final = slice(35, 43)
_DV: Final = 43
_FIM_DO_ALFANUMERICO: Final = 18
"""Indice exclusivo: as posicoes 6 a 17 aceitam letra; 18 e 19 sao os DV do CNPJ."""


def _valor(caractere: str) -> int:
    """Converte um caractere no valor da especificação: `ASCII - 48`."""
    return ord(caractere) - mod_cnpj.OFFSET_ASCII


def calcular_dv(base: str) -> int:
    """Calcula o dígito verificador das 43 primeiras posições da chave.

    Args:
        base: as 43 posições, sem o DV.

    Returns:
        O dígito verificador, de 0 a 9.

    Raises:
        ValueError: se não forem exatamente 43 posições.
    """
    if len(base) != _TAMANHO_DA_BASE:
        msg = f"calcular_dv espera {_TAMANHO_DA_BASE} posicoes, recebeu {len(base)}"
        raise ValueError(msg)
    return modulo11([_valor(c) for c in base], PESOS_DV)


def _caracteres(chave: str) -> str | None:
    """Extrai as 44 posições, se a grafia for uma das duas aceitas."""
    if _NUA.match(chave):
        return chave
    if _AGRUPADA.match(chave):
        nua = chave.replace(" ", "")
        return nua if _NUA.match(nua) else None
    return None


def e_alfanumerica(chave: str) -> bool:
    """Diz se a chave carrega um CNPJ alfanumérico.

    Args:
        chave: a chave, com ou sem agrupamento.

    Returns:
        `True` se houver letra nas posições 7 a 18.
    """
    nua = _caracteres(chave)
    return nua is not None and not nua[_CNPJ.start : _FIM_DO_ALFANUMERICO].isdigit()


def validar(chave: str) -> bool:
    """Valida uma chave de acesso de 44 posições.

    Quatro camadas, e nenhuma cobre a outra: grafia, dígito verificador, CNPJ
    embutido (que tem os **próprios** dois DVs) e faixa dos campos estruturais
    (cUF existente, mês de 1 a 12, modelo conhecido, tpEmis diferente de zero).

    Args:
        chave: a chave, com ou sem o agrupamento de quatro em quatro.

    Returns:
        `True` se as quatro camadas aprovam.
    """
    nua = _caracteres(chave)
    if nua is None or nua in REPETIDOS:
        return False
    if nua[_DV] != str(calcular_dv(nua[:_TAMANHO_DA_BASE])):
        return False
    if not mod_cnpj.validar(nua[_CNPJ]):
        return False
    if int(nua[_CUF]) not in CUFS_VALIDOS:
        return False
    if not MES_MINIMO <= int(nua[_MES]) <= MES_MAXIMO:
        return False
    return nua[_MODELO] in MODELOS and nua[_TPEMIS] != TPEMIS_INVALIDO


def _fatiar(chave: str) -> str:
    """Agrupa 44 caracteres quaisquer de quatro em quatro.

    Separada de `agrupar` pelo mesmo motivo de `boleto._fatiar`: `corromper`
    precisa preservar a grafia impressa mesmo quando o resultado deixou de casar
    com a expressão regular oficial — uma minúscula no meio de uma chave impressa
    é exatamente o que se quer mostrar ao agente.
    """
    return " ".join(chave[i : i + 4] for i in range(0, TAMANHO, 4))


def agrupar(nua: str) -> str:
    """Aplica a grafia impressa no DANFE: onze grupos de quatro.

    Args:
        nua: as 44 posições.

    Returns:
        A chave agrupada.

    Raises:
        ValueError: se a grafia nua não for aceita.
    """
    if not _NUA.match(nua):
        msg = f"agrupar espera {TAMANHO} posicoes no formato da NT, recebeu {nua!r}"
        raise ValueError(msg)
    return _fatiar(nua)


def gerar(
    rng_seed: int,
    *,
    cnpj_emitente: str,
    cuf: int,
    ano: int,
    mes: int,
    modelo: str = MODELO_NFE,
    agrupada: bool = False,
) -> Gerado:
    """Gera uma chave de acesso válida.

    Aceita CNPJ numérico ou alfanumérico — ver a pendência resolvida no topo do
    módulo. O emitente **não é sorteado aqui**: quem chama passa um CNPJ já
    gerado por `curupira.formatos.cnpj`, de modo que exista um único lugar no
    projeto que produz CNPJ, e um único lugar que o valida.

    Args:
        rng_seed: a seed.
        cnpj_emitente: CNPJ do emitente, 14 caracteres, nu ou mascarado.
        cuf: código IBGE da unidade federativa.
        ano: ano de emissão, 4 dígitos.
        mes: mês de emissão, 1 a 12.
        modelo: `"55"` para NF-e, `"65"` para NFC-e.
        agrupada: se verdadeiro, devolve na grafia do DANFE.

    Returns:
        A chave gerada.

    Raises:
        ValueError: se o CNPJ for inválido, o cUF não existir, o mês estiver fora
            de 1 a 12, ou o modelo não for conhecido.
    """
    emitente = apenas_alfanumericos(cnpj_emitente)
    if not mod_cnpj.validar(emitente):
        msg = f"cnpj_emitente invalido: {cnpj_emitente!r}"
        raise ValueError(msg)
    if cuf not in CUFS_VALIDOS:
        msg = f"cUF {cuf} nao pertence a unidade federativa nenhuma"
        raise ValueError(msg)
    if not MES_MINIMO <= mes <= MES_MAXIMO:
        msg = f"mes fora de {MES_MINIMO} a {MES_MAXIMO}: {mes}"
        raise ValueError(msg)
    if modelo not in MODELOS:
        msg = f"modelo desconhecido: {modelo!r}"
        raise ValueError(msg)

    rng = rng_de(rng_seed)
    base = (
        f"{cuf:02d}"
        f"{ano % 100:02d}{mes:02d}"
        f"{emitente}"
        f"{modelo}"
        f"{rng.randrange(1, 1000):03d}"
        f"{rng.randrange(1, 10**9):09d}"
        f"{rng.choice('124567'):1}"
        f"{rng.randrange(10**8):08d}"
    )
    nua = f"{base}{calcular_dv(base)}"
    return Gerado(
        valor=agrupar(nua) if agrupada else nua,
        valido=True,
        corrupcao=None,
        seed=rng_seed,
    )


def _com_cuf_inexistente(nua: str, rng_seed: int) -> str:
    """Refaz a chave com um cUF que não existe, **recalculando o DV**.

    A corrupção mais valiosa deste módulo, pelo mesmo motivo do fator de
    vencimento fora de faixa no boleto: a aritmética continua perfeita. O DV
    confere, o CNPJ confere, e mesmo assim a chave é impossível. Só reprova quem
    conhece a tabela do IBGE — e quem "completa a sequência" cai no 34.
    """
    rng = rng_de(rng_seed)
    base = f"{rng.choice(CUFS_INEXISTENTES):02d}" + nua[_CUF.stop : _TAMANHO_DA_BASE]
    return f"{base}{calcular_dv(base)}"


def _transpor(nua: str, rng_seed: int) -> str:
    """Troca dois caracteres vizinhos de forma verificadamente detectável.

    Três pontos cegos se somam aqui: o do resto 0/1 do módulo 11, o dos 43 pares
    de caracteres alfanuméricos cujos valores diferem em múltiplo de 11, e o fato
    de que uma troca dentro do CNPJ embutido precisa ser reprovada por **dois**
    verificadores independentes que podem discordar. Em vez de raciocinar sobre a
    interseção, o candidato é confirmado com o validador inteiro.
    """
    candidato = transpor_detectavel(nua, _TAMANHO_DA_BASE, validar, rng_seed)
    if candidato is not None:
        return candidato
    return trocar_caractere(nua, _DV, incrementar_digito(nua[_DV]))


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe uma chave de acesso pelo modo pedido.

    `CARACTERE_INVALIDO` usa **letra minúscula** dentro do espaço do CNPJ: o
    formato passou a aceitar letras, mas só maiúsculas. É o erro de quem leu a
    mudança de 2026 por alto, e produz uma chave que parece certa.

    Args:
        valor: uma chave válida.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        A chave corrompida, que `validar` reprova.

    Raises:
        ValueError: se `valor` não for válido, ou se o modo não se aplicar.
    """
    nua = _caracteres(valor)
    if nua is None or not validar(nua):
        msg = f"corromper espera uma chave de acesso valida, recebeu {valor!r}"
        raise ValueError(msg)

    rng = rng_de(rng_seed)
    agrupada = " " in valor

    if modo is Corrupcao.MASCARA_ERRADA:
        # Sai por aqui porque o resultado NAO deve ser reagrupado no fim.
        return Gerado(
            valor=".".join(nua[i : i + 11] for i in range(0, TAMANHO, 11)),
            valido=False,
            corrupcao=modo,
            seed=rng_seed,
        )

    if modo is Corrupcao.DV_TROCADO:
        corrompida = trocar_caractere(nua, _DV, incrementar_digito(nua[_DV]))
    elif modo is Corrupcao.TRANSPOSICAO:
        corrompida = _transpor(nua, rng_seed)
    elif modo is Corrupcao.FAIXA_INVALIDA:
        corrompida = _com_cuf_inexistente(nua, rng_seed)
    elif modo is Corrupcao.TAMANHO_ERRADO:
        corrompida = nua[: rng.randrange(1, TAMANHO)]
    elif modo is Corrupcao.CARACTERE_INVALIDO:
        posicao = rng.randrange(_CNPJ.start, _FIM_DO_ALFANUMERICO)
        corrompida = trocar_caractere(nua, posicao, "a")
    elif modo is Corrupcao.SEQUENCIA_REPETIDA:
        corrompida = str(rng.randrange(10)) * TAMANHO
    else:
        # Ver a nota em `boleto.corromper`: a exaustividade do enum e provada
        # pelo mypy, nao descoberta em runtime.
        assert_never(modo)

    if agrupada and len(corrompida) == TAMANHO:
        corrompida = _fatiar(corrompida)
    return Gerado(valor=corrompida, valido=False, corrupcao=modo, seed=rng_seed)
