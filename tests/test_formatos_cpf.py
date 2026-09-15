"""CPF: dígito verificador, blacklist de repetidos e corrupção declarada.

Os testes de propriedade são o ponto: `gerar` sempre produz válido, `corromper`
sempre produz inválido, para toda seed. Um validador que erra em 1 de cada 10 mil
casos passaria despercebido num punhado de exemplos escritos à mão.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from curupira.core.enums import Corrupcao
from curupira.formatos import cpf

MODOS_APLICAVEIS = [
    Corrupcao.DV_TROCADO,
    Corrupcao.TRANSPOSICAO,
    Corrupcao.MASCARA_ERRADA,
    Corrupcao.TAMANHO_ERRADO,
    Corrupcao.CARACTERE_INVALIDO,
    Corrupcao.SEQUENCIA_REPETIDA,
]

SEEDS = st.integers(min_value=0, max_value=2**31)


@given(SEEDS)
def test_todo_cpf_gerado_e_valido(seed: int) -> None:
    assert cpf.validar(cpf.gerar(seed).valor)


@given(SEEDS)
def test_todo_cpf_gerado_com_mascara_e_valido(seed: int) -> None:
    gerado = cpf.gerar(seed, com_mascara=True)
    assert cpf.validar(gerado.valor)
    assert gerado.valor.count(".") == 2
    assert "-" in gerado.valor


@given(SEEDS)
def test_geracao_e_deterministica(seed: int) -> None:
    """Mesma seed, mesmo CPF — é o que torna o dataset regenerável."""
    assert cpf.gerar(seed).valor == cpf.gerar(seed).valor


@given(SEEDS, st.sampled_from(MODOS_APLICAVEIS))
def test_todo_cpf_corrompido_e_invalido(seed: int, modo: Corrupcao) -> None:
    """A propriedade que mais vale: corrupção declarada é corrupção detectada."""
    valido = cpf.gerar(seed).valor
    corrompido = cpf.corromper(valido, modo, seed)
    assert corrompido.corrupcao is modo
    assert not corrompido.valido
    assert not cpf.validar(corrompido.valor), f"{modo} passou no validador: {corrompido.valor}"


@given(SEEDS)
def test_transposicao_de_vizinhos_e_sempre_detectada(seed: int) -> None:
    """O módulo 11 detecta toda troca de vizinhos distintos: a soma muda em (a-b)."""
    valido = cpf.gerar(seed).valor
    corrompido = cpf.corromper(valido, Corrupcao.TRANSPOSICAO, seed).valor
    assert not cpf.validar(corrompido)


@pytest.mark.parametrize("repetido", sorted(cpf.REPETIDOS))
def test_sequencias_repetidas_sao_invalidas(repetido: str) -> None:
    """Passam na aritmética do módulo 11. Sem blacklist, o validador está errado."""
    assert not cpf.validar(repetido)


def test_um_cpf_conhecido_valido() -> None:
    """Valor de referência público, usado em documentação da Receita."""
    assert cpf.validar("11144477735")
    assert cpf.validar("111.444.777-35")


def test_mascara_fora_do_padrao_e_invalida() -> None:
    """Dígitos certos, pontuação errada: é `Corrupcao.MASCARA_ERRADA`."""
    assert not cpf.validar("111.444.777.35")
    assert not cpf.validar("11144477-735")
    assert not cpf.validar("111 444 777 35")


@pytest.mark.parametrize("ruim", ["", "abc", "1114447773", "111444777355", "111.444.777-3X"])
def test_lixo_e_invalido(ruim: str) -> None:
    assert not cpf.validar(ruim)


def test_mascarar_recusa_entrada_errada() -> None:
    with pytest.raises(ValueError, match="11 digitos"):
        cpf.mascarar("111")


def test_corromper_recusa_cpf_invalido() -> None:
    with pytest.raises(ValueError, match="CPF valido"):
        cpf.corromper("00000000000", Corrupcao.DV_TROCADO, 1)


def test_modo_inaplicavel_estoura() -> None:
    """FAIXA_INVALIDA não existe em CPF: não há faixa nem ordem a violar."""
    valido = cpf.gerar(1).valor
    with pytest.raises(ValueError, match="nao se aplica"):
        cpf.corromper(valido, Corrupcao.FAIXA_INVALIDA, 1)


def test_transposicao_cai_na_sequencia_quando_a_base_e_toda_igual() -> None:
    """Base com os 9 dígitos iguais: não há par a transpor de forma útil."""
    corrompido = cpf._transpor("99999999999", 1)  # noqa: SLF001
    assert not cpf.validar(corrompido)
