"""A CLI de ponta a ponta, no dataset real do repositório."""

from __future__ import annotations

import importlib
import io
import json
import pkgutil
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import polars as pl
import pytest
import yaml
from rich.console import Console
from typer.testing import CliRunner

import curupira.adapters
from curupira.cli import (
    VARIAVEL_DA_CHAVE,
    Provedor,
    _adaptador,
    _avisar_sobre_infraestrutura,
    _pct,
    _tabela_das_trilhas,
    app,
)
from curupira.core.enums import Paridade, Trilha
from curupira.core.loader import carregar_diretorio
from curupira.core.registry import limpar_registro
from curupira.report.aggregate import MetricasDaTrilha, RelatorioDaRodada
from tests.fabricas import par_strict, tarefa_bruta

runner = CliRunner()
RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent


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


@pytest.fixture
def dataset_grande(tmp_path: Path) -> Path:
    """Dez tarefas soltas, para o teto da errata sair do piso absoluto."""
    raiz = tmp_path / "tasks-grande"
    raiz.mkdir()
    for indice in range(10):
        bruto = tarefa_bruta(
            task_id=f"g{indice:03d}",
            canary=f"g{indice:03d}-curupira-nao-treinar",
            valor=indice + 1,
        )
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


def _gravar_errata(suites: Path, *ids: str) -> None:
    """Escreve uma errata com uma entrada por id.

    Args:
        suites: o diretório das suítes.
        ids: as tarefas defeituosas.
    """
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
                    for alvo in ids
                ],
            }
        ),
        encoding="utf-8",
    )


def test_uma_errata_nao_mata_uma_suite_pequena(dataset: Path, tmp_path: Path) -> None:
    """O comportamento que a ADR 0008 corrige.

    Antes do piso absoluto, 5% de duas tarefas era 0,1 — e a primeira errata
    matava a suíte. O mecanismo desenhado para evitar recongelamento virava a
    razão para recongelar.
    """
    suites = tmp_path / "suites"
    comum = ["--tarefas", str(dataset), "--destino", str(suites)]
    assert runner.invoke(app, ["suite", "freeze", "v0.1", *comum]).exit_code == 0

    _gravar_errata(suites, next(dataset.glob("*-pt.yaml")).stem)

    assert runner.invoke(app, ["suite", "verify", "v0.1", *comum]).exit_code == 0


def test_verify_declara_suite_morta_acima_do_tolerado(dataset_grande: Path, tmp_path: Path) -> None:
    """Passando do tolerado, a suíte se encerra em vez de ser remendada.

    Sem esse limite, errata vira edição silenciosa com outro nome.
    """
    suites = tmp_path / "suites"
    comum = ["--tarefas", str(dataset_grande), "--destino", str(suites)]
    assert runner.invoke(app, ["suite", "freeze", "v0.1", *comum]).exit_code == 0

    _gravar_errata(suites, "g000", "g001", "g002")

    resultado = runner.invoke(app, ["suite", "verify", "v0.1", *comum])
    assert resultado.exit_code == 1
    assert "morta" in _saida(resultado)


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
    """Ensaio do congelamento do dataset real, sem tocar no repositório.

    O número esperado é **derivado do dataset**, não escrito à mão. A versão
    anterior cravava `"2 pares strict"` e reprovou no dia em que a família
    `data-ambigua` entrou — um teste que quebra porque o dataset cresceu não
    mede nada, só cobra pedágio, e ensina a editar o teste por reflexo. O que
    vale conferir é que a contagem impressa pela CLI é a mesma que sai dos
    arquivos.
    """
    copia = tmp_path / "tasks"
    shutil.copytree(raiz_do_repo / "tasks", copia)

    tarefas = list(carregar_diretorio(copia))
    strict = {t.pair_id for t in tarefas if t.parity is Paridade.STRICT and t.pair_id}
    assert strict, "o dataset real precisa ter ao menos um par strict"

    resultado = runner.invoke(
        app,
        ["suite", "freeze", "ensaio", "--tarefas", str(copia), "--destino", str(tmp_path / "s")],
    )

    assert resultado.exit_code == 0, resultado.output
    assert f"{len(strict)} pares strict" in _saida(resultado)


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


# --------------------------------------------------------------------------
# A tela nao pode mentir onde o JSON ja diz a verdade (achado da Entrega 9)
# --------------------------------------------------------------------------


def test_pct_distingue_zero_de_ausencia_de_medicao() -> None:
    """`0.0%` é uma nota; `—` é a falta dela.

    Este teste é minúsculo e é o coração do achado da Entrega 9: enquanto as
    duas coisas imprimiram igual, uma rodada 100% quebrada por chave inválida se
    parecia, na tela, com um agente que errou tudo.
    """
    assert _pct(0.0) == "0.0%"
    assert _pct(None) == "—"
    assert _pct(1.0) == "100.0%"


