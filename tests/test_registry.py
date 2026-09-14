"""O registro: nomes únicos, erro útil, e o inventário confere com o declarado."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

import pytest
from pydantic import JsonValue

from curupira.core.registry import (
    limpar_registro,
    nomes_registrados,
    obter_matcher,
    obter_validador,
    registrar_matcher,
    registrar_validador,
)
from curupira.formatos import NOMES as NOMES_DE_VALIDADOR
from curupira.formatos import registrar_validadores
from curupira.matchers import NOMES as NOMES_DE_MATCHER
from curupira.matchers import registrar_todos


@pytest.fixture(autouse=True)
def _registro_limpo() -> Iterator[None]:
    limpar_registro()
    yield
    limpar_registro()


def _matcher_falso(
    observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]
) -> bool:
    return observado == esperado and not params


def _validador_falso(valor: str) -> bool:
    return bool(valor)


def test_registrar_e_obter() -> None:
    registrar_matcher("falso", _matcher_falso)
    assert obter_matcher("falso") is _matcher_falso


def test_nome_duplicado_e_recusado() -> None:
    """Um nome significa uma implementação; sobrescrever mudaria tarefas escritas."""
    registrar_matcher("falso", _matcher_falso)
    with pytest.raises(ValueError, match="ja registrado"):
        registrar_matcher("falso", _matcher_falso)


def test_validador_duplicado_e_recusado() -> None:
    registrar_validador("falso", _validador_falso)
    with pytest.raises(ValueError, match="ja registrado"):
        registrar_validador("falso", _validador_falso)


def test_matcher_inexistente_lista_os_disponiveis() -> None:
    """A mensagem de erro é o que transforma um typo em conserto de 10 segundos."""
    registrar_matcher("exact_int", _matcher_falso)
    with pytest.raises(KeyError, match="exact_int"):
        obter_matcher("exact_intt")


def test_validador_inexistente_com_registro_vazio() -> None:
    with pytest.raises(KeyError, match="nenhum registrado"):
        obter_validador("cpf")


def test_registrar_todos_bate_com_o_inventario_declarado() -> None:
    """O `NOMES` do módulo não pode divergir do que é realmente registrado."""
    registrar_todos()
    registrar_validadores()
    matchers, validadores = nomes_registrados()
    assert matchers == frozenset(NOMES_DE_MATCHER)
    assert validadores == frozenset(NOMES_DE_VALIDADOR)


def test_nomes_registrados_devolve_copia() -> None:
    """O chamador pode iterar sem correr atrás do registro."""
    registrar_matcher("falso", _matcher_falso)
    matchers, _ = nomes_registrados()
    registrar_matcher("outro", _matcher_falso)
    assert matchers == frozenset({"falso"})
