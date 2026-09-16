"""Etapa 1: executar. Grava resposta crua, não veredicto.

REQUISITO DE CONCORRÊNCIA, não sugestão: com `concorrencia > 1`, as corrotinas
**não** podem fazer append em `raw.jsonl` diretamente. Escrita concorrente
intercala linhas e corrompe o arquivo bruto — que é justamente o artefato que
"guarde o bruto, agregue tarde" existe para proteger. E a corrupção é silenciosa:
o JSON quebrado só aparece na hora de agregar, depois de a API já ter sido paga.

Desenho implementado: as corrotinas de execução publicam numa `asyncio.Queue` e
**um único** coroutine escritor consome dela e escreve. O escritor faz `flush`
por linha e é o único dono do descritor de arquivo. Consequência colateral e
desejada: uma rodada interrompida no meio deixa no disco tudo o que já foi pago,
linha a linha, em vez de perder tudo.

Falha fecha antes de abrir
--------------------------
Três recusas acontecem **antes** da primeira chamada paga:

1. hash divergente do congelado na suíte — a rodada falha em vez de produzir
   número errado em silêncio;
2. tarefa da suíte ausente do dataset;
3. tarefa multi-turno (`followup_turns`), que a v0.1 ainda não sabe executar —
   descobrir isso na tarefa 200 custaria as outras 199.

E uma quarta, por execução: se o corpo literal contiver um segredo registrado, o
runner **recusa gravar**. Redigir seria pior, porque esconderia um defeito de
adaptador atrás de um artefato aparentemente limpo.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr

from curupira import __version__
from curupira.adapters.base import (
    AdaptadorDeModelo,
    ErroDoProvedor,
    Mensagem,
    ParametrosDeAmostragem,
)
from curupira.core.hashing import hash_da_tarefa
from curupira.core.io import acrescentar_linhas
from curupira.core.result import ExecucaoCrua, IdentidadeDoAgente, RespostaCrua
from curupira.core.suite import Suite, verificar_suite
from curupira.core.task import Tarefa
from curupira.runner.cache import chave_de_cache, gravar, ler
from curupira.security import contem_segredo

TEMPLATE_PADRAO: Final = "cru-v1"
"""O template de prompt da v0.1: nenhum.

A mensagem do usuário vai literalmente como a tarefa a declara, e o prompt de
sistema é o que a própria tarefa traz. É a escolha certa para um benchmark que
mede o custo de falar português: qualquer instrução extra nossa — "responda em
português", "use as ferramentas" — seria uma variável nossa dentro do número.
Um template diferente é um **agente diferente**, com id próprio no leaderboard.
"""

NOME_DO_BRUTO: Final = "raw.jsonl"
ARQUIVO_DA_RODADA: Final = "rodada.json"


class ErroDeSeguranca(RuntimeError):
    """O corpo a gravar contém um segredo registrado. A rodada para."""


class ContextoDaRodada(BaseModel):
    """A identidade da rodada. Só o que é serializável e público.

    A chave de API e o cliente HTTP ficam **fora** deste modelo, como argumentos
    separados. Não é estilo: este objeto acompanha o registro da rodada, e um
    campo capaz de segurar a chave é um campo por onde a chave vaza.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    suite_id: str
    agent_id: str
    modelo: str
    framework: str | None = None
    prompt_template_id: str = TEMPLATE_PADRAO
    cache: Path | None = None


def montar_mensagens(tarefa: Tarefa) -> tuple[Mensagem, ...]:
    """Converte a entrada da tarefa na conversa enviada ao provedor.

    Args:
        tarefa: a tarefa a executar.

    Returns:
        A conversa, com a mensagem do usuário literal.
    """
    return (Mensagem(role="user", content=tarefa.input.user_message),)


def seed_da_repeticao(base: int | None, repeticao: int) -> int | None:
    """Deriva a seed de uma repetição.

    Args:
        base: a seed declarada na rodada, se houver.
        repeticao: o índice da repetição, a partir de zero.

    Returns:
        `None` se não houver seed base; senão `base + repeticao`, para que as
        repetições não sejam cópias uma da outra num provedor que honra seed.
    """
    return None if base is None else base + repeticao


def identidade(
    contexto: ContextoDaRodada,
    adaptador: AdaptadorDeModelo,
    parametros: ParametrosDeAmostragem,
) -> IdentidadeDoAgente:
    """Monta a identidade do agente para uma repetição.

    Args:
        contexto: a identidade da rodada.
        adaptador: o provedor.
        parametros: os parâmetros **já** com a seed da repetição.

    Returns:
        A identidade, com `seed_aplicada` refletindo o que o provedor aceita.
    """
    aplicada = adaptador.suporta_seed and parametros.seed is not None
    return IdentidadeDoAgente(
        agent_id=contexto.agent_id,
        model=contexto.modelo,
        framework=contexto.framework,
        adapter_version=adaptador.versao,
        prompt_template_id=contexto.prompt_template_id,
        temperature=parametros.temperature,
        seed=parametros.seed,
        seed_aplicada=aplicada,
    )


