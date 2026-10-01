r"""Um agente que responde o gabarito, falando MCP pelo fio, tira 100%.

Por que isto existe
-------------------
`test_gabarito_executavel` prova que o **pontuador** aceita o gabarito. Ele não
prova que o gabarito **chega** ao pontuador intacto. Entre o agente e a nota há
o caminho inteiro que uma rodada real percorre:

1. o agente serializa a chamada em JSON-RPC — com `"João"` virando
   `"Jo\u00e3o"` se o cliente escapa não-ASCII, e `255000` podendo virar
   `255000.0` se alguém passar por float;
2. o servidor MCP parseia, grava a chamada e responde;
3. a sessão vira uma `ExecucaoCrua`, que é gravada no `raw.jsonl` e relida;
4. o `score` pontua a linha relida.

Qualquer passo que altere um argumento faria **todo agente** reprovar naquela
tarefa, e a primeira pista seria uma rodada paga com nota estranha. Este teste é
um agente oráculo de graça: ele responde exatamente o gabarito, pelo fio, e
precisa passar em tudo.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from curupira.core.enums import Desfecho
from curupira.core.expect import (
    EsperaChamadaDeFerramenta,
    EsperaEsclarecimento,
    EsperaNenhumaChamada,
)
from curupira.core.loader import carregar_diretorio
from curupira.core.registry import limpar_registro
from curupira.core.result import ExecucaoCrua, IdentidadeDoAgente
from curupira.core.task import Tarefa
from curupira.formatos import registrar_validadores
from curupira.matchers import registrar_todos
from curupira.mcp.protocolo import CHAVE_DA_VERSAO, CHAVE_DAS_CAPACIDADES, VERSAO_DO_PROTOCOLO
from curupira.mcp.rodada import execucao_da_sessao
from curupira.mcp.servidor import ServidorDeTarefa
from curupira.scoring.rodada import pontuar_execucao

RAIZ = Path(__file__).resolve().parent.parent
TAREFAS = sorted(carregar_diretorio(RAIZ / "tasks"), key=lambda t: t.id)

ORACULO = IdentidadeDoAgente(
    agent_id="oraculo",
    model="gabarito",
    adapter_version="mcp/teste",
    prompt_template_id="nenhum",
    temperature=0.0,
)


@pytest.fixture(autouse=True)
def _registro_pronto() -> Iterator[None]:
    limpar_registro()
    registrar_todos()
    registrar_validadores()
    yield
    limpar_registro()


def _chamadas_do_oraculo(tarefa: Tarefa) -> list[tuple[str, dict[str, Any]]]:
    """O que um agente perfeito chamaria nesta tarefa."""
    espera = tarefa.expect
    if isinstance(espera, EsperaChamadaDeFerramenta):
        return [(c.name, dict(c.args)) for c in espera.accept[0].calls]
    if isinstance(espera, EsperaEsclarecimento):
        return [
            ("pedir_esclarecimento", {"campo_faltante": slot, "pergunta": "?"})
            for slot in espera.missing_slots
        ]
    if isinstance(espera, EsperaNenhumaChamada):
        return []
    pytest.fail(f"{tarefa.id}: kind '{espera.kind}' sem oraculo; ensine este teste")


def _linha(identificador: int, nome: str, argumentos: dict[str, Any]) -> str:
    """Uma `tools/call` como um cliente MCP mandaria, com não-ASCII escapado."""
    corpo = {
        "jsonrpc": "2.0",
        "id": identificador,
        "method": "tools/call",
        "params": {
            "name": nome,
            "arguments": argumentos,
            "_meta": {CHAVE_DA_VERSAO: VERSAO_DO_PROTOCOLO, CHAVE_DAS_CAPACIDADES: {}},
        },
    }
    return json.dumps(corpo, ensure_ascii=True)


@pytest.mark.parametrize("tarefa", TAREFAS, ids=[t.id for t in TAREFAS])
def test_o_oraculo_passa_pelo_fio_e_pelo_bruto(tarefa: Tarefa) -> None:
    servidor = ServidorDeTarefa(tarefa)
    for i, (nome, argumentos) in enumerate(_chamadas_do_oraculo(tarefa), start=1):
        resposta = servidor.atender(_linha(i, nome, argumentos))
        assert resposta is not None
        assert "error" not in resposta, f"{tarefa.id}: o servidor recusou {nome}: {resposta}"

    execucao = execucao_da_sessao(
        tarefa,
        servidor.chamadas,
        suite_id="oraculo",
        agente=ORACULO,
        repeticao=0,
        latencia_ms=0,
    )
    relida = ExecucaoCrua.model_validate_json(execucao.model_dump_json())

    resultado = pontuar_execucao(relida, tarefa)
    assert resultado.outcome is Desfecho.PASSOU, f"{tarefa.id}: {resultado}"


def test_o_oraculo_cobre_o_dataset_inteiro() -> None:
    """Sem tarefa nenhuma, o teste parametrizado passaria vazio."""
    assert len(TAREFAS) >= 40
