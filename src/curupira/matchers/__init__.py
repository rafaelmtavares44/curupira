"""Matchers registrados, usados pelo AST checker para comparar argumentos.

Um matcher é um **nome registrado** que o YAML cita; a lógica vive aqui, testada.
O lint do dataset recusa tarefa que cite nome não registrado, antes de gastar API.

(Até a Entrega 20 este docstring dizia que os matchers estavam "registrados mas
não implementados" — verdade na Entrega 1, falso desde a 2. Ficou registrado
porque é o quinto caso desta base de documentação que envelheceu sem ninguém
ver.)
"""

from __future__ import annotations

from curupira.core.registry import registrar_matcher
from curupira.matchers.numerico import (
    data_iso,
    exact_int,
    moeda_normalizada,
    tolerancia_numerica,
)
from curupira.matchers.texto import contem_todos, exact_str, fuzzy_name, one_of, por_validador

NOMES = (
    "exact_int",
    "tolerancia_numerica",
    "moeda_normalizada",
    "data_iso",
    "exact_str",
    "one_of",
    "fuzzy_name",
    "por_validador",
    "contem_todos",
)
"""Inventário declarado dos matchers. O teste confere contra o registro real."""


def registrar_todos() -> None:
    """Registra todos os matchers embutidos no registro global.

    Chamado uma vez na inicialização da CLI. O lint do dataset depende disso para
    recusar uma tarefa que referencie matcher inexistente antes de rodar.
    """
    registrar_matcher("exact_int", exact_int)
    registrar_matcher("tolerancia_numerica", tolerancia_numerica)
    registrar_matcher("moeda_normalizada", moeda_normalizada)
    registrar_matcher("data_iso", data_iso)
    registrar_matcher("exact_str", exact_str)
    registrar_matcher("one_of", one_of)
    registrar_matcher("fuzzy_name", fuzzy_name)
    registrar_matcher("por_validador", por_validador)
    registrar_matcher("contem_todos", contem_todos)
