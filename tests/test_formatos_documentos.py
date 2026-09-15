"""Boleto e NF-e: os dois formatos com dígito verificador composto.

O que estes testes protegem, em ordem de importância:

1. **As duas convenções do módulo 11 não são a mesma.** O boleto faz 0, 10 e 11
   virarem 1; a NF-e faz resto menor que 2 virar 0. Um refator que "unifique" as
   duas quebra aqui e não em produção.
2. **O reinício do fator de vencimento em 22/02/2025.** A ida e volta fecha, e a
   resposta pela base antiga é exatamente a resposta errada que o dataset precisa
   registrar como falha silenciosa.
3. **Nenhuma camada de validação cobre a outra.** Há um contraexemplo por camada:
   47 zeros passam nos três DVs de campo e reprovam no DV geral; 44 zeros passam
   no DV da chave e reprovam na faixa do cUF.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import cast

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from curupira.core.enums import Corrupcao
from curupira.formatos import boleto, cnpj, nfe
from curupira.formatos.base import modulo11

SEEDS = st.integers(min_value=0, max_value=2**31 - 1)
VALORES = st.integers(min_value=0, max_value=boleto.VALOR_MAXIMO_CENTAVOS)
VENCIMENTOS = st.dates(min_value=boleto.PRIMEIRA_DATA, max_value=boleto.ULTIMA_DATA)
MESES = st.integers(min_value=nfe.MES_MINIMO, max_value=nfe.MES_MAXIMO)
CUFS = st.sampled_from(sorted(nfe.CUFS_VALIDOS))

MODOS_DO_BOLETO = (
    Corrupcao.DV_TROCADO,
    Corrupcao.TRANSPOSICAO,
    Corrupcao.FAIXA_INVALIDA,
    Corrupcao.MASCARA_ERRADA,
    Corrupcao.TAMANHO_ERRADO,
    Corrupcao.CARACTERE_INVALIDO,
    Corrupcao.SEQUENCIA_REPETIDA,
)
MODOS_DA_CHAVE = MODOS_DO_BOLETO

# --------------------------------------------------------------------------
# Vetor de referencia externo
# --------------------------------------------------------------------------

DV_DE_REFERENCIA_BASE = "4317120736461700013555000000012014100012014"
"""Exemplo didático publicado do cálculo do cDV: soma 489, resto 5, DV 6.

**Por que um valor de terceiro está no repositório, e por que isso não fere a
política do projeto.** É um vetor de conferência de algoritmo, no mesmo sentido
que um *test vector* de criptografia: sem nome, sem endereço, sem nenhum campo
associado, e vive em `tests/` — nunca em `tasks/`. A política de privacidade do
Curupira (SECURITY.md, seção 2) protege contra *identificação*, que exige
combinação de campos, e proíbe dado real no **dataset**. O teste
`test_o_vetor_de_referencia_nao_vazou_para_o_dataset` transforma essa distinção
em garantia executável em vez de promessa.