def _relatorio_quebrado(fracao: float) -> RelatorioDaRodada:
    """Um relatório com a fração de erro de infraestrutura que se quer testar."""
    return RelatorioDaRodada(
        suite_id="v0.1",
        agent_id="agente",
        errata_revision=0,
        n_tarefas_com_errata=0,
        por_trilha={
            "t2_formats": MetricasDaTrilha(
                trilha=Trilha.T2_FORMATOS,
                n_tarefas=2,
                n_execucoes=4,
                n_decididas=0,
                acuracia=None,
                taxa_de_falha_silenciosa=None,
                taxa_de_falha_silenciosa_rotulada=0.0,
                taxa_de_abstencao_indevida=None,
                taxa_de_instabilidade=None,
                latencia_p50_ms=0,
                latencia_p95_ms=0,
                fracao_pontuada_por_juiz=0.0,
                fracao_com_erro_de_infraestrutura=fracao,
            )
        },
    )


def test_a_tabela_mostra_travessao_em_vez_de_zero_sem_medicao() -> None:
    """A coluna de acurácia de uma trilha sem execução decidida sai vazia."""
    tabela = _tabela_das_trilhas(_relatorio_quebrado(1.0))
    console_de_teste = Console(file=io.StringIO(), width=200)
    console_de_teste.print(tabela)
    texto = console_de_teste.file.getvalue()  # type: ignore[attr-defined]

    assert "erro infra" in texto
    assert "100.0%" in texto
    assert "—" in texto


