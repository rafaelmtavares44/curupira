"""Toda tarefa do dataset é passável pelo próprio gabarito.

Por que isto existe
-------------------
O lint confere que a tarefa está **bem formada**: matcher registrado, régua igual
dos dois lados do par, `enum` do esclarecimento coerente. Ele não confere que a
tarefa é **acertável**. Uma régua apertada demais, um matcher que não aceita o
próprio valor de referência, um `one_of` mal declarado — qualquer um deles faz a
tarefa reprovar todo agente, e o defeito só apareceria depois de uma rodada paga,
disfarçado de "o modelo foi mal".

E o simétrico: um rótulo de `silent_failure_if` cujo valor **passa** no matcher
nunca rotula nada, porque rótulo só se aplica a erro. O diagnóstico — o gráfico
do artigo — sairia vazio sem ninguém saber por quê.

Este módulo roda o pontuador contra cada tarefa real com duas respostas
fabricadas:

- **a resposta do gabarito**, montada a partir do próprio `expect`. Tem de passar;
- **cada erro rotulado**, montado a partir de cada regra de `silent_failure_if`.
  Tem de reprovar **e** receber o rótulo declarado.

É genérico de propósito: vale para as tarefas que ainda vão entrar, sem que
ninguém precise lembrar de escrever o teste delas.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import JsonValue

from curupira.core.enums import Desfecho
from curupira.core.expect import (
    ChamadaEsperada,
    EsperaChamadaDeFerramenta,
    EsperaEsclarecimento,
    EsperaNenhumaChamada,
    RegraDeFalhaSilenciosa,
)
from curupira.core.loader import FERRAMENTAS_DE_ABSTENCAO, carregar_diretorio
from curupira.core.registry import limpar_registro
from curupira.core.result import ChamadaObservada, RespostaCrua
from curupira.core.task import Tarefa
from curupira.formatos import registrar_validadores
from curupira.matchers import registrar_todos
from curupira.scoring.pontuador import pontuar
from curupira.scoring.silent_failure import rotular

RAIZ = Path(__file__).resolve().parent.parent
TAREFAS = sorted(carregar_diretorio(RAIZ / "tasks"), key=lambda t: t.id)

KINDS_COBERTOS = frozenset({"tool_call", "no_tool_call", "clarify"})
"""Os `kind` que este módulo sabe exercitar.

