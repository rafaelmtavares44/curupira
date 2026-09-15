"""A etapa 2 de ponta a ponta: bruto -> pontuado, e a trava de hash.

O teste que mais importa aqui é `test_hash_divergente_recusa_pontuar`. Sem ele, o
Curupira pontuaria a resposta de uma pergunta com o gabarito de outra e o número
sairia com aparência perfeitamente normal — o pior desfecho possível para um
benchmark.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from curupira.core.enums import CamadaDePontuacao, ClasseDeFalha, Desfecho, Locale
from curupira.core.hashing import hash_da_tarefa
from curupira.core.registry import limpar_registro
from curupira.core.result import (
    ChamadaObservada,
    ExecucaoCrua,
    IdentidadeDoAgente,
    RespostaCrua,
)
from curupira.core.task import Tarefa
from curupira.formatos import registrar_validadores
from curupira.matchers import registrar_todos
from curupira.scoring.rodada import (
    COLUNAS,
    NOME_DO_PONTUADO,
    gravar_pontuado,
    para_dataframe,
    pontuar_execucao,
    pontuar_rodada,
)
from curupira.security import esquecer_segredos, registrar_segredo
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


def _execucao(tarefa: Tarefa, **overrides: Any) -> ExecucaoCrua:
    base: dict[str, Any] = {
        "task_id": tarefa.id,
        "task_version": tarefa.task_version,
        "task_hash": hash_da_tarefa(tarefa),
        "suite_id": "v-teste",
        "agent": AGENTE,
        "repetition": 0,
        "timestamp": datetime.now(UTC),
        "latency_ms": 12,
        "curupira_version": "0.1.0.dev0",
        "request_body": "{}",
        "raw": RespostaCrua(
            tool_calls=(
                ChamadaObservada(
                    name="criar_transferencia",
                    args={"valor_centavos": 123456, "favorecido": "Silva"},
                ),
            ),
            finish_reason="tool_use",
            prompt_tokens=10,
            completion_tokens=4,
        ),
    }
    base.update(overrides)
    return ExecucaoCrua(**base)


# --------------------------------------------------------------------------
# Uma execucao
# --------------------------------------------------------------------------


def test_pontua_um_acerto() -> None:
    tarefa = Tarefa.model_validate(tarefa_bruta())
    resultado = pontuar_execucao(_execucao(tarefa), tarefa)
    assert resultado.outcome is Desfecho.PASSOU
    assert resultado.failure_class is ClasseDeFalha.ACERTO_CONFIANTE
    assert resultado.scoring_layer is CamadaDePontuacao.AST
    assert resultado.silent_failure_label is None


def test_o_contexto_da_tarefa_viaja_com_o_resultado() -> None:
    """O agregador não pode ter de reconciliar contra um dataset que mudou."""
    tarefa = Tarefa.model_validate(par_strict("par-x")[0])
    resultado = pontuar_execucao(_execucao(tarefa), tarefa)
    assert resultado.track is tarefa.track
    assert resultado.locale is Locale.PT_BR
    assert resultado.pair_id == "par-x"
    assert resultado.parity is tarefa.parity


def test_rotula_a_falha_silenciosa() -> None:
    """Saber COMO errou é o que vira gráfico no artigo."""
    bruto = tarefa_bruta()
    bruto["expect"]["silent_failure_if"] = [
        {"arg": "valor_centavos", "equals": 123456000, "label": "leu_ponto_como_decimal"}
    ]
    tarefa = Tarefa.model_validate(bruto)
    resposta = RespostaCrua(
        text="Transferencia criada.",
        tool_calls=(
            ChamadaObservada(
                name="criar_transferencia",
                args={"valor_centavos": 123456000, "favorecido": "Silva"},
            ),
        ),
    )
    resultado = pontuar_execucao(_execucao(tarefa, raw=resposta), tarefa)
    assert resultado.outcome is Desfecho.FALHOU
    assert resultado.failure_class is ClasseDeFalha.FALHA_SILENCIOSA
    assert resultado.silent_failure_label == "leu_ponto_como_decimal"


def test_erro_de_infraestrutura_vira_nao_aplicavel() -> None:
    tarefa = Tarefa.model_validate(tarefa_bruta())
    execucao = _execucao(tarefa, raw=None, erro="anthropic: HTTP 529: overloaded")
    resultado = pontuar_execucao(execucao, tarefa)
    assert resultado.outcome is Desfecho.ERRO_DE_EXECUCAO
    assert resultado.failure_class is ClasseDeFalha.NAO_APLICAVEL
    assert "529" in resultado.motivo


def test_hash_divergente_recusa_pontuar() -> None:
    """A trava que impede comparar resposta de uma pergunta com gabarito de outra."""
    tarefa = Tarefa.model_validate(tarefa_bruta())
    execucao = _execucao(tarefa)
    editada = tarefa.model_copy(update={"difficulty": 5})
    with pytest.raises(ValueError, match="hash"):
        pontuar_execucao(execucao, editada)


def test_execucao_de_outra_tarefa_recusa() -> None:
    tarefa = Tarefa.model_validate(tarefa_bruta())
    outra = Tarefa.model_validate(tarefa_bruta(task_id="outra", canary="outra-canary-nao-treinar"))
    with pytest.raises(ValueError, match="pontuada contra"):
        pontuar_execucao(_execucao(tarefa), outra)


def test_rotulo_so_existe_em_tool_call() -> None:
    """`silent_failure_if` não existe em `no_tool_call`; o rotulador não inventa."""
    tarefa = Tarefa.model_validate(
        tarefa_bruta(expect={"kind": "no_tool_call", "rationale": "nao ha ferramenta"})
    )
    resultado = pontuar_execucao(_execucao(tarefa), tarefa)
    assert resultado.outcome is Desfecho.FALHOU
    assert resultado.silent_failure_label is None


# --------------------------------------------------------------------------
# A rodada inteira
# --------------------------------------------------------------------------


def test_pontua_a_rodada_na_ordem_do_bruto() -> None:
    tarefas = {b["id"]: Tarefa.model_validate(b) for b in par_strict("par-a")}
    execucoes = [_execucao(t) for t in tarefas.values()]
    resultados = pontuar_rodada(execucoes, tarefas)
    assert [r.task_id for r in resultados] == [e.task_id for e in execucoes]


def test_tarefa_sumida_recusa_a_rodada() -> None:
    tarefa = Tarefa.model_validate(tarefa_bruta())
    with pytest.raises(ValueError, match="sumiram do dataset"):
        pontuar_rodada([_execucao(tarefa)], {})


# --------------------------------------------------------------------------
# O parquet
# --------------------------------------------------------------------------


def test_parquet_tem_as_colunas_declaradas() -> None:
    tarefa = Tarefa.model_validate(tarefa_bruta())
    frame = para_dataframe(pontuar_rodada([_execucao(tarefa)], {tarefa.id: tarefa}))
    assert frame.columns == list(COLUNAS)


def test_o_agente_e_achatado_em_colunas() -> None:
    """Struct aninhado transformaria cada filtro do relatório numa expressão."""
    tarefa = Tarefa.model_validate(tarefa_bruta())
    frame = para_dataframe(pontuar_rodada([_execucao(tarefa)], {tarefa.id: tarefa}))
    assert frame["agent_id"][0] == "agente-de-teste"
    assert frame["seed_aplicada"][0] is False
    assert "agent" not in frame.columns


def test_o_bruto_nao_e_duplicado_no_parquet() -> None:
    """Fonte de verdade é o `raw.jsonl`; o parquet é derivado e descartável."""
    tarefa = Tarefa.model_validate(tarefa_bruta())
    frame = para_dataframe(pontuar_rodada([_execucao(tarefa)], {tarefa.id: tarefa}))
    assert "raw" not in frame.columns
    assert "request_body" not in frame.columns


def test_parquet_vazio_estoura() -> None:
    """Parquet sem linhas não tem esquema, e isso só apareceria no relatório."""
    with pytest.raises(ValueError, match="nao ha o que gravar"):
        para_dataframe([])


def test_grava_e_le_de_volta(tmp_path: Path) -> None:
    tarefas = {b["id"]: Tarefa.model_validate(b) for b in par_strict("par-a")}
    resultados = pontuar_rodada([_execucao(t) for t in tarefas.values()], tarefas)
    destino = gravar_pontuado(resultados, tmp_path / "rodada")

    assert destino.name == NOME_DO_PONTUADO
    relido = pl.read_parquet(destino)
    assert relido.height == 2
    assert set(relido["locale"]) == {"pt-BR", "en-US"}
    assert relido["outcome"].to_list() == ["passou", "passou"]


def test_o_motivo_gravado_passa_pela_redacao(tmp_path: Path) -> None:
    """O parquet é publicado junto com o leaderboard, e o motivo cita o modelo.

    É o único caminho por onde texto de terceiro chegaria a um artefato
    distribuído sem passar pela barreira 3.
    """
    segredo = "valor-secreto-que-o-modelo-ecoou"
    registrar_segredo(segredo)
    try:
        tarefa = Tarefa.model_validate(tarefa_bruta())
        resposta = RespostaCrua(
            tool_calls=(
                ChamadaObservada(
                    name="criar_transferencia",
                    args={"valor_centavos": 1, "favorecido": segredo},
                ),
            )
        )
        resultado = pontuar_execucao(_execucao(tarefa, raw=resposta), tarefa)
        assert segredo not in resultado.motivo
        assert "[REDIGIDO]" in resultado.motivo
        frame = para_dataframe([resultado])
        assert segredo not in str(frame["motivo"][0])
        gravar_pontuado([resultado], tmp_path / "r")
    finally:
        esquecer_segredos()
