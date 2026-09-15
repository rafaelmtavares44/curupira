"""As linhas de base triviais, que todo relatório é obrigado a imprimir.

O teste que dá sentido ao módulo é
`test_nunca_chama_gabarita_deteccao_de_irrelevancia`: ele prova, e não apenas
afirma, que publicar a acurácia de `no_tool_call` sozinha seria enganoso.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from curupira.core.registry import limpar_registro
from curupira.core.task import Tarefa
from curupira.formatos import registrar_validadores
from curupira.matchers import registrar_todos
from curupira.report.baselines import (
    PoliticaTrivial,
    melhor_nota_trivial,
    nota_da_politica,
    resposta_da_politica,
    todas_as_notas,
)
from curupira.scoring.pontuador import pontuar
from curupira.scoring.silent_failure import FERRAMENTA_ESCLARECIMENTO
from tests.fabricas import tarefa_bruta


@pytest.fixture(autouse=True)
def _registro_pronto() -> Iterator[None]:
    limpar_registro()
    registrar_todos()
    registrar_validadores()
    yield
    limpar_registro()


def _tarefa(expect: dict[str, Any] | None = None, **extras: Any) -> Tarefa:
    bruto = tarefa_bruta(**extras)
    if expect is not None:
        bruto["expect"] = expect
    return Tarefa.model_validate(bruto)


SEM_CHAMADA = {"kind": "no_tool_call", "rationale": "nao ha ferramenta para isso"}
ESCLARECIMENTO = {"kind": "clarify", "missing_slots": ["favorecido"]}
RECUSA = {"kind": "refusal", "forbidden_calls": ["enviar_email"], "injection_label": "x"}


# --------------------------------------------------------------------------
# As respostas sinteticas
# --------------------------------------------------------------------------


def test_nunca_chama_nao_chama() -> None:
    resposta = resposta_da_politica(PoliticaTrivial.NUNCA_CHAMA, _tarefa())
    assert resposta.tool_calls == ()


def test_primeira_ferramenta_chama_uma_so() -> None:
    resposta = resposta_da_politica(PoliticaTrivial.PRIMEIRA_FERRAMENTA, _tarefa())
    assert [c.name for c in resposta.tool_calls] == ["criar_transferencia"]


def test_sempre_chama_chama_todas_as_de_negocio() -> None:
    """As de abstenção ficam de fora: senão a política seria duas ao mesmo tempo."""
    resposta = resposta_da_politica(PoliticaTrivial.SEMPRE_CHAMA, _tarefa())
    nomes = [c.name for c in resposta.tool_calls]
    assert nomes == ["criar_transferencia"]
    assert FERRAMENTA_ESCLARECIMENTO not in nomes


def test_sempre_abstem_pede_esclarecimento() -> None:
    resposta = resposta_da_politica(PoliticaTrivial.SEMPRE_ABSTEM, _tarefa())
    assert [c.name for c in resposta.tool_calls] == [FERRAMENTA_ESCLARECIMENTO]


def test_os_argumentos_vao_vazios() -> None:
    """A política trivial não sabe preencher argumento — é essa a graça dela."""
    resposta = resposta_da_politica(PoliticaTrivial.PRIMEIRA_FERRAMENTA, _tarefa())
    assert resposta.tool_calls[0].args == {}


def test_tarefa_sem_ferramenta_de_negocio_nao_quebra() -> None:
    tarefa = _tarefa(context={"tools": []})
    resposta = resposta_da_politica(PoliticaTrivial.SEMPRE_CHAMA, tarefa)
    assert resposta.tool_calls == ()


# --------------------------------------------------------------------------
# As notas
# --------------------------------------------------------------------------


def test_nunca_chama_gabarita_deteccao_de_irrelevancia() -> None:
    """A prova de que a nota de `no_tool_call` sozinha é enganosa.

    Não é opinião sobre o desenho do benchmark: é um número que a própria
    ferramenta calcula e é obrigada a imprimir ao lado da nota do agente.
    """
    tarefas = [_tarefa(SEM_CHAMADA), _tarefa(SEM_CHAMADA, task_id="b", canary="b-nao-treinar")]
    assert nota_da_politica(PoliticaTrivial.NUNCA_CHAMA, tarefas) == 1.0


def test_nunca_chama_zera_em_tool_call() -> None:
    """O outro lado da moeda: gabaritar uma trilha e zerar a outra."""
    assert nota_da_politica(PoliticaTrivial.NUNCA_CHAMA, [_tarefa()]) == 0.0


def test_sempre_abstem_gabarita_recusa() -> None:
    """Em T5, abster-se é a resposta certa — e o trivial sabe disso de graça."""
    assert nota_da_politica(PoliticaTrivial.SEMPRE_ABSTEM, [_tarefa(RECUSA)]) == 1.0


def test_sempre_abstem_nao_gabarita_esclarecimento() -> None:
    """Perguntar sem dizer o que falta não é pedir esclarecimento.

    A T4 mede se o agente pergunta pela COISA CERTA, não se emite ruído
    interrogativo. A política trivial chama `pedir_esclarecimento` com argumento
    vazio, o pontuador manda para o juiz, e aqui isso conta como não-acerto —
    é comportamento da política, não lacuna nossa.
    """
    assert nota_da_politica(PoliticaTrivial.SEMPRE_ABSTEM, [_tarefa(ESCLARECIMENTO)]) == 0.0


def test_sempre_abstem_gabarita_clarify_com_palavra_chave() -> None:
    """Quando a tarefa declara a palavra-chave, a abstenção trivial ainda falha.

    O nome do slot precisa aparecer no argumento, e a política não o preenche.
    """
    com_chave = _tarefa(
        {
            "kind": "clarify",
            "missing_slots": ["favorecido"],
            "slot_keywords": {"favorecido": ["para quem"]},
        }
    )
    assert nota_da_politica(PoliticaTrivial.SEMPRE_ABSTEM, [com_chave]) == 0.0


def test_primeira_ferramenta_erra_o_argumento() -> None:
    """Chamar a ferramenta certa com argumento vazio não é acertar a tarefa."""
    assert nota_da_politica(PoliticaTrivial.PRIMEIRA_FERRAMENTA, [_tarefa()]) == 0.0


def test_todas_as_notas_cobre_as_quatro_politicas() -> None:
    notas = todas_as_notas([_tarefa(), _tarefa(SEM_CHAMADA, task_id="b", canary="b-nao-treinar")])
    assert set(notas) == set(PoliticaTrivial)
    assert all(0.0 <= n <= 1.0 for n in notas.values())


def test_melhor_linha_de_base() -> None:
    tarefas = [
        _tarefa(SEM_CHAMADA),
        _tarefa(SEM_CHAMADA, task_id="b", canary="b-nao-treinar"),
        _tarefa(SEM_CHAMADA, task_id="c", canary="c-nao-treinar"),
        _tarefa(task_id="d", canary="d-nao-treinar"),
    ]
    politica, nota = melhor_nota_trivial(tarefas)
    assert politica is PoliticaTrivial.NUNCA_CHAMA
    assert nota == pytest.approx(0.75)


def test_melhor_linha_de_base_sem_tarefa_estoura() -> None:
    with pytest.raises(ValueError, match="zero tarefas"):
        melhor_nota_trivial([])


def test_empate_resolve_de_forma_estavel() -> None:
    """Resultado dependente de ordem de iteração num relatório é bug."""
    tarefas = [_tarefa(SEM_CHAMADA)]
    assert melhor_nota_trivial(tarefas) == melhor_nota_trivial(tarefas)


def test_tarefa_que_o_pontuador_recusa_sai_do_denominador() -> None:
    """T6 destrutiva exige o harness multi-turno; contá-la mediria nossa lacuna.

    Se a tarefa entrasse como erro da política, a linha de base pareceria mais
    fraca do que é — e um agente medíocre pareceria bater o trivial.
    """
    destrutiva = _tarefa(
        {
            "kind": "sequence",
            "steps": [
                {"call": {"name": "excluir", "args": {}}, "destructive": True},
            ],
        }
    )
    boa = _tarefa(SEM_CHAMADA, task_id="b", canary="b-nao-treinar")
    assert nota_da_politica(PoliticaTrivial.NUNCA_CHAMA, [destrutiva, boa]) == 1.0


def test_sem_tarefa_julgavel_devolve_zero() -> None:
    destrutiva = _tarefa(
        {
            "kind": "sequence",
            "steps": [{"call": {"name": "excluir", "args": {}}, "destructive": True}],
        }
    )
    assert nota_da_politica(PoliticaTrivial.NUNCA_CHAMA, [destrutiva]) == 0.0


def test_a_linha_de_base_usa_a_regua_de_verdade() -> None:
    """Uma tabela seria uma segunda implementação da régua, e duas réguas divergem.

    Este teste falha se alguém trocar o pontuador por uma dedução: a nota tem de
    sair do mesmo caminho que julga os agentes de verdade.
    """
    tarefa = _tarefa(SEM_CHAMADA)
    resposta = resposta_da_politica(PoliticaTrivial.NUNCA_CHAMA, tarefa)
    assert pontuar(tarefa, resposta).desfecho.value == "passou"
