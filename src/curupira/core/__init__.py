"""Modelo de dados do Curupira: tarefa, expectativa, resultado, suíte e hash.

Este subpacote é o único lugar onde o formato das tarefas é definido. Os modelos
são `frozen=True` e `extra="forbid"`: uma tarefa com campo desconhecido é erro de
carga, não campo ignorado em silêncio.
"""

from __future__ import annotations