Um `kind` novo no dataset reprova `test_todo_kind_do_dataset_e_exercitado` até
alguém ensinar este módulo a montar o gabarito dele. Sem isso, a tarefa nova
passaria por aqui sem ser testada — e o teste daria verde mentindo.
"""


@pytest.fixture(autouse=True)
def _registro_pronto() -> Iterator[None]:
    limpar_registro()
    registrar_todos()
    registrar_validadores()
    yield
    limpar_registro()


def _observada(chamada: ChamadaEsperada) -> ChamadaObservada:
    """A chamada que o gabarito descreve, como se o agente a tivesse feito."""
    return ChamadaObservada(name=chamada.name, args=dict(chamada.args))


def _ids(tarefas: list[Tarefa]) -> list[str]:
    return [t.id for t in tarefas]


DE_CHAMADA = [t for t in TAREFAS if isinstance(t.expect, EsperaChamadaDeFerramenta)]
SEM_CHAMADA = [t for t in TAREFAS if isinstance(t.expect, EsperaNenhumaChamada)]
DE_ESCLARECIMENTO = [t for t in TAREFAS if isinstance(t.expect, EsperaEsclarecimento)]

REGRAS: list[tuple[Tarefa, RegraDeFalhaSilenciosa]] = [
    (t, regra)
    for t in DE_CHAMADA
    if isinstance(t.expect, EsperaChamadaDeFerramenta)
    for regra in t.expect.silent_failure_if
]


def test_o_dataset_real_foi_carregado() -> None:
    """Sem tarefa nenhuma, todo teste parametrizado abaixo passaria vazio."""
    assert len(TAREFAS) >= 40


def test_todo_kind_do_dataset_e_exercitado() -> None:
    kinds = {t.expect.kind for t in TAREFAS}
    assert kinds <= KINDS_COBERTOS, (
        f"kinds sem gabarito executavel: {sorted(kinds - KINDS_COBERTOS)}"
    )


# --------------------------------------------------------------------------
# O gabarito passa
# --------------------------------------------------------------------------


@pytest.mark.parametrize("tarefa", DE_CHAMADA, ids=_ids(DE_CHAMADA))
def test_cada_alternativa_do_gabarito_passa(tarefa: Tarefa) -> None:
    """Toda alternativa aceitável, montada literalmente, tem de passar."""
    assert isinstance(tarefa.expect, EsperaChamadaDeFerramenta)
    for alternativa in tarefa.expect.accept:
        resposta = RespostaCrua(tool_calls=tuple(_observada(c) for c in alternativa.calls))
        veredicto = pontuar(tarefa, resposta)
        assert veredicto.desfecho is Desfecho.PASSOU, (
            f"{tarefa.id}, alternativa '{alternativa.id}': o proprio gabarito reprovou -- "
            f"{veredicto.motivo}"
        )


@pytest.mark.parametrize("tarefa", SEM_CHAMADA, ids=_ids(SEM_CHAMADA))
def test_irrelevancia_passa_sem_chamar_e_reprova_chamando(tarefa: Tarefa) -> None:
    assert pontuar(tarefa, RespostaCrua(text="Que bom!")).desfecho is Desfecho.PASSOU

    negocio = next(f for f in tarefa.context.tools if f.name not in FERRAMENTAS_DE_ABSTENCAO)
    agiu = RespostaCrua(tool_calls=(ChamadaObservada(name=negocio.name, args={}),))
    assert pontuar(tarefa, agiu).desfecho is Desfecho.FALHOU


@pytest.mark.parametrize("tarefa", DE_ESCLARECIMENTO, ids=_ids(DE_ESCLARECIMENTO))
def test_esclarecimento_passa_pedindo_cada_slot_por_identificador(tarefa: Tarefa) -> None:
    """O caminho da ferramenta: um `pedir_esclarecimento` por slot faltante."""
    assert isinstance(tarefa.expect, EsperaEsclarecimento)
    resposta = RespostaCrua(
        tool_calls=tuple(
            ChamadaObservada(
                name="pedir_esclarecimento",
                args={"campo_faltante": slot, "pergunta": "?"},
            )
            for slot in tarefa.expect.missing_slots
        )
    )
    veredicto = pontuar(tarefa, resposta)
    assert veredicto.desfecho is Desfecho.PASSOU, f"{tarefa.id}: {veredicto.motivo}"


@pytest.mark.parametrize("tarefa", DE_ESCLARECIMENTO, ids=_ids(DE_ESCLARECIMENTO))
def test_esclarecimento_reprova_quem_inventa(tarefa: Tarefa) -> None:
    negocio = next(f for f in tarefa.context.tools if f.name not in FERRAMENTAS_DE_ABSTENCAO)
    inventou = RespostaCrua(tool_calls=(ChamadaObservada(name=negocio.name, args={}),))
    assert pontuar(tarefa, inventou).desfecho is Desfecho.FALHOU


# --------------------------------------------------------------------------
# Todo rótulo de falha silenciosa é alcançável
# --------------------------------------------------------------------------


def _resposta_com_o_erro(tarefa: Tarefa, regra: RegraDeFalhaSilenciosa) -> RespostaCrua:
    """O gabarito, com o argumento da regra trocado pelo valor do erro.

    Se nenhuma chamada do gabarito tem esse argumento, o erro é **ter chamado
    outra ferramenta** — a que tem. É assim que `escolha-de-ferramenta` rotula a
    ferramenta errada com uma regra que só enxerga argumento.
    """
    assert isinstance(tarefa.expect, EsperaChamadaDeFerramenta)
    chamadas = [_observada(c) for c in tarefa.expect.accept[0].calls]
    for i, chamada in enumerate(chamadas):
        if regra.arg in chamada.args:
            args: dict[str, JsonValue] = {**chamada.args, regra.arg: regra.equals}
            chamadas[i] = ChamadaObservada(name=chamada.name, args=args)
            return RespostaCrua(tool_calls=tuple(chamadas))

    def declara(propriedades: JsonValue) -> bool:
        return isinstance(propriedades, dict) and regra.arg in propriedades

    dona = next(
        f
        for f in tarefa.context.tools
        if f.name not in FERRAMENTAS_DE_ABSTENCAO and declara(f.parameters.get("properties"))
    )
    return RespostaCrua(
        tool_calls=(ChamadaObservada(name=dona.name, args={regra.arg: regra.equals}),)
    )


@pytest.mark.parametrize(
    ("tarefa", "regra"),
    REGRAS,
    ids=[f"{t.id}:{r.label}:{r.equals}" for t, r in REGRAS],
)
def test_o_erro_rotulado_reprova_e_recebe_o_rotulo(
    tarefa: Tarefa, regra: RegraDeFalhaSilenciosa
) -> None:
    """Rótulo só se aplica a erro: se o valor passa no matcher, o rótulo é morto."""
    resposta = _resposta_com_o_erro(tarefa, regra)

    veredicto = pontuar(tarefa, resposta)
    assert veredicto.desfecho is Desfecho.FALHOU, (
        f"{tarefa.id}: o erro '{regra.label}' ({regra.arg}={regra.equals!r}) PASSOU no "
        "matcher -- a regua e frouxa demais, ou o rotulo descreve algo que nao e erro"
    )
    assert isinstance(tarefa.expect, EsperaChamadaDeFerramenta)
    assert rotular(tarefa.expect.silent_failure_if, resposta.tool_calls) == regra.label
