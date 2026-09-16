"""Cache de resposta, por hash de (modelo, corpo, temperatura, seed, repetição).

**Barreira 5 das seis de SECURITY.md:** a chave do cache é um hash e o valor é
apenas o corpo da resposta, validado contra `RespostaCrua`. Headers nunca são
persistidos, porque headers carregam a chave de API — e o modelo tem
`extra="forbid"`, de modo que uma entrada adulterada com um campo a mais é
recusada na leitura em vez de contaminar a rodada.

A repetição entra na chave **de propósito**. Sem ela, as `k` repetições de uma
tarefa colapsariam num acerto de cache só, e a métrica de não-determinismo — o
detector principal de "acertou por sorte" — passaria a medir zero por
construção. É o tipo de bug que não aparece no teste e sim no artigo.

Escrita atômica: grava num temporário no mesmo diretório e renomeia. Com
`concorrencia > 1`, duas corrotinas podem gravar a mesma chave ao mesmo tempo; a
renomeação garante que um leitor nunca veja meio arquivo.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

from pydantic import ValidationError

from curupira.core.io import gravar_texto
from curupira.core.result import RespostaCrua

_log = logging.getLogger(__name__)

PREFIXO_DE_PASTA = 2
"""Quantos caracteres da chave viram subdiretório.

256 subpastas em vez de um diretório com dezenas de milhares de arquivos, que
degrada em qualquer sistema de arquivos e, no Windows, chega a travar o
Explorer.
"""


def chave_de_cache(
    *,
    task_id: str,
    modelo: str,
    corpo_literal: str,
    temperatura: float,
    seed: int | None,
    repeticao: int,
) -> str:
    """Calcula a chave determinística de uma entrada de cache.

    Modelo e temperatura entram aqui mesmo já constando do corpo. É redundância
    barata que protege do adaptador que, por qualquer razão, deixe de incluí-los
    no corpo: sem isso, duas rodadas com temperaturas diferentes compartilhariam
    cache e a segunda mediria a primeira.

    `task_id` entra por uma razão mais séria, descoberta rodando o ensaio. O
    cache é por conteúdo, então **duas tarefas diferentes com o mesmo corpo
    compartilhariam a resposta**. No caso geral isso é economia; no caso de um
    par PT/EN mal traduzido, cujos corpos ficaram idênticos, seria a resposta em
    português servindo de resposta em inglês — e o Delta daquele par leria zero
    por construção, errando na direção que favorece o projeto. O lint recusa o
    par idêntico (`par-idiomas-diferentes`), mas uma métrica-assinatura não deve
    depender de uma única barreira.

    Args:
        task_id: o id da tarefa.
        modelo: o identificador do modelo.
        corpo_literal: o corpo JSON canônico enviado ao provedor.
        temperatura: a temperatura usada.
        seed: a seed, quando houver.
        repeticao: o índice da repetição.

    Returns:
        Hash hexadecimal de 64 caracteres.
    """
    material = json.dumps(
        {
            "task_id": task_id,
            "modelo": modelo,
            "corpo": corpo_literal,
            "temperatura": temperatura,
            "seed": seed,
            "repeticao": repeticao,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def caminho_da_entrada(diretorio: Path, chave: str) -> Path:
    """Devolve o arquivo que guarda uma chave.

    Args:
        diretorio: o diretório de cache.
        chave: a chave calculada.

    Returns:
        O caminho do arquivo JSON.
    """
    return diretorio / chave[:PREFIXO_DE_PASTA] / f"{chave}.json"


def ler(diretorio: Path, chave: str) -> RespostaCrua | None:
    """Lê uma resposta do cache.

    Entrada ilegível ou fora do schema é tratada como **ausência**, com aviso no
    log: cache é otimização, e derrubar uma rodada paga por causa de um arquivo
    corrompido seria trocar um problema barato por um caro. O aviso existe para
    que a corrupção não passe despercebida.

    Args:
        diretorio: o diretório de cache.
        chave: a chave calculada.

    Returns:
        A resposta, ou `None` se não houver entrada utilizável.
    """
    caminho = caminho_da_entrada(diretorio, chave)
    if not caminho.is_file():
        return None
    try:
        return RespostaCrua.model_validate_json(caminho.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        _log.warning("entrada de cache ilegivel, tratando como ausente: %s", caminho)
        return None


def gravar(diretorio: Path, chave: str, resposta: RespostaCrua) -> None:
    """Grava uma resposta no cache, de forma atômica.

    Args:
        diretorio: o diretório de cache.
        chave: a chave calculada.
        resposta: a resposta a persistir. Nenhum header é gravado — `RespostaCrua`
            não tem onde guardar um.
    """
    caminho = caminho_da_entrada(diretorio, chave)
    temporario = caminho.with_name(f"{caminho.name}.{os.getpid()}.tmp")
    gravar_texto(temporario, resposta.model_dump_json())
    temporario.replace(caminho)
