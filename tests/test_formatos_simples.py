"""CEP, telefone e placa: os formatos sem dígito verificador.

A propriedade que todo módulo de `curupira.formatos` promete, e que estes testes
cobram: **todo valor gerado passa na validação, e todo valor corrompido falha.**

Sem dígito verificador, essa promessa é mais difícil de cumprir do que parece —
não há aritmética garantindo nada, só formato e faixa. É por isso que cada módulo
declara quais modos de corrupção se aplicam a ele e **recusa** os que não podem
ser garantidos. Um `corromper` que devolvesse um valor aprovado pelo validador
seria um gabarito errado disfarçado de tarefa.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from curupira.core.enums import Corrupcao
from curupira.formatos import cep, placa, telefone

SEEDS = st.integers(min_value=0, max_value=2**31 - 1)

MODOS_DE_CEP = (
    Corrupcao.FAIXA_INVALIDA,
    Corrupcao.MASCARA_ERRADA,
    Corrupcao.TAMANHO_ERRADO,
    Corrupcao.CARACTERE_INVALIDO,
    Corrupcao.SEQUENCIA_REPETIDA,
)
MODOS_DE_TELEFONE = MODOS_DE_CEP
MODOS_DE_PLACA = (
    Corrupcao.MASCARA_ERRADA,
    Corrupcao.TAMANHO_ERRADO,
    Corrupcao.CARACTERE_INVALIDO,
    Corrupcao.SEQUENCIA_REPETIDA,
)
SEM_DV = (Corrupcao.DV_TROCADO, Corrupcao.TRANSPOSICAO)


# --------------------------------------------------------------------------
# CEP
# --------------------------------------------------------------------------


@given(SEEDS)
def test_todo_cep_gerado_e_valido(seed: int) -> None:
    gerado = cep.gerar(seed)
    assert gerado.valido
    assert cep.validar(gerado.valor)


@given(SEEDS, st.sampled_from(MODOS_DE_CEP))
def test_todo_cep_corrompido_e_invalido(seed: int, modo: Corrupcao) -> None:
    corrompido = cep.corromper(cep.gerar(seed).valor, modo, seed)
    assert not corrompido.valido
    assert not cep.validar(corrompido.valor)


@given(SEEDS, st.sampled_from([f.uf for f in cep.FAIXAS]))
def test_cep_gerado_por_uf_cai_na_faixa_da_uf(seed: int, uf: str) -> None:
    assert cep.uf_de(cep.gerar(seed, uf=uf).valor) == uf


def test_roraima_mora_dentro_do_bloco_do_amazonas() -> None:
    """O detalhe que quebra implementação ingênua.

    `69300-000` está dentro de `69000-000` a `69899-999`, que é o Amazonas. Um
    validador que percorra as faixas em ordem alfabética de UF nunca devolve RR.
    A ordem de `FAIXAS` é comportamento, não estilo.
    """
    assert cep.uf_de("69301-000") == "RR"
    assert cep.uf_de("69050-000") == "AM"
    assert cep.uf_de("69450-000") == "AM"


def test_cep_de_buraco_nao_tem_uf() -> None:
    """Oito dígitos, formato impecável, e não existe."""
    assert cep.uf_de("78950-000") is None
    assert not cep.validar("78950-000")
    assert not cep.validar("00123-456")


def test_cep_aceita_so_duas_grafias() -> None:
    assert cep.validar("01310-100")
    assert cep.validar("01310100")
    assert not cep.validar("01.310-100")
    assert not cep.validar("01310 100")


def test_cep_repetido_nem_sempre_e_invalido() -> None:
    """Contraexemplo à intuição herdada do CPF.

    `11111111` é um CEP de faixa atribuída e o validador o aprova, porque CEP não
    tem blacklist — não tem dígito verificador para burlar. Só `00000000` cai num
    buraco, e é por isso que é ele que `SEQUENCIA_REPETIDA` produz.
    """
    assert cep.validar("11111111")
    assert not cep.validar("00000000")


def test_cep_recusa_uf_inexistente() -> None:
    with pytest.raises(ValueError, match="desconhecida"):
        cep.gerar(1, uf="XX")


@pytest.mark.parametrize("modo", SEM_DV)
def test_cep_recusa_modo_sem_digito_verificador(modo: Corrupcao) -> None:
    with pytest.raises(ValueError, match="nao se aplica"):
        cep.corromper(cep.gerar(1).valor, modo, 1)


def test_cep_recusa_corromper_invalido() -> None:
    with pytest.raises(ValueError, match="invalido"):
        cep.corromper("abc", Corrupcao.TAMANHO_ERRADO, 1)


# --------------------------------------------------------------------------
# Telefone
# --------------------------------------------------------------------------


@given(SEEDS, st.booleans())
def test_todo_telefone_gerado_e_valido(seed: int, movel: bool) -> None:
    gerado = telefone.gerar(seed, movel=movel)
    assert gerado.valido
    assert telefone.validar(gerado.valor)
    assert telefone.e_movel(gerado.valor) is movel


@given(SEEDS, st.sampled_from(MODOS_DE_TELEFONE), st.booleans())
def test_todo_telefone_corrompido_e_invalido(seed: int, modo: Corrupcao, movel: bool) -> None:
    original = telefone.gerar(seed, movel=movel).valor
    corrompido = telefone.corromper(original, modo, seed)
    assert not corrompido.valido
    assert not telefone.validar(corrompido.valor)


@given(SEEDS)
def test_o_movel_sem_o_nono_digito_nunca_passa(seed: int) -> None:
    """O achado que motivou `_encurtar` a verificar em vez de deduzir.

    Tirar o `9` da frente de um móvel produz um **fixo válido** sempre que o
    segundo dígito for 2 a 5 — perto de 40% dos casos. A corrupção só é honesta
    porque confere o resultado antes de devolvê-lo.
    """
    original = telefone.gerar(seed, movel=True).valor
    corrompido = telefone.corromper(original, Corrupcao.TAMANHO_ERRADO, seed)
    assert not telefone.validar(corrompido.valor)


@given(SEEDS)
def test_telefone_com_ddd_inexistente_se_declara_invalido(seed: int) -> None:
    """Um `Gerado` que se dissesse válido sendo inválido seria a pior mentira."""
    gerado = telefone.gerar(seed, ddd_inexistente=True)
    assert not gerado.valido
    assert not telefone.validar(gerado.valor)


def test_os_ddds_sao_67_e_os_buracos_22() -> None:
    assert len(telefone.DDDS_VALIDOS) == 67
    assert len(telefone.DDDS_INEXISTENTES) == 22
    assert set(telefone.DDDS_VALIDOS) & set(telefone.DDDS_INEXISTENTES) == set()


@pytest.mark.parametrize("ddd", [20, 23, 26, 30, 39, 50, 60, 70, 80, 90])
def test_ddds_que_nunca_existiram(ddd: int) -> None:
    assert ddd not in telefone.DDDS_VALIDOS
    assert not telefone.validar(f"+55{ddd}999998888")


def test_telefone_aceita_as_duas_grafias() -> None:
    assert telefone.validar("+5562999998888")
    assert telefone.validar("(62) 99999-8888")
    assert telefone.validar("(62) 3333-4444")
    assert not telefone.validar("62999998888")
    assert not telefone.validar("+55 62 99999-8888")


def test_fixo_nao_pode_comecar_com_nove() -> None:
    assert not telefone.validar("+556293334444")
    assert telefone.validar("+556233334444")


@pytest.mark.parametrize("modo", SEM_DV)
def test_telefone_recusa_modo_sem_digito_verificador(modo: Corrupcao) -> None:
    with pytest.raises(ValueError, match="nao se aplica"):
        telefone.corromper(telefone.gerar(1).valor, modo, 1)


# --------------------------------------------------------------------------
# Placa
# --------------------------------------------------------------------------


@given(SEEDS, st.booleans())
def test_toda_placa_gerada_e_valida(seed: int, mercosul: bool) -> None:
    gerada = placa.gerar(seed, mercosul=mercosul)
    assert gerada.valido
    assert placa.validar(gerada.valor)
    assert placa.e_mercosul(gerada.valor) is mercosul


@given(SEEDS, st.sampled_from(MODOS_DE_PLACA), st.booleans())
def test_toda_placa_corrompida_e_invalida(seed: int, modo: Corrupcao, mercosul: bool) -> None:
    original = placa.gerar(seed, mercosul=mercosul).valor
    corrompida = placa.corromper(original, modo, seed)
    assert not corrompida.valido
    assert not placa.validar(corrompida.valor)


@given(SEEDS)
def test_toda_placa_antiga_converte_para_uma_mercosul_valida(seed: int) -> None:
    antiga = placa.gerar(seed, mercosul=False).valor
    convertida = placa.converter_para_mercosul(antiga)
    assert placa.e_mercosul(convertida)
    assert placa.validar(convertida)


def test_a_conversao_troca_o_segundo_digito() -> None:
    """`ABC-1234` vira `ABC1C34`, não `ABC1234`."""
    assert placa.converter_para_mercosul("ABC-1234") == "ABC1C34"
    assert placa.converter_para_mercosul("ABC1234") == "ABC1C34"
    assert placa.converter_para_mercosul("XYZ-9087") == "XYZ9A87"


def test_so_remover_o_hifen_produz_uma_placa_valida() -> None:
    """A razão de a conversão ser armadilha de alto valor.

    Um agente que apenas tira o hífen devolve `ABC1234`, que é uma placa antiga
    perfeitamente válida. O erro não é detectável pelo validador — é falha
    silenciosa em estado puro, e só a tarefa consegue pegá-lo, comparando com o
    gabarito.
    """
    errado = "ABC-1234".replace("-", "")
    assert placa.validar(errado)
    assert errado != placa.converter_para_mercosul("ABC-1234")


def test_placa_exige_maiuscula() -> None:
    assert placa.validar("ABC1D23")
    assert not placa.validar("abc1d23")


def test_placa_aceita_o_formato_antigo_com_e_sem_hifen() -> None:
    assert placa.validar("ABC1234")
    assert placa.validar("ABC-1234")
    assert not placa.validar("AB-C1234")


def test_conversao_recusa_placa_que_ja_e_mercosul() -> None:
    with pytest.raises(ValueError, match="padrao antigo"):
        placa.converter_para_mercosul("ABC1D23")


@pytest.mark.parametrize("modo", [*SEM_DV, Corrupcao.FAIXA_INVALIDA])
def test_placa_recusa_modo_inaplicavel(modo: Corrupcao) -> None:
    """Não existe placa fora de faixa: o que casa o padrão é válido."""
    with pytest.raises(ValueError, match="nao se aplica"):
        placa.corromper(placa.gerar(1).valor, modo, 1)


def test_os_intervalos_do_amazonas_excluem_roraima() -> None:
    """O achado que o Hypothesis encontrou e a leitura não pegaria.

    A faixa do AM esta certa, o sorteio esta certo, e a composicao dos dois
    estava errada: em ~11% das vezes o CEP "do Amazonas" caia em Roraima.
    """
    assert cep.intervalos_de("AM") == ((69000000, 69299999), (69400000, 69899999))
    assert cep.intervalos_de("RR") == ((69300000, 69399999),)
    assert cep.intervalos_de("SP") == ((1000000, 19999999),)


def test_intervalos_de_recusa_uf_inexistente() -> None:
    with pytest.raises(ValueError, match="desconhecida"):
        cep.intervalos_de("XX")


def test_telefone_fixo_gerado_na_grafia_usual() -> None:
    gerado = telefone.gerar(4, movel=False, formato_e164=False)
    assert telefone.validar(gerado.valor)
    assert gerado.valor.startswith("(")
    assert not telefone.e_movel(gerado.valor)


def test_telefone_corrompido_na_grafia_usual_tambem_falha() -> None:
    original = telefone.gerar(4, formato_e164=False).valor
    for modo in MODOS_DE_TELEFONE:
        assert not telefone.validar(telefone.corromper(original, modo, 4).valor)


def test_e_movel_recusa_telefone_invalido() -> None:
    assert not telefone.e_movel("nao e telefone")


def test_telefone_recusa_corromper_invalido() -> None:
    with pytest.raises(ValueError, match="invalido"):
        telefone.corromper("+5520999998888", Corrupcao.TAMANHO_ERRADO, 1)


def test_placa_recusa_corromper_invalida() -> None:
    with pytest.raises(ValueError, match="invalida"):
        placa.corromper("abc1d23", Corrupcao.TAMANHO_ERRADO, 1)
