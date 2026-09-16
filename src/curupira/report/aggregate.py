"""Etapa 3: agregar. Sempre a partir do pontuado, nunca durante a execução.

Lê o `scored.parquet` que o `curupira score` produziu. A entrada mudou de
`raw.jsonl` para o parquet quando a etapa 2 ganhou comando próprio: agregar a
partir do bruto obrigaria a reimplementar a pontuação aqui, e duas implementações
da mesma régua divergem.

Quatro decisões de denominador, e cada uma é uma forma de mentir que este módulo
recusa
--------------------------------------------------------------------------------
1. **Erro de infraestrutura sai de tudo.** Um 529 do provedor não é erro do
   agente. Contá-lo favoreceria quem rodou num dia tranquilo.
2. **`pendente_de_juiz` sai do numerador e do denominador**, e a fração é
   reportada em separado. Chutar enviesaria o Delta, porque o resíduo é maior no
   idioma em que o agente se expressa de forma menos previsível.
3. **Latência ignora acerto de cache.** Entrada de cache tem `latency_ms = 0`, e
   deixá-la no p50 daria a impressão de um agente mais rápido a cada reexecução.
4. **O Delta recusa o par cuja contraparte não foi decidida.** Comparar EN e PT
   com denominadores diferentes é viés disfarçado de número.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final

import polars as pl
from pydantic import BaseModel, ConfigDict

from curupira.core.enums import CamadaDePontuacao, ClasseDeFalha, Desfecho, Locale, Paridade, Trilha
from curupira.core.suite import Errata
from curupira.core.task import Tarefa
from curupira.report.baselines import PoliticaTrivial, melhor_nota_trivial, todas_as_notas
from curupira.report.delta import ResultadoDelta, calcular
from curupira.scoring.silent_failure import ROTULO_NAO_ROTULADO

FORA_DO_DENOMINADOR: Final = (Desfecho.ERRO_DE_EXECUCAO.value, Desfecho.PENDENTE_DE_JUIZ.value)
TETO_DE_JUIZ: Final = 0.15


class MetricasDaTrilha(BaseModel):
    """As métricas reportadas por trilha."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trilha: Trilha
    n_tarefas: int
    n_execucoes: int
    n_decididas: int

    acuracia: float | None
    """`None` quando NENHUMA execução foi decidida por camada objetiva.

    ACHADO da Entrega 9, encontrado ensaiando com chave inválida de propósito.
    Antes disto, uma rodada que falhou 100% por erro de infraestrutura — chave
    errada, provedor fora do ar, rede caída — reportava `acuracia: 0.0` e a
    tabela imprimia `0.0%`. Ou seja: **um número com cara de medição, produzido
    a partir de zero observações.**

    O leitor humano conclui que o agente errou tudo. O script que lê o
    `report.json` conclui a mesma coisa, e pior, sem ninguém por perto.

    Zero é uma nota. Ausência de medição não é nota nenhuma, e as duas coisas
    não podem ter a mesma representação. É o mesmo princípio de
    `Desfecho.PENDENTE_DE_JUIZ`: o agregador **não chuta**.
    """

    taxa_de_falha_silenciosa: float | None
    taxa_de_falha_silenciosa_rotulada: float
    taxa_de_abstencao_indevida: float | None

    taxa_de_instabilidade: float | None
    """Fração de tarefas cujo resultado variou entre repetições. Um acerto que só
    acontece às vezes não é competência. `None` sem execução decidida."""

    consistencia_de_grupo: float | None = None
    """Fração de grupos de variantes acertados integralmente. Quem entende
    separador decimal acerta o grupo inteiro; quem casou padrão, um subconjunto."""

    tokens_por_acerto: float | None = None
    """Tokens gastos por tarefa acertada. Não expira.

    Esta é a métrica de eficiência que o relatório sempre traz, porque um número
    em tokens continua verdadeiro daqui a um ano. O custo em reais depende de
    tabela de preço e cotação, que mudam sem avisar.
    """

    custo_por_acerto_brl: float | None = None
    """Só existe quando uma tabela de preços datada foi fornecida. `None` não é
    lacuna: é a recusa de publicar um número monetário sem procedência."""

    latencia_p50_ms: int
    latencia_p95_ms: int
    fracao_pontuada_por_juiz: float
    """Se passar de 15% numa trilha, a tarefa está mal desenhada."""

    fracao_com_erro_de_infraestrutura: float

    melhor_linha_de_base: str | None = None
    linha_de_base: float | None = None
    bate_a_linha_de_base: bool | None = None
    """A comparação com a política trivial é **por trilha**, e isso não é detalhe.

    Uma política degenerada gabarita uma trilha e zera as outras — é essa a
    definição dela. Comparar a média global do agente contra a média global do
    trivial dilui as duas pontas e esconde exatamente o que as linhas de base
    existem para expor: que em T1 um agente que nunca chama nada tira 100% em
    detecção de irrelevância.

    Empatar com o trivial **não** é bater o trivial. A comparação é estrita.
    """


