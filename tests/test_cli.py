"""A CLI de ponta a ponta, no dataset real do repositório."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from curupira.cli import app
from curupira.core.registry import limpar_registro
from tests.fabricas import par_strict

runner = CliRunner()


def _saida(resultado: object) -> str:
    """Normaliza espaços em branco da saída antes de procurar texto nela.

    Defesa em profundidade: mesmo com `soft_wrap`, um teste que casa string em
    saída de terminal não pode depender da largura da janela de quem roda.
    """
    return " ".join(str(getattr(resultado, "output", "")).split())


@pytest.fixture(autouse=True)
def _registro_limpo() -> Iterator[None]:
    limpar_registro()
    yield
    limpar_registro()


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    raiz = tmp_path / "tasks"
    raiz.mkdir()
    for bruto in par_strict():
        (raiz / f"{bruto['id']}.yaml").write_text(
            yaml.safe_dump(bruto, allow_unicode=True), encoding="utf-8"
        )
    return raiz


def test_ajuda_lista_os_comandos() -> None:
    resultado = runner.invoke(app, ["--help"])
    assert resultado.exit_code == 0
    for comando in ("run", "score", "report", "validate", "suite"):
        assert comando in _saida(resultado)


def test_validate_no_dataset_real(raiz_do_repo: Path) -> None:
    """O dataset versionado passa no próprio lint, em modo estrito."""
    resultado = runner.invoke(
        app, ["validate", "--tarefas", str(raiz_do_repo / "tasks"), "--strict"]
    )
    assert resultado.exit_code == 0, resultado.output
    assert "0 erros" in _saida(resultado)


def test_validate_com_diretorio_inexistente(tmp_path: Path) -> None:
    resultado = runner.invoke(app, ["validate", "--tarefas", str(tmp_path / "nao-existe")])
    assert resultado.exit_code == 2


def test_validate_com_diretorio_vazio(tmp_path: Path) -> None:
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    resultado = runner.invoke(app, ["validate", "--tarefas", str(vazio)])
    assert resultado.exit_code == 0
    assert "nenhuma tarefa" in _saida(resultado)


def test_validate_falha_com_dataset_defeituoso(dataset: Path) -> None:
    bruto = par_strict()[0]
    bruto["id"] = "clone"
    (dataset / "clone.yaml").write_text(yaml.safe_dump(bruto), encoding="utf-8")

    resultado = runner.invoke(app, ["validate", "--tarefas", str(dataset)])
    assert resultado.exit_code == 1
    assert "canario-unico" in _saida(resultado)


def test_freeze_e_verify(dataset: Path, tmp_path: Path) -> None:
    suites = tmp_path / "suites"
    comum = ["--tarefas", str(dataset), "--destino", str(suites)]

    congelar = runner.invoke(app, ["suite", "freeze", "v0.1", *comum])
    assert congelar.exit_code == 0, congelar.output
    assert (suites / "v0.1.yaml").is_file()
    assert "1 pares strict" in _saida(congelar)

    conferir = runner.invoke(app, ["suite", "verify", "v0.1", *comum])
    assert conferir.exit_code == 0, conferir.output
    assert "integra" in _saida(conferir)


def test_freeze_recusa_sobrescrever(dataset: Path, tmp_path: Path) -> None:
    """Uma suíte congelada que muda não é uma suíte congelada."""
    suites = tmp_path / "suites"
    comum = ["--tarefas", str(dataset), "--destino", str(suites)]
    assert runner.invoke(app, ["suite", "freeze", "v0.1", *comum]).exit_code == 0

    segunda = runner.invoke(app, ["suite", "freeze", "v0.1", *comum])
    assert segunda.exit_code == 2


def test_freeze_recusa_dataset_com_erro(dataset: Path, tmp_path: Path) -> None:
    """Congelar um defeito o eterniza: a suíte roda para sempre."""
    bruto = par_strict()[0]
    bruto["id"] = "clone"
    (dataset / "clone.yaml").write_text(yaml.safe_dump(bruto), encoding="utf-8")

    resultado = runner.invoke(
        app,
        ["suite", "freeze", "v0.1", "--tarefas", str(dataset), "--destino", str(tmp_path / "s")],
    )
    assert resultado.exit_code == 1
    assert not (tmp_path / "s" / "v0.1.yaml").exists()


def test_verify_denuncia_edicao_silenciosa(dataset: Path, tmp_path: Path) -> None:
    suites = tmp_path / "suites"
    comum = ["--tarefas", str(dataset), "--destino", str(suites)]
    assert runner.invoke(app, ["suite", "freeze", "v0.1", *comum]).exit_code == 0

    alvo = next(dataset.glob("*-pt.yaml"))
    bruto = yaml.safe_load(alvo.read_text(encoding="utf-8"))
    bruto["difficulty"] = 5
    alvo.write_text(yaml.safe_dump(bruto, allow_unicode=True), encoding="utf-8")

    resultado = runner.invoke(app, ["suite", "verify", "v0.1", *comum])
    assert resultado.exit_code == 1
    assert "edicao silenciosa" in _saida(resultado)


def test_verify_com_suite_inexistente(dataset: Path, tmp_path: Path) -> None:
    resultado = runner.invoke(
        app,
        ["suite", "verify", "v9.9", "--tarefas", str(dataset), "--destino", str(tmp_path)],
    )
    assert resultado.exit_code == 2


def test_verify_declara_suite_morta_por_errata(dataset: Path, tmp_path: Path) -> None:
    """Passando de 5% de errata, a suíte se encerra em vez de ser remendada."""
    suites = tmp_path / "suites"
    comum = ["--tarefas", str(dataset), "--destino", str(suites)]
    assert runner.invoke(app, ["suite", "freeze", "v0.1", *comum]).exit_code == 0

    alvo = next(dataset.glob("*-pt.yaml")).stem
    (suites / "v0.1.errata.yaml").write_text(
        yaml.safe_dump(
            {
                "suite_id": "v0.1",
                "revision": 1,
                "entries": [
                    {
                        "task_id": alvo,
                        "task_version": 1,
                        "date": "2026-09-14",
                        "defect": "gabarito ambiguo",
                        "test_ref": "tests/test_errata.py::test_repro",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    resultado = runner.invoke(app, ["suite", "verify", "v0.1", *comum])
    assert resultado.exit_code == 1


def test_comandos_ainda_nao_implementados_estouram_alto(tmp_path: Path) -> None:
    """Um stub tem que estourar, não devolver zero e mentir que rodou."""
    for args in (
        ["run", "--suite", "v0.1", "--agent", "x"],
        ["score", str(tmp_path)],
        ["report", str(tmp_path)],
    ):
        resultado = runner.invoke(app, args)
        assert resultado.exit_code != 0
        assert isinstance(resultado.exception, NotImplementedError)


def test_dataset_real_congela(raiz_do_repo: Path, tmp_path: Path) -> None:
    """Ensaio do congelamento da v0.1, sem tocar no repositório."""
    copia = tmp_path / "tasks"
    shutil.copytree(raiz_do_repo / "tasks", copia)
    resultado = runner.invoke(
        app,
        ["suite", "freeze", "ensaio", "--tarefas", str(copia), "--destino", str(tmp_path / "s")],
    )
    assert resultado.exit_code == 0, resultado.output
    assert "2 pares strict" in _saida(resultado)
