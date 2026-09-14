"""Carga do dataset em YAML, com normalização e lint."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from curupira.core.task import Tarefa


def carregar_tarefa(caminho: Path) -> Tarefa:
    """Carrega e valida uma tarefa de um arquivo YAML.

    Normaliza a forma curta do `expect` (`calls:`) para a canônica (`accept:`)
    antes de validar, de modo que exista um só caminho de código depois da carga.

    Args:
        caminho: o arquivo YAML da tarefa.

    Returns:
        A tarefa validada.

    Raises:
        ValidationError: se a tarefa não obedecer ao schema.
    """
    raise NotImplementedError


def carregar_diretorio(raiz: Path) -> Iterator[Tarefa]:
    """Carrega recursivamente todas as tarefas sob um diretório.

    Args:
        raiz: diretório raiz (normalmente `tasks/`).

    Yields:
        Cada tarefa validada.
    """
    raise NotImplementedError


def lint_do_dataset(tarefas: list[Tarefa], *, estrito: bool) -> list[str]:
    """Verifica as invariantes do dataset que o schema sozinho não pega.

    Verifica, no mínimo:

    - `canary_guid` único em todo o dataset;
    - `parity: strict` com `pair_id` preenchido e contraparte presente no outro
      idioma, com a mesma `difficulty`;
    - todo matcher e validador referenciado existe no registro;
    - `generated_from` é sempre `pt-BR`;
    - nenhuma tarefa `held_out` no repositório público;
    - grupos de variantes com mais de um membro e gabaritos distintos.

    Args:
        tarefas: as tarefas carregadas.
        estrito: se verdadeiro, avisos viram erros.

    Returns:
        Lista de problemas. Vazia significa dataset íntegro.
    """
    raise NotImplementedError
