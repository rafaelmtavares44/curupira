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
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from curupira.core.enums import (
    CamadaDePontuacao,
    ClasseDeFalha,
    Desfecho,
    Locale,
    Paridade,
    Trilha,
)

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

    provider_fingerprint: str | None = None
    """Identificador do backend que atendeu a requisição, quando o provedor dá um.

    A OpenAI devolve `system_fingerprint` e declara o efeito da `seed` como
    *best-effort*: mesma seed, mesmo corpo, e ainda assim o resultado pode mudar
    se o backend mudou. O fingerprint é a **única evidência verificável** de que
    não mudou.

    Sem ele, dizer "a rodada usou seed" é promessa; com ele, é conferível — duas
    rodadas com o mesmo fingerprint e resultados diferentes são um achado, e com
    fingerprints diferentes não são comparáveis. É `None` em provedor que não
    expõe nada equivalente, e essa ausência também é informação.
    """


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

    seed_aplicada: bool = False
    """Se a seed foi **de fato** enviada ao provedor.

    A Messages API da Anthropic não tem parâmetro de seed. Sem este campo, a
    tupla de reprodutibilidade listaria uma seed que ninguém honrou — e alguém
    concluiria, com razão aparente, que a rodada é reproduzível bit a bit.
    `False` aqui significa: repita à vontade, mas o que você está medindo é
    não-determinismo do provedor, não uma amostragem fixada.
    """

    @model_validator(mode="after")
    def _seed_coerente(self) -> Self:
        """Recusa declarar seed aplicada sem seed.

        Returns:
            A própria identidade, validada.

        Raises:
            ValueError: se `seed_aplicada` for verdadeiro sem `seed`.
        """
        if self.seed_aplicada and self.seed is None:
            msg = "seed_aplicada=True sem seed: a tupla de reprodutibilidade mentiria"
            raise ValueError(msg)
        return self


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

    track: Trilha
    locale: Locale
    parity: Paridade
    pair_id: str | None = None
    variant_group: str | None = None
    family_id: str | None = None
    """O contexto da tarefa viaja junto com o resultado, e não por conveniência.

    O Delta PT-BR pareia por `pair_id` e filtra por `parity`; a consistência de
    grupo agrupa por `variant_group`; o bootstrap reamostra `family_id`. Se
    esses campos ficassem só no dataset, o
    agregador teria de recarregá-lo e reconciliar — e reconciliar contra um
    dataset que mudou desde a rodada é exatamente o erro silencioso que a suíte
    congelada existe para impedir. Aqui eles são um retrato do que valia quando a
    resposta foi produzida.
    """

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
    motivo: str = ""
    """Por que falhou, em texto. Diagnóstico, não nota."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    do_cache: bool = False

    raw: RespostaCrua | None = None
    """A resposta crua **não** é copiada para cá pelo `curupira score`.

    Ela já está em `raw.jsonl`, que é a fonte de verdade e nunca é reescrito.
    Duplicá-la no arquivo pontuado criaria duas cópias que podem divergir — e a
    que divergiria é a derivada, que é justamente a que se regenera de graça.
    O campo existe para quem quiser montar o resultado completo em memória.
    """


class ExecucaoCrua(BaseModel):
    """Uma linha de `raw.jsonl`: o que a etapa 1 produz, antes de pontuar.

    Separado de `ResultadoDeRodada` de propósito. Esta etapa **não sabe** se o
    agente acertou, e não deve saber: misturar execução e pontuação num modelo só
    convidaria a pontuar durante a rodada, que é exatamente o que "guarde o
    bruto, agregue tarde" proíbe. Trocar um matcher depois exigiria pagar a API
    outra vez.

    `request_body` é o corpo literal enviado, sem headers. É o que permite a um
    terceiro conferir que a tarefa chegou ao modelo do jeito que o dataset
    declara — e, com `curupira score`, refazer a nota sem tocar no provedor.
    """

    model_config = _CFG

    task_id: str
    task_version: int
    task_hash: str
    suite_id: str

    agent: IdentidadeDoAgente
    repetition: int = Field(ge=0)

    timestamp: datetime
    latency_ms: int = Field(ge=0)
    cost_brl: float = Field(default=0.0, ge=0.0)
    """Sempre 0.0 nesta etapa, de propósito.

    Converter token em real exige uma tabela de preços que muda sem aviso e uma
    cotação do dólar com data. Inventar qualquer um dos dois produziria um
    "custo por acerto" com aparência de medição. Os tokens ficam gravados em
    `raw`; o custo é calculado no relatório, a partir de uma tabela declarada e
    datada.
    """

    curupira_version: str
    request_body: str
    do_cache: bool = False

    raw: RespostaCrua | None = None
    erro: str | None = None
    """Mensagem de falha de infraestrutura, já redigida.

    Presente exclui `raw`. O agregador trata estas linhas como
    `Desfecho.ERRO_DE_EXECUCAO`: um 529 do provedor não é erro do agente, e
    contá-lo como erro do agente favoreceria quem rodou num dia tranquilo.
    """

    @model_validator(mode="after")
    def _resposta_ou_erro(self) -> Self:
        """Exige exatamente um entre resposta e erro.

        Returns:
            A própria execução, validada.

        Raises:
            ValueError: se vierem os dois ou nenhum.
        """
        if (self.raw is None) == (self.erro is None):
            msg = "ExecucaoCrua precisa de exatamente um entre `raw` e `erro`"
            raise ValueError(msg)
        return self


class RegistroDaRodada(BaseModel):
    """O cabeçalho de uma rodada: a tupla de reprodutibilidade, num arquivo só.

    Gravado ao lado do `raw.jsonl`. Sem ele, um `raw.jsonl` é um monte de
    respostas sem procedência — e comparar duas rodadas viraria adivinhação.
    """

    model_config = _CFG

    suite_id: str
    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    """Hash do **arquivo** da suíte, não das tarefas.

    As tarefas já têm hash individual dentro da suíte. Este aqui pega o caso em
    que alguém edita o próprio arquivo congelado — trocar uma entrada por outra
    manteria cada hash de tarefa válido e mesmo assim mudaria a suíte.
    """

    agent: IdentidadeDoAgente
    repeticoes: int = Field(ge=1)
    max_tokens: int = Field(ge=1)
    concorrencia: int = Field(ge=1)

    iniciada_em: datetime
    terminada_em: datetime
    curupira_version: str
    python_version: str

    tarefas: int = Field(ge=1)
    execucoes: int = Field(ge=0)
    erros: int = Field(default=0, ge=0)
    acertos_de_cache: int = Field(default=0, ge=0)
