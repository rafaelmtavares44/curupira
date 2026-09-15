"""A agregação: denominadores, Delta e linhas de base.

Quase todo teste aqui é sobre **denominador**. A acurácia é uma divisão, e num
benchmark cada forma de mentir é uma escolha errada de quem entra embaixo da
barra.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from curupira.core.enums import CamadaDePontuacao, ClasseDeFalha, Desfecho
from curupira.core.registry import limpar_registro
from curupira.core.result import IdentidadeDoAgente, ResultadoDeRodada
from curupira.core.suite import Errata
from curupira.core.task import Tarefa
from curupira.formatos import registrar_validadores
from curupira.matchers import registrar_todos
from curupira.report.aggregate import agregar, vetores_do_delta
from curupira.scoring.rodada import gravar_pontuado, para_dataframe
from tests.fabricas import par_strict, tarefa_bruta

AGENTE = IdentidadeDoAgente(
    agent_id="agente-de-teste",
    model="falso-1",
    adapter_version="0.1.0",
    prompt_template_id="cru-v1",
    temperature=0.0,
)


@pytest.fixture(autouse=True)
def _registro_pronto() -> Iterator[None]:
    limpar_registro()
    registrar_todos()
    registrar_validadores()
    yield
    limpar_registro()


def _resultado(tarefa: Tarefa, **overrides: Any) -> ResultadoDeRodada:
    base: dict[str, Any] = {
        "task_id": tarefa.id,
        "task_version": tarefa.task_version,
        "task_hash": "0" * 64,
        "suite_id": "v-teste",
        "track": tarefa.track,
        "locale": tarefa.locale,
        "parity": tarefa.parity,
        "pair_id": tarefa.pair_id,
        "variant_group": tarefa.variant_group,
        "agent": AGENTE,
        "repetition": 0,
        "timestamp": datetime.now(UTC),
        "latency_ms": 100,
        "curupira_version": "0.1.0.dev0",
        "outcome": Desfecho.PASSOU,
        "failure_class": ClasseDeFalha.ACERTO_CONFIANTE,
        "scoring_layer": CamadaDePontuacao.AST,
        "prompt_tokens": 10,
        "completion_tokens": 5,
    }
    base.update(overrides)
    return ResultadoDeRodada(**base)


def _par() -> tuple[Tarefa, Tarefa]:
    pt, en = par_strict("par-a")
    return Tarefa.model_validate(pt), Tarefa.model_validate(en)


def _gravar(resultados: list[ResultadoDeRodada], destino: Path) -> Path:
    return gravar_pontuado(resultados, destino)


# --------------------------------------------------------------------------
# Denominadores
# --------------------------------------------------------------------------


def test_erro_de_infraestrutura_sai_do_denominador(tmp_path: Path) -> None:
    """Um 529 favoreceria quem rodou num dia tranquilo."""
    pt, _ = _par()
    resultados = [
        _resultado(pt),
        _resultado(
            pt,
            repetition=1,
            outcome=Desfecho.ERRO_DE_EXECUCAO,
            failure_class=ClasseDeFalha.NAO_APLICAVEL,
        ),
    ]
    relatorio = agregar(_gravar(resultados, tmp_path / "r"), [pt])
    trilha = relatorio.por_trilha["t2_formats"]
    assert trilha.n_execucoes == 2
    assert trilha.n_decididas == 1
    assert trilha.acuracia == 1.0
    assert trilha.fracao_com_erro_de_infraestrutura == 0.5


def test_pendente_de_juiz_sai_do_denominador(tmp_path: Path) -> None:
    """Chutar enviesaria o Delta: o resíduo é maior num dos idiomas."""
    pt, _ = _par()
    resultados = [
        _resultado(pt),
        _resultado(
            pt,
            repetition=1,
            outcome=Desfecho.PENDENTE_DE_JUIZ,
            failure_class=ClasseDeFalha.NAO_APLICAVEL,
            scoring_layer=CamadaDePontuacao.JUIZ,
        ),
    ]
    trilha = agregar(_gravar(resultados, tmp_path / "r"), [pt]).por_trilha["t2_formats"]
    assert trilha.n_decididas == 1
    assert trilha.acuracia == 1.0
    assert trilha.fracao_pontuada_por_juiz == 0.5


def test_latencia_ignora_acerto_de_cache(tmp_path: Path) -> None:
    """Cache tem latência 0, e ela daria a impressão de um agente mais rápido."""
    pt, _ = _par()
    resultados = [
        _resultado(pt, latency_ms=900),
        _resultado(pt, repetition=1, latency_ms=0, do_cache=True),
        _resultado(pt, repetition=2, latency_ms=0, do_cache=True),
    ]
    trilha = agregar(_gravar(resultados, tmp_path / "r"), [pt]).por_trilha["t2_formats"]
    assert trilha.latencia_p50_ms == 900
    assert trilha.latencia_p95_ms == 900


# --------------------------------------------------------------------------
# Metricas de diagnostico
# --------------------------------------------------------------------------


def test_taxa_de_falha_silenciosa_e_a_rotulada(tmp_path: Path) -> None:
    pt, _ = _par()
    resultados = [
        _resultado(
            pt,
            outcome=Desfecho.FALHOU,
            failure_class=ClasseDeFalha.FALHA_SILENCIOSA,
            silent_failure_label="leu_ponto_como_decimal",
        ),
        _resultado(
            pt,
            repetition=1,
            outcome=Desfecho.FALHOU,
            failure_class=ClasseDeFalha.FALHA_SILENCIOSA,
            silent_failure_label="erro_nao_rotulado",
        ),
    ]
    trilha = agregar(_gravar(resultados, tmp_path / "r"), [pt]).por_trilha["t2_formats"]
    assert trilha.taxa_de_falha_silenciosa == 1.0
    assert trilha.taxa_de_falha_silenciosa_rotulada == 0.5


def test_instabilidade_pega_o_acerto_por_sorte(tmp_path: Path) -> None:
    """Um acerto que só acontece às vezes não é competência, é ruído."""
    pt, _ = _par()
    resultados = [
        _resultado(pt),
        _resultado(pt, repetition=1, outcome=Desfecho.FALHOU),
        _resultado(pt, repetition=2, outcome=Desfecho.FALHOU),
    ]
    trilha = agregar(_gravar(resultados, tmp_path / "r"), [pt]).por_trilha["t2_formats"]
    assert trilha.taxa_de_instabilidade == 1.0
    assert trilha.acuracia == pytest.approx(1 / 3)


def test_consistencia_de_grupo_e_none_sem_grupo(tmp_path: Path) -> None:
    """0.0 sugeriria falha em algo que nem foi medido."""
    pt, _ = _par()
    trilha = agregar(_gravar([_resultado(pt)], tmp_path / "r"), [pt]).por_trilha["t2_formats"]
    assert trilha.consistencia_de_grupo is None


def test_consistencia_de_grupo_exige_o_grupo_inteiro(tmp_path: Path) -> None:
    """Quem entende separador decimal acerta o grupo todo; quem casou padrão, não."""
    pt, _ = _par()
    resultados = [
        _resultado(pt, variant_group="g1"),
        _resultado(pt, repetition=1, variant_group="g1", outcome=Desfecho.FALHOU),
        _resultado(pt, variant_group="g2"),
    ]
    trilha = agregar(_gravar(resultados, tmp_path / "r"), [pt]).por_trilha["t2_formats"]
    assert trilha.consistencia_de_grupo == pytest.approx(0.5)


def test_custo_em_reais_fica_none_sem_tabela_de_precos(tmp_path: Path) -> None:
    """`None` não é lacuna: é a recusa de publicar valor monetário sem procedência."""
    pt, _ = _par()
    trilha = agregar(_gravar([_resultado(pt)], tmp_path / "r"), [pt]).por_trilha["t2_formats"]
    assert trilha.custo_por_acerto_brl is None
    assert trilha.tokens_por_acerto == pytest.approx(15.0)


def test_tokens_por_acerto_e_none_sem_acerto(tmp_path: Path) -> None:
    pt, _ = _par()
    resultado = _resultado(pt, outcome=Desfecho.FALHOU)
    trilha = agregar(_gravar([resultado], tmp_path / "r"), [pt]).por_trilha["t2_formats"]
    assert trilha.tokens_por_acerto is None


# --------------------------------------------------------------------------
# O subconjunto do Delta
# --------------------------------------------------------------------------


def test_delta_pareia_as_duas_versoes(tmp_path: Path) -> None:
    pt, en = _par()
    resultados = [_resultado(en), _resultado(pt, outcome=Desfecho.FALHOU)]
    relatorio = agregar(_gravar(resultados, tmp_path / "r"), [pt, en])
    assert relatorio.delta is not None
    assert relatorio.delta.n_pares == 1
    assert relatorio.delta.delta == pytest.approx(1.0)
    assert relatorio.delta.acuracia_en == 1.0
    assert relatorio.delta.acuracia_pt == 0.0


def test_o_par_com_uma_versao_no_juiz_sai_do_delta(tmp_path: Path) -> None:
    """Comparar EN e PT com denominadores diferentes é viés disfarçado de número.

    Este é o requisito que a Entrega 4 deixou plantado, e é o mais fácil de
    esquecer: o par parece completo, tem as duas versões no arquivo, e mesmo
    assim só uma delas foi decidida.
    """
    pt, en = _par()
    resultados = [
        _resultado(en),
        _resultado(
            pt,
            outcome=Desfecho.PENDENTE_DE_JUIZ,
            failure_class=ClasseDeFalha.NAO_APLICAVEL,
            scoring_layer=CamadaDePontuacao.JUIZ,
        ),
    ]
    relatorio = agregar(_gravar(resultados, tmp_path / "r"), [pt, en])
    assert relatorio.delta is None
    assert relatorio.motivo_sem_delta is not None


def test_o_par_nao_strict_sai_do_delta(tmp_path: Path) -> None:
    """Afrouxar isso daria um número maior e indefensável."""
    bruto_pt, bruto_en = par_strict("par-b")
    for bruto in (bruto_pt, bruto_en):
        bruto["parity"] = "localized"
        bruto["parity_notes"] = "adaptada culturalmente"
    pt, en = Tarefa.model_validate(bruto_pt), Tarefa.model_validate(bruto_en)
    resultados = [_resultado(en), _resultado(pt, outcome=Desfecho.FALHOU)]
    relatorio = agregar(_gravar(resultados, tmp_path / "r"), [pt, en])
    assert relatorio.delta is None


def test_a_tarefa_pontuada_por_juiz_nunca_entra_no_delta() -> None:
    """Um juiz em português degrada pela mesma razão que estamos medindo."""
    pt, en = _par()
    frame = para_dataframe(
        [
            _resultado(en, scoring_layer=CamadaDePontuacao.JUIZ),
            _resultado(pt, scoring_layer=CamadaDePontuacao.JUIZ),
        ]
    )
    vetor_en, vetor_pt, motivo = vetores_do_delta(frame)
    assert vetor_en == [] and vetor_pt == []
    assert motivo is not None


def test_delta_com_meio_par_no_arquivo(tmp_path: Path) -> None:
    pt, _ = _par()
    relatorio = agregar(_gravar([_resultado(pt)], tmp_path / "r"), [pt])
    assert relatorio.delta is None
    assert "duas versoes" in (relatorio.motivo_sem_delta or "")


# --------------------------------------------------------------------------
# Invariantes do relatorio
# --------------------------------------------------------------------------


def test_relatorio_recusa_misturar_agentes(tmp_path: Path) -> None:
    """Uma média entre agentes não é o Delta de nenhum deles."""
    pt, en = _par()
    outro = AGENTE.model_copy(update={"agent_id": "outro-agente"})
    resultados = [_resultado(pt), _resultado(en, agent=outro)]
    with pytest.raises(ValueError, match="mistura os agentes"):
        agregar(_gravar(resultados, tmp_path / "r"), [pt, en])


def test_relatorio_recusa_arquivo_vazio(tmp_path: Path) -> None:
    vazio = tmp_path / "vazio.parquet"
    pl.DataFrame({"agent_id": []}).write_parquet(vazio)
    with pytest.raises(ValueError, match="nenhuma execucao"):
        agregar(vazio, [])


def test_errata_exclui_a_tarefa_e_conta(tmp_path: Path) -> None:
    """A suíte não muda um byte; quem exclui é o agregador."""
    pt, en = _par()
    errata = Errata.model_validate(
        {
            "suite_id": "v-teste",
            "revision": 2,
            "entries": [
                {
                    "task_id": pt.id,
                    "task_version": 1,
                    "date": "2026-09-15",
                    "defect": "gabarito ambiguo",
                    "test_ref": "tests/test_errata.py::test_repro",
                }
            ],
        }
    )
    resultados = [_resultado(pt, outcome=Desfecho.FALHOU), _resultado(en)]
    relatorio = agregar(_gravar(resultados, tmp_path / "r"), [pt, en], errata=errata)
    assert relatorio.n_tarefas_com_errata == 1
    assert relatorio.errata_revision == 2
    assert relatorio.por_trilha["t2_formats"].n_decididas == 1
    assert relatorio.por_trilha["t2_formats"].acuracia == 1.0
    assert relatorio.delta is None


def test_linhas_de_base_saem_sempre(tmp_path: Path) -> None:
    """Publicar a nota sem a política trivial ao lado é enganoso por construção."""
    pt, en = _par()
    relatorio = agregar(_gravar([_resultado(pt), _resultado(en)], tmp_path / "r"), [pt, en])
    assert set(relatorio.linhas_de_base) == {
        "nunca_chama",
        "sempre_chama",
        "chama_a_primeira_ferramenta",
        "sempre_abstem",
    }
    assert relatorio.melhor_linha_de_base is not None


def test_avisa_quando_o_agente_nao_bate_o_trivial(tmp_path: Path) -> None:
    """Sem bater o trivial, não há competência demonstrada."""
    sem_chamada = Tarefa.model_validate(
        tarefa_bruta(expect={"kind": "no_tool_call", "rationale": "nao ha ferramenta"})
    )
    resultado = _resultado(sem_chamada, outcome=Desfecho.FALHOU)
    relatorio = agregar(_gravar([resultado], tmp_path / "r"), [sem_chamada])
    assert relatorio.nota_bate_a_linha_de_base is False


def test_grava_o_report_json(tmp_path: Path) -> None:
    pt, en = _par()
    destino = tmp_path / "report.json"
    agregar(_gravar([_resultado(pt), _resultado(en)], tmp_path / "r"), [pt, en], saida=destino)
    conteudo = json.loads(destino.read_text(encoding="utf-8"))
    assert conteudo["agent_id"] == "agente-de-teste"
    assert conteudo["delta"]["n_pares"] == 1


def test_delta_sem_nenhum_par_completo(tmp_path: Path) -> None:
    """Dois pares diferentes, cada um com so uma versao decidida."""
    pt_a, en_a = _par()
    en_b = Tarefa.model_validate(par_strict("par-b")[1])
    resultados = [
        _resultado(pt_a),
        _resultado(
            en_b,
            outcome=Desfecho.PENDENTE_DE_JUIZ,
            failure_class=ClasseDeFalha.NAO_APLICAVEL,
            scoring_layer=CamadaDePontuacao.JUIZ,
        ),
    ]
    relatorio = agregar(_gravar(resultados, tmp_path / "r"), [pt_a, en_a, en_b])
    assert relatorio.delta is None
    assert relatorio.motivo_sem_delta is not None


def test_a_linha_de_base_e_comparada_por_trilha(tmp_path: Path) -> None:
    """Media global esconde o que as linhas de base existem para expor.

    Uma politica degenerada gabarita UMA trilha e zera as outras — e essa a
    definicao dela. Comparar medias globais deixaria o agente compensar a trilha
    em que perde para o trivial com a trilha em que o trivial nem compete.
    """
    sem_chamada = Tarefa.model_validate(
        tarefa_bruta(expect={"kind": "no_tool_call", "rationale": "nao ha ferramenta"})
    )
    resultado = _resultado(sem_chamada, outcome=Desfecho.FALHOU)
    relatorio = agregar(_gravar([resultado], tmp_path / "r"), [sem_chamada])

    trilha = relatorio.por_trilha["t2_formats"]
    assert trilha.melhor_linha_de_base == "nunca_chama"
    assert trilha.linha_de_base == 1.0
    assert trilha.bate_a_linha_de_base is False


def test_empatar_com_o_trivial_nao_e_bater_o_trivial(tmp_path: Path) -> None:
    """A comparacao e estrita: empate nao demonstra competencia."""
    pt, _ = _par()
    relatorio = agregar(_gravar([_resultado(pt, outcome=Desfecho.FALHOU)], tmp_path / "r"), [pt])
    trilha = relatorio.por_trilha["t2_formats"]
    assert trilha.acuracia == 0.0
    assert trilha.linha_de_base == 0.0
    assert trilha.bate_a_linha_de_base is False


def test_bate_o_trivial_quando_acerta(tmp_path: Path) -> None:
    pt, _ = _par()
    relatorio = agregar(_gravar([_resultado(pt)], tmp_path / "r"), [pt])
    trilha = relatorio.por_trilha["t2_formats"]
    assert trilha.acuracia == 1.0
    assert trilha.bate_a_linha_de_base is True
    assert relatorio.nota_bate_a_linha_de_base is True