def test_o_aviso_de_infraestrutura_grita_acima_do_limiar(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Uma rodada comprometida tem de dizer que está comprometida.

    Sem isto, o leitor recebe uma tabela de travessões e nenhuma explicação — e
    a explicação é justamente a informação mais útil daquela rodada.
    """
    _avisar_sobre_infraestrutura(_relatorio_quebrado(1.0))
    saida = capsys.readouterr()
    assert "ATENCAO" in saida.err
    assert "NAO e desempenho do agente" in saida.err


def test_rodada_saudavel_nao_recebe_aviso(capsys: pytest.CaptureFixture[str]) -> None:
    """O aviso tem de ser raro, senão vira ruído que ninguém lê."""
    _avisar_sobre_infraestrutura(_relatorio_quebrado(0.0))
    assert not capsys.readouterr().err


# --------------------------------------------------------------------------
# Nenhum adaptador fica órfão
# --------------------------------------------------------------------------

ADAPTADORES_FORA_DO_CLI = {
    "AdaptadorGoogle": (
        "ADR 0004: o Gemini tem duas APIs vigentes (generateContent e "
        "Interactions) e a escolha entre elas ainda nao foi feita. Os dois "
        "metodos sao stubs que estouram NotImplementedError; expo-los na linha "
        "de comando entregaria uma opcao que quebra."
    ),
}
"""Adaptadores implementados que **de propósito** não aparecem no `--provedor`.

Estar aqui exige um motivo escrito. É a diferença entre uma decisão e um
esquecimento — e foi um esquecimento que deixou o adaptador da OpenAI testado,
coberto e inalcançável entre as Entregas 8 e 12.
"""


def _adaptadores_implementados() -> dict[str, type]:
    """Descobre toda classe de adaptador do pacote.

    Returns:
        Mapa de nome da classe para a classe, varrendo `curupira.adapters`.
    """
    encontrados: dict[str, type] = {}
    for info in pkgutil.iter_modules(curupira.adapters.__path__):
        modulo = importlib.import_module(f"curupira.adapters.{info.name}")
        for nome, objeto in vars(modulo).items():
            if not nome.startswith("Adaptador") or not isinstance(objeto, type):
                continue
            if getattr(objeto, "__module__", None) != modulo.__name__:
                continue
            # `_is_protocol` e como o proprio `typing` marca um Protocol. O
            # contrato `AdaptadorDeModelo` nao e uma implementacao e nao tem o
            # que ser alcancado pelo `--provedor`.
            if getattr(objeto, "_is_protocol", False):
                continue
            encontrados[nome] = objeto
    return encontrados


def _adaptadores_alcancaveis() -> set[str]:
    """Nomes das classes que o `--provedor` consegue instanciar.

    Returns:
        Os nomes de classe, um por valor do enum.
    """
    return {type(_adaptador(p)).__name__ for p in Provedor}


def test_nenhum_adaptador_fica_inalcancavel_pela_linha_de_comando() -> None:
    """Adaptador que o `--provedor` não alcança é código que não faz nada.

    Este teste nasce de um defeito real: o `AdaptadorOpenAI` foi escrito na
    Entrega 8, com ADR, testes e cobertura — e ficou fora do enum `Provedor`.
    Passou por ruff, mypy, bandit, 820 testes e cinco rodadas de CI sem que nada
    apontasse, porque **nenhum teste ligava as duas pontas**. Só apareceu quando
    alguém perguntou como se usa o sistema.

    Sair da linha de comando continua sendo permitido. O que não é permitido é
    sair sem dizer por quê.
    """
    implementados = set(_adaptadores_implementados())
    alcancaveis = _adaptadores_alcancaveis()
    declarados_fora = set(ADAPTADORES_FORA_DO_CLI)

    orfaos = implementados - alcancaveis - declarados_fora
    assert not orfaos, (
        f"adaptadores implementados e inalcancaveis pelo --provedor: {sorted(orfaos)}. "
        "Acrescente ao enum Provedor e a _adaptador, ou declare em "
        "ADAPTADORES_FORA_DO_CLI com o motivo."
    )


def test_a_lista_de_excecoes_nao_guarda_adaptador_que_ja_entrou() -> None:
    """A exceção tem de morrer quando deixa de ser exceção.

    Sem isto, `ADAPTADORES_FORA_DO_CLI` viraria um cemitério: nomes de
    adaptadores que já foram plugados continuariam listados como "de propósito
    fora", e a lista deixaria de significar alguma coisa.
    """
    ja_entraram = set(ADAPTADORES_FORA_DO_CLI) & _adaptadores_alcancaveis()
    assert not ja_entraram, (
        f"{sorted(ja_entraram)} esta no --provedor E na lista de excecoes. Remova da lista."
    )


def test_a_lista_de_excecoes_nao_guarda_adaptador_que_nao_existe() -> None:
    """Adaptador apagado não pode deixar uma justificativa órfã para trás."""
    fantasmas = set(ADAPTADORES_FORA_DO_CLI) - set(_adaptadores_implementados())
    assert not fantasmas, f"{sorted(fantasmas)} nao existe mais; remova da lista de excecoes"


def test_todo_provedor_com_rede_declara_de_onde_sai_a_chave() -> None:
    """Provedor que chama API e não declara variável usaria chave vazia.

    O sintoma seria um 401 em toda a rodada — barato, mas confuso. O `falso` é a
    exceção legítima: não tem rede e não tem chave.
    """
    sem_chave = {p.value for p in Provedor} - set(VARIAVEL_DA_CHAVE) - {Provedor.FALSO.value}
    assert not sem_chave, f"{sorted(sem_chave)} chamam API e nao tem variavel em VARIAVEL_DA_CHAVE"


def test_a_chave_de_cada_provedor_tem_o_prefixo_do_projeto() -> None:
    """`CURUPIRA_` de propósito: não reaproveitamos a chave da sessão do dev.

    Quem roda o benchmark declara, num gesto explícito, qual chave vai ser gasta.
    """
    for provedor, variavel in sorted(VARIAVEL_DA_CHAVE.items()):
        assert variavel.startswith("CURUPIRA_"), f"{provedor}: {variavel}"


# --------------------------------------------------------------------------
# `curupira errata add` — o caminho certo, com menos atrito que o errado
# --------------------------------------------------------------------------

TESTE_QUE_EXISTE = "tests/test_cli.py::test_ajuda_lista_os_comandos"


@pytest.fixture
def congelado(dataset: Path, tmp_path: Path) -> Path:
    """Congela a v0.1 sobre o dataset de teste e devolve o diretório das suítes."""
    suites = tmp_path / "suites"
    comum = ["--tarefas", str(dataset), "--destino", str(suites)]
    assert runner.invoke(app, ["suite", "freeze", "v0.1", *comum]).exit_code == 0
    return suites


def _errata_add(dataset: Path, suites: Path, **opcoes: str) -> Any:
    """Chama `errata add` com os caminhos de teste já preenchidos.

    O retorno é o `Result` do click, que não tem stubs de tipo publicados. O
    resto do arquivo usa `runner.invoke` sem anotação e o mypy infere; aqui a
    anotação é obrigatória, e `Any` é o que o projeto já permite em testes.
    """
    argumentos = [
        "errata",
        "add",
        "v0.1",
        "--tarefas",
        str(dataset),
        "--destino",
        str(suites),
        "--raiz",
        str(RAIZ_DO_PROJETO),
    ]
    for chave, valor in opcoes.items():
        argumentos += [f"--{chave.replace('_', '-')}", valor]
    return runner.invoke(app, argumentos)


def test_errata_add_grava_e_sobe_a_revisao(dataset: Path, congelado: Path) -> None:
    """O caminho feliz: uma tarefa defeituosa sai do agregado sem tocar na suíte."""
    alvo = next(dataset.glob("*-pt.yaml")).stem

    resultado = _errata_add(
        dataset, congelado, tarefa=alvo, defeito="gabarito ambiguo", teste=TESTE_QUE_EXISTE
    )

    assert resultado.exit_code == 0, resultado.output
    gravada = yaml.safe_load((congelado / "v0.1.errata.yaml").read_text(encoding="utf-8"))
    assert gravada["revision"] == 1
    assert gravada["entries"][0]["task_id"] == alvo
    assert gravada["entries"][0]["test_ref"] == TESTE_QUE_EXISTE


def test_errata_recusa_teste_que_nao_existe(dataset: Path, congelado: Path) -> None:
    """A trava que faltava: `test_ref` era texto livre que ninguém conferia.

    Sem esta checagem, "errata exige defeito demonstrável" era uma frase no
    docstring, não uma garantia — e nada separava um gabarito errado de um
    modelo que foi mal.
    """
    alvo = next(dataset.glob("*-pt.yaml")).stem

    resultado = _errata_add(
        dataset,
        congelado,
        tarefa=alvo,
        defeito="gabarito ambiguo",
        teste="tests/test_que_nunca_existiu.py::test_x",
    )

    assert resultado.exit_code != 0
    assert not (congelado / "v0.1.errata.yaml").exists()


def test_errata_recusa_tarefa_fora_da_suite(dataset: Path, congelado: Path) -> None:
    """Errata é sobre o que está congelado; o resto se corrige editando."""
    resultado = _errata_add(
        dataset, congelado, tarefa="nao-congelada-0001", defeito="x", teste=TESTE_QUE_EXISTE
    )
    assert resultado.exit_code != 0


def test_errata_e_append_only(dataset: Path, congelado: Path) -> None:
    """Repetir uma entrada esconderia qual dos dois defeitos vale."""
    alvo = next(dataset.glob("*-pt.yaml")).stem
    comum = {"tarefa": alvo, "teste": TESTE_QUE_EXISTE}

    assert _errata_add(dataset, congelado, defeito="primeiro", **comum).exit_code == 0
    repetida = _errata_add(dataset, congelado, defeito="segundo", **comum)

    assert repetida.exit_code != 0
    assert "append-only" in _saida(repetida)


def test_errata_recusa_substituta_inexistente(dataset: Path, congelado: Path) -> None:
    """A correção é uma tarefa NOVA: ela precisa existir antes da errata."""
    alvo = next(dataset.glob("*-pt.yaml")).stem

    resultado = _errata_add(
        dataset,
        congelado,
        tarefa=alvo,
        defeito="x",
        teste=TESTE_QUE_EXISTE,
        substituida_por="tarefa-que-ninguem-escreveu",
    )

    assert resultado.exit_code != 0


def test_errata_avisa_quando_a_suite_morre(dataset_grande: Path, tmp_path: Path) -> None:
    """Passando do tolerado, o comando falha e manda cortar a próxima suíte."""
    suites = tmp_path / "suites"
    comum = ["--tarefas", str(dataset_grande), "--destino", str(suites)]
    assert runner.invoke(app, ["suite", "freeze", "v0.1", *comum]).exit_code == 0

    for indice in range(3):
        resultado = _errata_add(
            dataset_grande,
            suites,
            tarefa=f"g{indice:03d}",
            defeito="gabarito errado",
            teste=TESTE_QUE_EXISTE,
        )

    assert resultado.exit_code != 0
    assert "MORTA" in _saida(resultado)


def test_errata_show_sem_errata_nao_e_erro(congelado: Path) -> None:
    """Suíte sem errata é o estado normal, e o comando precisa dizer isso."""
    resultado = runner.invoke(app, ["errata", "show", "v0.1", "--destino", str(congelado)])
    assert resultado.exit_code == 0
    assert "nao tem errata" in _saida(resultado)


def test_errata_show_lista_o_que_foi_marcado(dataset: Path, congelado: Path) -> None:
    alvo = next(dataset.glob("*-pt.yaml")).stem
    assert (
        _errata_add(
            dataset, congelado, tarefa=alvo, defeito="gabarito ambiguo", teste=TESTE_QUE_EXISTE
        ).exit_code
        == 0
    )

    resultado = runner.invoke(app, ["errata", "show", "v0.1", "--destino", str(congelado)])

    assert resultado.exit_code == 0
    assert "revisao 1" in _saida(resultado)
