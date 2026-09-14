"""Fixtures compartilhadas."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from curupira.security import esquecer_segredos

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