async def executar_repeticao(
    tarefa: Tarefa,
    adaptador: AdaptadorDeModelo,
    parametros: ParametrosDeAmostragem,
    *,
    contexto: ContextoDaRodada,
    chave: SecretStr,
    cliente: httpx.AsyncClient,
    repeticao: int,
) -> ExecucaoCrua:
    """Executa UMA repetição de UMA tarefa e devolve a linha bruta.

    Args:
        tarefa: a tarefa.
        adaptador: o provedor.
        parametros: os parâmetros da rodada; a seed da repetição é derivada aqui.
        contexto: a identidade da rodada.
        chave: a chave de API.
        cliente: cliente HTTP reusado.
        repeticao: o índice da repetição, a partir de zero.

    Returns:
        A execução crua, com resposta ou com erro de infraestrutura.

    Raises:
        ErroDeSeguranca: se o corpo a gravar contiver um segredo registrado.
    """
    da_vez = parametros.model_copy(update={"seed": seed_da_repeticao(parametros.seed, repeticao)})
    requisicao = adaptador.preparar(
        modelo=contexto.modelo,
        mensagens=montar_mensagens(tarefa),
        ferramentas=tarefa.context.tools,
        parametros=da_vez,
        system=tarefa.context.system_prompt,
    )
    literal = requisicao.literal()
    if contem_segredo(literal):
        msg = (
            f"o corpo preparado por '{adaptador.nome}' contem um segredo registrado. "
            "A rodada para: redigir esconderia um defeito do adaptador."
        )
        raise ErroDeSeguranca(msg)

    marca = chave_de_cache(
        task_id=tarefa.id,
        modelo=contexto.modelo,
        corpo_literal=literal,
        temperatura=da_vez.temperature,
        seed=da_vez.seed,
        repeticao=repeticao,
    )
    erro: str | None = None
    do_cache = False
    decorrido = 0

    resposta: RespostaCrua | None = (
        ler(contexto.cache, marca) if contexto.cache is not None else None
    )
    if resposta is not None:
        do_cache = True
    else:
        inicio = perf_counter()
        try:
            resposta = await adaptador.completar(requisicao, chave=chave, cliente=cliente)
        except ErroDoProvedor as falha:
            erro = str(falha)
        decorrido = round((perf_counter() - inicio) * 1000)
        if resposta is not None and contexto.cache is not None:
            gravar(contexto.cache, marca, resposta)

    return ExecucaoCrua(
        task_id=tarefa.id,
        task_version=tarefa.task_version,
        task_hash=hash_da_tarefa(tarefa),
        suite_id=contexto.suite_id,
        agent=identidade(contexto, adaptador, da_vez),
        repetition=repeticao,
        timestamp=datetime.now(UTC),
        latency_ms=decorrido,
        curupira_version=__version__,
        request_body=literal,
        do_cache=do_cache,
        raw=resposta,
        erro=erro,
    )


async def executar_tarefa(
    tarefa: Tarefa,
    adaptador: AdaptadorDeModelo,
    parametros: ParametrosDeAmostragem,
    *,
    contexto: ContextoDaRodada,
    chave: SecretStr,
    cliente: httpx.AsyncClient,
    fila: asyncio.Queue[ExecucaoCrua | None],
    repeticoes: int,
) -> None:
    """Executa uma tarefa N vezes e publica cada resposta crua na fila.

    Repetição é o detector principal de "acertou por sorte": um acerto que só
    acontece em 1 de 5 repetições não é competência, é ruído. Repetir é ordens de
    magnitude mais barato que autorar tarefa nova.

    As repetições de uma mesma tarefa são **sequenciais** de propósito. A
    concorrência está entre tarefas; paralelizar também dentro da tarefa
    multiplicaria a taxa de requisição sem ganho de wall-clock relevante e
    aumentaria a chance de 429 — que entraria no resultado como erro de
    infraestrutura e sujaria a medição.

    Args:
        tarefa: a tarefa a executar.
        adaptador: o provedor.
        parametros: temperatura, seed e limite de tokens.
        contexto: a identidade da rodada.
        chave: a chave de API.
        cliente: cliente HTTP reusado.
        fila: a fila do escritor único.
        repeticoes: quantas vezes repetir.
    """
    for repeticao in range(repeticoes):
        execucao = await executar_repeticao(
            tarefa,
            adaptador,
            parametros,
            contexto=contexto,
            chave=chave,
            cliente=cliente,
            repeticao=repeticao,
        )
        await fila.put(execucao)


async def _escrever(fila: asyncio.Queue[ExecucaoCrua | None], destino: Path) -> None:
    """Consome a fila e escreve `raw.jsonl`. Único dono do descritor de arquivo.

    Args:
        fila: a fila alimentada pelas corrotinas de execução.
        destino: o arquivo de saída.
    """
    with acrescentar_linhas(destino) as saida:
        while True:
            item = await fila.get()
            if item is None:
                return
            saida.escrever_linha(item.model_dump_json())
            saida.descarregar()


