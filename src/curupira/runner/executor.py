"""Etapa 1: executar. Grava resposta crua, não veredicto.

REQUISITO DE CONCORRÊNCIA, não sugestão: com `concorrencia > 1`, as corrotinas
**não** podem fazer append em `raw.jsonl` diretamente. Escrita concorrente
intercala linhas e corrompe o arquivo bruto — que é justamente o artefato que
"guarde o bruto, agregue tarde" existe para proteger. E a corrupção é silenciosa:
o JSON quebrado só aparece na hora de agregar, depois de a API já ter sido paga.

Desenho obrigatório: as corrotinas de execução publicam numa `asyncio.Queue` e
**um único** coroutine escritor consome dela e escreve. O escritor faz `flush`
por linha e é o único dono do descritor de arquivo.
"""

from __future__ import annotations

from pathlib import Path

from curupira.adapters.base import AdaptadorDeModelo, ParametrosDeAmostragem
from curupira.core.suite import Suite
from curupira.core.task import Tarefa


async def executar_tarefa(
    tarefa: Tarefa,
    adaptador: AdaptadorDeModelo,
    parametros: ParametrosDeAmostragem,
    *,
    repeticoes: int,
) -> None:
    """Executa uma tarefa N vezes e grava as respostas cruas.

    Repetição é o detector principal de "acertou por sorte": um acerto que só
    acontece em 1 de 5 repetições não é competência, é ruído. Repetir é ordens de
    magnitude mais barato que autorar tarefa nova.

    Args:
        tarefa: a tarefa a executar.
        adaptador: o provedor.
        parametros: temperatura, seed e limite de tokens.
        repeticoes: quantas vezes repetir, com seeds distintas.
    """
    raise NotImplementedError


async def executar_suite(
    suite: Suite,
    adaptador: AdaptadorDeModelo,
    parametros: ParametrosDeAmostragem,
    *,
    repeticoes: int,
    saida: Path,
    concorrencia: int = 4,
) -> Path:
    """Executa uma suíte congelada inteira.

    Confere os hashes antes de começar: se alguém alterou uma tarefa sem subir
    `task_version`, a rodada **falha** em vez de produzir número errado em
    silêncio.

    Args:
        suite: a suíte congelada.
        adaptador: o provedor.
        parametros: os parâmetros de amostragem.
        repeticoes: repetições por tarefa.
        saida: diretório da rodada.
        concorrencia: chamadas simultâneas ao provedor.

    Returns:
        O caminho do `raw.jsonl` produzido.

    Raises:
        ValueError: se algum hash divergir do congelado na suíte.
    """
    raise NotImplementedError
