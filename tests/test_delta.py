"""O Delta PT-BR e a estatística que o sustenta.

Conferimento contra o scipy
---------------------------
`report/delta.py` não usa scipy de propósito (ver a ADR no cabeçalho do módulo):
somar ~30 MB de supply chain por três funções seria mau negócio num projeto com
janela de carência, lockfile com hash e pip-audit.

O risco dessa escolha é implementação própria errar em silêncio. A mitigação está
aqui: **os valores de referência abaixo foram calculados com `scipy 1.17.1` em
15/09/2026 e congelados como constantes.** O CI não ganha dependência; o número
ganha testemunha.

- McNemar: `scipy.stats.binomtest(b, b + c, 0.5, alternative="two-sided")`
- Wilcoxon: `scipy.stats.wilcoxon(nao_nulas, zero_method="wilcox", correction=True)`
- BCa: `scipy.stats.bootstrap(..., method="BCa")`, que usa outro gerador — a
  concordância ali é de 0,013 no pior limite, e isso é ruído de reamostragem,
  não divergência de método.

Para refazer o conferimento: instale o scipy num ambiente **descartável**, nunca
no venv do projeto, e compare com estas constantes.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from curupira.report.delta import (
    METODO_AMOSTRA_INSUFICIENTE,
    METODO_BCA,
    METODO_DEGENERADO,
    bootstrap_bca,
    calcular,
    diferencas_pareadas,
    mcnemar_exato,
    wilcoxon_pareado,
)

# --------------------------------------------------------------------------
# Valores conferidos contra scipy 1.17.1 em 15/09/2026
# --------------------------------------------------------------------------

MCNEMAR_DE_REFERENCIA = {
    (0, 0): 1.0,
    (1, 0): 1.0,
    (3, 0): 0.25,
    (5, 1): 0.21875,
    (10, 2): 0.03857421875,
    (7, 7): 1.0,
    (12, 3): 0.03515625,
    (20, 8): 0.03569813817739487,
    (1, 1): 1.0,
    (2, 5): 0.453125,
}

WILCOXON_DE_REFERENCIA = [
    ([0.2, -0.1, 0.4, 0.3, -0.05, 0.6, 0.15, 0.22], 0.0390625),
    ([0.5, 0.5, 0.5, -0.5, 0.5, 0.5, 0.5], 0.0726009394),
    ([1.0, 1.0, 1.0, 1.0, 0.0, 0.0], 0.0718606382),
    ([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, -0.15], 0.0029296875),
    ([0.33, -0.33, 0.66, 0.0, 0.66, -0.33, 0.33, 0.66], 0.1404581822),
]

DIFERENCAS_DE_REFERENCIA = [
    0.33,
    0.00,
    0.67,
    0.33,
    1.00,
    0.00,
    0.33,
    0.67,
    0.00,
    0.33,
    0.67,
    0.33,
    0.00,
    0.33,
    0.67,
    0.00,
    0.33,
    0.33,
    0.67,
    0.00,
    0.33,
    0.67,
    0.00,
    0.33,
    0.67,
]
"""25 pares, k = 3. O scipy devolveu [0.2528, 0.4796] para o mesmo vetor."""

BCA_DE_REFERENCIA = (0.252, 0.4672)
BCA_DO_SCIPY = (0.2528, 0.4796)
TOLERANCIA_ENTRE_GERADORES = 0.02


# --------------------------------------------------------------------------
# McNemar exato
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("contagens", "esperado"), MCNEMAR_DE_REFERENCIA.items())
def test_mcnemar_bate_com_o_scipy(contagens: tuple[int, int], esperado: float) -> None:
    assert mcnemar_exato(*contagens) == pytest.approx(esperado, abs=1e-12)


def test_mcnemar_sem_discordantes() -> None:
    """Sem discordante não há evidência de diferença, e não há como haver."""
    assert mcnemar_exato(0, 0) == 1.0


def test_mcnemar_e_simetrico() -> None:
    """O teste é bilateral: trocar os idiomas de lado não muda o valor-p."""
    assert mcnemar_exato(9, 2) == mcnemar_exato(2, 9)


def test_mcnemar_recusa_contagem_negativa() -> None:
    with pytest.raises(ValueError, match="negativas"):
        mcnemar_exato(-1, 3)


def test_mcnemar_nao_usa_a_aproximacao_qui_quadrado() -> None:
    """Com poucos discordantes a aproximação mente, e é exatamente onde vamos estar.

    Com b=10, c=2 o qui-quadrado com correção de Yates daria ~0,0389; o exato dá
    0,03857. A diferença é pequena aqui e cresce à medida que n encolhe — e n vai
    ser pequeno num piloto de 30 pares.
    """
    assert mcnemar_exato(10, 2) == pytest.approx(0.03857421875, abs=1e-12)


@given(st.integers(min_value=0, max_value=60), st.integers(min_value=0, max_value=60))
def test_mcnemar_devolve_probabilidade(b: int, c: int) -> None:
    assert 0.0 <= mcnemar_exato(b, c) <= 1.0


# --------------------------------------------------------------------------
# Wilcoxon
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("diferencas", "esperado"), WILCOXON_DE_REFERENCIA)
def test_wilcoxon_bate_com_o_scipy(diferencas: list[float], esperado: float) -> None:
    assert wilcoxon_pareado(diferencas) == pytest.approx(esperado, abs=1e-9)


def test_wilcoxon_com_todas_as_diferencas_nulas() -> None:
    """Empate perfeito em todos os pares: nenhuma evidência de nada."""
    assert wilcoxon_pareado([0.0] * 10) == 1.0


def test_wilcoxon_descarta_os_zeros() -> None:
    """Convenção do teste: um par em que os dois idiomas empataram não é evidência.

    Mantê-lo só encolheria o valor-p de graça, que é a forma mais silenciosa de
    fabricar significância.
    """
    com_zeros = [0.4, -0.2, 0.6, 0.0, 0.0, 0.0]
    sem_zeros = [0.4, -0.2, 0.6]
    assert wilcoxon_pareado(com_zeros) == wilcoxon_pareado(sem_zeros)


def test_wilcoxon_e_simetrico() -> None:
    diferencas = [0.3, -0.1, 0.5, 0.2, -0.4, 0.6]
    invertidas = [-d for d in diferencas]
    assert wilcoxon_pareado(diferencas) == pytest.approx(wilcoxon_pareado(invertidas))


@given(
    st.lists(
        st.floats(min_value=-1, max_value=1, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=30,
    )
)
def test_wilcoxon_devolve_probabilidade(diferencas: list[float]) -> None:
    assert 0.0 <= wilcoxon_pareado(diferencas) <= 1.0


# --------------------------------------------------------------------------
# Bootstrap BCa
# --------------------------------------------------------------------------


def test_bca_bate_com_o_scipy_dentro_do_ruido_de_reamostragem() -> None:
    inferior, superior, metodo = bootstrap_bca(DIFERENCAS_DE_REFERENCIA)
    assert metodo == METODO_BCA
    assert (inferior, superior) == pytest.approx(BCA_DE_REFERENCIA, abs=1e-9)
    assert inferior == pytest.approx(BCA_DO_SCIPY[0], abs=TOLERANCIA_ENTRE_GERADORES)
    assert superior == pytest.approx(BCA_DO_SCIPY[1], abs=TOLERANCIA_ENTRE_GERADORES)


def test_bca_e_reprodutivel() -> None:
    """Um IC que muda a cada execucao nao e reprodutivel.

    O projeto inteiro existe para produzir numero reprodutivel.
    """
    primeiro = bootstrap_bca(DIFERENCAS_DE_REFERENCIA, replicas=2000)
    segundo = bootstrap_bca(DIFERENCAS_DE_REFERENCIA, replicas=2000)
    assert primeiro == segundo


def test_bca_cobre_o_ponto_estimado() -> None:
    inferior, superior, _ = bootstrap_bca(DIFERENCAS_DE_REFERENCIA)
    media = math.fsum(DIFERENCAS_DE_REFERENCIA) / len(DIFERENCAS_DE_REFERENCIA)
    assert inferior <= media <= superior


def test_bca_sem_variacao_devolve_o_proprio_ponto() -> None:
    """Jackknife com variância zero não tem assimetria a corrigir."""
    assert bootstrap_bca([0.3] * 8, replicas=500) == (0.3, 0.3, METODO_DEGENERADO)


def test_bca_com_amostra_pequena_declara_o_nome() -> None:
    """Degradar em silêncio seria pior: alguém leria número de piloto como resultado."""
    _, _, metodo = bootstrap_bca([0.1, 0.9, 0.5], replicas=500)
    assert metodo == METODO_AMOSTRA_INSUFICIENTE


def test_bca_com_um_par_so() -> None:
    assert bootstrap_bca([0.4], replicas=100) == (0.4, 0.4, METODO_DEGENERADO)


def test_bca_recusa_amostra_vazia() -> None:
    with pytest.raises(ValueError, match="zero pares"):
        bootstrap_bca([])


def test_bca_recusa_replicas_invalidas() -> None:
    with pytest.raises(ValueError, match="replicas"):
        bootstrap_bca([0.1, 0.2], replicas=0)


# --------------------------------------------------------------------------
# Diferencas pareadas
# --------------------------------------------------------------------------


def test_diferencas_pareadas() -> None:
    assert diferencas_pareadas([1.0, 0.5], [0.0, 0.5]) == [1.0, 0.0]


def test_vetores_de_tamanhos_diferentes_nao_sao_pareamento() -> None:
    with pytest.raises(ValueError, match="nao e um pareamento"):
        diferencas_pareadas([1.0, 0.5], [0.0])


def test_fracao_fora_do_intervalo_e_erro() -> None:
    """Um Delta sobre vetores errados é pior do que Delta nenhum."""
    with pytest.raises(ValueError, match=r"fora de \[0, 1\]"):
        diferencas_pareadas([1.5], [0.0])


# --------------------------------------------------------------------------
# calcular
# --------------------------------------------------------------------------


def test_calcular_escolhe_mcnemar_com_dados_binarios() -> None:
    """Com k = 1 o teste certo e o exato de McNemar, escolhido pelos dados."""
    en = [1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    pt = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0]
    resultado = calcular("agente", "v0.1", 0, en, pt)
    assert resultado.teste == "mcnemar_exato"
    assert resultado.n_pares == 12
    assert resultado.delta == pytest.approx(9 / 12)


def test_calcular_escolhe_wilcoxon_com_fracoes() -> None:
    en = [1.0, 0.67, 0.33, 1.0, 0.67]
    pt = [0.33, 0.33, 0.0, 0.67, 0.33]
    assert calcular("agente", "v0.1", 0, en, pt).teste == "wilcoxon_pareado"


def test_calcular_reporta_as_duas_acuracias() -> None:
    """O Delta sozinho não diz se o agente é bom; diz o que o idioma custa."""
    resultado = calcular("agente", "v0.1", 0, [1.0, 1.0, 0.0, 1.0], [1.0, 0.0, 0.0, 0.0])
    assert resultado.acuracia_en == pytest.approx(0.75)
    assert resultado.acuracia_pt == pytest.approx(0.25)
    assert resultado.delta == pytest.approx(0.5)


def test_delta_positivo_significa_pt_pior() -> None:
    """O sinal é a manchete: positivo = falar português custa pontos."""
    assert calcular("a", "v0.1", 0, [1.0, 1.0], [0.0, 0.0]).delta > 0
    assert calcular("a", "v0.1", 0, [0.0, 0.0], [1.0, 1.0]).delta < 0


def test_calcular_sem_par_nenhum_estoura() -> None:
    """Um Delta de zero pares seria um número inventado."""
    with pytest.raises(ValueError, match="subconjunto do Delta esta vazio"):
        calcular("agente", "v0.1", 0, [], [])


def test_calcular_carrega_a_procedencia() -> None:
    """Comparar Deltas de suítes ou erratas diferentes tem de ser detectável."""
    resultado = calcular("agente-x", "v0.2", 3, [1.0, 0.0], [0.0, 0.0])
    assert resultado.agent_id == "agente-x"
    assert resultado.suite_id == "v0.2"
    assert resultado.errata_revision == 3
    assert resultado.metodo_ic == METODO_AMOSTRA_INSUFICIENTE


def test_percentil_com_uma_replica_so() -> None:
    """Guarda de borda: com uma reamostragem o intervalo degenera no ponto."""
    inferior, superior, _ = bootstrap_bca([0.1, 0.9], replicas=1)
    assert inferior == superior


def test_bca_com_replicas_poucas_ainda_devolve_intervalo() -> None:
    inferior, superior, metodo = bootstrap_bca([0.0, 0.5, 1.0, 0.5], replicas=3)
    assert inferior <= superior
    assert metodo == METODO_AMOSTRA_INSUFICIENTE
