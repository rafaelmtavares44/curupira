"""As cinco chaves PIX, com os formatos do schema oficial do DICT.

Dois testes carregam o módulo nas costas:

- `test_uuid_v1_passa_por_aleatorio_no_formato` — a armadilha central. Um UUID v1
  casa o formato textual do EVP e não é aleatório coisa nenhuma: carrega
  timestamp e endereço MAC.
- `test_cpf_valido_mascarado_nao_e_chave_pix` — a armadilha sutil. `123.456.789-09`
  é um CPF válido e uma chave inválida, e modelos erram porque a pontuação é o
  formato "bonito" que aparece em documento.
"""

from __future__ import annotations

import uuid

import pytest
from hypothesis import given
from hypothesis import strategies as st

from curupira.core.enums import Corrupcao
from curupira.formatos import cnpj as mod_cnpj
from curupira.formatos import cpf as mod_cpf
from curupira.formatos import pix
from curupira.formatos.pix import TipoDeChavePix

SEEDS = st.integers(min_value=0, max_value=2**31 - 1)
TIPOS = st.sampled_from(list(TipoDeChavePix))

MODOS_POR_TIPO = {
    TipoDeChavePix.CPF: (Corrupcao.DV_TROCADO, Corrupcao.MASCARA_ERRADA),
    TipoDeChavePix.CNPJ: (Corrupcao.DV_TROCADO, Corrupcao.MASCARA_ERRADA),
    TipoDeChavePix.TELEFONE: (Corrupcao.FAIXA_INVALIDA, Corrupcao.TAMANHO_ERRADO),
    TipoDeChavePix.EMAIL: (
        Corrupcao.MASCARA_ERRADA,
        Corrupcao.TAMANHO_ERRADO,
        Corrupcao.CARACTERE_INVALIDO,
        Corrupcao.SEQUENCIA_REPETIDA,
    ),
    TipoDeChavePix.ALEATORIA: (
        Corrupcao.MASCARA_ERRADA,
        Corrupcao.TAMANHO_ERRADO,
        Corrupcao.CARACTERE_INVALIDO,
        Corrupcao.FAIXA_INVALIDA,
        Corrupcao.SEQUENCIA_REPETIDA,
    ),
}


# --------------------------------------------------------------------------
# Geracao e deteccao
# --------------------------------------------------------------------------


@given(SEEDS, TIPOS)
def test_toda_chave_gerada_e_valida(seed: int, tipo: TipoDeChavePix) -> None:
    gerada = pix.gerar(seed, tipo)
    assert gerada.valido
    assert pix.validar(gerada.valor)
    assert pix.validar_como(gerada.valor, tipo)


@given(SEEDS, TIPOS)
def test_o_tipo_detectado_e_o_tipo_gerado(seed: int, tipo: TipoDeChavePix) -> None:
    """Os cinco espaços não se cruzam: a inferência é sem ambiguidade."""
    assert pix.detectar_tipo(pix.gerar(seed, tipo).valor) is tipo


@given(SEEDS, TIPOS)
def test_a_geracao_e_reprodutivel(seed: int, tipo: TipoDeChavePix) -> None:
    """Sem isso o dataset não se regenera a partir da seed."""
    assert pix.gerar(seed, tipo).valor == pix.gerar(seed, tipo).valor


@given(SEEDS)
def test_o_evp_gerado_e_v4_de_verdade(seed: int) -> None:
    gerado = pix.gerar(seed, TipoDeChavePix.ALEATORIA).valor
    identificador = uuid.UUID(gerado)
    assert identificador.version == pix.VERSAO_ALEATORIA
    assert identificador.variant == uuid.RFC_4122


def test_a_geracao_do_evp_nao_usa_uuid4() -> None:
    """`uuid.uuid4()` daria um UUID legítimo e irreprodutível.

    Duas chamadas com a mesma seed têm de dar a mesma chave, senão a regeneração
    do dataset quebra — e com ela a conferência de hash no CI.
    """
    assert pix.gerar(99, TipoDeChavePix.ALEATORIA) == pix.gerar(99, TipoDeChavePix.ALEATORIA)


# --------------------------------------------------------------------------
# As duas armadilhas
# --------------------------------------------------------------------------


def test_uuid_v1_passa_por_aleatorio_no_formato() -> None:
    """A armadilha central: v1 casa o formato textual e não é aleatório.

    Ele carrega timestamp e endereço MAC de quem o gerou. Um agente que "gera uma
    chave aleatória" com a primeira função que encontra pode entregar isto.
    """
    v1 = "c232ab00-9414-11ec-b3c8-9e6bdeced846"
    assert pix._UUID.match(v1) is not None  # noqa: SLF001
    assert uuid.UUID(v1).version == 1
    assert not pix.validar(v1)
    assert not pix.validar_como(v1, TipoDeChavePix.ALEATORIA)


def test_uuid_nil_nao_e_chave() -> None:
    assert not pix.validar("00000000-0000-0000-0000-000000000000")


