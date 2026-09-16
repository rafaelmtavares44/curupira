"""O servidor MCP: serve as ferramentas da tarefa e grava antes de julgar.

A garantia que este arquivo existe para provar é uma só, e ela é contrária ao
que um servidor MCP normal faz:

    **O argumento errado é a medição, e precisa sobreviver.**

Se o servidor rejeitar `valor_centavos: 123456000` por qualquer motivo — schema,
tipo, ferramenta inexistente — antes de gravar, o benchmark perde exatamente o
dado que existe para capturar. Vários testes aqui atacam esse ponto por ângulos
diferentes, de propósito.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from typer.testing import CliRunner

from curupira.cli import app
from curupira.core.loader import carregar_diretorio
from curupira.core.registry import limpar_registro
from curupira.core.task import Tarefa
from curupira.matchers import registrar_todos
from curupira.mcp.protocolo import (
    CHAVE_DA_VERSAO,
    CHAVE_DAS_CAPACIDADES,
    ERRO_DE_CAPACIDADE,
    ERRO_DE_METODO,
    ERRO_DE_PARAMETROS,
    ERRO_DE_PARSING,
    ERRO_DE_REQUISICAO,
    ERRO_DE_VERSAO,
    LIMITE_DA_MENSAGEM,
    RESULTADO_COMPLETO,
    VERSAO_DO_PROTOCOLO,
)
from curupira.mcp.rodada import (
    MOTIVO_DE_PARADA,
    VERSAO_DO_ADAPTADOR,
    corpo_da_requisicao,
)
from curupira.mcp.servidor import ServidorDeTarefa

runner = CliRunner()
RAIZ = Path(__file__).resolve().parent.parent

CAMINHO_DAS_TAREFAS = Path(__file__).resolve().parent.parent / "tasks" / "t2_formats"

META_VALIDO = {
    CHAVE_DA_VERSAO: VERSAO_DO_PROTOCOLO,
    CHAVE_DAS_CAPACIDADES: {},
}


@pytest.fixture(autouse=True)
def _registro_limpo() -> Iterator[None]:
    limpar_registro()
    registrar_todos()
    yield
    limpar_registro()


@pytest.fixture
def tarefa() -> Tarefa:
    """A tarefa real do dataset, não uma fabricada.

    O ponto da entrega é provar que o `context.tools` escrito na Parte A
    alimenta o `tools/list` **sem conversão**. Uma tarefa sintética provaria
    menos.
    """
    return next(t for t in carregar_diretorio(CAMINHO_DAS_TAREFAS) if t.id == "t2-money-0001")


def _linha(metodo: str, parametros: dict[str, Any] | None = None, identificador: Any = 1) -> str:
    """Monta uma mensagem JSON-RPC bem formada, com o `_meta` obrigatório.

    Args:
        metodo: o método MCP.
        parametros: os parâmetros, sem o `_meta`.
        identificador: o `id`; `None` produz uma notificação.

    Returns:
        A linha serializada.
    """
    params = dict(parametros or {})
    params["_meta"] = dict(META_VALIDO)
    corpo: dict[str, Any] = {"jsonrpc": "2.0", "method": metodo, "params": params}
    if identificador is not None:
        corpo["id"] = identificador
    return json.dumps(corpo)


def _atender(servidor: ServidorDeTarefa, metodo: str, **kwargs: Any) -> dict[str, Any]:
    """Atende uma requisição bem formada e devolve a resposta."""
    return _crua(servidor, _linha(metodo, **kwargs))


def _crua(servidor: ServidorDeTarefa, linha: str) -> dict[str, Any]:
    """Atende uma linha montada à mão, exigindo que exista resposta.

    Os testes de envelope precisam montar mensagens deliberadamente erradas,
    que `_linha` não sabe produzir porque ela sempre escreve o `_meta` certo.
    """
    resposta: dict[str, Any] | None = servidor.atender(linha)
    assert resposta is not None
    return resposta


# --------------------------------------------------------------------------
# tools/list — o dataset alimenta o protocolo sem conversão
# --------------------------------------------------------------------------


def test_o_input_schema_e_o_parameters_da_tarefa_sem_traducao(tarefa: Tarefa) -> None:
    """A hipótese central da entrega, em um assert.

    O `parameters` que a tarefa declara no YAML **é** JSON Schema, e o
    `inputSchema` do MCP **é** JSON Schema. Se precisasse de conversão, cada
    campo novo no dataset viraria trabalho aqui, e as duas formas divergiriam
    com o tempo.
    """
    resposta = _atender(ServidorDeTarefa(tarefa), "tools/list")
    servidas = resposta["result"]["tools"]

    assert len(servidas) == len(tarefa.context.tools)
    for servida, declarada in zip(servidas, tarefa.context.tools, strict=True):
        assert servida["name"] == declarada.name
        assert servida["description"] == declarada.description
        assert servida["inputSchema"] == declarada.parameters


def test_as_ferramentas_de_abstencao_chegam_ao_agente(tarefa: Tarefa) -> None:
    """`pedir_esclarecimento` e `recusar` estão em TODA tarefa, por desenho.

    Elas resolvem, sem juiz e sem léxico de hedge, dois dos seis tipos de
    `expect`. E resolvem também uma dúvida que a ADR 0007 tinha deixado em
    aberto: `clarify` e `refusal` seriam observáveis por um servidor MCP?

    São. O agente que quer perguntar **chama uma ferramenta**, e uma chamada é
    exatamente o que este servidor vê. Nenhuma camada extra de protocolo é
    necessária para esses dois casos.
    """
    resposta = _atender(ServidorDeTarefa(tarefa), "tools/list")
    nomes = {f["name"] for f in resposta["result"]["tools"]}
    assert {"pedir_esclarecimento", "recusar"} <= nomes


@pytest.mark.parametrize(
    ("ferramenta", "argumentos"),
    [
        (
            "pedir_esclarecimento",
            {"campo_faltante": "valor", "pergunta": "e em reais ou centavos?"},
        ),
        ("recusar", {"motivo": "pedido ambiguo demais para executar com seguranca"}),
    ],
)
def test_abstencao_e_observada_como_qualquer_outra_chamada(
    tarefa: Tarefa, ferramenta: str, argumentos: dict[str, Any]
) -> None:
    """Perguntar e recusar viram dado pelo mesmo caminho de sempre."""
    servidor = ServidorDeTarefa(tarefa)
    resposta = _atender(
        servidor,
        "tools/call",
        parametros={"name": ferramenta, "arguments": argumentos},
    )

    assert "error" not in resposta
    (chamada,) = servidor.chamadas
    assert chamada.name == ferramenta
    assert chamada.args == argumentos


def test_todo_resultado_declara_o_tipo(tarefa: Tarefa) -> None:
    """`resultType` é obrigatório na revisão 2026-07-28."""
    resposta = _atender(ServidorDeTarefa(tarefa), "tools/list")
    assert resposta["result"]["resultType"] == RESULTADO_COMPLETO


def test_a_ordem_das_ferramentas_e_deterministica(tarefa: Tarefa) -> None:
    """A especificação pede ordem estável para o cliente poder cachear."""
    servidor = ServidorDeTarefa(tarefa)
    primeira = _atender(servidor, "tools/list")["result"]["tools"]
    segunda = _atender(servidor, "tools/list")["result"]["tools"]
    assert primeira == segunda


# --------------------------------------------------------------------------
# GRAVA PRIMEIRO — a regra que define este servidor
# --------------------------------------------------------------------------


def test_o_argumento_mil_vezes_maior_e_gravado_como_veio(tarefa: Tarefa) -> None:
    """A falha silenciosa do separador decimal precisa chegar ao `raw.jsonl`.

    Este é o erro que o Curupira existe para medir. Um servidor que validasse
    contra o schema aceitaria (é integer válido) — mas um que validasse
    semanticamente, ou um SDK que normalizasse, apagaria o dado.
    """
    servidor = ServidorDeTarefa(tarefa)
    _atender(
        servidor,
        "tools/call",
        parametros={
            "name": "criar_transferencia",
            "arguments": {"valor_centavos": 123456000, "favorecido": "Silva"},
        },
    )

    (chamada,) = servidor.chamadas
    assert chamada.args["valor_centavos"] == 123456000


def test_ferramenta_inexistente_e_gravada_e_depois_recusada(tarefa: Tarefa) -> None:
    """Alucinação de ferramenta é comportamento do agente, e é dado.

    A especificação manda devolver erro de protocolo para ferramenta
    desconhecida. Fazemos as duas coisas, nesta ordem: grava, depois recusa.
    Inverter a ordem apagaria a evidência de que o agente inventou a ferramenta.
    """
    servidor = ServidorDeTarefa(tarefa)
    resposta = _atender(
        servidor,
        "tools/call",
        parametros={"name": "transferir_pix", "arguments": {"valor": 1}},
    )

    assert resposta["error"]["code"] == ERRO_DE_PARAMETROS
    (chamada,) = servidor.chamadas
    assert chamada.name == "transferir_pix"


def test_argumento_de_tipo_errado_e_gravado(tarefa: Tarefa) -> None:
    """Texto onde se esperava inteiro é um modo de erro clássico.

    `"1.234,56"` como string, em vez de centavos, é exatamente o que um modelo
    anglófono faz com a notação brasileira.
    """
    servidor = ServidorDeTarefa(tarefa)
    _atender(
        servidor,
        "tools/call",
        parametros={
            "name": "criar_transferencia",
            "arguments": {"valor_centavos": "1.234,56", "favorecido": "Silva"},
        },
    )

    (chamada,) = servidor.chamadas
    assert chamada.args["valor_centavos"] == "1.234,56"


def test_o_literal_dos_argumentos_fica_guardado(tarefa: Tarefa) -> None:
    """`raw_arguments` preserva a forma exata, não só os valores parseados."""
    servidor = ServidorDeTarefa(tarefa)
    _atender(
        servidor,
        "tools/call",
        parametros={
            "name": "criar_transferencia",
            "arguments": {"valor_centavos": 123456, "favorecido": "Silva"},
        },
    )

    (chamada,) = servidor.chamadas
    assert chamada.raw_arguments is not None
    assert json.loads(chamada.raw_arguments) == {
        "valor_centavos": 123456,
        "favorecido": "Silva",
    }


def test_argumentos_que_nao_sao_objeto_nao_derrubam_o_registro(tarefa: Tarefa) -> None:
    """Um agente pode mandar qualquer coisa; nada disso pode perder a chamada."""
    servidor = ServidorDeTarefa(tarefa)
    _atender(
        servidor,
        "tools/call",
        parametros={"name": "criar_transferencia", "arguments": ["Silva", 123456]},
    )

    (chamada,) = servidor.chamadas
    assert chamada.args == {}
    assert chamada.raw_arguments == '["Silva", 123456]'


def test_a_ordem_das_chamadas_e_preservada(tarefa: Tarefa) -> None:
    """A trilha T6 pontua a sequência; a ordem é o dado."""
    servidor = ServidorDeTarefa(tarefa)
    for valor in (1, 2, 3):
        _atender(
            servidor,
            "tools/call",
            parametros={
                "name": "criar_transferencia",
                "arguments": {"valor_centavos": valor, "favorecido": "Silva"},
            },
        )

    assert [c.args["valor_centavos"] for c in servidor.chamadas] == [1, 2, 3]


# --------------------------------------------------------------------------
# Erro de envelope NÃO é dado do agente
# --------------------------------------------------------------------------


def test_requisicao_sem_meta_nao_registra_chamada(tarefa: Tarefa) -> None:
    """`_meta` ausente é integração malfeita de quem avalia, não do agente.

    Registrar isso contaminaria a medição com ruído do harness — e um agente
    seria penalizado por um erro que não cometeu.
    """
    servidor = ServidorDeTarefa(tarefa)
    bruto = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "criar_transferencia", "arguments": {"valor_centavos": 1}},
        }
    )

    resposta = _crua(servidor, bruto)
    assert resposta["error"]["code"] == ERRO_DE_PARAMETROS
    assert servidor.chamadas == ()


def test_versao_de_protocolo_diferente_e_recusada(tarefa: Tarefa) -> None:
    """Melhor recusar do que manter uma conversa que quase funciona."""
    servidor = ServidorDeTarefa(tarefa)
    bruto = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {"_meta": {CHAVE_DA_VERSAO: "2024-11-05", CHAVE_DAS_CAPACIDADES: {}}},
        }
    )

    resposta = _crua(servidor, bruto)
    assert resposta["error"]["code"] == ERRO_DE_VERSAO
    assert resposta["error"]["data"]["supported"] == [VERSAO_DO_PROTOCOLO]


def test_capacidades_ausentes_recebem_o_erro_proprio_do_mcp(tarefa: Tarefa) -> None:
    """A especificação define `-32021` e manda listar o que faltou."""
    servidor = ServidorDeTarefa(tarefa)
    bruto = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {"_meta": {CHAVE_DA_VERSAO: VERSAO_DO_PROTOCOLO}},
        }
    )

    resposta = _crua(servidor, bruto)
    assert resposta["error"]["code"] == ERRO_DE_CAPACIDADE
    assert CHAVE_DAS_CAPACIDADES in resposta["error"]["data"]["requiredCapabilities"]


def test_json_quebrado_vira_erro_de_parsing(tarefa: Tarefa) -> None:
    servidor = ServidorDeTarefa(tarefa)
    resposta = _crua(servidor, "{isto nao e json")
    assert resposta["error"]["code"] == ERRO_DE_PARSING


def test_mensagem_que_nao_e_objeto_e_recusada(tarefa: Tarefa) -> None:
    servidor = ServidorDeTarefa(tarefa)
    resposta = _crua(servidor, "[1, 2, 3]")
    assert resposta["error"]["code"] == ERRO_DE_REQUISICAO


def test_mensagem_gigante_e_recusada_sem_parsear(tarefa: Tarefa) -> None:
    """Limite explícito contra exaustão de recurso, como a especificação pede."""
    servidor = ServidorDeTarefa(tarefa)
    resposta = _crua(servidor, "x" * (LIMITE_DA_MENSAGEM + 1))
    assert resposta["error"]["code"] == ERRO_DE_REQUISICAO


def test_metodo_desconhecido_e_recusado(tarefa: Tarefa) -> None:
    """Só servimos ferramentas; resources e prompts estão fora do escopo."""
    resposta = _atender(ServidorDeTarefa(tarefa), "resources/list")
    assert resposta["error"]["code"] == ERRO_DE_METODO


def test_notificacao_nao_recebe_resposta(tarefa: Tarefa) -> None:
    """Por especificação, o receptor de uma notificação não responde."""
    servidor = ServidorDeTarefa(tarefa)
    assert servidor.atender(_linha("notifications/initialized", identificador=None)) is None


def test_tools_call_sem_nome_e_recusado(tarefa: Tarefa) -> None:
    resposta = _atender(ServidorDeTarefa(tarefa), "tools/call", parametros={"arguments": {}})
    assert resposta["error"]["code"] == ERRO_DE_PARAMETROS


# --------------------------------------------------------------------------
# A resposta da ferramenta não pode ter idioma
# --------------------------------------------------------------------------


def test_a_resposta_da_ferramenta_nao_tem_palavra_em_idioma_nenhum(tarefa: Tarefa) -> None:
    """Uma confirmação em português entraria no Delta como se fosse do agente.

    O par `strict` roda a mesma tarefa em PT-BR e em EN-US. Se o servidor
    respondesse "transferência criada com sucesso", a versão portuguesa
    carregaria um contexto que a inglesa não tem, e parte do Delta mediria a
    **nossa** resposta. É a mesma armadilha que a ADR 0005 D3 registrou na
    notação numérica — com a diferença de que aqui dava para eliminar.
    """
    resposta = _atender(
        ServidorDeTarefa(tarefa),
        "tools/call",
        parametros={
            "name": "criar_transferencia",
            "arguments": {"valor_centavos": 123456, "favorecido": "Silva"},
        },
    )

    texto = resposta["result"]["content"][0]["text"]
    assert json.loads(texto) == {"status": "ok"}
    assert resposta["result"]["isError"] is False

    proibidas = (
        "transfer",
        "sucesso",
        "success",
        "criada",
        "created",
        "reais",
        "erro",
        "error",
    )
    minusculo = texto.lower()
    assert not any(p in minusculo for p in proibidas), texto


# --------------------------------------------------------------------------
# O laço do transporte
# --------------------------------------------------------------------------


def test_servir_responde_uma_linha_por_requisicao(tarefa: Tarefa) -> None:
    servidor = ServidorDeTarefa(tarefa)
    entrada = [
        _linha("tools/list", identificador=1),
        _linha(
            "tools/call",
            parametros={
                "name": "criar_transferencia",
                "arguments": {"valor_centavos": 123456, "favorecido": "Silva"},
            },
            identificador=2,
        ),
    ]

    saidas = [json.loads(linha) for linha in servidor.servir(entrada)]

    assert [s["id"] for s in saidas] == [1, 2]
    assert len(servidor.chamadas) == 1


def test_servir_ignora_linha_em_branco_e_nao_responde_notificacao(tarefa: Tarefa) -> None:
    """Linha vazia é ruído de transporte, não mensagem."""
    servidor = ServidorDeTarefa(tarefa)
    entrada = [
        "",
        "   \n",
        _linha("notifications/initialized", identificador=None),
        _linha("tools/list", identificador=7),
    ]

    saidas = [json.loads(linha) for linha in servidor.servir(entrada)]

    assert len(saidas) == 1
    assert saidas[0]["id"] == 7


# --------------------------------------------------------------------------
# O `serve`, de ponta a ponta, até o `score`
# --------------------------------------------------------------------------


def _sessao(chamadas: list[dict[str, Any]]) -> str:
    """Monta uma sessão stdio completa: lista as ferramentas e chama algumas.

    Args:
        chamadas: os `params` de cada `tools/call`.

    Returns:
        As linhas da sessão, prontas para o stdin.
    """
    linhas = [_linha("tools/list", identificador=1)]
    linhas += [
        _linha("tools/call", parametros=p, identificador=i) for i, p in enumerate(chamadas, start=2)
    ]
    return "\n".join(linhas) + "\n"


def test_o_bruto_do_mcp_e_lido_pelo_score_sem_mudanca(tmp_path: Path) -> None:
    """A prova de que a entrega não inventou formato.

    O agente erra por mil — lê o ponto de `1.234,56` como separador decimal — e
    o `score`, que não sabe nada sobre MCP, classifica isso como a falha
    silenciosa que a tarefa declara em `silent_failure_if`.

    Se este teste cair, o servidor deixou de produzir o `raw.jsonl` que o resto
    do pipeline já sabia ler, e os onze entregas anteriores param de valer para
    o caminho do agente.
    """
    saida = tmp_path / "rodada"
    sessao = _sessao(
        [
            {
                "name": "criar_transferencia",
                "arguments": {"valor_centavos": 123456000, "favorecido": "Silva"},
            }
        ]
    )

    servido = runner.invoke(
        app,
        [
            "serve",
            "--suite",
            "v0.1",
            "--tarefa",
            "t2-money-0001",
            "--agent",
            "ensaio",
            "--modelo",
            "claude-haiku-4-5-20251001",
            "--framework",
            "crewai",
            "--tarefas",
            str(RAIZ / "tasks"),
            "--destino",
            str(RAIZ / "suites"),
            "--saida",
            str(saida),
        ],
        input=sessao,
    )
    assert servido.exit_code == 0, servido.output

    pontuado = runner.invoke(app, ["score", str(saida)])
    assert pontuado.exit_code == 0, pontuado.output

    frame = pl.read_parquet(saida / "scored.parquet")
    assert frame["outcome"][0] == "falhou"
    assert frame["failure_class"][0] == "falha_silenciosa"
    assert frame["silent_failure_label"][0] == "leu_ponto_como_decimal"
    assert frame["adapter_version"][0] == VERSAO_DO_ADAPTADOR
    assert frame["framework"][0] == "crewai"


def test_o_serve_recusa_tarefa_fora_da_suite(tmp_path: Path) -> None:
    """Rodar tarefa que a suíte não congelou produziria nota incomparável."""
    resultado = runner.invoke(
        app,
        [
            "serve",
            "--suite",
            "v0.1",
            "--tarefa",
            "t2-inexistente-9999",
            "--agent",
            "ensaio",
            "--modelo",
            "m",
            "--tarefas",
            str(RAIZ / "tasks"),
            "--destino",
            str(RAIZ / "suites"),
            "--saida",
            str(tmp_path / "rodada"),
        ],
        input="",
    )
    assert resultado.exit_code != 0


def test_o_corpo_da_requisicao_guarda_o_que_foi_oferecido(tarefa: Tarefa) -> None:
    """Sem corpo enviado, o equivalente auditável é o que o agente teve à mão.

    É o que permite a um terceiro conferir que a tarefa chegou do jeito que o
    dataset declara — a mesma função que o `request_body` cumpre no `run`.
    """
    corpo = json.loads(corpo_da_requisicao(tarefa))

    assert corpo["user_message"] == tarefa.input.user_message
    assert [f["name"] for f in corpo["tools"]] == [t.name for t in tarefa.context.tools]


def test_a_sessao_declara_como_terminou() -> None:
    """O fim por stdin fechado é provisório, e precisa estar legível no dado.

    Quando a camada de tarefa chegar (Entrega 14), rodadas antigas continuarão
    dizendo por qual mecanismo pararam — e não serão confundidas com as novas.
    """
    assert MOTIVO_DE_PARADA == "stdin_fechado"
