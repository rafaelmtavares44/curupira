"""As suítes congeladas do repositório, contra o dataset do repositório.

O lint do `validate` já recusa tarefa congelada que muda ou some. Este arquivo
cobra duas garantias que o lint não cobra:

1. toda suíte em `suites/` passa no `verificar_suite` — o mesmo portão que o
   `run` usa antes da primeira chamada paga;
2. a v0.2 nasceu com famílias suficientes para o intervalo do Delta sair por
   BCa. Foi o critério que fez a T4 entrar no lote (Entrega 18), e uma suíte
   congelada abaixo dele publicaria um Delta com intervalo de percentil.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from curupira.core.enums import Paridade
from curupira.core.loader import carregar_diretorio
from curupira.core.suite import Suite, carregar_suites, verificar_suite
from curupira.report.delta import N_MINIMO_PARA_BCA

RAIZ = Path(__file__).resolve().parent.parent
SUITES = carregar_suites(RAIZ / "suites")
TAREFAS = {t.id: t for t in carregar_diretorio(RAIZ / "tasks")}


def test_o_repositorio_tem_as_suites_esperadas() -> None:
    """Sem suíte nenhuma, o teste parametrizado abaixo passaria vazio."""
    assert {s.id for s in SUITES} >= {"v0.1", "v0.2"}


@pytest.mark.parametrize("suite", SUITES, ids=[s.id for s in SUITES])
def test_toda_suite_congelada_continua_integra(suite: Suite) -> None:
    assert verificar_suite(suite, TAREFAS) == []


@pytest.mark.parametrize("suite", SUITES, ids=[s.id for s in SUITES])
def test_o_subconjunto_do_delta_so_tem_pares_strict_completos(suite: Suite) -> None:
    ids = {e.task_id for e in suite.entries}
    for par in suite.delta_subset:
        lados = [t for t in TAREFAS.values() if t.pair_id == par and t.id in ids]
        assert len(lados) == 2, f"{suite.id}: o par {par} nao tem os dois lados na suite"
        assert all(t.parity is Paridade.STRICT for t in lados), f"{par} nao e strict"


def test_a_v0_2_tem_familias_para_o_bca() -> None:
    (v02,) = [s for s in SUITES if s.id == "v0.2"]
    familias = {t.family_id for t in TAREFAS.values() if t.pair_id in set(v02.delta_subset)}
    assert None not in familias, "par do Delta sem family_id: o bootstrap nao saberia reamostrar"
    assert len(familias) >= N_MINIMO_PARA_BCA, sorted(f for f in familias if f)
