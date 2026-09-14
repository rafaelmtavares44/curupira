"""Registro de matchers e validadores por nome.

**Regra de ouro do dataset:** matchers e validadores são nomes registrados no
código Python, nunca lógica embutida no YAML. O dataset permanece declarativo e
auditável por humano; a lógica vive em Python, testada e coberta. Se alguém
precisar de `eval()` para rodar o benchmark, o benchmark está errado.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pydantic import JsonValue

Matcher = Callable[[JsonValue, JsonValue, Mapping[str, JsonValue]], bool]
"""Assinatura: (valor_observado, valor_esperado, params) -> casou?"""

Validador = Callable[[str], bool]
"""Assinatura: (valor) -> é válido? Usado por `expect.kind == "extraction"`."""

_MATCHERS: dict[str, Matcher] = {}
_VALIDADORES: dict[str, Validador] = {}


def registrar_matcher(nome: str, fn: Matcher) -> None:
    """Registra um matcher sob um nome usável no YAML.

    Args:
        nome: nome referenciado em `arg_specs[...].matcher`.
        fn: a implementação.

    Raises:
        ValueError: se o nome já estiver registrado.
    """
    raise NotImplementedError


def obter_matcher(nome: str) -> Matcher:
    """Recupera um matcher registrado.

    Args:
        nome: o nome usado no YAML.

    Returns:
        A implementação.

    Raises:
        KeyError: se o nome não existir. O lint do dataset usa isso para recusar
            uma tarefa que referencia matcher inexistente, antes de rodar.
    """
    raise NotImplementedError


def registrar_validador(nome: str, fn: Validador) -> None:
    """Registra um validador de formato sob um nome usável no YAML.

    Args:
        nome: nome referenciado no YAML.
        fn: a implementação.

    Raises:
        ValueError: se o nome já estiver registrado.
    """
    raise NotImplementedError


def obter_validador(nome: str) -> Validador:
    """Recupera um validador registrado.

    Args:
        nome: o nome usado no YAML.

    Returns:
        A implementação.

    Raises:
        KeyError: se o nome não existir.
    """
    raise NotImplementedError


def nomes_registrados() -> tuple[frozenset[str], frozenset[str]]:
    """Lista tudo que está registrado, para o lint do dataset.

    Returns:
        Par (matchers, validadores).
    """
    raise NotImplementedError
