"""A linha de comando do Curupira.

Toda rodada nomeia uma suíte: `curupira run --suite v0.1`. Comparar notas de
suítes diferentes é erro explícito da ferramenta.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from curupira.core.loader import (
    ProblemaDeLint,
    Severidade,
    carregar_diretorio,
    lint_do_dataset,
    tem_erro,
)
from curupira.core.registry import limpar_registro
from curupira.core.suite import (
    carregar_errata,
    carregar_suite,
    congelar,
    gravar_suite,
    suite_esta_morta,
    verificar_suite,
)
from curupira.formatos import registrar_validadores
from curupira.matchers import registrar_todos

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
    repeticoes: Annotated[int, typer.Option(help="Repeticoes por tarefa.")] = 3,
    temperatura: Annotated[float, typer.Option(help="Temperatura de amostragem.")] = 0.0,
    saida: Annotated[Path, typer.Option(help="Diretorio da rodada.")] = Path("runs"),
) -> None:
    """Executa uma suite e grava apenas as respostas cruas.

    Nao pontua e nao agrega: guarde o bruto, agregue tarde.
    """
    raise NotImplementedError


@app.command()
def score(
    rodada: Annotated[Path, typer.Argument(help="Diretorio da rodada a pontuar.")],
) -> None:
    """Pontua as respostas cruas de uma rodada, sem chamar nenhum provedor."""
    raise NotImplementedError


@app.command()
def report(
    rodada: Annotated[Path, typer.Argument(help="Diretorio da rodada.")],
    errata: Annotated[Path | None, typer.Option(help="Errata a aplicar.")] = None,
) -> None:
    """Agrega uma rodada pontuada em metricas, Delta PT-BR e linhas de base."""
    raise NotImplementedError


if __name__ == "__main__":  # pragma: no cover
    app()