def test_cpf_valido_mascarado_nao_e_chave_pix() -> None:
    """A armadilha sutil: a chave é sem pontuação, e o CPF bonito tem pontuação."""
    nu = mod_cpf.gerar(5).valor
    mascarado = mod_cpf.mascarar(nu)
    assert mod_cpf.validar(mascarado)
    assert pix.validar(nu)
    assert not pix.validar(mascarado)


def test_cnpj_mascarado_nao_e_chave_pix() -> None:
    nu = mod_cnpj.gerar(5).valor
    assert pix.validar(nu)
    assert not pix.validar(mod_cnpj.mascarar(nu))


# --------------------------------------------------------------------------
# E-mail
# --------------------------------------------------------------------------


def test_email_precisa_ser_minusculo() -> None:
    assert pix.validar("fulano@exemplo.com.br")
    assert not pix.validar("Fulano@Exemplo.com.br")


def test_email_respeita_o_limite_do_dict() -> None:
    dominio = "@exemplo.com.br"
    no_limite = "a" * (pix.TAMANHO_MAXIMO_DE_EMAIL - len(dominio)) + dominio
    assert len(no_limite) == pix.TAMANHO_MAXIMO_DE_EMAIL
    assert pix.validar(no_limite)
    assert not pix.validar("a" + no_limite)


def test_email_sem_dominio_completo_nao_vale() -> None:
    assert not pix.validar("fulano@localhost")
    assert not pix.validar("fulano@")
    assert not pix.validar("@exemplo.com.br")


# --------------------------------------------------------------------------
# Telefone
# --------------------------------------------------------------------------


def test_telefone_exige_o_mais() -> None:
    assert pix.validar("+5562999998888")
    assert not pix.validar("5562999998888")


def test_telefone_brasileiro_passa_pelo_validador_proprio() -> None:
    """DDD 20 não existe, e a chave PIX não deveria aceitá-lo."""
    assert not pix.validar("+5520999998888")


def test_telefone_estrangeiro_e_aceito_pelo_formato() -> None:
    """O DICT aceita E.164 de qualquer país; só o brasileiro temos como conferir."""
    assert pix.validar("+14155552671")


# --------------------------------------------------------------------------
# Corrupcao
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tipo", "modo"),
    [(tipo, modo) for tipo, modos in MODOS_POR_TIPO.items() for modo in modos],
)
def test_toda_chave_corrompida_e_invalida(tipo: TipoDeChavePix, modo: Corrupcao) -> None:
    for seed in range(20):
        original = pix.gerar(seed, tipo).valor
        corrompida = pix.corromper(original, modo, seed)
        assert not corrompida.valido
        assert not pix.validar(corrompida.valor), (tipo, modo, corrompida.valor)


def test_a_corrupcao_do_evp_por_faixa_produz_um_v1() -> None:
    """O modo que fabrica exatamente a armadilha central do módulo."""
    original = pix.gerar(3, TipoDeChavePix.ALEATORIA).valor
    corrompida = pix.corromper(original, Corrupcao.FAIXA_INVALIDA, 3)
    assert uuid.UUID(corrompida.valor).version == 1
    assert not pix.validar(corrompida.valor)


def test_a_corrupcao_de_cpf_delega_ao_modulo_do_formato() -> None:
    """Duplicar a lógica aqui criaria duas réguas que divergem com o tempo."""
    original = pix.gerar(7, TipoDeChavePix.CPF).valor
    pela_chave = pix.corromper(original, Corrupcao.DV_TROCADO, 7).valor
    pelo_formato = mod_cpf.corromper(original, Corrupcao.DV_TROCADO, 7).valor
    assert pela_chave == pelo_formato


def test_corromper_chave_invalida_estoura() -> None:
    with pytest.raises(ValueError, match="invalida"):
        pix.corromper("nao e chave", Corrupcao.MASCARA_ERRADA, 1)


def test_modo_inaplicavel_ao_evp_estoura() -> None:
    original = pix.gerar(1, TipoDeChavePix.ALEATORIA).valor
    with pytest.raises(ValueError, match="nao se aplica"):
        pix.corromper(original, Corrupcao.DV_TROCADO, 1)


def test_modo_inaplicavel_ao_email_estoura() -> None:
    original = pix.gerar(1, TipoDeChavePix.EMAIL).valor
    with pytest.raises(ValueError, match="nao se aplica"):
        pix.corromper(original, Corrupcao.DV_TROCADO, 1)


def test_validar_como_forcando_o_tipo_errado() -> None:
    evp = pix.gerar(2, TipoDeChavePix.ALEATORIA).valor
    assert pix.validar_como(evp, TipoDeChavePix.ALEATORIA)
    assert not pix.validar_como(evp, TipoDeChavePix.CPF)
    assert not pix.validar_como(evp, TipoDeChavePix.EMAIL)


def test_email_com_ponto_e_sinais_aceitos_pelo_dict() -> None:
    assert pix.validar("nome.sobrenome+tag@exemplo.com.br")
    assert not pix.validar("nome sobrenome@exemplo.com.br")
