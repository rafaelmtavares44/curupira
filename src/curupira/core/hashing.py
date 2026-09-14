"""Serialização canônica e hash de conteúdo de tarefa.

O hash é calculado sobre o **modelo Pydantic normalizado**, nunca sobre o texto
do YAML. Consequência desejada: a forma curta (`calls:`) e a forma canônica
(`accept:`) hasheiam igual, e o dataset pode ter duas grafias com um só caminho
de código depois da carga.

Consequência menos óbvia, e importante: o conjunto de alternativas aceitáveis
entra no hash. Descobrir um caminho válido esquecido **sobe `task_version`** —
não é edição silenciosa. Se a tarefa já está numa suíte congelada, vira errata.
"""

from __future__ import annotations

from curupira.core.task import Tarefa


def bytes_canonicos(tarefa: Tarefa) -> bytes:
    """Serializa a tarefa de forma canônica e determinística.

    Chaves ordenadas, sem espaço supérfluo, UTF-8 normalizado em NFC, campos
    não-semânticos excluídos.

    Args:
        tarefa: a tarefa a serializar.

    Returns:
        Os bytes canônicos.
    """
    raise NotImplementedError


def hash_da_tarefa(tarefa: Tarefa) -> str:
    """Calcula o SHA-256 hexadecimal dos bytes canônicos da tarefa.

    Args:
        tarefa: a tarefa a hashear.

    Returns:
        Hash hexadecimal de 64 caracteres.
    """
    raise NotImplementedError
