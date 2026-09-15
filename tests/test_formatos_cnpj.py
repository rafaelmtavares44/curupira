"""CNPJ numérico e alfanumérico.

O teste que mais importa aqui é `test_exemplo_da_especificacao`: ele fixa o
algoritmo contra o exemplo publicado do CNPJ alfanumérico. Sem ele, um erro de
peso ou de offset ASCII passaria despercebido e contaminaria a trilha inteira.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from curupira.core.enums import Corrupcao
from curupira.formatos import cnpj, cpf

MODOS_APLICAVEIS = [
    Corrupcao.DV_TROCADO,
    Corrupcao.TRANSPOSICAO,
    Corrupcao.MASCARA_ERRADA,
    Corrupcao.TAMANHO_ERRADO,
    Corrupcao.CARACTERE_INVALIDO,
    Corrupcao.SEQUENCIA_REPETIDA,
]

SEEDS = st.integers(min_value=0, max_value=2**31)


def test_exemplo_da_especificacao() -> None:
    """O algoritmo reproduz o exemplo publicado, dígito por dígito.

    `AB12CD34EFGH` -> soma 850, DV1 8; soma 888, DV2 3 -> `AB12CD34EFGH83`.
    A=17 e Z=42 vêm de `ASCII - 48`, que é o coração da mudança de 2026.
    """
    assert cnpj.validar("AB12CD34EFGH83")
    assert cnpj.validar("AB.12C.D34/EFGH-83")
    assert not cnpj.validar("AB12CD34EFGH84")

    assert cnpj._valor("A") == 17  # noqa: SLF001
    assert cnpj._valor("Z") == 42  # noqa: SLF001
    assert cnpj._valor("0") == 0  # noqa: SLF001


@given(SEEDS, st.booleans())
def test_todo_cnpj_gerado_e_valido(seed: int, alfanumerico: bool) -> None:
    assert cnpj.validar(cnpj.gerar(seed, alfanumerico=alfanumerico).valor)


@given(SEEDS, st.booleans())
def test_todo_cnpj_gerado_com_mascara_e_valido(seed: int, alfanumerico: bool) -> None:
    gerado = cnpj.gerar(seed, alfanumerico=alfanumerico, com_mascara=True)
    assert cnpj.validar(gerado.valor)
    assert "/" in gerado.valor


@given(SEEDS)
def test_alfanumerico_tem_letra_e_dv_numerico(seed: int) -> None:
    """O formato aceita letras nos 12 primeiros; o DV continua numérico."""
    valor = cnpj.gerar(seed, alfanumerico=True).valor
    assert cnpj.e_alfanumerico(valor)
    assert valor[12:].isdigit(), "o DV do CNPJ alfanumerico e sempre numerico"


@given(SEEDS)
def test_numerico_nao_e_marcado_como_alfanumerico(seed: int) -> None:
    assert not cnpj.e_alfanumerico(cnpj.gerar(seed, alfanumerico=False).valor)


@given(SEEDS, st.booleans(), st.sampled_from(MODOS_APLICAVEIS))
def test_todo_cnpj_corrompido_e_invalido(seed: int, alfanumerico: bool, modo: Corrupcao) -> None:
    valido = cnpj.gerar(seed, alfanumerico=alfanumerico).valor
    corrompido = cnpj.corromper(valido, modo, seed)
    assert corrompido.corrupcao is modo
    assert not cnpj.validar(corrompido.valor), f"{modo} passou: {corrompido.valor}"


@given(SEEDS)
def test_minuscula_invalida_o_alfanumerico(seed: int) -> None:
    """O erro clássico de quem leu a mudança por alto: o formato só aceita maiúscula."""
    valido = cnpj.gerar(seed, alfanumerico=True).valor
    corrompido = cnpj.corromper(valido, Corrupcao.CARACTERE_INVALIDO, seed).valor
    assert any(c.islower() for c in corrompido)
    assert not cnpj.validar(corrompido)


@pytest.mark.parametrize("repetido", sorted(cnpj.REPETIDOS))
def test_sequencias_repetidas_sao_invalidas(repetido: str) -> None:
    assert not cnpj.validar(repetido)


@pytest.mark.parametrize(
    "ruim",
    ["", "abc", "AB12CD34EFGH8", "AB12CD34EFGH834", "ab12cd34efgh83", "AB12CD34EFGHAB"],
)
def test_lixo_e_invalido(ruim: str) -> None:
    assert not cnpj.validar(ruim)


def test_dv_alfanumerico_e_invalido() -> None:
    """`AB12CD34EFGHAB`: DV com letra. O DV é sempre numérico."""
    assert not cnpj.validar("AB12CD34EFGHAB")


def test_corromper_recusa_cnpj_invalido() -> None:
    with pytest.raises(ValueError, match="CNPJ valido"):
        cnpj.corromper("00000000000000", Corrupcao.DV_TROCADO, 1)


def test_modo_inaplicavel_estoura() -> None:
    valido = cnpj.gerar(1).valor
    with pytest.raises(ValueError, match="nao se aplica"):
        cnpj.corromper(valido, Corrupcao.FAIXA_INVALIDA, 1)


def test_mascarar_recusa_entrada_errada() -> None:
    with pytest.raises(ValueError, match="12 alfanumericos"):
        cnpj.mascarar("123")


def test_o_dv_alfanumerico_nao_detecta_toda_transposicao() -> None:
    """ACHADO documentado: o formato de 2026 perdeu uma garantia do antigo.

    O módulo 11 detecta toda troca de vizinhos quando os valores vão de 0 a 9 —
    a soma muda em `(a-b)`, nunca múltiplo de 11. No alfanumérico os valores vão
    até 42 (`Z`), e 43 pares diferem por múltiplo de 11. Trocar dois desses
    vizinhos deixa a soma intacta e o DV aprova o CNPJ trocado.

    Isto não é defeito da implementação: é do formato. Vira tarefa da T2.
    """
    pares = cnpj.transposicoes_indetectaveis()
    assert ("0", "F") in pares
    assert ("A", "L") in pares
    assert len(pares) == 43

    # Prova concreta: um CNPJ valido continua valido depois da troca.
    base = "0F" + "1234567890"
    dv1, dv2 = cnpj._dvs(base)  # noqa: SLF001
    original = f"{base}{dv1}{dv2}"
    trocado = f"F0{base[2:]}{dv1}{dv2}"
    assert cnpj.validar(original)
    assert cnpj.validar(trocado), "a troca de '0' por 'F' escapa do digito verificador"
    assert original != trocado


def test_no_cpf_isso_e_impossivel() -> None:
    """O contraste que dá sentido ao achado: dígitos vão de 0 a 9."""
    assert all(abs(a - b) % 11 != 0 for a in range(10) for b in range(10) if a != b)
    assert cpf.validar("11144477735")


def test_transposicao_cai_no_dv_quando_nao_ha_par_detectavel() -> None:
    """Base sem nenhum par vizinho transponível de forma detectável.

    Com todos os caracteres iguais, qualquer troca é inócua. O gerador então
    corrompe o dígito verificador, que qualquer alteração única sempre quebra —
    a corrupção continua sendo corrupção.
    """
    base = "A" * 12
    dv1, dv2 = cnpj._dvs(base)  # noqa: SLF001
    valido = f"{base}{dv1}{dv2}"
    assert cnpj.validar(valido)
    assert not cnpj.validar(cnpj._transpor(valido, 1))  # noqa: SLF001
