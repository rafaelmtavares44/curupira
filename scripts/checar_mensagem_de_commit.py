"""Valida a mensagem de commit contra o Conventional Commits.

O portão de qualidade do projeto exige Conventional Commits desde a Fase 0, e até
a Entrega 7 **nada verificava isso**. O `.pre-commit-config.yaml` pedia o gatilho
`commit-msg` em `default_install_hook_types` e não tinha nenhum hook para ele: a
exigência estava no papel e não no CI.

Esse buraco era visível a olho nu em qualquer commit. Como nenhum hook declarava
`stages`, todos eram candidatos aos dois gatilhos, e a segunda leva saía inteira
como `Skipped (no files to check)` — o pre-commit montava o ambiente de cada hook
para descobrir que não havia o que fazer. Custava segundos e não verificava nada.

Uso, como hook de `commit-msg`:

    python scripts/checar_mensagem_de_commit.py .git/COMMIT_EDITMSG
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Final

TIPOS: Final = (
    "build",
    "chore",
    "ci",
    "docs",
    "feat",
    "fix",
    "perf",
    "refactor",
    "revert",
    "style",
    "test",
)
"""Os tipos do Conventional Commits, mais `revert`. Ordem alfabetica de proposito:
a mensagem de erro os lista, e uma lista ordenada e mais facil de conferir."""

LIMITE_DO_ASSUNTO: Final = 72
"""Convencao de largura, NAO faz parte do Conventional Commits.

Setenta e dois e o que cabe no `git log --oneline` de um terminal comum sem
quebrar. Reprovar em vez de avisar e decisao de portao: um aviso que ninguem le
nao e portao, e um limite que so vale as vezes vira discussao em revisao."""

_CABECALHO: Final = re.compile(
    r"^(?P<tipo>[a-z]+)(?:\((?P<escopo>[a-z0-9][a-z0-9._-]*)\))?(?P<ruptura>!)?: (?P<assunto>.+)$"
)

_ISENTOS: Final = ("Merge ", "Revert ", "fixup! ", "squash! ", "amend! ")
"""Prefixos que o git gera sozinho. Reprova-los quebraria merge e rebase."""


def _problema_no_assunto(assunto: str) -> str | None:
    """Diz o que há de errado com a primeira linha, sozinha."""
    casou = _CABECALHO.match(assunto)
    if casou is None:
        return (
            f"cabecalho fora do Conventional Commits: {assunto!r}\n"
            f"  esperado: <tipo>[(escopo)][!]: <descricao>\n"
            f"  exemplo:  feat(formatos): boleto e chave de acesso da NF-e"
        )
    if casou.group("tipo") not in TIPOS:
        return f"tipo desconhecido: {casou.group('tipo')!r}\n  tipos aceitos: {', '.join(TIPOS)}"
    if casou.group("assunto").endswith("."):
        return "o assunto nao termina em ponto final"
    if len(assunto) > LIMITE_DO_ASSUNTO:
        return f"assunto com {len(assunto)} caracteres; o limite e {LIMITE_DO_ASSUNTO}"
    return None


def validar_mensagem(texto: str) -> str | None:
    """Diz o que há de errado com uma mensagem de commit.

    Args:
        texto: o conteúdo bruto do arquivo de mensagem, comentários inclusive.

    Returns:
        A explicação do problema, ou `None` se a mensagem passar.
    """
    linhas = [linha for linha in texto.splitlines() if not linha.startswith("#")]
    assunto = next((linha for linha in linhas if linha.strip()), "")

    if not assunto:
        return "mensagem vazia"
    if assunto.startswith(_ISENTOS):
        return None

    problema = _problema_no_assunto(assunto)
    if problema is not None:
        return problema

    corpo = linhas[1:]
    if corpo and corpo[0].strip():
        return "falta a linha em branco entre o assunto e o corpo"
    return None


def main(argumentos: list[str]) -> int:
    """Ponto de entrada do hook.

    Args:
        argumentos: os argumentos da linha de comando, sem o nome do programa.

    Returns:
        0 se a mensagem passa, 1 se não passa, 2 se o uso estiver errado.
    """
    if len(argumentos) != 1:
        sys.stderr.write(f"uso: {Path(__file__).name} <arquivo-da-mensagem>\n")
        return 2

    caminho = Path(argumentos[0])
    if not caminho.is_file():
        sys.stderr.write(f"arquivo de mensagem inexistente: {caminho}\n")
        return 2

    problema = validar_mensagem(caminho.read_text(encoding="utf-8"))
    if problema is None:
        return 0
    sys.stderr.write(f"mensagem de commit recusada: {problema}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
