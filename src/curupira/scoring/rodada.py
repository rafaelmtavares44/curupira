"""Etapa 2: pontuar. Lê o bruto do disco, nunca chama provedor.

É a etapa que torna "guarde o bruto, agregue tarde" um fato operacional em vez de
um slogan: corrigir um matcher, rotular um modo de falha novo ou aplicar uma
errata custa uma reexecução desta função — segundos — em vez de uma rodada paga.

A trava que sustenta isso
-------------------------
Cada linha do bruto carrega o `task_hash` que valia quando a resposta foi
produzida. Se o hash da tarefa no dataset de hoje for outro, a pontuação estaria
comparando a resposta de uma pergunta com o gabarito de outra — e o resultado
teria aparência perfeitamente normal. Por isso a divergência é **erro**, nunca
aviso: o pior desfecho possível para este projeto é um número errado que ninguém
questiona.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

import polars as pl

from curupira.core.enums import CamadaDePontuacao, ClasseDeFalha, Desfecho
from curupira.core.expect import EsperaChamadaDeFerramenta
from curupira.core.hashing import hash_da_tarefa
from curupira.core.result import ExecucaoCrua, ResultadoDeRodada
from curupira.core.task import Tarefa
from curupira.scoring.pontuador import Veredicto, abstencao_era_esperada, pontuar
from curupira.scoring.silent_failure import classificar, rotular
from curupira.security import redigir

NOME_DO_PONTUADO: Final = "scored.parquet"

COLUNAS: Final = (
    "task_id",
    "task_version",
    "task_hash",
    "suite_id",
    "errata_revision",
    "track",
    "locale",
    "parity",
    "pair_id",
    "variant_group",
    "agent_id",
    "model",
    "framework",
    "adapter_version",
    "prompt_template_id",
    "temperature",
    "seed",
    "seed_aplicada",
    "repetition",
    "timestamp",
    "latency_ms",
    "cost_brl",
    "curupira_version",
    "outcome",
    "failure_class",
    "scoring_layer",
    "matched_accept_id",
    "preference_rank",
    "silent_failure_label",
    "motivo",
    "prompt_tokens",
    "completion_tokens",
    "do_cache",
)
"""As colunas do `scored.parquet`, em ordem fixa.

