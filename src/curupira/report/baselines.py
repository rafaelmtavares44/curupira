"""Linhas de base triviais. Obrigatórias em todo relatório.

Em T1, um agente que **nunca chama nada** tira 100% em detecção de irrelevância e
0% no resto. Publicar a nota de irrelevância sem a nota de tool calling ao lado é
enganoso por construção.

Por isso o harness calcula automaticamente as políticas degeneradas e as imprime
em toda rodada. Nota que não bate a política trivial é reportada como tal, em
destaque.

Por que isto roda o pontuador de verdade
----------------------------------------
Seria mais rápido deduzir a nota trivial por tabela — "`nunca_chama` acerta toda
tarefa `no_tool_call`" — e seria errado. Uma tabela é uma segunda implementação
da régua, e duas réguas divergem: bastaria alguém mudar o pontuador para que a
linha de base passasse a medir a régua de ontem.

Aqui a política vira uma `RespostaCrua` sintética e passa pelo **mesmo**
`scoring.pontuador` que julga os agentes de verdade. Se a régua mudar, a linha de
base muda junto, que é a única forma de a comparação continuar significando algo.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from curupira.core.enums import Desfecho
from curupira.core.result import ChamadaObservada, RespostaCrua
from curupira.core.task import Tarefa
from curupira.scoring.pontuador import pontuar
from curupira.scoring.silent_failure import (
    FERRAMENTA_ESCLARECIMENTO,
    FERRAMENTAS_DE_ABSTENCAO,
)


class PoliticaTrivial(StrEnum):
    """Políticas degeneradas contra as quais toda nota é comparada."""

    NUNCA_CHAMA = "nunca_chama"
    SEMPRE_CHAMA = "sempre_chama"
    PRIMEIRA_FERRAMENTA = "chama_a_primeira_ferramenta"
    SEMPRE_ABSTEM = "sempre_abstem"


TEXTO_TRIVIAL = "resposta da politica trivial"
"""Sem interrogação e sem palavra de hedge, de propósito.

O texto de uma política degenerada não pode, por acidente de redação, casar o
léxico de hesitação ou o `slot_keywords` de uma tarefa `clarify` — isso daria à
linha de base um crédito que ela não conquistou.
"""


def _ferramentas_de_negocio(tarefa: Tarefa) -> list[str]:
    """Os nomes das ferramentas da tarefa, sem as duas de abstenção."""
    return [f.name for f in tarefa.context.tools if f.name not in FERRAMENTAS_DE_ABSTENCAO]


def resposta_da_politica(politica: PoliticaTrivial, tarefa: Tarefa) -> RespostaCrua:
    """Monta a resposta sintética que a política degenerada daria.

    Os argumentos vão **vazios**. A política trivial não sabe preencher argumento
    — é essa a graça dela. Se acertasse argumento, não seria trivial, e a
    comparação perderia o sentido.

    Args:
        politica: a política degenerada.
        tarefa: a tarefa, de onde saem as ferramentas oferecidas.

    Returns:
        A resposta crua sintética.
    """
    if politica is PoliticaTrivial.NUNCA_CHAMA:
        return RespostaCrua(text=TEXTO_TRIVIAL, finish_reason="end_turn")
    if politica is PoliticaTrivial.SEMPRE_ABSTEM:
        return RespostaCrua(
            tool_calls=(ChamadaObservada(name=FERRAMENTA_ESCLARECIMENTO, args={}),),
            finish_reason="tool_use",
        )

    negocio = _ferramentas_de_negocio(tarefa)
    if not negocio:
        return RespostaCrua(text=TEXTO_TRIVIAL, finish_reason="end_turn")
    alvos = negocio[:1] if politica is PoliticaTrivial.PRIMEIRA_FERRAMENTA else negocio
    return RespostaCrua(
        tool_calls=tuple(ChamadaObservada(name=nome, args={}) for nome in alvos),
        finish_reason="tool_use",
    )


def _acertou(politica: PoliticaTrivial, tarefa: Tarefa) -> bool | None:
    """Diz se a política acerta esta tarefa.

    Duas formas de "não deu para julgar", tratadas de forma **diferente** de
    propósito:

    - O pontuador **recusa** julgar (T6 com passo destrutivo, que exige o harness
      multi-turno): isso é lacuna nossa, não comportamento da política. Devolve
      `None` e a tarefa sai do denominador; contá-la faria a linha de base medir
      o que o Curupira ainda não sabe fazer.
    - O pontuador julga e devolve `pendente_de_juiz`: isso **é** comportamento da
      política — ela produziu uma resposta ambígua. Conta como não-acerto.

    A segunda escolha é a conservadora na direção certa. Dar o benefício da
    dúvida à política inflaria o piso, e um piso inflado reprovaria agentes
    competentes. Do jeito que está, a nota trivial é um **limite inferior**: o
    agente que não bate nem ela não demonstrou competência nenhuma.
    """
    try:
        veredicto = pontuar(tarefa, resposta_da_politica(politica, tarefa))
    except ValueError:
        return None
    return veredicto.desfecho is Desfecho.PASSOU


def nota_da_politica(politica: PoliticaTrivial, tarefas: Sequence[Tarefa]) -> float:
    """Calcula a nota que uma política degenerada tiraria nestas tarefas.

    Args:
        politica: a política degenerada.
        tarefas: as tarefas da suíte.

    Returns:
        A acurácia, de 0 a 1, sobre as tarefas que o pontuador soube julgar.
        Sem nenhuma tarefa julgável, devolve 0,0.
    """
    julgadas = [a for a in (_acertou(politica, t) for t in tarefas) if a is not None]
    if not julgadas:
        return 0.0
    return sum(julgadas) / len(julgadas)


def todas_as_notas(tarefas: Sequence[Tarefa]) -> dict[PoliticaTrivial, float]:
    """Calcula as notas de todas as políticas triviais.

    Args:
        tarefas: as tarefas da suíte.

    Returns:
        Mapa de política para acurácia.
    """
    return {politica: nota_da_politica(politica, tarefas) for politica in PoliticaTrivial}


def melhor_nota_trivial(tarefas: Sequence[Tarefa]) -> tuple[PoliticaTrivial, float]:
    """A política trivial mais forte e a nota dela.

    É contra esta que a nota do agente se compara. Um agente que não a bate não
    demonstrou competência nenhuma naquela trilha, por mais alto que o número
    pareça isoladamente.

    Args:
        tarefas: as tarefas da suíte.

    Returns:
        A política vencedora e a nota. Empate resolve pela ordem do enum, que é
        fixa — resultado dependente de ordem de iteração num relatório é bug.

    Raises:
        ValueError: se não houver tarefa nenhuma.
    """
    if not tarefas:
        msg = "nao ha linha de base trivial sobre zero tarefas"
        raise ValueError(msg)
    notas = todas_as_notas(tarefas)
    vencedora = max(notas, key=lambda p: (notas[p], -list(PoliticaTrivial).index(p)))
    return vencedora, notas[vencedora]
