"""O esqueleto importa inteiro e as pontas soltas estão declaradas como tal."""

from __future__ import annotations

import importlib
import pkgutil
from importlib.metadata import distribution

import pytest

import curupira
from curupira.core.hashing import hash_da_tarefa


def _todos_os_modulos() -> list[str]:
    nomes = [curupira.__name__]
    for info in pkgutil.walk_packages(curupira.__path__, prefix="curupira."):
        nomes.append(info.name)
    return sorted(nomes)


@pytest.mark.parametrize("nome", _todos_os_modulos())
def test_modulo_importa(nome: str) -> None:
    """Nenhum módulo do pacote quebra no import."""
    importlib.import_module(nome)


def test_nao_ha_litellm_entre_as_dependencias() -> None:
    """ADR 0002: `litellm` não é dependência deste projeto, nem como extra."""
    requisitos = distribution("curupira").requires or []
    assert not any("litellm" in r.lower() for r in requisitos)


def test_stub_falha_alto_e_nao_devolve_valor_errado() -> None:
    """Um stub tem que estourar, não devolver `None` e contaminar um relatório."""
    with pytest.raises(NotImplementedError):
        hash_da_tarefa(None)  # type: ignore[arg-type]
