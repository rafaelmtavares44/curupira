"""A CLI de ponta a ponta, no dataset real do repositório."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import polars as pl
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


def test_o_pipeline_inteiro_esta_na_ajuda() -> None:
    """Nenhum comando da v0.1 e mais um stub: as tres etapas existem."""
    saida = _saida(runner.invoke(app, ["--help"]))
    for comando in ("validate", "suite", "run", "score", "report"):
        assert comando in saida


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------


def _congelar(dataset: Path, suites: Path) -> list[str]:
    """Congela a suíte de teste e devolve as opções comuns de `run`."""
    congelar = runner.invoke(
        app, ["suite", "freeze", "v0.1", "--tarefas", str(dataset), "--destino", str(suites)]
    )
    assert congelar.exit_code == 0, congelar.output
    return ["--tarefas", str(dataset), "--destino", str(suites)]


def test_run_com_o_adaptador_falso(dataset: Path, tmp_path: Path) -> None:
    """Ensaio de ponta a ponta sem chave, sem rede e sem custo.

    É este caminho que o CI roda: um runner só exercitado contra a API de verdade
    é um runner testado em lugar nenhum.
    """
    suites = tmp_path / "suites"
    saida = tmp_path / "runs"
    comum = _congelar(dataset, suites)
    resultado = runner.invoke(
        app,
        [
            "run",
            "--suite",
            "v0.1",
            "--agent",
            "ensaio",
            "--modelo",
            "falso-1",
            "--provedor",
            "falso",
            "--repeticoes",
            "2",
            "--saida",
            str(saida),
            *comum,
        ],
    )
    assert resultado.exit_code == 0, resultado.output

    (rodada,) = list(saida.iterdir())
    linhas = (rodada / "raw.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 4
    assert all(json.loads(linha)["suite_id"] == "v0.1" for linha in linhas)

    registro = json.loads((rodada / "rodada.json").read_text(encoding="utf-8"))
    assert registro["execucoes"] == 4
    assert registro["erros"] == 0
    assert len(registro["suite_sha256"]) == 64


def test_run_com_cache_reaproveita(dataset: Path, tmp_path: Path) -> None:
    suites = tmp_path / "suites"
    comum = _congelar(dataset, suites)
    args = [
        "run",
        "--suite",
        "v0.1",
        "--agent",
        "ensaio",
        "--modelo",
        "falso-1",
        "--repeticoes",
        "1",
        "--cache",
        str(tmp_path / "cache"),
        "--saida",
        str(tmp_path / "runs"),
        *comum,
    ]
    assert runner.invoke(app, args).exit_code == 0
    segunda = runner.invoke(app, args)
    assert segunda.exit_code == 0, segunda.output
    assert "2 do cache" in _saida(segunda)


def test_run_avisa_quando_a_seed_nao_sera_aplicada(dataset: Path, tmp_path: Path) -> None:
    """Quem pede seed pede reprodutibilidade; se não vai ter, precisa saber."""
    comum = _congelar(dataset, tmp_path / "suites")
    resultado = runner.invoke(
        app,
        [
            "run",
            "--suite",
            "v0.1",
            "--agent",
            "x",
            "--modelo",
            "falso-1",
            "--seed",
            "7",
            "--repeticoes",
            "1",
            "--saida",
            str(tmp_path / "runs"),
            *comum,
        ],
    )
    assert resultado.exit_code == 0, resultado.output
    assert "nao aceita seed" not in _saida(resultado)


def test_run_com_provedor_que_ignora_seed_avisa(
    dataset: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CURUPIRA_ANTHROPIC_API_KEY", "chave-falsa-so-para-o-aviso")
    comum = _congelar(dataset, tmp_path / "suites")
    resultado = runner.invoke(
        app,
        [
            "run",
            "--suite",
            "v0.1",
            "--agent",
            "x",
            "--modelo",
            "m",
            "--provedor",
            "anthropic",
            "--seed",
            "7",
            "--repeticoes",
            "1",
            "--saida",
            str(tmp_path / "runs"),
            *comum,
        ],
    )
    # A rodada segue e falha nas chamadas (sem rede), mas o aviso tem que sair
    # ANTES — e sair junto com o resultado, nao no lugar dele.
    assert "nao aceita seed" in _saida(resultado)


def test_run_termina_em_1_quando_ha_erro_de_infraestrutura(
    dataset: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rodada com erro de provedor não pode sair 0 e parecer completa."""
    monkeypatch.setenv("CURUPIRA_ANTHROPIC_API_KEY", "chave-falsa-sem-rede-nenhuma")
    comum = _congelar(dataset, tmp_path / "suites")
    saida = tmp_path / "runs"
    resultado = runner.invoke(
        app,
        [
            "run",
            "--suite",
            "v0.1",
            "--agent",
            "x",
            "--modelo",
            "m",
            "--provedor",
            "anthropic",
            "--repeticoes",
            "1",
            "--saida",
            str(saida),
            *comum,
        ],
    )
    assert resultado.exit_code == 1
    (rodada,) = list(saida.iterdir())
    registro = json.loads((rodada / "rodada.json").read_text(encoding="utf-8"))
    assert registro["erros"] == 2
    assert registro["execucoes"] == 2


