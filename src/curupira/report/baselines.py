"""Linhas de base triviais. Obrigatórias em todo relatório.

Em T1, um agente que **nunca chama nada** tira 100% em detecção de irrelevância e
0% no resto. Publicar a nota de irrelevância sem a nota de tool calling ao lado é
enganoso por construção.

Por isso o harness calcula automaticamente as políticas degeneradas e as imprime
em toda rodada. Nota que não bate a política trivial é reportada como tal, em
destaque.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from curupira.core.task import Tarefa


class PoliticaTrivial(StrEnum):
    """Políticas degeneradas contra as quais toda nota é comparada."""

    NUNCA_CHAMA = "nunca_chama"
    SEMPRE_CHAMA = "sempre_chama"
    PRIMEIRA_FERRAMENTA = "chama_a_primeira_ferramenta"
    SEMPRE_ABSTEM = "sempre_abstem"


def nota_da_politica(politica: PoliticaTrivial, tarefas: Sequence[Tarefa]) -> float:
    """Calcula a nota que uma política degenerada tiraria nestas tarefas.

    Args:
        politica: a política degenerada.
        tarefas: as tarefas da suíte.

    Returns:
        A acurácia, de 0 a 1.
    """
    raise NotImplementedError


def todas_as_notas(tarefas: Sequence[Tarefa]) -> dict[PoliticaTrivial, float]:
    """Calcula as notas de todas as políticas triviais.

    Args:
        tarefas: as tarefas da suíte.

    Returns:
        Mapa de política para acurácia.
    """
    raise NotImplementedError