def _recusas_previas(suite: Suite, tarefas: Mapping[str, Tarefa]) -> list[str]:
    """Tudo o que impede a rodada de começar, conferido antes de pagar nada.

    Args:
        suite: a suíte congelada.
        tarefas: o dataset carregado agora.

    Returns:
        A lista de motivos. Vazia significa que a rodada pode começar.
    """
    motivos = verificar_suite(suite, tarefas)
    motivos.extend(
        f"{entrada.task_id}: tem followup_turns e a v0.1 executa so um turno. "
        "Multi-turno (T6) entra na v0.3; tire a tarefa desta suite."
        for entrada in suite.entries
        if (tarefa := tarefas.get(entrada.task_id)) is not None and tarefa.input.followup_turns
    )
    return motivos


def tarefas_da_suite(suite: Suite, tarefas: Mapping[str, Tarefa]) -> list[Tarefa]:
    """Devolve as tarefas da suíte, na ordem congelada.

    Args:
        suite: a suíte congelada.
        tarefas: o dataset carregado agora.

    Returns:
        As tarefas correspondentes às entradas da suíte.
    """
    presentes = (tarefas.get(entrada.task_id) for entrada in suite.entries)
    return [tarefa for tarefa in presentes if tarefa is not None]


async def executar_suite(
    suite: Suite,
    tarefas: Mapping[str, Tarefa],
    adaptador: AdaptadorDeModelo,
    parametros: ParametrosDeAmostragem,
    *,
    contexto: ContextoDaRodada,
    chave: SecretStr,
    cliente: httpx.AsyncClient,
    repeticoes: int,
    saida: Path,
    concorrencia: int = 4,
) -> Path:
    """Executa uma suíte congelada inteira.

    Args:
        suite: a suíte congelada.
        tarefas: o dataset carregado agora, indexado por `task_id`.
        adaptador: o provedor.
        parametros: os parâmetros de amostragem.
        chave: a chave de API.
        cliente: cliente HTTP reusado.
        contexto: a identidade da rodada.
        repeticoes: repetições por tarefa.
        saida: diretório da rodada.
        concorrencia: chamadas simultâneas ao provedor.

    Returns:
        O caminho do `raw.jsonl` produzido.

    Raises:
        ValueError: se algum hash divergir, alguma tarefa sumir, alguma tarefa
            for multi-turno, ou se `repeticoes`/`concorrencia` não fizerem
            sentido.
    """
    if repeticoes < 1 or concorrencia < 1:
        msg = f"repeticoes e concorrencia precisam ser >= 1 (vieram {repeticoes}, {concorrencia})"
        raise ValueError(msg)

    motivos = _recusas_previas(suite, tarefas)
    if motivos:
        msg = "a rodada nao comeca:\n  " + "\n  ".join(motivos)
        raise ValueError(msg)

    bruto = saida / NOME_DO_BRUTO
    if bruto.exists():
        # O escritor abre em modo append para nunca truncar o que ja foi pago.
        # A contrapartida e que duas rodadas apontadas para o mesmo diretorio
        # fundiriam seus brutos num arquivo so — com dois `rodada.json`
        # impossiveis de separar depois. Recusar e a unica saida honesta.
        msg = f"{bruto} ja existe: uma rodada nao se mistura com outra. Use outro diretorio."
        raise ValueError(msg)

    saida.mkdir(parents=True, exist_ok=True)
    fila: asyncio.Queue[ExecucaoCrua | None] = asyncio.Queue()
    escritor = asyncio.create_task(_escrever(fila, bruto))
    limite = asyncio.Semaphore(concorrencia)

    async def _uma(tarefa: Tarefa) -> None:
        async with limite:
            await executar_tarefa(
                tarefa,
                adaptador,
                parametros,
                contexto=contexto,
                chave=chave,
                cliente=cliente,
                fila=fila,
                repeticoes=repeticoes,
            )

    alvos: Sequence[Tarefa] = tarefas_da_suite(suite, tarefas)
    try:
        await asyncio.gather(*(_uma(tarefa) for tarefa in alvos))
    finally:
        # A sentinela vai na fila mesmo se uma corrotina estourou: sem ela o
        # escritor esperaria para sempre e o erro de verdade viraria um travamento.
        await fila.put(None)
        await escritor

    return bruto


def ler_bruto(caminho: Path) -> list[ExecucaoCrua]:
    """Lê um `raw.jsonl` de volta, validando linha a linha.

    Args:
        caminho: o arquivo bruto.

    Returns:
        As execuções, na ordem em que foram escritas.
    """
    with caminho.open(encoding="utf-8") as origem:
        return [ExecucaoCrua.model_validate_json(linha) for linha in origem if linha.strip()]
