"""Registro de matchers e validadores por nome.

**Regra de ouro do dataset:** matchers e validadores são nomes registrados no
código Python, nunca lógica embutida no YAML. O dataset permanece declarativo e
auditável por humano; a lógica vive em Python, testada e coberta. Se alguém
precisar de `eval()` para rodar o benchmark, o benchmark está errado.

Ciclo de vida
-------------
O registro é **escrito uma vez**, na inicialização (`registrar_todos()` e
`registrar_validadores()`), e só lido depois. `obter_*` faz lookup simples, que é
atômico em CPython. Registrar depois que a rodada começou é erro de uso: mudaria
o significado do dataset no meio da medição.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Final

from pydantic import JsonValue

Matcher = Callable[[JsonValue, JsonValue, Mapping[str, JsonValue]], bool]
"""Assinatura: (valor_observado, valor_esperado, params) -> casou?"""

Validador = Callable[[str], bool]
"""Assinatura: (valor) -> é válido? Usado por `expect.kind == "extraction"`."""

_MATCHERS: Final[dict[str, Matcher]] = {}
_VALIDADORES: Final[dict[str, Validador]] = {}


def registrar_matcher(nome: str, fn: Matcher) -> None:
    """Registra um matcher sob um nome usável no YAML.

    Args:
        nome: nome referenciado em `arg_specs[...].matcher`.
        fn: a implementação.

    Raises:
        ValueError: se o nome já estiver registrado. Sobrescrever silenciosamente
            mudaria o significado de tarefas já escritas.
    """
    if nome in _MATCHERS:
        msg = f"matcher '{nome}' ja registrado; um nome significa uma implementacao"
        raise ValueError(msg)
    _MATCHERS[nome] = fn


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
    try:
        return _MATCHERS[nome]
    except KeyError:
        disponiveis = ", ".join(sorted(_MATCHERS)) or "(nenhum registrado)"
        msg = f"matcher '{nome}' nao existe. Registrados: {disponiveis}"
        raise KeyError(msg) from None


def registrar_validador(nome: str, fn: Validador) -> None:
    """Registra um validador de formato sob um nome usável no YAML.

    Args:
        nome: nome referenciado no YAML.
        fn: a implementação.

    Raises:
        ValueError: se o nome já estiver registrado.
    """
    if nome in _VALIDADORES:
        msg = f"validador '{nome}' ja registrado; um nome significa uma implementacao"
        raise ValueError(msg)
    _VALIDADORES[nome] = fn


def obter_validador(nome: str) -> Validador:
    """Recupera um validador registrado.

    Args:
        nome: o nome usado no YAML.

    Returns:
        A implementação.

    Raises:
        KeyError: se o nome não existir.
    """
    try:
        return _VALIDADORES[nome]
    except KeyError:
        disponiveis = ", ".join(sorted(_VALIDADORES)) or "(nenhum registrado)"
        msg = f"validador '{nome}' nao existe. Registrados: {disponiveis}"
        raise KeyError(msg) from None


def nomes_registrados() -> tuple[frozenset[str], frozenset[str]]:
    """Lista tudo que está registrado, para o lint do dataset.

    Returns:
        Par (matchers, validadores). Cópias imutáveis: o chamador pode iterar à
        vontade sem correr atrás do registro.
    """
    return frozenset(_MATCHERS), frozenset(_VALIDADORES)


def limpar_registro() -> None:
    """Esvazia o registro. Existe para os testes, não para uso em produção."""
    _MATCHERS.clear()
    _VALIDADORES.clear()