def test_run_recusa_suite_inexistente(dataset: Path, tmp_path: Path) -> None:
    resultado = runner.invoke(
        app,
        [
            "run",
            "--suite",
            "v9.9",
            "--agent",
            "x",
            "--modelo",
            "m",
            "--tarefas",
            str(dataset),
            "--destino",
            str(tmp_path),
        ],
    )
    assert resultado.exit_code == 2


def test_run_recusa_dataset_editado_em_silencio(dataset: Path, tmp_path: Path) -> None:
    """A rodada falha antes de gastar, em vez de produzir número errado."""
    suites = tmp_path / "suites"
    comum = _congelar(dataset, suites)

    alvo = next(dataset.glob("*-pt.yaml"))
    bruto = yaml.safe_load(alvo.read_text(encoding="utf-8"))
    bruto["difficulty"] = 5
    alvo.write_text(yaml.safe_dump(bruto, allow_unicode=True), encoding="utf-8")

    resultado = runner.invoke(
        app,
        [
            "run",
            "--suite",
            "v0.1",
            "--agent",
            "x",
            "--modelo",
            "m",
            "--saida",
            str(tmp_path / "runs"),
            *comum,
        ],
    )
    assert resultado.exit_code == 1
    assert "edicao silenciosa" in _saida(resultado)
    assert not (tmp_path / "runs").exists()


