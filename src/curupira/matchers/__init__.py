"""Matchers registrados, usados pelo AST checker para comparar argumentos.

Nesta fase os matchers estão **registrados mas não implementados**: o nome existe
no registro e o lint do dataset já consegue recusar uma tarefa que referencie um
matcher inexistente, mesmo antes de a comparação funcionar.

Isso não é meia-implementação disfarçada. São duas garantias distintas: "este
nome é conhecido" (agora) e "este nome compara corretamente" (Entrega 2). A
primeira já tem valor — ela pega erro de digitação no YAML antes de gastar API.
"""

from __future__ import annotations

from curupira.core.registry import registrar_matcher
from curupira.matchers.numerico import (
    data_iso,
    exact_int,
    moeda_normalizada,
    tolerancia_numerica,
)
from curupira.matchers.texto import exact_str, fuzzy_name, one_of, por_validador

NOMES = (
    "exact_int",
    "tolerancia_numerica",
    "moeda_normalizada",
    "data_iso",
    "exact_str",
    "one_of",
    "fuzzy_name",
    "por_validador",
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
