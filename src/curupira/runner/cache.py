"""Cache de resposta, por hash de (prompt, ferramentas, parâmetros, modelo).

**Barreira 5 das seis de SECURITY.md:** a chave do cache é um hash e o valor é
apenas o corpo da resposta. Headers nunca são persistidos, porque headers
carregam a chave de API.
"""

from __future__ import annotations

from pathlib import Path

from curupira.core.result import RespostaCrua


def chave_de_cache(
    *, modelo: str, corpo_literal: str, temperatura: float, seed: int | None, repeticao: int
) -> str:
    """Calcula a chave determinística de uma entrada de cache.

    Args:
        modelo: o identificador do modelo.
        corpo_literal: o corpo JSON enviado ao provedor.
        temperatura: a temperatura usada.
        seed: a seed, quando houver.
        repeticao: o índice da repetição.

    Returns:
        Hash hexadecimal.
    """
    raise NotImplementedError


def ler(diretorio: Path, chave: str) -> RespostaCrua | None:
    """Lê uma resposta do cache.

    Args:
        diretorio: o diretório de cache.
        chave: a chave calculada.

    Returns:
        A resposta, ou `None` se não houver entrada.
    """
    raise NotImplementedError


def gravar(diretorio: Path, chave: str, resposta: RespostaCrua) -> None:
    """Grava uma resposta no cache.

    Args:
        diretorio: o diretório de cache.
        chave: a chave calculada.
        resposta: a resposta a persistir. Nenhum header é gravado.
    """
    raise NotImplementedError