Sem este vetor, a única prova de que o DV está certo seria a implementação
conferindo a si mesma.
"""

DV_DE_REFERENCIA_SOMA = 489
DV_DE_REFERENCIA_RESTO = 5
DV_DE_REFERENCIA_DIGITO = 6


def test_o_dv_da_chave_reproduz_o_vetor_de_referencia() -> None:
    """A aritmética bate com uma fonte independente, dígito a dígito."""
    valores = [ord(c) - 48 for c in DV_DE_REFERENCIA_BASE]
    soma = sum(v * p for v, p in zip(valores, nfe.PESOS_DV, strict=True))
    assert soma == DV_DE_REFERENCIA_SOMA
    assert soma % 11 == DV_DE_REFERENCIA_RESTO
    assert nfe.calcular_dv(DV_DE_REFERENCIA_BASE) == DV_DE_REFERENCIA_DIGITO


def test_o_vetor_de_referencia_nao_vazou_para_o_dataset() -> None:
    """Nenhum arquivo de tarefa contém o vetor de conferência.

    A política do projeto vale para o dataset; este teste é o que impede que um
    copiar-e-colar distraído transforme um vetor de teste numa tarefa publicada.
    """
    tarefas = Path(__file__).resolve().parent.parent / "tasks"
    if not tarefas.is_dir():
        pytest.skip("pasta tasks/ ausente")
    for arquivo in tarefas.rglob("*"):
        if arquivo.is_file():
            assert DV_DE_REFERENCIA_BASE not in arquivo.read_text(encoding="utf-8"), arquivo


def test_os_pesos_batem_com_a_especificacao() -> None:
    """Pesos 2 a 9 da direita para a esquerda, já alinhados para a esquerda.

    Fixa as duas pontas porque é ali que um erro por um se esconde: o último
    caractere tem de receber peso 2, e 43 não é múltiplo de 8.
    """
    assert len(nfe.PESOS_DV) == 43
    assert nfe.PESOS_DV[-8:] == (9, 8, 7, 6, 5, 4, 3, 2)
    assert nfe.PESOS_DV[0] == 4


# --------------------------------------------------------------------------
# As duas convencoes do modulo 11
# --------------------------------------------------------------------------


def test_as_duas_convencoes_do_modulo_11_divergem() -> None:
    """O contraexemplo que impede alguém de "unificar" as duas funções.

    Se algum dia este teste falhar, alguém trocou uma convenção pela outra e o
    benchmark passou a medir a régua errada.
    """
    zeros = "0" * 43
    # Convencao CPF/CNPJ/NF-e: soma 0, resto 0, digito 0.
    assert modulo11([0] * 43, nfe.PESOS_DV) == 0
    # Convencao FEBRABAN: o mesmo resto produz 1, nunca 0.
    assert boleto.modulo11_febraban(zeros) == 1


@given(SEEDS, VENCIMENTOS, VALORES)
@settings(max_examples=50)
def test_o_dv_geral_nunca_e_zero(seed: int, vencimento: date, centavos: int) -> None:
    """Invariante de graça da convenção FEBRABAN: o campo 4 nunca é 0."""
    linha = boleto.gerar(seed, vencimento=vencimento, valor_centavos=centavos).valor
    assert linha[32] != "0"


def test_modulo11_febraban_recusa_entrada_que_nao_e_digito() -> None:
    with pytest.raises(ValueError, match="espera digitos"):
        boleto.modulo11_febraban("12X4")
    with pytest.raises(ValueError, match="espera digitos"):
        boleto.modulo11_febraban("")


# --------------------------------------------------------------------------
# Fator de vencimento: o reinicio de 2025
# --------------------------------------------------------------------------


def test_o_reinicio_do_fator_fecha_nos_dois_sentidos() -> None:
    """As duas eras se encontram exatamente na virada, sem sobrepor nem pular.

    07/10/1997 + 9999 dias é 21/02/2025, e o dia seguinte é o fator 1000. Se essa
    aritmética não fechasse, toda data decodificada estaria um dia fora.
    """
    assert boleto.DATA_BASE_ANTIGA + timedelta(days=boleto.FATOR_MAXIMO) == date(2025, 2, 21)
    assert boleto.fator_para_data(boleto.FATOR_NO_REINICIO) == date(2025, 2, 22)
    assert boleto.data_para_fator(date(2025, 2, 22)) == boleto.FATOR_NO_REINICIO


@given(VENCIMENTOS)
def test_a_ida_e_volta_do_fator_fecha(vencimento: date) -> None:
    assert boleto.fator_para_data(boleto.data_para_fator(vencimento)) == vencimento


def test_a_base_antiga_produz_a_resposta_errada_esperada() -> None:
    """A armadilha, com número: o mesmo fator, 24 anos e meio de diferença.

    Este é o valor que vai para `silent_failure_if` com o rótulo
    `usou_data_base_antiga_1997`.
    """
    fator = boleto.data_para_fator(date(2026, 9, 14))
    assert fator == 1569
    assert boleto.fator_para_data(fator) == date(2026, 9, 14)
    assert boleto.fator_para_data_pela_base_antiga(fator) == date(2002, 1, 23)


@given(st.integers(min_value=boleto.FATOR_NO_REINICIO, max_value=boleto.FATOR_MAXIMO))
def test_a_base_antiga_erra_sempre_pelo_mesmo_intervalo(fator: int) -> None:
    """O erro é uma constante: 9.000 dias, e é isso que o torna reconhecível.

    Os 10.000 dias entre as duas datas-base menos os 1.000 do reinício. Um
    relatório que veja várias datas exatamente 9.000 dias no passado não está
    diante de ruído: está diante de um agente com a data-base de 1997 na cabeça.
    """
    diferenca = boleto.fator_para_data(fator) - boleto.fator_para_data_pela_base_antiga(fator)
    assert diferenca.days == 9000


@pytest.mark.parametrize("fator", [0, 1, 999, 10000, -1])
def test_fator_fora_da_faixa_estoura(fator: int) -> None:
    """Inclusive o `0000`, que é válido no boleto e **não** tem data."""
    with pytest.raises(ValueError, match="fora da faixa"):
        boleto.fator_para_data(fator)
    with pytest.raises(ValueError, match="fora da faixa"):
        boleto.fator_para_data_pela_base_antiga(fator)


@pytest.mark.parametrize("dia", [date(2025, 2, 21), date(2049, 10, 14), date(1999, 1, 1)])
def test_data_fora_da_faixa_estoura(dia: date) -> None:
    with pytest.raises(ValueError, match="fora da faixa"):
        boleto.data_para_fator(dia)


# --------------------------------------------------------------------------
# Boleto: geracao, grafia e camadas
# --------------------------------------------------------------------------


@given(SEEDS, VENCIMENTOS, VALORES)
@settings(max_examples=100)
def test_toda_linha_gerada_e_valida(seed: int, vencimento: date, centavos: int) -> None:
    gerada = boleto.gerar(seed, vencimento=vencimento, valor_centavos=centavos)
    assert gerada.valido
    assert boleto.validar(gerada.valor)
    assert boleto.validar(boleto.mascarar(gerada.valor))


@given(SEEDS, VENCIMENTOS, VALORES)
@settings(max_examples=100)
def test_a_linha_preserva_o_que_foi_pedido(seed: int, vencimento: date, centavos: int) -> None:
    """Decodificar a linha devolve exatamente o vencimento e o valor pedidos."""
    linha = boleto.gerar(seed, vencimento=vencimento, valor_centavos=centavos).valor
    partes = boleto.partes_de(linha)
    assert boleto.fator_para_data(int(partes.fator)) == vencimento
    assert int(partes.valor) == centavos


@given(SEEDS, VENCIMENTOS, VALORES)
@settings(max_examples=50)
def test_o_codigo_de_barras_tem_44_digitos(seed: int, vencimento: date, centavos: int) -> None:
    linha = boleto.gerar(seed, vencimento=vencimento, valor_centavos=centavos).valor
    assert len(boleto.codigo_de_barras(linha)) == boleto.TAMANHO_DO_BARRAS


@given(SEEDS, VENCIMENTOS, VALORES)
@settings(max_examples=50)
def test_a_geracao_do_boleto_e_reprodutivel(seed: int, vencimento: date, centavos: int) -> None:
    primeira = boleto.gerar(seed, vencimento=vencimento, valor_centavos=centavos)
    segunda = boleto.gerar(seed, vencimento=vencimento, valor_centavos=centavos)
    assert primeira == segunda


def test_a_linha_digitavel_nao_e_o_codigo_de_barras_reordenado_a_esmo() -> None:
    """Os campos mudam de lugar, e três DVs existem só na linha digitável.

    Quem trata as duas grafias como a mesma coisa erra por construção; este teste
    fixa o mapeamento posição a posição.
    """
    linha = boleto.gerar(9, vencimento=date(2026, 3, 10), valor_centavos=99999).valor
    barras = boleto.codigo_de_barras(linha)
    assert barras[0:4] == linha[0:4]
    assert barras[4] == linha[32]
    assert barras[5:19] == linha[33:47]
    assert barras[19:24] == linha[4:9]
    assert barras[24:34] == linha[10:20]
    assert barras[34:44] == linha[21:31]


def test_quarenta_e_sete_zeros_passam_nos_dvs_de_campo_e_reprovam_no_geral() -> None:
    """Contraexemplo da camada: "conferir o dígito verificador" não é uma coisa só."""
    zeros = "0" * 47
    assert boleto.modulo11_febraban("0" * 43) != 0
    assert zeros[9] == "0"
    assert zeros[20] == "0"
    assert zeros[31] == "0"
    assert not boleto.validar(zeros)


def test_fator_fora_da_faixa_com_aritmetica_perfeita_e_reprovado() -> None:
    """A camada que nenhum dígito verificador cobre."""
    linha = boleto.gerar(4, vencimento=date(2026, 6, 1), valor_centavos=50000).valor
    corrompida = boleto.corromper(linha, Corrupcao.FAIXA_INVALIDA, 4).valor
    partes = boleto.partes_de(corrompida)
    assert 0 < int(partes.fator) < boleto.FATOR_NO_REINICIO
    assert not boleto.validar(corrompida)
    # E a prova de que so a faixa reprova: os quatro DVs conferem.
    barras = boleto.codigo_de_barras(corrompida)
    esperado = boleto.modulo11_febraban(barras[0:4] + barras[5:44])
    assert barras[4] == str(esperado)


def test_moeda_diferente_de_real_e_reprovada() -> None:
    """Outra camada sem DV: a moeda. Só existe o Real."""
    linha = boleto.gerar(11, vencimento=date(2026, 6, 1), valor_centavos=1).valor
    partes = boleto.partes_de(linha)._replace(moeda="8")
    forjada = boleto._linha_de(partes)  # noqa: SLF001
    assert not boleto.validar(forjada)


def test_grafia_recusada_pelo_boleto() -> None:
    assert not boleto.validar("123")
    assert not boleto.validar("0019291418777631706679074391500231569000012345X")
    assert not boleto.validar("00192.91418 77763.170667 90743.915002 3-15690000123456")


def test_mascarar_boleto_recusa_entrada_errada() -> None:
    with pytest.raises(ValueError, match="espera 47 digitos"):
        boleto.mascarar("123")


def test_codigo_de_barras_recusa_grafia_desconhecida() -> None:
    with pytest.raises(ValueError, match="nao reconhecida"):
        boleto.codigo_de_barras("nao e linha digitavel")


@pytest.mark.parametrize(
    ("banco", "centavos"),
    [("12", 1), ("abc", 1), ("001", -1), ("001", boleto.VALOR_MAXIMO_CENTAVOS + 1)],
)
def test_gerar_boleto_recusa_argumento_impossivel(banco: str, centavos: int) -> None:
    with pytest.raises(ValueError, match=r"banco espera|valor_centavos fora"):
        boleto.gerar(1, vencimento=date(2026, 1, 5), valor_centavos=centavos, banco=banco)


@pytest.mark.parametrize("modo", MODOS_DO_BOLETO)
def test_toda_linha_corrompida_e_invalida(modo: Corrupcao) -> None:
    for seed in range(25):
        linha = boleto.gerar(seed, vencimento=date(2026, 5, 20), valor_centavos=seed * 137).valor
        corrompida = boleto.corromper(linha, modo, seed)
        assert not corrompida.valido
        assert not boleto.validar(corrompida.valor), (modo, corrompida.valor)


@pytest.mark.parametrize(
    "modo",
    [m for m in MODOS_DO_BOLETO if m not in {Corrupcao.MASCARA_ERRADA, Corrupcao.TAMANHO_ERRADO}],
)
def test_a_corrupcao_do_boleto_preserva_a_grafia_mascarada(modo: Corrupcao) -> None:
    """Uma linha mascarada não vira nua ao ser corrompida.

    Se virasse, a corrupção mudaria **dois** atributos de uma vez — o defeito
    pedido e a grafia — e o gabarito passaria a mentir sobre qual deles o agente
    deveria ter percebido. `MASCARA_ERRADA` e `TAMANHO_ERRADO` ficam de fora
    porque neles a grafia é o próprio defeito.
    """
    linha = boleto.gerar(3, vencimento=date(2026, 5, 20), valor_centavos=7700, com_mascara=True)
    corrompida = boleto.corromper(linha.valor, modo, 3).valor
    assert " " in corrompida
    assert "." in corrompida


def test_corromper_linha_invalida_estoura() -> None:
    with pytest.raises(ValueError, match="valida"):
        boleto.corromper("0" * 47, Corrupcao.DV_TROCADO, 1)


# --------------------------------------------------------------------------
# NF-e
# --------------------------------------------------------------------------


@given(SEEDS, CUFS, MESES)
@settings(max_examples=100)
def test_toda_chave_gerada_e_valida(seed: int, cuf: int, mes: int) -> None:
    emitente = cnpj.gerar(seed).valor
    gerada = nfe.gerar(seed, cnpj_emitente=emitente, cuf=cuf, ano=2026, mes=mes)
    assert gerada.valido
    assert len(gerada.valor) == nfe.TAMANHO
    assert nfe.validar(gerada.valor)
    assert nfe.validar(nfe.agrupar(gerada.valor))


@given(SEEDS, CUFS, MESES)
@settings(max_examples=100)
def test_toda_chave_alfanumerica_gerada_e_valida(seed: int, cuf: int, mes: int) -> None:
    """O caso que a NT 2025.001 criou, e que nenhum modelo servido hoje viu no treino."""
    emitente = cnpj.gerar(seed, alfanumerico=True).valor
    gerada = nfe.gerar(seed, cnpj_emitente=emitente, cuf=cuf, ano=2026, mes=mes)
    assert nfe.validar(gerada.valor)
    assert nfe.e_alfanumerica(gerada.valor)
    assert len(gerada.valor) == nfe.TAMANHO


@given(SEEDS, CUFS, MESES)
@settings(max_examples=50)
def test_a_chave_preserva_o_que_foi_pedido(seed: int, cuf: int, mes: int) -> None:
    emitente = cnpj.gerar(seed).valor
    chave = nfe.gerar(seed, cnpj_emitente=emitente, cuf=cuf, ano=2026, mes=mes).valor
    assert int(chave[0:2]) == cuf
    assert chave[2:6] == f"26{mes:02d}"
    assert chave[6:20] == emitente
    assert chave[20:22] == nfe.MODELO_NFE


@given(SEEDS)
@settings(max_examples=30)
def test_a_geracao_da_chave_e_reprodutivel(seed: int) -> None:
    emitente = cnpj.gerar(seed).valor
    argumentos = {"cnpj_emitente": emitente, "cuf": 52, "ano": 2026, "mes": 3}
    assert nfe.gerar(seed, **argumentos) == nfe.gerar(seed, **argumentos)  # type: ignore[arg-type]


def test_quarenta_e_quatro_zeros_passam_no_dv_e_reprovam_na_faixa() -> None:
    """O espelho exato do caso do boleto — e por isso os dois moram no mesmo arquivo.

    Lá, os DVs de campo aprovam e o DV geral reprova. Aqui, o DV da chave aprova
    (porque a regra "resto menor que 2 vira 0" produz justamente o 0 que está na
    última posição) e quem reprova é a tabela do IBGE.
    """
    zeros = "0" * nfe.TAMANHO
    assert nfe.calcular_dv("0" * 43) == 0
    assert zeros[43] == "0"
    assert not nfe.validar(zeros)


def test_o_cuf_34_nao_existe() -> None:
    """Entre RJ (33) e SP (35) não há nada. É o buraco que um modelo preenche."""
    assert 34 in nfe.CUFS_INEXISTENTES
    assert nfe.CUF_POR_UF["RJ"] == 33
    assert nfe.CUF_POR_UF["SP"] == 35
    assert len(nfe.CUFS_VALIDOS) == 27


def test_o_cnpj_embutido_e_conferido_de_verdade() -> None:
    """Corromper o CNPJ dentro da chave e recalcular o DV da chave não salva.

    São dois verificadores independentes; o de fora não conhece o de dentro.
    """
    emitente = cnpj.gerar(21).valor
    chave = nfe.gerar(21, cnpj_emitente=emitente, cuf=52, ano=2026, mes=4).valor
    quebrado = cnpj.corromper(emitente, Corrupcao.DV_TROCADO, 21).valor
    base = chave[0:6] + quebrado + chave[20:43]
    forjada = base + str(nfe.calcular_dv(base))
    assert nfe.calcular_dv(forjada[:43]) == int(forjada[43])
    assert not nfe.validar(forjada)


def test_mes_treze_com_dv_correto_e_reprovado() -> None:
    """Data impossível que a aritmética aprova."""
    emitente = cnpj.gerar(31).valor
    chave = nfe.gerar(31, cnpj_emitente=emitente, cuf=52, ano=2026, mes=4).valor
    base = chave[0:4] + "13" + chave[6:43]
    forjada = base + str(nfe.calcular_dv(base))
    assert not nfe.validar(forjada)


def test_modelo_desconhecido_e_reprovado() -> None:
    emitente = cnpj.gerar(41).valor
    chave = nfe.gerar(41, cnpj_emitente=emitente, cuf=52, ano=2026, mes=4).valor
    base = chave[0:20] + "57" + chave[22:43]
    forjada = base + str(nfe.calcular_dv(base))
    assert not nfe.validar(forjada)


def test_tpemis_zero_e_reprovado() -> None:
    emitente = cnpj.gerar(43).valor
    chave = nfe.gerar(43, cnpj_emitente=emitente, cuf=52, ano=2026, mes=4).valor
    base = chave[0:34] + "0" + chave[35:43]
    forjada = base + str(nfe.calcular_dv(base))
    assert not nfe.validar(forjada)


def test_grafia_recusada_pela_chave() -> None:
    assert not nfe.validar("123")
    assert not nfe.validar("a" * 44)
    emitente = cnpj.gerar(51).valor
    chave = nfe.gerar(51, cnpj_emitente=emitente, cuf=52, ano=2026, mes=4).valor
    assert not nfe.validar(chave[:20] + " " + chave[21:])


def test_agrupar_recusa_entrada_errada() -> None:
    with pytest.raises(ValueError, match="espera 44 posicoes"):
        nfe.agrupar("123")


def test_calcular_dv_recusa_tamanho_errado() -> None:
    with pytest.raises(ValueError, match="espera 43 posicoes"):
        nfe.calcular_dv("0" * 42)


@pytest.mark.parametrize(
    ("cuf", "mes", "modelo", "emitente"),
    [
        (34, 5, nfe.MODELO_NFE, None),
        (52, 13, nfe.MODELO_NFE, None),
        (52, 0, nfe.MODELO_NFE, None),
        (52, 5, "57", None),
        (52, 5, nfe.MODELO_NFE, "00000000000000"),
    ],
)
def test_gerar_chave_recusa_argumento_impossivel(
    cuf: int, mes: int, modelo: str, emitente: str | None
) -> None:
    valor = emitente if emitente is not None else cnpj.gerar(1).valor
    with pytest.raises(ValueError, match=r"invalido|nao pertence|mes fora|desconhecido"):
        nfe.gerar(1, cnpj_emitente=valor, cuf=cuf, ano=2026, mes=mes, modelo=modelo)


@pytest.mark.parametrize("modo", MODOS_DA_CHAVE)
@pytest.mark.parametrize("alfanumerico", [False, True])
def test_toda_chave_corrompida_e_invalida(modo: Corrupcao, alfanumerico: bool) -> None:
    for seed in range(20):
        emitente = cnpj.gerar(seed, alfanumerico=alfanumerico).valor
        chave = nfe.gerar(seed, cnpj_emitente=emitente, cuf=52, ano=2026, mes=7).valor
        corrompida = nfe.corromper(chave, modo, seed)
        assert not corrompida.valido
        assert not nfe.validar(corrompida.valor), (modo, alfanumerico, corrompida.valor)


def test_a_corrupcao_por_faixa_da_chave_mantem_o_dv_correto() -> None:
    """A prova de que `FAIXA_INVALIDA` não é `DV_TROCADO` disfarçado."""
    emitente = cnpj.gerar(61).valor
    chave = nfe.gerar(61, cnpj_emitente=emitente, cuf=52, ano=2026, mes=7).valor
    corrompida = nfe.corromper(chave, Corrupcao.FAIXA_INVALIDA, 61).valor
    assert nfe.calcular_dv(corrompida[:43]) == int(corrompida[43])
    assert int(corrompida[0:2]) in nfe.CUFS_INEXISTENTES
    assert not nfe.validar(corrompida)


def test_a_corrupcao_por_caractere_usa_minuscula() -> None:
    """O erro de quem leu a mudança de 2026 por alto: letra sim, minúscula não."""
    emitente = cnpj.gerar(71, alfanumerico=True).valor
    chave = nfe.gerar(71, cnpj_emitente=emitente, cuf=52, ano=2026, mes=7).valor
    corrompida = nfe.corromper(chave, Corrupcao.CARACTERE_INVALIDO, 71).valor
    assert "a" in corrompida
    assert not nfe.validar(corrompida)


def test_a_corrupcao_preserva_o_agrupamento() -> None:
    emitente = cnpj.gerar(81).valor
    chave = nfe.gerar(81, cnpj_emitente=emitente, cuf=52, ano=2026, mes=7, agrupada=True).valor
    corrompida = nfe.corromper(chave, Corrupcao.DV_TROCADO, 81).valor
    assert " " in corrompida


def test_corromper_chave_invalida_estoura() -> None:
    with pytest.raises(ValueError, match="valida"):
        nfe.corromper("0" * 44, Corrupcao.DV_TROCADO, 1)


# --------------------------------------------------------------------------
# A guarda contra modo novo esquecido
# --------------------------------------------------------------------------


def test_os_dois_modulos_tratam_todo_modo_de_corrupcao() -> None:
    """Boleto e NF-e cobrem o enum inteiro — e continuam cobrindo.

    Este é o teste que quebra no dia em que alguém acrescentar um modo a
    `Corrupcao` e esquecer destes dois módulos. Sem ele, o modo novo cairia no
    `else` e estouraria só quando uma tarefa o usasse, meses depois.
    """
    linha = boleto.gerar(5, vencimento=date(2026, 8, 1), valor_centavos=4200).valor
    chave = nfe.gerar(5, cnpj_emitente=cnpj.gerar(5).valor, cuf=52, ano=2026, mes=8).valor
    for modo in Corrupcao:
        assert not boleto.validar(boleto.corromper(linha, modo, 5).valor), modo
        assert not nfe.validar(nfe.corromper(chave, modo, 5).valor), modo


def test_modo_desconhecido_falha_alto_em_vez_de_passar_batido() -> None:
    """A rede embaixo da exaustividade que o mypy já provou.

    O mypy garante, em tempo de checagem, que todo modo de `Corrupcao` está
    tratado — tanto que o `else` dos dois `corromper` é código que ele considera
    inalcançável, e por isso ali mora um `assert_never` em vez de um `raise`
    escrito à mão.

    Este teste cuida do que o mypy não alcança: alguém que dribla os tipos e
    passa uma string qualquer. O importante não é o tipo da exceção, e sim que
    haja exceção — um `corromper` que devolvesse a entrada intacta produziria
    uma tarefa cujo "valor corrompido" é válido, que é o pior defeito possível
    neste subpacote.
    """
    desconhecido = cast("Corrupcao", "modo_que_nao_existe")
    linha = boleto.gerar(6, vencimento=date(2026, 8, 1), valor_centavos=1).valor
    chave = nfe.gerar(6, cnpj_emitente=cnpj.gerar(6).valor, cuf=52, ano=2026, mes=8).valor
    with pytest.raises(AssertionError):
        boleto.corromper(linha, desconhecido, 6)
    with pytest.raises(AssertionError):
        nfe.corromper(chave, desconhecido, 6)
