"""A linha de comando do Curupira.

Toda rodada nomeia uma suíte: `curupira run --suite v0.1`. Comparar notas de
suítes diferentes é erro explícito da ferramenta.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    name="curupira",
    help="Benchmark de agentes de IA em portugues brasileiro.",
    no_args_is_help=True,
    add_completion=False,
)

suite_app = typer.Typer(help="Congelar e conferir suites.", no_args_is_help=True)
app.add_typer(suite_app, name="suite")


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


@app.command()
def validate(
    tarefas: Annotated[Path, typer.Option(help="Raiz do dataset.")] = Path("tasks"),
    estrito: Annotated[bool, typer.Option("--strict", help="Avisos viram erros.")] = False,
) -> None:
    """Faz o lint do dataset: canarios unicos, paridade, matchers registrados."""
    raise NotImplementedError


@suite_app.command("freeze")
def suite_freeze(
    identificador: Annotated[str, typer.Argument(help="Id da nova suite, ex.: v0.1.")],
    tarefas: Annotated[Path, typer.Option(help="Raiz do dataset.")] = Path("tasks"),
) -> None:
    """Congela uma suite: id, task_version e sha256 de cada tarefa."""
    raise NotImplementedError


@suite_app.command("verify")
def suite_verify(
    identificador: Annotated[str, typer.Argument(help="Id da suite a conferir.")],
    tarefas: Annotated[Path, typer.Option(help="Raiz do dataset.")] = Path("tasks"),
) -> None:
    """Confere os hashes do dataset contra os congelados na suite."""
    raise NotImplementedError


if __name__ == "__main__":  # pragma: no cover
    app()
