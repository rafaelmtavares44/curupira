"""Matchers registrados, usados pelo AST checker para comparar argumentos."""

from __future__ import annotations


def registrar_todos() -> None:
    """Registra todos os matchers embutidos no registro global.

    Chamado uma vez na inicialização da CLI. O lint do dataset depende disso para
    recusar uma tarefa que referencie matcher inexistente antes de rodar.
    """
    raise NotImplementedError