def test_run_sem_chave_para_antes_de_rodar(
    dataset: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem chave o comando para em 2, e nenhum diretório de rodada é criado."""
    monkeypatch.delenv("CURUPIRA_ANTHROPIC_API_KEY", raising=False)
    comum = _congelar(dataset, tmp_path / "suites")
    resultado = runner.invoke(
        app,
        [
            "run",
            "--suite",
            "v0.1",
            "--agent",
            "x",
            "--modelo",
            "m",
            "--provedor",
            "anthropic",
            "--saida",
            str(tmp_path / "runs"),
            *comum,
        ],
    )
    assert resultado.exit_code == 2
    assert "chave indisponivel" in _saida(resultado)
    assert not (tmp_path / "runs").exists()


def test_run_recusa_diretorio_de_tarefas_inexistente(tmp_path: Path, dataset: Path) -> None:
    comum = _congelar(dataset, tmp_path / "suites")
    del comum
    resultado = runner.invoke(
        app,
        [
            "run",
            "--suite",
            "v0.1",
            "--agent",
            "x",
            "--modelo",
            "m",
            "--tarefas",
            str(tmp_path / "nao-existe"),
            "--destino",
            str(tmp_path / "suites"),
        ],
    )
    assert resultado.exit_code == 2


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


# --------------------------------------------------------------------------
# score
# --------------------------------------------------------------------------


def _rodar(dataset: Path, tmp_path: Path, **extras: str) -> Path:
    """Congela, roda com o adaptador falso e devolve o diretório da rodada."""
    comum = _congelar(dataset, tmp_path / "suites")
    args = [
        "run",
        "--suite",
        "v0.1",
        "--agent",
        "ensaio",
        "--modelo",
        "falso-1",
        "--repeticoes",
        "1",
        "--saida",
        str(tmp_path / "runs"),
        *comum,
    ]
    for chave, valor in extras.items():
        args += [f"--{chave}", valor]
    resultado = runner.invoke(app, args)
    assert resultado.exit_code == 0, resultado.output
    (rodada,) = list((tmp_path / "runs").iterdir())
    return rodada


def test_score_de_ponta_a_ponta(dataset: Path, tmp_path: Path) -> None:
    """`run` e `score` são etapas separadas, e o score não fala com provedor."""
    rodada = _rodar(dataset, tmp_path)
    resultado = runner.invoke(app, ["score", str(rodada), "--tarefas", str(dataset)])
    assert resultado.exit_code == 0, resultado.output

    pontuado = rodada / "scored.parquet"
    assert pontuado.is_file()
    frame = pl.read_parquet(pontuado)
    assert frame.height == 2
    assert set(frame["locale"]) == {"pt-BR", "en-US"}
    assert (rodada / "raw.jsonl").is_file()


def test_score_e_reexecutavel(dataset: Path, tmp_path: Path) -> None:
    """É o que torna "guarde o bruto, agregue tarde" operacional, não slogan.

    Corrigir um matcher custa uma nova rodada deste comando — segundos — em vez
    de uma rodada paga.
    """
    rodada = _rodar(dataset, tmp_path)
    comum = ["score", str(rodada), "--tarefas", str(dataset)]
    assert runner.invoke(app, comum).exit_code == 0
    segunda = runner.invoke(app, comum)
    assert segunda.exit_code == 0, segunda.output
    assert pl.read_parquet(rodada / "scored.parquet").height == 2


def test_score_recusa_dataset_editado_depois_da_rodada(dataset: Path, tmp_path: Path) -> None:
    """O pior desfecho possível é um número errado que ninguém questiona."""
    rodada = _rodar(dataset, tmp_path)

    alvo = next(dataset.glob("*-pt.yaml"))
    bruto = yaml.safe_load(alvo.read_text(encoding="utf-8"))
    bruto["difficulty"] = 5
    alvo.write_text(yaml.safe_dump(bruto, allow_unicode=True), encoding="utf-8")

    resultado = runner.invoke(app, ["score", str(rodada), "--tarefas", str(dataset)])
    assert resultado.exit_code == 1
    assert "hash" in _saida(resultado)
    assert not (rodada / "scored.parquet").exists()


def test_score_sem_bruto_recusa(tmp_path: Path) -> None:
    vazio = tmp_path / "sem-rodada"
    vazio.mkdir()
    resultado = runner.invoke(app, ["score", str(vazio)])
    assert resultado.exit_code == 2
    assert "bruto nao encontrado" in _saida(resultado)


def test_score_recusa_dataset_inexistente(dataset: Path, tmp_path: Path) -> None:
    rodada = _rodar(dataset, tmp_path)
    resultado = runner.invoke(
        app, ["score", str(rodada), "--tarefas", str(tmp_path / "nao-existe")]
    )
    assert resultado.exit_code == 2


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------


def test_report_de_ponta_a_ponta(dataset: Path, tmp_path: Path) -> None:
    """As tres etapas encadeadas: run -> score -> report."""
    rodada = _rodar(dataset, tmp_path)
    assert runner.invoke(app, ["score", str(rodada), "--tarefas", str(dataset)]).exit_code == 0

    resultado = runner.invoke(app, ["report", str(rodada), "--tarefas", str(dataset)])
    assert resultado.exit_code == 0, resultado.output

    relatorio = json.loads((rodada / "report.json").read_text(encoding="utf-8"))
    assert relatorio["agent_id"] == "ensaio"
    assert relatorio["suite_id"] == "v0.1"
    assert set(relatorio["linhas_de_base"])


def test_report_sempre_imprime_as_linhas_de_base(dataset: Path, tmp_path: Path) -> None:
    """Obrigatorio: publicar a nota sem o trivial ao lado e enganoso."""
    rodada = _rodar(dataset, tmp_path)
    runner.invoke(app, ["score", str(rodada), "--tarefas", str(dataset)])
    saida = _saida(runner.invoke(app, ["report", str(rodada), "--tarefas", str(dataset)]))
    assert "Linhas de base triviais" in saida
    assert "nunca_chama" in saida


def test_report_recusa_rodada_nao_pontuada(dataset: Path, tmp_path: Path) -> None:
    rodada = _rodar(dataset, tmp_path)
    resultado = runner.invoke(app, ["report", str(rodada), "--tarefas", str(dataset)])
    assert resultado.exit_code == 2
    assert "nao pontuada" in _saida(resultado)


def test_report_declara_quando_nao_ha_delta(dataset: Path, tmp_path: Path) -> None:
    """O adaptador falso erra tudo, entao ha Delta; o que falta e par decidido."""
    rodada = _rodar(dataset, tmp_path)
    runner.invoke(app, ["score", str(rodada), "--tarefas", str(dataset)])
    saida = _saida(runner.invoke(app, ["report", str(rodada), "--tarefas", str(dataset)]))
    assert "Delta PT-BR" in saida


def test_report_com_errata_conta_a_exclusao(dataset: Path, tmp_path: Path) -> None:
    """A suite nao muda um byte; quem exclui e o agregador."""
    rodada = _rodar(dataset, tmp_path)
    runner.invoke(app, ["score", str(rodada), "--tarefas", str(dataset)])

    alvo = next(dataset.glob("*-pt.yaml")).stem
    errata = tmp_path / "errata.yaml"
    errata.write_text(
        yaml.safe_dump(
            {
                "suite_id": "v0.1",
                "revision": 1,
                "entries": [
                    {
                        "task_id": alvo,
                        "task_version": 1,
                        "date": "2026-09-15",
                        "defect": "gabarito ambiguo",
                        "test_ref": "tests/test_errata.py::test_repro",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    resultado = runner.invoke(
        app, ["report", str(rodada), "--tarefas", str(dataset), "--errata", str(errata)]
    )
    assert resultado.exit_code == 0, resultado.output
    saida = _saida(resultado)
    assert "excluida(s) pela errata" in saida
    assert "Delta PT-BR nao calculado" in saida
