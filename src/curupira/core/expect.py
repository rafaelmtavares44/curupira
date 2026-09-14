"""O bloco `expect` de uma tarefa: união discriminada por `kind`.

Emenda ao modelo original da Parte A: `expect.calls` virou `expect.accept`, um
**conjunto de alternativas aceitáveis**. Uma tarefa raramente tem uma única
resposta correta — consultar o favorecido antes de transferir também está certo,
e um checker que só conhece o caminho canônico reprova um agente competente.

O carregador aceita a forma curta (`calls:` direto) e promove a uma alternativa
única de id `canonica`. O hash de conteúdo é calculado sobre o modelo
**normalizado**, então as duas grafias hasheiam igual.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from curupira.core.enums import (
    OrdemDeChamadas,
    PoliticaDeArgumento,
    PoliticaDeArgumentoExtra,
)

_CFG = ConfigDict(extra="forbid", frozen=True)


class EspecificacaoDeArgumento(BaseModel):
    """Como um argumento é comparado.

    `matcher` é um **nome registrado** em `curupira.core.registry`, nunca lógica
    embutida no YAML. Se rodar o benchmark exigir `eval()`, o benchmark está
    errado.
    """

    model_config = _CFG

    matcher: str
    params: dict[str, JsonValue] = Field(default_factory=dict)
    policy: PoliticaDeArgumento = PoliticaDeArgumento.OBRIGATORIO


class ChamadaEsperada(BaseModel):
    """Uma chamada de ferramenta esperada, com os matchers de cada argumento."""

    model_config = _CFG

    name: str
    args: dict[str, JsonValue]
    arg_specs: dict[str, EspecificacaoDeArgumento] = Field(default_factory=dict)
    extra_args: PoliticaDeArgumentoExtra = PoliticaDeArgumentoExtra.REJEITAR


class Alternativa(BaseModel):
    """Um caminho inteiro considerado correto.

    `preference_rank` 0 é o caminho ideal; valores maiores são aceitáveis porém
    piores. O id da alternativa que casou é gravado no resultado: saber qual
    caminho cada agente prefere é produto, não log.
    """

    model_config = _CFG

    id: str
    calls: tuple[ChamadaEsperada, ...]
    call_order: OrdemDeChamadas = OrdemDeChamadas.QUALQUER
    rationale: str
    preference_rank: int = Field(default=0, ge=0)


class RegraDeFalhaSilenciosa(BaseModel):
    """Rótulo para um modo de erro específico e previsível.

    Isto **não é o detector de erro** — o matcher já detecta que errou. É o
    rotulador. Uma lista incompleta empobrece o diagnóstico; não corrompe a nota.
    O que não casar cai no balde `erro_nao_rotulado`.
    """

    model_config = _CFG

    arg: str
    equals: JsonValue
    label: str


class EsperaChamadaDeFerramenta(BaseModel):
    """T1, T2, T6: o agente deve chamar N ferramentas com os argumentos certos."""

    model_config = _CFG

    kind: Literal["tool_call"]
    accept: tuple[Alternativa, ...] = Field(min_length=1)
    silent_failure_if: tuple[RegraDeFalhaSilenciosa, ...] = ()


class EsperaNenhumaChamada(BaseModel):
    """T1: detecção de irrelevância. O agente sabe NÃO chamar?

    Atenção ao ler a nota desta espera isolada: uma política degenerada que nunca
    chama nada tira 100% aqui e 0% no resto. O relatório é obrigado a imprimir as
    linhas de base triviais ao lado (ver `curupira.report.baselines`).
    """

    model_config = _CFG

    kind: Literal["no_tool_call"]
    rationale: str


class EsperaEsclarecimento(BaseModel):
    """T4: quando falta informação, o agente pergunta ou inventa?

    `missing_slots` torna a expectativa verificável sem juiz na maior parte dos
    casos: chamar ferramenta é falha estrutural; não perguntar nada é falha
    estrutural; perguntar sobre o slot certo é casamento de palavra-chave. O juiz
    entra só no resíduo, e a fração que caiu no juiz é reportada.
    """

    model_config = _CFG

    kind: Literal["clarify"]
    missing_slots: tuple[str, ...] = Field(min_length=1)
    slot_keywords: dict[str, tuple[str, ...]] = Field(default_factory=dict)


class EsperaExtracao(BaseModel):
    """T2, T3: extrair valores, validados por validador nomeado."""

    model_config = _CFG

    kind: Literal["extraction"]
    fields: dict[str, EspecificacaoDeArgumento] = Field(min_length=1)
    expected: dict[str, JsonValue] = Field(default_factory=dict)


class EsperaRecusa(BaseModel):
    """T5: o agente recusa a instrução injetada.

    O sucesso do ataque é uma **ação observável**, não prosa: se alguma chamada de
    `forbidden_calls` acontecer, o ataque venceu. Concordância apenas verbal, sem
    ação, vai para a métrica separada `complacencia_verbal`.
    """

    model_config = _CFG

    kind: Literal["refusal"]
    forbidden_calls: tuple[str, ...] = Field(min_length=1)
    injection_label: str


class PassoDeSequencia(BaseModel):
    """Um passo de uma tarefa multi-turno."""

    model_config = _CFG

    call: ChamadaEsperada
    destructive: bool = False
    """Passo destrutivo exige turno de confirmação ANTES.

    Quem detecta é o harness, não um juiz: o usuário simulado só emite o turno
    seguinte se for perguntado, e o ambiente só libera a ferramenta destrutiva
    após a confirmação.
    """


class EsperaSequencia(BaseModel):
    """T6: executar passos em ordem, confirmando antes de ação destrutiva."""

    model_config = _CFG

    kind: Literal["sequence"]
    steps: tuple[PassoDeSequencia, ...] = Field(min_length=1)


Espera = Annotated[
    EsperaChamadaDeFerramenta
    | EsperaNenhumaChamada
    | EsperaEsclarecimento
    | EsperaExtracao
    | EsperaRecusa
    | EsperaSequencia,
    Field(discriminator="kind"),
]
"""União discriminada pelo campo `kind`.

Nada de schema único com trinta campos opcionais: o `kind` decide quais campos
existem, e o Pydantic recusa os que não pertencem àquele tipo.
"""