Ordem fixa e lista explícita porque o relatório lê este arquivo por nome de
coluna. Derivar as colunas do modelo faria um campo novo aparecer no parquet sem
ninguém decidir, e um campo que aparece sozinho é um campo que ninguém testou.
"""


def _veredicto_de_erro(execucao: ExecucaoCrua) -> Veredicto:
    """Monta o veredicto de uma linha que nem chegou a ter resposta."""
    return Veredicto(
        desfecho=Desfecho.ERRO_DE_EXECUCAO,
        camada=CamadaDePontuacao.AST,
        motivo=execucao.erro or "erro de infraestrutura sem mensagem",
    )


def pontuar_execucao(execucao: ExecucaoCrua, tarefa: Tarefa) -> ResultadoDeRodada:
    """Pontua uma linha do bruto contra a tarefa que a gerou.

    Args:
        execucao: a linha de `raw.jsonl`.
        tarefa: a tarefa, carregada do dataset.

    Returns:
        O resultado pontuado.

    Raises:
        ValueError: se o hash da tarefa divergir do gravado na execução, ou se a
            execução for de outra tarefa.
    """
    if execucao.task_id != tarefa.id:
        msg = f"execucao de '{execucao.task_id}' pontuada contra a tarefa '{tarefa.id}'"
        raise ValueError(msg)

    atual = hash_da_tarefa(tarefa)
    if atual != execucao.task_hash:
        msg = (
            f"{tarefa.id}: a rodada usou o hash {execucao.task_hash[:12]} e o dataset "
            f"esta em {atual[:12]}. Pontuar assim compararia a resposta de uma pergunta "
            "com o gabarito de outra. Faca checkout da versao que rodou, ou rode de novo."
        )
        raise ValueError(msg)

    resposta = execucao.raw
    if resposta is None:
        veredicto = _veredicto_de_erro(execucao)
        classe = ClasseDeFalha.NAO_APLICAVEL
        rotulo = None
    else:
        veredicto = pontuar(tarefa, resposta)
        classe = classificar(
            veredicto.desfecho,
            resposta,
            abstencao_era_esperada=abstencao_era_esperada(tarefa),
            locale=tarefa.locale.value,
        )
        rotulo = (
            rotular(tarefa.expect.silent_failure_if, resposta.tool_calls)
            if veredicto.desfecho is Desfecho.FALHOU
            and isinstance(tarefa.expect, EsperaChamadaDeFerramenta)
            else None
        )

    return ResultadoDeRodada(
        task_id=execucao.task_id,
        task_version=execucao.task_version,
        task_hash=execucao.task_hash,
        suite_id=execucao.suite_id,
        track=tarefa.track,
        locale=tarefa.locale,
        parity=tarefa.parity,
        pair_id=tarefa.pair_id,
        variant_group=tarefa.variant_group,
        agent=execucao.agent,
        repetition=execucao.repetition,
        timestamp=execucao.timestamp,
        latency_ms=execucao.latency_ms,
        cost_brl=execucao.cost_brl,
        curupira_version=execucao.curupira_version,
        outcome=veredicto.desfecho,
        failure_class=classe,
        scoring_layer=veredicto.camada,
        matched_accept_id=veredicto.matched_accept_id,
        preference_rank=veredicto.preference_rank,
        silent_failure_label=rotulo,
        # O motivo cita argumentos que o MODELO produziu, e o parquet e um
        # artefato que se publica junto com o leaderboard. Redigir aqui custa
        # nada e fecha o unico caminho por onde texto de terceiro chega a um
        # arquivo distribuido sem passar pela barreira 3.
        motivo=redigir(veredicto.motivo),
        prompt_tokens=resposta.prompt_tokens if resposta else None,
        completion_tokens=resposta.completion_tokens if resposta else None,
        do_cache=execucao.do_cache,
    )


def pontuar_rodada(
    execucoes: Sequence[ExecucaoCrua], tarefas: Mapping[str, Tarefa]
) -> list[ResultadoDeRodada]:
    """Pontua todas as linhas de uma rodada.

    Args:
        execucoes: as linhas de `raw.jsonl`.
        tarefas: o dataset indexado por `task_id`.

    Returns:
        Os resultados, na ordem do bruto.

    Raises:
        ValueError: se alguma tarefa do bruto não existir no dataset, ou se algum
            hash divergir.
    """
    ausentes = sorted({e.task_id for e in execucoes if e.task_id not in tarefas})
    if ausentes:
        msg = f"a rodada tem tarefas que sumiram do dataset: {ausentes}"
        raise ValueError(msg)
    return [pontuar_execucao(execucao, tarefas[execucao.task_id]) for execucao in execucoes]


def _linha(resultado: ResultadoDeRodada) -> dict[str, object]:
    """Achata um resultado nas colunas do parquet."""
    bruto = resultado.model_dump(mode="json", exclude={"agent", "raw"})
    agente = resultado.agent
    bruto |= {
        "agent_id": agente.agent_id,
        "model": agente.model,
        "framework": agente.framework,
        "adapter_version": agente.adapter_version,
        "prompt_template_id": agente.prompt_template_id,
        "temperature": agente.temperature,
        "seed": agente.seed,
        "seed_aplicada": agente.seed_aplicada,
    }
    return {coluna: bruto[coluna] for coluna in COLUNAS}


def para_dataframe(resultados: Sequence[ResultadoDeRodada]) -> pl.DataFrame:
    """Monta o DataFrame do `scored.parquet`.

    A identidade do agente é **achatada** em colunas, em vez de virar struct: o
    relatório agrupa por `agent_id` e filtra por `model`, e struct aninhado
    transforma cada filtro numa expressão de acesso que ninguém lê depois.

    Args:
        resultados: os resultados pontuados.

    Returns:
        O DataFrame, com as colunas de `COLUNAS` em ordem.

    Raises:
        ValueError: se a lista estiver vazia — um parquet sem linhas não tem
            esquema, e um esquema ausente só apareceria no relatório.
    """
    if not resultados:
        msg = "rodada sem nenhuma execucao pontuada: nao ha o que gravar"
        raise ValueError(msg)
    return pl.DataFrame([_linha(r) for r in resultados]).select(COLUNAS)


def gravar_pontuado(resultados: Sequence[ResultadoDeRodada], diretorio: Path) -> Path:
    """Grava o `scored.parquet` de uma rodada.

    Args:
        resultados: os resultados pontuados.
        diretorio: o diretório da rodada.

    Returns:
        O caminho do arquivo gravado.
    """
    diretorio.mkdir(parents=True, exist_ok=True)
    destino = diretorio / NOME_DO_PONTUADO
    para_dataframe(resultados).write_parquet(destino)
    return destino
