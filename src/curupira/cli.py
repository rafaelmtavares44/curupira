"""A linha de comando do Curupira.

Toda rodada nomeia uma suíte: `curupira run --suite v0.1`. Comparar notas de
suítes diferentes é erro explícito da ferramenta.
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Final

import httpx
import typer
from pydantic import SecretStr
from rich import box
from rich.console import Console
from rich.table import Table

from curupira import __version__
from curupira.adapters.anthropic import AdaptadorAnthropic
from curupira.adapters.base import AdaptadorDeModelo, ParametrosDeAmostragem
from curupira.adapters.falso import AdaptadorFalso, Politica
from curupira.adapters.openai import AdaptadorOpenAI
from curupira.core.enums import ClasseDeFalha, Desfecho
from curupira.core.io import gravar_texto
from curupira.core.loader import (
    ProblemaDeLint,
    Severidade,
    carregar_diretorio,
    lint_do_dataset,
    tem_erro,
)
from curupira.core.registry import limpar_registro
from curupira.core.result import RegistroDaRodada
from curupira.core.suite import (
    Suite,
    carregar_errata,
    carregar_suite,
    congelar,
    gravar_suite,
    suite_esta_morta,
    verificar_suite,
)
from curupira.core.task import Tarefa
from curupira.formatos import registrar_validadores
from curupira.matchers import registrar_todos
from curupira.report.aggregate import RelatorioDaRodada, agregar
from curupira.report.delta import METODO_BCA
from curupira.runner.executor import (
    ARQUIVO_DA_RODADA,
    NOME_DO_BRUTO,
    ContextoDaRodada,
    ErroDeSeguranca,
    executar_suite,
    identidade,
    ler_bruto,
)
from curupira.scoring.rodada import NOME_DO_PONTUADO, gravar_pontuado, pontuar_rodada
from curupira.security import carregar_chave

ARQUIVO_DE_RELATORIO: Final = "report.json"

app = typer.Typer(
    name="curupira",
    help="Benchmark de agentes de IA em portugues brasileiro.",
    no_args_is_help=True,
    add_completion=False,
)

suite_app = typer.Typer(help="Congelar e conferir suites.", no_args_is_help=True)
app.add_typer(suite_app, name="suite")

# soft_wrap=True: saida de diagnostico NAO deve ser quebrada pelo rich conforme
# a largura do terminal. Quem le log de CI usa grep, e uma mensagem partida no
# meio de "edicao silenciosa" some do grep. Deixamos o terminal quebrar se
# quiser; a linha logica continua uma linha.
console = Console(soft_wrap=True)
erro_console = Console(stderr=True, soft_wrap=True)

CODIGO_DE_USO = 2
"""Saida para erro de uso: caminho inexistente, suite ja congelada."""

TETO_DE_JUIZ: Final = 0.15
"""Fracao de execucoes no juiz acima da qual a trilha esta mal desenhada.

Nao e limite tecnico, e sinal de projeto: toda execucao que vai para o juiz sai
do denominador da acuracia, e um denominador que encolhe de forma diferente entre
os dois idiomas e viés dentro do Delta.
"""

TEMPO_LIMITE: Final = 120.0
"""Segundos por chamada. Generoso de proposito: um timeout curto transformaria
lentidao do provedor em erro de infraestrutura, e erro de infraestrutura some da
medicao — o resultado ficaria mais limpo do que a realidade."""

LIMIAR_DE_INFRA: Final = 0.10
"""Acima disto, a rodada e reportada como comprometida por infraestrutura.

Dez por cento e baixo de proposito. Erro de infraestrutura nao e ruido que se
dilui: ele REMOVE execucoes do denominador, e as que remove nao sao sorteadas —
tendem a ser as mais lentas, as mais longas, as que estouraram limite. Uma
rodada com 10% de erro ja esta medindo um subconjunto enviesado."""

VARIAVEL_DA_CHAVE: Final = {
    "anthropic": "CURUPIRA_ANTHROPIC_API_KEY",
    "openai": "CURUPIRA_OPENAI_API_KEY",
}
"""De onde sai a chave de cada provedor.

