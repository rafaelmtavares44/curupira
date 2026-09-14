"""O registro de uma rodada. Modelo fechado, de propósito.

`extra="forbid"` é barreira de segurança, não preciosismo: nenhum campo aqui é
capaz de guardar headers de requisição, e o modelo recusa qualquer tentativa de
enfiar um. É a barreira 4 das seis de SECURITY.md, e `tests/test_segredos.py`
prova que ela vale.

Sobre o desenho: este modelo guarda a **resposta crua**. Sem isso, rotular um
modo de falha novo, aplicar uma errata ou corrigir um matcher exigiria rerodar o
benchmark inteiro. Guarde o bruto, agregue tarde.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from curupira.core.enums import CamadaDePontuacao, ClasseDeFalha, Desfecho

_CFG = ConfigDict(extra="forbid", frozen=True)


class ChamadaObservada(BaseModel):
    """Uma chamada de ferramenta como o modelo a emitiu, sem normalização."""

    model_config = _CFG

    name: str
    args: dict[str, JsonValue]
    raw_arguments: str | None = None
    """O texto literal dos argumentos antes de qualquer parsing.

    Um modelo que devolve `"1.234,56"` onde se esperava inteiro erra de um jeito
    específico, e o jeito é o dado.
    """


class RespostaCrua(BaseModel):
    """A resposta do modelo, preservada para reprocessamento posterior."""

    model_config = _CFG

    text: str | None = None
    tool_calls: tuple[ChamadaObservada, ...] = ()
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class IdentidadeDoAgente(BaseModel):
    """O que está sendo pontuado.

    O Curupira é leaderboard de AGENTE, não de modelo: modelo + framework +
    prompt + ferramentas. Trocar CrewAI por LangGraph muda a nota, e essa
    informação é o produto.
    """

    model_config = _CFG

    agent_id: str
    model: str
    framework: str | None = None
    adapter_version: str
    prompt_template_id: str
    temperature: float
    seed: int | None = None


class ResultadoDeRodada(BaseModel):
    """O resultado de UMA repetição de UMA tarefa.

    A tupla de reprodutibilidade é o registro inteiro: suíte + hash da tarefa +
    identidade do agente + parâmetros de amostragem + data + custo + versão do
    curupira.
    """

    model_config = _CFG

    task_id: str
    task_version: int
    task_hash: str
    suite_id: str
    errata_revision: int = 0

    agent: IdentidadeDoAgente
    repetition: int = Field(ge=0)

    timestamp: datetime
    latency_ms: int = Field(ge=0)
    cost_brl: float = Field(default=0.0, ge=0.0)
    curupira_version: str

    outcome: Desfecho
    failure_class: ClasseDeFalha = ClasseDeFalha.NAO_APLICAVEL
    scoring_layer: CamadaDePontuacao

    matched_accept_id: str | None = None
    preference_rank: int | None = None
    silent_failure_label: str | None = None

    raw: RespostaCrua
