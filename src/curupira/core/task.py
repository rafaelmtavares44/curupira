"""O modelo de uma tarefa do Curupira."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from curupira.core.enums import Locale, Paridade, Split, Trilha
from curupira.core.expect import Espera

_CFG = ConfigDict(extra="forbid", frozen=True)


class DefinicaoDeFerramenta(BaseModel):
    """Uma ferramenta oferecida ao agente, em JSON Schema.

    A descrição em inglês com usuário falando português é caso de teste da T1, e
    não erro de autoria: é o cenário real de quem usa uma biblioteca gringa.
    """

    model_config = _CFG

    name: str
    description: str
    parameters: dict[str, JsonValue]


class ReferenciaDeDocumento(BaseModel):
    """Documento sintético anexado à tarefa (T3).

    `degradation` é eixo de medição, não enfeite: a curva acurácia por degradação
    sai de graça porque a sujeira é parametrizada e semeada.
    """

    model_config = _CFG

    path: str
    media_type: str
    degradation: int = Field(default=0, ge=0, le=3)


class ContextoDaTarefa(BaseModel):
    """O que o agente enxerga além da mensagem do usuário."""

    model_config = _CFG

    tools: tuple[DefinicaoDeFerramenta, ...] = ()
    documents: tuple[ReferenciaDeDocumento, ...] = ()
    system_prompt: str | None = None


class TurnoDeUsuario(BaseModel):
    """Um turno do usuário simulado, em tarefas multi-turno."""

    model_config = _CFG

    message: str
    depends_on_agent_question: bool = False
    """Se verdadeiro, o harness só emite este turno se o agente perguntar antes."""


class EntradaDaTarefa(BaseModel):
    """A entrada do agente."""

    model_config = _CFG

    user_message: str
    followup_turns: tuple[TurnoDeUsuario, ...] = ()


class Tarefa(BaseModel):
    """Uma tarefa do benchmark.

    Regras de integridade que o carregador e o lint do dataset impõem:

    - `parity: strict` exige `pair_id` preenchido e uma contraparte no outro
      idioma. Só esses pares entram no Delta PT-BR.
    - `generated_from` é sempre `pt-BR`: as tarefas nascem em português e o par
      em inglês é derivado delas. A regra do projeto vira dado auditável.
    - Mudou o conteúdo, sobe `task_version`. Nunca se edita tarefa em silêncio.
    """

    model_config = _CFG

    id: str
    schema_version: int = 1
    task_version: int = Field(default=1, ge=1)

    track: Trilha
    locale: Locale
    split: Split = Split.PUBLIC
    difficulty: int = Field(ge=1, le=5)
    tags: tuple[str, ...] = ()

    pair_id: str | None = None
    parity: Paridade
    parity_notes: str | None = None
    generated_from: Locale = Locale.PT_BR

    variant_group: str | None = None
    """Grupo de variantes próximas com gabaritos DIFERENTES.

    Detector de "acertou por sorte": quem entende separador decimal acerta o
    grupo inteiro; quem casou padrão acerta um subconjunto.

    **Escopado por locale.** O par EN de uma tarefa não pertence ao mesmo grupo
    que a versão PT-BR: um grupo mistura superfícies dentro de um idioma, não
    entre idiomas — isso é trabalho do `pair_id`. Por convenção, o grupo em
    inglês leva o sufixo `-en`. O lint recusa grupo com menos de dois membros no
    mesmo locale ou com gabaritos idênticos.
    """

    family_id: str | None = None
    """Molde de origem. É a unidade de reamostragem do bootstrap do Delta.

    Duas tarefas da mesma família não são observações independentes: quem
    entende o molde acerta as duas, quem não entende erra as duas. Tratá-las
    como independentes estreita o intervalo de confiança sem que nada avise —
    o erro que mais engana, porque produz um número mais bonito.

    **Escopado por PAR, não por locale.** As duas versões de um `pair_id`
    carregam a mesma família, e o lint recusa divergência. Aqui está a diferença
    para `variant_group`, que é escopado por locale: a unidade do Delta é o par,
    que atravessa os dois idiomas.

    Relação com `variant_group`: todo grupo de variantes está contido numa
    família — se duas tarefas são variantes próximas, elas vieram do mesmo
    molde. A recíproca é falsa: uma família pode reunir tarefas com o mesmo
    gabarito (várias de detecção de irrelevância, por exemplo), que o lint de
    `variant_group` recusaria. O lint cobra a contenção.

    `None` significa "família de um membro só". É aceito com aviso enquanto o
    dataset é piloto, e vira erro quando o piloto for autorado — ver ADR 0006.
    """

    canary_guid: str
    """GUID único, estilo BIG-bench. Pedido de exclusão do treino e detector de
    contaminação: se um modelo souber reproduzi-lo, o dataset vazou."""

    generator_version: str | None = None
    generator_seed: int | None = None
    """Sem estes dois, o dataset não é regenerável e o CI não pode conferir os
    hashes contra uma regeneração."""

    context: ContextoDaTarefa
    input: EntradaDaTarefa
    expect: Espera