Prefixo `CURUPIRA_` de proposito: nao reaproveitamos `ANTHROPIC_API_KEY`, que
costuma estar exportada na sessao inteira do desenvolvedor. Quem roda o
benchmark declara, num gesto explicito, qual chave vai ser gasta.
"""


class Provedor(StrEnum):
    """Provedores que o `run` sabe instanciar.

    Todo adaptador implementado precisa aparecer aqui ou estar declarado em
    `tests/test_cli.py::ADAPTADORES_FORA_DO_CLI`, com o motivo. Um adaptador
    testado, coberto e inalcançável pela linha de comando é código que passou
    por todos os portões sem fazer nada — foi o que aconteceu com o da OpenAI
    entre as Entregas 8 e 12.
    """

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    FALSO = "falso"
    """Deterministico, sem rede e sem custo. Ensaio e linha de base trivial."""


def _adaptador(provedor: Provedor) -> AdaptadorDeModelo:
    """Instancia o adaptador do provedor escolhido.

    Args:
        provedor: o provedor pedido na linha de comando.

    Returns:
        O adaptador.
    """
    if provedor is Provedor.ANTHROPIC:
        return AdaptadorAnthropic()
    if provedor is Provedor.OPENAI:
        return AdaptadorOpenAI()
    return AdaptadorFalso(Politica.PRIMEIRA_FERRAMENTA)


def _chave_do_provedor(provedor: Provedor) -> SecretStr:
    """Obtem a chave do provedor, ou uma vazia quando nao ha rede.

    Args:
        provedor: o provedor escolhido.

    Returns:
        A chave, ja registrada para redacao.

    Raises:
        typer.Exit: se a variavel de ambiente nao estiver definida.
    """
    variavel = VARIAVEL_DA_CHAVE.get(provedor.value)
    if variavel is None:
        return SecretStr("")
    try:
        return carregar_chave(variavel)
    except (KeyError, ValueError) as falha:
        erro_console.print(f"chave indisponivel: {falha}", style="red")
        raise typer.Exit(code=CODIGO_DE_USO) from falha


def _sha256_do_arquivo(caminho: Path) -> str:
    """Hash do arquivo da suite, para pregar a rodada ao arquivo exato."""
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _dataset(tarefas: Path) -> dict[str, Tarefa]:
    """Carrega o dataset indexado por id, abortando se o diretorio nao existir.

    Args:
        tarefas: a raiz do dataset.

    Returns:
        Mapa de `task_id` para tarefa.

    Raises:
        typer.Exit: se o diretorio nao existir.
    """
    if not tarefas.is_dir():
        erro_console.print(f"diretorio nao encontrado: {tarefas}", style="red")
        raise typer.Exit(code=CODIGO_DE_USO)
    return {tarefa.id: tarefa for tarefa in carregar_diretorio(tarefas)}


def _suite_do_disco(destino: Path, identificador: str) -> tuple[Suite, Path]:
    """Carrega uma suite congelada pelo id.

    Args:
        destino: o diretorio das suites.
        identificador: o id da suite.

    Returns:
        A suite e o caminho do arquivo.

    Raises:
        typer.Exit: se o arquivo nao existir.
    """
    caminho = destino / f"{identificador}.yaml"
    if not caminho.is_file():
        erro_console.print(f"suite nao encontrada: {caminho}", style="red")
        raise typer.Exit(code=CODIGO_DE_USO)
    return carregar_suite(caminho), caminho


def _preparar_registro() -> None:
    """Deixa o registro de matchers e validadores no estado inicial.

    Limpa antes de registrar para que o comando seja idempotente. Rodar isso no
    meio de uma rodada seria erro; aqui roda no inicio de um comando, antes de
    qualquer tarefa ser carregada.
    """
    limpar_registro()
    registrar_todos()
    registrar_validadores()


def _imprimir(problemas: list[ProblemaDeLint]) -> None:
    """Imprime os problemas do lint, um por linha, colorido por severidade."""
    for problema in problemas:
        cor = "red" if problema.severidade is Severidade.ERRO else "yellow"
        # markup=False: as mensagens carregam colchetes de listas Python, que o
        # rich interpretaria como marcacao e engoliria.
        console.print(str(problema), style=cor, markup=False)


@app.command()
def validate(
    tarefas: Annotated[Path, typer.Option(help="Raiz do dataset.")] = Path("tasks"),
    estrito: Annotated[bool, typer.Option("--strict", help="Avisos viram erros.")] = False,
) -> None:
    """Faz o lint do dataset: canarios unicos, paridade, matchers registrados."""
    _preparar_registro()
    if not tarefas.is_dir():
        erro_console.print(f"diretorio nao encontrado: {tarefas}", style="red")
        raise typer.Exit(code=CODIGO_DE_USO)

    carregadas = list(carregar_diretorio(tarefas))
    if not carregadas:
        console.print(f"nenhuma tarefa em {tarefas}", style="yellow")
        return

    problemas = lint_do_dataset(carregadas, estrito=estrito)
    _imprimir(problemas)

    erros = sum(1 for p in problemas if p.severidade is Severidade.ERRO)
    avisos = len(problemas) - erros
    console.print(
        f"\n{len(carregadas)} tarefas · {erros} erros · {avisos} avisos",
        style="bold",
    )
    if tem_erro(problemas):
        raise typer.Exit(code=1)


@suite_app.command("freeze")
def suite_freeze(
    identificador: Annotated[str, typer.Argument(help="Id da nova suite, ex.: v0.1.")],
    tarefas: Annotated[Path, typer.Option(help="Raiz do dataset.")] = Path("tasks"),
    destino: Annotated[Path, typer.Option(help="Diretorio das suites.")] = Path("suites"),
) -> None:
    """Congela uma suite: id, task_version e sha256 de cada tarefa.

    Recusa congelar um dataset com erro de lint, e recusa sobrescrever uma suite
    que ja existe. As duas recusas sao o ponto: uma suite congelada que muda nao
    e uma suite congelada.
    """
    _preparar_registro()
    caminho = destino / f"{identificador}.yaml"
    if caminho.exists():
        erro_console.print(
            f"a suite '{identificador}' ja existe em {caminho}. Suite congelada nao "
            "se sobrescreve: corrija por errata, ou corte a proxima suite.",
            style="red",
        )
        raise typer.Exit(code=CODIGO_DE_USO)

    carregadas = list(carregar_diretorio(tarefas))
    problemas = lint_do_dataset(carregadas, estrito=False)
    if tem_erro(problemas):
        _imprimir(problemas)
        erro_console.print(
            "\ndataset com erro nao se congela: a suite herdaria o defeito para sempre.",
            style="red",
        )
        raise typer.Exit(code=1)

    suite = congelar(carregadas, suite_id=identificador)
    gravar_suite(suite, caminho)
    console.print(
        f"suite '{suite.id}' congelada em {caminho}\n"
        f"  {len(suite.entries)} tarefas\n"
        f"  {len(suite.delta_subset)} pares strict no subconjunto do Delta",
        style="green",
    )


@suite_app.command("verify")
def suite_verify(
    identificador: Annotated[str, typer.Argument(help="Id da suite a conferir.")],
    tarefas: Annotated[Path, typer.Option(help="Raiz do dataset.")] = Path("tasks"),
    destino: Annotated[Path, typer.Option(help="Diretorio das suites.")] = Path("suites"),
) -> None:
    """Confere os hashes do dataset contra os congelados na suite."""
    _preparar_registro()
    caminho = destino / f"{identificador}.yaml"
    if not caminho.is_file():
        erro_console.print(f"suite nao encontrada: {caminho}", style="red")
        raise typer.Exit(code=CODIGO_DE_USO)

    suite = carregar_suite(caminho)
    carregadas = {t.id: t for t in carregar_diretorio(tarefas)}
    divergencias = verificar_suite(suite, carregadas)

    caminho_errata = destino / f"{identificador}.errata.yaml"
    if caminho_errata.is_file():
        errata = carregar_errata(caminho_errata)
        console.print(
            f"errata revisao {errata.revision}: {len(errata.entries)} tarefas",
            style="yellow",
        )
        if suite_esta_morta(suite, errata):
            erro_console.print(
                "a errata passou de 5% da suite. Suite morta: encerre e corte a "
                "proxima, em vez de remendar.",
                style="red",
            )
            raise typer.Exit(code=1)

    for divergencia in divergencias:
        console.print(divergencia, style="red", markup=False)

    if divergencias:
        raise typer.Exit(code=1)
    console.print(
        f"suite '{suite.id}' integra: {len(suite.entries)} hashes conferem",
        style="green",
    )


@app.command()
def run(
    suite: Annotated[str, typer.Option(help="Id da suite congelada, ex.: v0.1.")],
    agent: Annotated[str, typer.Option(help="Id do agente a pontuar.")],
    modelo: Annotated[str, typer.Option(help="Identificador do modelo no provedor.")],
    provedor: Annotated[Provedor, typer.Option(help="Provedor.")] = Provedor.FALSO,
    repeticoes: Annotated[int, typer.Option(help="Repeticoes por tarefa.")] = 3,
    temperatura: Annotated[float, typer.Option(help="Temperatura de amostragem.")] = 0.0,
    seed: Annotated[int | None, typer.Option(help="Seed base, se o provedor aceitar.")] = None,
    max_tokens: Annotated[int, typer.Option(help="Limite de tokens da resposta.")] = 4096,
    concorrencia: Annotated[int, typer.Option(help="Chamadas simultaneas.")] = 4,
    framework: Annotated[str | None, typer.Option(help="Framework do agente.")] = None,
    tarefas: Annotated[Path, typer.Option(help="Raiz do dataset.")] = Path("tasks"),
    destino: Annotated[Path, typer.Option(help="Diretorio das suites.")] = Path("suites"),
    cache: Annotated[Path | None, typer.Option(help="Diretorio de cache de resposta.")] = None,
    saida: Annotated[Path, typer.Option(help="Diretorio das rodadas.")] = Path("runs"),
) -> None:
    """Executa uma suite e grava apenas as respostas cruas.

    Nao pontua e nao agrega: guarde o bruto, agregue tarde. Pontuar aqui
    amarraria o numero aos matchers do dia da rodada, e corrigir um matcher
    passaria a custar uma rodada paga inteira.
    """
    _preparar_registro()
    congelada, caminho_da_suite = _suite_do_disco(destino, suite)
    carregadas = _dataset(tarefas)
    adaptador = _adaptador(provedor)
    chave = _chave_do_provedor(provedor)

    parametros = ParametrosDeAmostragem(temperature=temperatura, seed=seed, max_tokens=max_tokens)
    contexto = ContextoDaRodada(
        suite_id=congelada.id,
        agent_id=agent,
        modelo=modelo,
        framework=framework,
        cache=cache,
    )
    carimbo = datetime.now(UTC)
    # Microssegundos, nao segundos: duas rodadas disparadas no mesmo segundo
    # cairiam no mesmo diretorio e os dois `raw.jsonl` se fundiriam. O executor
    # tambem recusa um bruto preexistente — cinto e suspensorio, porque essa
    # colisao e silenciosa e so apareceria como numero estranho no relatorio.
    diretorio = saida / f"{congelada.id}__{agent}__{carimbo:%Y%m%dT%H%M%S.%fZ}"

    if seed is not None and not adaptador.suporta_seed:
        console.print(
            f"aviso: '{adaptador.nome}' nao aceita seed. A rodada roda assim mesmo e "
            "grava seed_aplicada=false — repeticao mede nao-determinismo, nao "
            "reprodutibilidade bit a bit.",
            style="yellow",
        )

    try:
        bruto = asyncio.run(
            _rodar(
                congelada,
                carregadas,
                adaptador,
                parametros,
                contexto=contexto,
                chave=chave,
                repeticoes=repeticoes,
                diretorio=diretorio,
                concorrencia=concorrencia,
            )
        )
    except (ValueError, ErroDeSeguranca) as falha:
        erro_console.print(str(falha), style="red", markup=False)
        raise typer.Exit(code=1) from falha

    execucoes = ler_bruto(bruto)
    registro = RegistroDaRodada(
        suite_id=congelada.id,
        suite_sha256=_sha256_do_arquivo(caminho_da_suite),
        agent=identidade(contexto, adaptador, parametros),
        repeticoes=repeticoes,
        max_tokens=max_tokens,
        concorrencia=concorrencia,
        iniciada_em=carimbo,
        terminada_em=datetime.now(UTC),
        curupira_version=__version__,
        python_version=sys.version.split()[0],
        tarefas=len(congelada.entries),
        execucoes=len(execucoes),
        erros=sum(1 for execucao in execucoes if execucao.erro is not None),
        acertos_de_cache=sum(1 for execucao in execucoes if execucao.do_cache),
    )
    gravar_texto(diretorio / ARQUIVO_DA_RODADA, registro.model_dump_json(indent=2))

    console.print(
        f"rodada em {diretorio}\n"
        f"  {registro.execucoes} execucoes · {registro.erros} erros de infraestrutura · "
        f"{registro.acertos_de_cache} do cache\n"
        f"  proximo passo: curupira score {diretorio}",
        style="green",
    )
    if registro.erros:
        raise typer.Exit(code=1)


async def _rodar(
    congelada: Suite,
    carregadas: dict[str, Tarefa],
    adaptador: AdaptadorDeModelo,
    parametros: ParametrosDeAmostragem,
    *,
    contexto: ContextoDaRodada,
    chave: SecretStr,
    repeticoes: int,
    diretorio: Path,
    concorrencia: int,
) -> Path:
    """Abre um cliente HTTP e executa a suite.

    Args:
        congelada: a suite congelada.
        carregadas: o dataset indexado por id.
        adaptador: o provedor.
        parametros: os parametros de amostragem.
        contexto: a identidade da rodada.
        chave: a chave de API.
        repeticoes: repeticoes por tarefa.
        diretorio: o diretorio da rodada.
        concorrencia: chamadas simultaneas.

    Returns:
        O caminho do `raw.jsonl`.
    """
    limites = httpx.Limits(max_connections=max(concorrencia, 1))
    async with httpx.AsyncClient(timeout=TEMPO_LIMITE, limits=limites) as cliente:
        return await executar_suite(
            congelada,
            carregadas,
            adaptador,
            parametros,
            contexto=contexto,
            chave=chave,
            cliente=cliente,
            repeticoes=repeticoes,
            saida=diretorio,
            concorrencia=concorrencia,
        )


@app.command()
def score(
    rodada: Annotated[Path, typer.Argument(help="Diretorio da rodada a pontuar.")],
    tarefas: Annotated[Path, typer.Option(help="Raiz do dataset.")] = Path("tasks"),
) -> None:
    """Pontua as respostas cruas de uma rodada, sem chamar nenhum provedor.

    Re-executavel a vontade: corrigir um matcher ou rotular um modo de falha novo
    custa uma nova rodada deste comando, nao uma rodada paga. O `raw.jsonl` nunca
    e reescrito.

    Recusa pontuar se o hash de alguma tarefa divergir do que a rodada usou. A
    resposta seria de uma pergunta e o gabarito de outra, e o numero sairia com
    aparencia perfeitamente normal.
    """
    _preparar_registro()
    bruto = rodada / NOME_DO_BRUTO
    if not bruto.is_file():
        erro_console.print(f"bruto nao encontrado: {bruto}", style="red")
        raise typer.Exit(code=CODIGO_DE_USO)

    carregadas = _dataset(tarefas)
    try:
        resultados = pontuar_rodada(ler_bruto(bruto), carregadas)
        destino = gravar_pontuado(resultados, rodada)
    except ValueError as falha:
        erro_console.print(str(falha), style="red", markup=False)
        raise typer.Exit(code=1) from falha

    total = len(resultados)
    passou = sum(1 for r in resultados if r.outcome is Desfecho.PASSOU)
    juiz = sum(1 for r in resultados if r.outcome is Desfecho.PENDENTE_DE_JUIZ)
    infra = sum(1 for r in resultados if r.outcome is Desfecho.ERRO_DE_EXECUCAO)
    silenciosas = sum(1 for r in resultados if r.failure_class is ClasseDeFalha.FALHA_SILENCIOSA)
    decididas = total - juiz - infra

    console.print(
        f"pontuado em {destino}\n"
        f"  {total} execucoes · {decididas} decididas · {juiz} pendentes de juiz · "
        f"{infra} erros de infraestrutura\n"
        f"  {passou} passaram · {silenciosas} falhas silenciosas\n"
        f"  proximo passo: curupira report {rodada}",
        style="green",
    )
    if juiz and decididas and juiz / (juiz + decididas) > TETO_DE_JUIZ:
        console.print(
            f"aviso: mais de {TETO_DE_JUIZ:.0%} das execucoes cairam no juiz. "
            "Isso e defeito de desenho de tarefa, nao do agente: declare "
            "slot_keywords ou reescreva a tarefa como acao observavel.",
            style="yellow",
        )


def _pct(valor: float | None) -> str:
    """Formata uma taxa, distinguindo zero de ausencia de medicao.

    `0.0%` e uma nota: o agente foi medido e nao acertou nada. `—` e a ausencia
    de nota: ninguem mediu. Imprimir as duas coisas igual foi o defeito que a
    Entrega 9 encontrou — ver `MetricasDaTrilha.acuracia`.
    """
    return "—" if valor is None else f"{valor:.1%}"


def _tabela_das_trilhas(relatorio: RelatorioDaRodada) -> Table:
    """Monta a tabela de metricas por trilha."""
    tabela = Table(title=f"{relatorio.agent_id} · suite {relatorio.suite_id}", box=box.SIMPLE)
    colunas = (
        "trilha",
        "n",
        "acuracia",
        "trivial",
        "falha silenc.",
        "abst. indev.",
        "instab.",
        "juiz",
        "erro infra",
    )
    for coluna in colunas:
        tabela.add_column(coluna, justify="right" if coluna != "trilha" else "left")
    for nome, m in sorted(relatorio.por_trilha.items()):
        # A coluna de erro de infraestrutura passa a ser IMPRESSA. Ela ja existia
        # no report.json e so o JSON a mostrava: uma rodada 100% quebrada saia na
        # tabela como um agente que errou tudo. O numero mais importante de uma
        # rodada ruim nao pode ficar so no arquivo.
        infra = f"{m.fracao_com_erro_de_infraestrutura:.1%}"
        tabela.add_row(
            nome,
            str(m.n_decididas),
            _pct(m.acuracia),
            _pct(m.linha_de_base),
            _pct(m.taxa_de_falha_silenciosa),
            _pct(m.taxa_de_abstencao_indevida),
            _pct(m.taxa_de_instabilidade),
            _pct(m.fracao_pontuada_por_juiz),
            f"[red]{infra}[/red]"
            if m.fracao_com_erro_de_infraestrutura > LIMIAR_DE_INFRA
            else infra,
        )
    return tabela


def _avisar_sobre_infraestrutura(relatorio: RelatorioDaRodada) -> None:
    """Grita quando a rodada foi comprometida por falha de infraestrutura.

    Sem isto, uma rodada em que o provedor recusou toda requisicao produz uma
    tabela cheia de travessoes e nenhuma explicacao. O leitor fica com a nota
    vazia e sem saber por que.
    """
    quebradas = {
        nome: m.fracao_com_erro_de_infraestrutura
        for nome, m in relatorio.por_trilha.items()
        if m.fracao_com_erro_de_infraestrutura > LIMIAR_DE_INFRA
    }
    if not quebradas:
        return
    detalhe = " · ".join(f"{nome} {fracao:.0%}" for nome, fracao in sorted(quebradas.items()))
    erro_console.print(
        f"\nATENCAO: erro de infraestrutura acima de {LIMIAR_DE_INFRA:.0%} em {detalhe}.\n"
        "  Isto NAO e desempenho do agente: sao chamadas que nunca chegaram a ser "
        "respondidas.\n  Confira a chave, o nome do modelo e a rede antes de ler "
        "qualquer numero desta rodada.",
        style="red",
    )


def _imprimir_delta(relatorio: RelatorioDaRodada) -> None:
    """Imprime o Delta PT-BR, ou por que ele nao existe."""
    delta = relatorio.delta
    if delta is None:
        erro_console.print(
            f"Delta PT-BR nao calculado: {relatorio.motivo_sem_delta}", style="yellow"
        )
        return
    console.print(
        f"\n[bold]Delta PT-BR[/bold] = {delta.delta:+.1%}  "
        f"IC 95% [{delta.ic_inferior:+.1%}, {delta.ic_superior:+.1%}] ({delta.metodo_ic})\n"
        f"  EN {delta.acuracia_en:.1%} · PT-BR {delta.acuracia_pt:.1%} · "
        f"{delta.n_pares} pares strict em {delta.n_familias} familias",
    )
    if delta.metodo_ic != METODO_BCA:
        console.print(
            f"  aviso: o intervalo saiu por '{delta.metodo_ic}', nao por BCa. "
            "Leia como numero de piloto, nao como resultado.",
            style="yellow",
        )


def _imprimir_linhas_de_base(relatorio: RelatorioDaRodada) -> None:
    """Imprime as politicas triviais ao lado da nota. Obrigatorio."""
    if not relatorio.linhas_de_base:
        return
    linhas = " · ".join(f"{p} {n:.1%}" for p, n in sorted(relatorio.linhas_de_base.items()))
    console.print(f"\n[bold]Linhas de base triviais[/bold]\n  {linhas}")
    perdeu = [
        f"{nome} (trivial '{m.melhor_linha_de_base}' {m.linha_de_base:.1%})"
        for nome, m in sorted(relatorio.por_trilha.items())
        if m.bate_a_linha_de_base is False and m.linha_de_base is not None
    ]
    if perdeu:
        erro_console.print(
            "  ATENCAO: o agente NAO bate a politica trivial em: " + " · ".join(perdeu) + ". "
            "Sem bater o trivial, nao ha competencia demonstrada naquela trilha.",
            style="red",
        )


@app.command()
def report(
    rodada: Annotated[Path, typer.Argument(help="Diretorio da rodada.")],
    tarefas: Annotated[Path, typer.Option(help="Raiz do dataset.")] = Path("tasks"),
    errata: Annotated[Path | None, typer.Option(help="Errata a aplicar.")] = None,
) -> None:
    """Agrega uma rodada pontuada em metricas, Delta PT-BR e linhas de base.

    As linhas de base triviais saem SEMPRE, ao lado da nota. Publicar a acuracia
    de uma trilha sem a politica degenerada ao lado e enganoso por construcao.
    """
    _preparar_registro()
    caminho = rodada / NOME_DO_PONTUADO
    if not caminho.is_file():
        erro_console.print(
            f"rodada nao pontuada: {caminho} nao existe. Rode `curupira score {rodada}` antes.",
            style="red",
        )
        raise typer.Exit(code=CODIGO_DE_USO)

    carregadas = list(_dataset(tarefas).values())
    aplicada = carregar_errata(errata) if errata is not None else None
    try:
        relatorio = agregar(
            caminho, carregadas, errata=aplicada, saida=rodada / ARQUIVO_DE_RELATORIO
        )
    except ValueError as falha:
        erro_console.print(str(falha), style="red", markup=False)
        raise typer.Exit(code=1) from falha

    console.print(_tabela_das_trilhas(relatorio))
    _avisar_sobre_infraestrutura(relatorio)
    _imprimir_delta(relatorio)
    _imprimir_linhas_de_base(relatorio)
    if relatorio.n_tarefas_com_errata:
        console.print(
            f"\n{relatorio.n_tarefas_com_errata} tarefa(s) excluida(s) pela errata "
            f"revisao {relatorio.errata_revision}",
            style="yellow",
        )
    console.print(f"\nrelatorio em {rodada / ARQUIVO_DE_RELATORIO}", style="green")


if __name__ == "__main__":  # pragma: no cover
    app()
