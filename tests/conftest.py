"""Fixtures compartilhadas."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings

from curupira.security import esquecer_segredos

# deadline=None de proposito: o deadline do Hypothesis mede TEMPO, e tempo varia
# com a maquina. Um teste de propriedade que falha porque o runner do CI estava
# ocupado nao esta reportando bug — esta gastando a confianca no portao.
settings.register_profile(
    "curupira",
    deadline=None,
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("curupira")

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _limpar_segredos() -> Iterator[None]:
    """Garante que nenhum segredo registrado vaze de um teste para o outro."""
    esquecer_segredos()
    yield
    esquecer_segredos()


@pytest.fixture
def raiz_do_repo() -> Path:
    """A raiz do repositório, para localizar `tasks/` e `suites/`."""
    return RAIZ
