"""Torna visível a porta dos fundos da cobertura.

`[tool.coverage.report].exclude_lines` exclui `raise NotImplementedError`. Sem
isso, o esqueleto da Fase 0 derrubaria o portão de 85%. Com isso, uma função que
você esqueceu de implementar **não derruba nada** — a cobertura fica bonita e
mentirosa.

Este teste fecha o buraco por outro lado: ele varre a árvore com `ast`, lista
toda função cujo corpo é só docstring mais `raise NotImplementedError`, e compara
com um manifesto congelado. Implementou uma? O teste falha e obriga a tirar do
manifesto. Adicionou um stub novo sem perceber? O teste falha também.

Quando `tests/stubs_pendentes.txt` ficar vazio, apague a linha
`"raise NotImplementedError"` do `exclude_lines` e apague este arquivo.
"""

from __future__ import annotations

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src" / "curupira"
MANIFESTO = Path(__file__).resolve().parent / "stubs_pendentes.txt"


def _levanta_nao_implementado(no: ast.stmt) -> bool:
    """Diz se a instrução é exatamente `raise NotImplementedError` (com ou sem call)."""
    if not isinstance(no, ast.Raise) or no.exc is None:
        return False
    alvo = no.exc
    if isinstance(alvo, ast.Call):
        alvo = alvo.func
    return isinstance(alvo, ast.Name) and alvo.id == "NotImplementedError"


def _e_stub(no: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Corpo composto apenas de docstring opcional mais o `raise`."""
    corpo = list(no.body)
    if (
        corpo
        and isinstance(corpo[0], ast.Expr)
        and isinstance(corpo[0].value, ast.Constant)
        and isinstance(corpo[0].value.value, str)
    ):
        corpo = corpo[1:]
    return len(corpo) == 1 and _levanta_nao_implementado(corpo[0])


def stubs_encontrados() -> set[str]:
    """Varre `src/curupira` e devolve os stubs no formato `caminho::funcao`."""
    achados: set[str] = set()
    for arquivo in sorted(SRC.rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef) and _e_stub(no):
                achados.add(f"{arquivo.relative_to(SRC).as_posix()}::{no.name}")
    return achados


def _manifesto() -> set[str]:
    linhas = MANIFESTO.read_text(encoding="utf-8").splitlines()
    return {ln.strip() for ln in linhas if ln.strip() and not ln.lstrip().startswith("#")}


def test_inventario_de_stubs_confere_com_o_manifesto() -> None:
    """O conjunto de pontas soltas é declarado, não descoberto por acidente."""
    encontrados = stubs_encontrados()
    declarados = _manifesto()

    implementados = sorted(declarados - encontrados)
    novos = sorted(encontrados - declarados)

    assert not implementados, (
        "estes stubs foram implementados; remova-os de tests/stubs_pendentes.txt "
        f"no mesmo commit: {implementados}"
    )
    assert not novos, (
        "stub novo entrou sem ser declarado; se e intencional, acrescente a "
        f"tests/stubs_pendentes.txt: {novos}"
    )


def test_lembrete_de_remover_a_exclusao_de_cobertura() -> None:
    """Quando não sobrar stub, a exclusão da cobertura tem que sair junto."""
    if stubs_encontrados():
        return
    texto = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    assert "raise NotImplementedError" not in texto, (
        "nao ha mais stubs: remova 'raise NotImplementedError' de "
        "[tool.coverage.report].exclude_lines e apague tests/test_inventario_de_stubs.py"
    )
