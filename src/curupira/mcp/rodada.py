"""Transforma uma sessão MCP no `raw.jsonl` que o `score` já sabe ler.

O ponto desta camada é **não inventar formato**. O que sai daqui é a mesma
`ExecucaoCrua` que o `run` produz, então `curupira score` e `curupira report`
funcionam sem uma linha de mudança — incluindo a família, o Delta e a taxa de
falha silenciosa.

O que muda de verdade: quem observa
------------------------------------
No `run`, o Curupira monta a requisição e lê a resposta; ele **sabe** a
temperatura, a seed, o modelo. Aqui o agente roda na máquina de quem avalia, com
o framework, o prompt e os parâmetros que essa pessoa escolheu. O Curupira vê as
chamadas de ferramenta e mais nada.

**Vários campos da tupla de reprodutibilidade passam a ser auto-declarados.**
`model`, `framework`, `temperature`, `prompt_template_id`: nada disso é
observável por um servidor MCP. Quem avalia declara, e o Curupira anota.

Isso não é defeito do desenho — é o desenho. E é exatamente por isso que o
leaderboard tem duas colunas que nunca se misturam: um resultado **auto-reportado**
carrega números que ninguém verificou, e um resultado **verificado** vem de
execução que o Curupira controlou. Chamar os dois de "resultado" seria mentir por
omissão.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from curupira import __version__
from curupira.core.hashing import hash_da_tarefa
from curupira.core.io import acrescentar_linhas
from curupira.core.result import ChamadaObservada, ExecucaoCrua, IdentidadeDoAgente, RespostaCrua
from curupira.core.task import Tarefa

VERSAO_DO_ADAPTADOR: Final = "mcp/2026-07-28"
"""Identifica o caminho de observação, não um provedor.

Uma rodada por MCP e uma por API direta **não são comparáveis**: o agente do
outro lado é outro objeto. Este campo é o que deixa isso legível no resultado
em vez de escondido.
"""

MOTIVO_DE_PARADA: Final = "stdin_fechado"
"""Como a sessão terminou.

Provisório, e declarado como tal. O MCP é stateless por especificação, então o
fim da tarefa não é observável no protocolo: hoje ele é o fim do processo do
agente. A camada de tarefa que resolve isso direito é a Entrega 14.
"""


def corpo_da_requisicao(tarefa: Tarefa) -> str:
    """Serializa o que o agente teve à disposição, para auditoria de terceiro.

    No `run` este campo guarda o corpo literal enviado ao provedor. Aqui não há
    corpo: o agente puxa as ferramentas quando quer. O equivalente honesto é
    registrar **o que foi oferecido** — a mensagem do usuário e as ferramentas
    servidas —, que é o que permite conferir que a tarefa chegou do jeito que o
    dataset declara.

    Args:
        tarefa: a tarefa servida.

    Returns:
        O JSON canônico do que foi oferecido.
    """
    return json.dumps(
        {
            "user_message": tarefa.input.user_message,
            "system_prompt": tarefa.context.system_prompt,
            "tools": [
                {"name": t.name, "description": t.description, "parameters": t.parameters}
                for t in tarefa.context.tools
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def execucao_da_sessao(
    tarefa: Tarefa,
    chamadas: tuple[ChamadaObservada, ...],
    *,
    suite_id: str,
    agente: IdentidadeDoAgente,
    repeticao: int,
    latencia_ms: int,
) -> ExecucaoCrua:
    """Monta a `ExecucaoCrua` de uma sessão MCP encerrada.

    Args:
        tarefa: a tarefa servida.
        chamadas: as chamadas observadas, na ordem.
        suite_id: a suíte da rodada.
        agente: a identidade auto-declarada por quem avalia.
        repeticao: o índice da repetição.
        latencia_ms: o tempo da sessão inteira.

    Returns:
        A linha a gravar no `raw.jsonl`.
    """
    return ExecucaoCrua(
        task_id=tarefa.id,
        task_version=tarefa.task_version,
        task_hash=hash_da_tarefa(tarefa),
        suite_id=suite_id,
        agent=agente,
        repetition=repeticao,
        timestamp=datetime.now(UTC),
        latency_ms=latencia_ms,
        curupira_version=__version__,
        request_body=corpo_da_requisicao(tarefa),
        raw=RespostaCrua(tool_calls=chamadas, finish_reason=MOTIVO_DE_PARADA),
    )


def identidade_declarada(
    agent_id: str,
    modelo: str,
    *,
    framework: str | None,
    temperatura: float,
    prompt_template_id: str,
) -> IdentidadeDoAgente:
    """Monta a identidade que quem avalia **declara** sobre o próprio agente.

    Nenhum destes campos é observável por um servidor MCP. Estão no resultado
    porque o leaderboard precisa deles para não comparar coisas diferentes — e
    o selo de auto-reportado existe porque nada aqui foi verificado.

    Args:
        agent_id: o identificador do agente no leaderboard.
        modelo: o modelo que o agente usa, com data.
        framework: o framework, quando houver.
        temperatura: a temperatura configurada no agente.
        prompt_template_id: o identificador do prompt do agente.

    Returns:
        A identidade, marcada como não tendo seed aplicada pelo Curupira.
    """
    return IdentidadeDoAgente(
        agent_id=agent_id,
        model=modelo,
        framework=framework,
        adapter_version=VERSAO_DO_ADAPTADOR,
        prompt_template_id=prompt_template_id,
        temperature=temperatura,
        seed=None,
        seed_aplicada=False,
    )


def gravar(destino: Path, execucao: ExecucaoCrua) -> None:
    """Acrescenta uma execução ao `raw.jsonl`.

    Args:
        destino: o arquivo de bruto da rodada.
        execucao: a linha a gravar.
    """
    with acrescentar_linhas(destino) as escritor:
        escritor.escrever_linha(execucao.model_dump_json())
        escritor.descarregar()