class RelatorioDaRodada(BaseModel):
    """O relatório completo de uma rodada, por agente."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    suite_id: str
    agent_id: str
    errata_revision: int
    n_tarefas_com_errata: int
    por_trilha: dict[str, MetricasDaTrilha]
    delta: ResultadoDelta | None = None
    """`None` quando não sobrou par strict com as duas versões decididas."""

    motivo_sem_delta: str | None = None
    linhas_de_base: dict[str, float] = {}
    melhor_linha_de_base: str | None = None
    nota_bate_a_linha_de_base: bool | None = None


def _percentil_inteiro(valores: Sequence[int], fracao: float) -> int:
    """Percentil de latência, em milissegundos inteiros."""
    if not valores:
        return 0
    ordenados = sorted(valores)
    indice = min(int(fracao * (len(ordenados) - 1) + 0.5), len(ordenados) - 1)
    return ordenados[indice]


def _instabilidade(decididas: pl.DataFrame) -> float | None:
    """Fração de tarefas cujo desfecho variou entre repetições.

    Args:
        decididas: só as linhas que entraram no denominador.

    Returns:
        A fração, de 0 a 1, ou `None` se nada foi decidido.
    """
    if decididas.is_empty():
        return None
    por_tarefa = decididas.group_by("task_id").agg(pl.col("outcome").n_unique().alias("variou"))
    return float((por_tarefa["variou"] > 1).sum()) / por_tarefa.height


def _consistencia_de_grupo(decididas: pl.DataFrame) -> float | None:
    """Fração de grupos de variantes acertados integralmente.

    Returns:
        A fração, ou `None` se não houver grupo de variantes nesta trilha —
        devolver 0,0 sugeriria que o agente falhou em algo que nem foi medido.
    """
    com_grupo = decididas.filter(pl.col("variant_group").is_not_null())
    if com_grupo.is_empty():
        return None
    por_grupo = com_grupo.group_by("variant_group").agg(
        (pl.col("outcome") == Desfecho.PASSOU.value).all().alias("integral")
    )
    return float(por_grupo["integral"].sum()) / por_grupo.height


def _tokens_por_acerto(decididas: pl.DataFrame, acertos: int) -> float | None:
    """Tokens totais divididos pelos acertos.

    Returns:
        `None` sem acerto nenhum (divisão por zero) ou sem contagem de token
        gravada — o adaptador falso, por exemplo, não devolve `usage`.
    """
    if acertos == 0 or decididas.is_empty():
        return None
    total = decididas.select(
        (pl.col("prompt_tokens").fill_null(0) + pl.col("completion_tokens").fill_null(0)).sum()
    ).item()
    return None if not total else float(total) / acertos


def _metricas(trilha: str, linhas: pl.DataFrame, tarefas: Sequence[Tarefa]) -> MetricasDaTrilha:
    """Calcula as métricas de uma trilha, com a linha de base **daquela** trilha.

    Args:
        trilha: o identificador da trilha.
        linhas: as execuções daquela trilha.
        tarefas: as tarefas daquela trilha, para a política trivial.
    """
    decididas = linhas.filter(~pl.col("outcome").is_in(FORA_DO_DENOMINADOR))
    n_decididas = decididas.height
    acertos = int((decididas["outcome"] == Desfecho.PASSOU.value).sum()) if n_decididas else 0

    silenciosas = decididas.filter(pl.col("failure_class") == ClasseDeFalha.FALHA_SILENCIOSA.value)
    rotuladas = silenciosas.filter(
        pl.col("silent_failure_label").is_not_null()
        & (pl.col("silent_failure_label") != ROTULO_NAO_ROTULADO)
    )
    indevidas = (
        int((decididas["failure_class"] == ClasseDeFalha.ABSTENCAO_INDEVIDA.value).sum())
        if n_decididas
        else 0
    )

    sem_cache = decididas.filter(~pl.col("do_cache"))
    latencias = sem_cache["latency_ms"].to_list() if not sem_cache.is_empty() else []

    def por_decididas(valor: int) -> float | None:
        """Taxa sobre o denominador de decididas, ou `None` se ele for zero.

        Devolver 0.0 aqui era o defeito: fabricava uma taxa a partir de nenhuma
        observação. Ver a nota em `MetricasDaTrilha.acuracia`.
        """
        return valor / n_decididas if n_decididas else None

    acuracia = por_decididas(acertos)
    politica, piso = melhor_nota_trivial(tarefas) if tarefas else (None, None)

    # Sem acuracia nao ha veredicto. Um `False` aqui afirmaria que o agente NAO
    # bate a politica trivial, o que e uma afirmacao sobre competencia — e nao
    # se afirma nada sobre competencia com zero observacoes. O agregador global
    # ja descarta os `None`, entao o veredicto da rodada fica indeterminado
    # sozinho, que e o certo.
    bate = None if (piso is None or acuracia is None) else acuracia > piso

    return MetricasDaTrilha(
        trilha=Trilha(trilha),
        melhor_linha_de_base=str(politica) if politica else None,
        linha_de_base=piso,
        bate_a_linha_de_base=bate,
        n_tarefas=linhas["task_id"].n_unique(),
        n_execucoes=linhas.height,
        n_decididas=n_decididas,
        acuracia=acuracia,
        taxa_de_falha_silenciosa=por_decididas(silenciosas.height),
        taxa_de_falha_silenciosa_rotulada=(
            rotuladas.height / silenciosas.height if silenciosas.height else 0.0
        ),
        taxa_de_abstencao_indevida=por_decididas(indevidas),
        taxa_de_instabilidade=_instabilidade(decididas),
        consistencia_de_grupo=_consistencia_de_grupo(decididas),
        tokens_por_acerto=_tokens_por_acerto(decididas, acertos),
        latencia_p50_ms=_percentil_inteiro(latencias, 0.50),
        latencia_p95_ms=_percentil_inteiro(latencias, 0.95),
        fracao_pontuada_por_juiz=(
            int((linhas["outcome"] == Desfecho.PENDENTE_DE_JUIZ.value).sum()) / linhas.height
        ),
        fracao_com_erro_de_infraestrutura=(
            int((linhas["outcome"] == Desfecho.ERRO_DE_EXECUCAO.value).sum()) / linhas.height
        ),
    )


def vetores_do_delta(pontuado: pl.DataFrame) -> tuple[list[float], list[float], str | None]:
    """Extrai os vetores pareados do Delta, aplicando os três invariantes.

    Entra no subconjunto D o par que cumpre **todas** as condições:

    - `parity: strict`;
    - tem as duas versões, PT-BR e EN-US;
    - nenhuma das duas foi pontuada por juiz nem ficou pendente de juiz;
    - as duas têm ao menos uma repetição decidida.

    A terceira condição é a que mais elimina par, e é a que mais importa: um par
    em que só a versão EN foi decidida compararia denominadores diferentes, e a
    diferença apareceria como se fosse efeito do idioma.

    Args:
        pontuado: o `scored.parquet` de UM agente.

    Returns:
        As frações por par em EN e em PT, na mesma ordem de `pair_id`, e o motivo
        de o subconjunto estar vazio quando estiver.
    """
    strict = pontuado.filter(
        (pl.col("parity") == Paridade.STRICT.value)
        & pl.col("pair_id").is_not_null()
        & (pl.col("scoring_layer") != CamadaDePontuacao.JUIZ.value)
        & ~pl.col("outcome").is_in(FORA_DO_DENOMINADOR)
    )
    if strict.is_empty():
        return [], [], "nenhuma execucao strict decidida por camada objetiva"

    por_par = (
        strict.group_by(["pair_id", "locale"])
        .agg((pl.col("outcome") == Desfecho.PASSOU.value).mean().alias("fracao"))
        .pivot(on="locale", index="pair_id", values="fracao")
    )
    pt, en = Locale.PT_BR.value, Locale.EN_US.value
    if pt not in por_par.columns or en not in por_par.columns:
        return [], [], "os pares strict nao tem as duas versoes decididas"

    completos = por_par.filter(pl.col(pt).is_not_null() & pl.col(en).is_not_null()).sort("pair_id")
    if completos.is_empty():
        return [], [], "nenhum par strict ficou com as duas versoes decididas"
    return completos[en].to_list(), completos[pt].to_list(), None


def agregar(
    pontuado: Path,
    tarefas: Sequence[Tarefa],
    *,
    errata: Errata | None = None,
    saida: Path | None = None,
) -> RelatorioDaRodada:
    """Agrega um `scored.parquet` em métricas, Delta e linhas de base.

    Args:
        pontuado: o arquivo produzido por `curupira score`.
        tarefas: as tarefas da suíte, para as linhas de base triviais.
        errata: a errata a aplicar, quando houver.
        saida: onde gravar o `report.json`, quando desejado.

    Returns:
        O relatório.

    Raises:
        ValueError: se o arquivo estiver vazio ou misturar agentes — um relatório
            que soma dois agentes não é relatório de nenhum dos dois.
    """
    frame = pl.read_parquet(pontuado)
    if frame.is_empty():
        msg = f"{pontuado} nao tem nenhuma execucao pontuada"
        raise ValueError(msg)

    agentes = sorted(set(frame["agent_id"].to_list()))
    if len(agentes) > 1:
        msg = (
            f"o arquivo mistura os agentes {agentes}. Delta e por agente, e uma media "
            "entre agentes nao e o Delta de nenhum deles."
        )
        raise ValueError(msg)

    com_errata = {e.task_id for e in errata.entries} if errata else set()
    elegiveis = frame.filter(~pl.col("task_id").is_in(list(com_errata))) if com_errata else frame
    sem_errata = [t for t in tarefas if t.id not in com_errata]

    por_trilha = {
        str(trilha): _metricas(
            str(trilha),
            elegiveis.filter(pl.col("track") == trilha),
            [t for t in sem_errata if t.track.value == str(trilha)],
        )
        for trilha in sorted(set(elegiveis["track"].to_list()))
    }

    en, pt, motivo = vetores_do_delta(elegiveis)
    suite_id = str(frame["suite_id"][0])
    revisao = errata.revision if errata else 0
    delta = calcular(agentes[0], suite_id, revisao, en, pt) if en else None

    notas = todas_as_notas(sem_errata) if sem_errata else {}
    melhor: PoliticaTrivial | None = None
    if sem_errata:
        melhor, _ = melhor_nota_trivial(sem_errata)
    # O veredicto global exige bater o trivial em TODA trilha medida. Bastar a
    # media deixaria um agente compensar a trilha em que perde para a politica
    # degenerada com a trilha em que ela nao compete — que e justamente o
    # esconderijo que as linhas de base existem para fechar.
    julgadas = [
        m.bate_a_linha_de_base for m in por_trilha.values() if m.bate_a_linha_de_base is not None
    ]
    bate = all(julgadas) if julgadas else None

    relatorio = RelatorioDaRodada(
        suite_id=suite_id,
        agent_id=agentes[0],
        errata_revision=revisao,
        n_tarefas_com_errata=len(com_errata),
        por_trilha=por_trilha,
        delta=delta,
        motivo_sem_delta=motivo,
        linhas_de_base={str(p): n for p, n in notas.items()},
        melhor_linha_de_base=str(melhor) if melhor else None,
        nota_bate_a_linha_de_base=bate,
    )
    if saida is not None:
        saida.parent.mkdir(parents=True, exist_ok=True)
        saida.write_text(relatorio.model_dump_json(indent=2), encoding="utf-8")
    return relatorio
