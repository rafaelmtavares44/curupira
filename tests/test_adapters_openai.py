"""O adaptador da OpenAI: mapeamento, o literal dos argumentos e o fingerprint.

Nenhum teste aqui toca a rede — `httpx.MockTransport` responde do próprio
processo.

O teste que carrega o arquivo nas costas é
`test_argumentos_invalidos_viram_dado_nao_erro`. Ele fixa a decisão de projeto
mais consequente deste adaptador: um argumento que não é JSON válido é
**exatamente o achado** que a trilha T2 procura, e estourar ali apagaria a linha
mais informativa da rodada — ainda por cima contaminando a taxa de erro de
infraestrutura com erro do agente.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from curupira.adapters.base import (
    AdaptadorDeModelo,
    ErroDoProvedor,
    Mensagem,
    ParametrosDeAmostragem,
)
from curupira.adapters.openai import URL, AdaptadorOpenAI, converter
from curupira.core.task import DefinicaoDeFerramenta
from curupira.security import esquecer_segredos, registrar_segredo
from tests.fabricas import FERRAMENTA_TRANSFERENCIA

CHAVE = SecretStr("chave-de-teste-nao-e-segredo-de-verdade")
MENSAGENS = (Mensagem(role="user", content="faz uma transferencia de 1.234,56 pro Silva"),)
FERRAMENTAS = (DefinicaoDeFerramenta.model_validate(FERRAMENTA_TRANSFERENCIA),)


def _cliente(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _sucesso(**corpo: Any) -> Any:
    padrao: dict[str, Any] = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "model": "modelo-x",
        "system_fingerprint": "fp_abc123",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "criar_transferencia",
                                "arguments": '{"valor_centavos": 123456, "favorecido": "Silva"}',
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
    }
    padrao.update(corpo)

    def handler(request: httpx.Request) -> httpx.Response:
        handler.ultima = request  # type: ignore[attr-defined]
        return httpx.Response(200, json=padrao)

    return handler


# --------------------------------------------------------------------------
# Contrato
# --------------------------------------------------------------------------


def test_o_adaptador_cumpre_o_protocolo() -> None:
    """A anotação é o teste: o mypy strict checa estruturalmente."""
    adaptador: AdaptadorDeModelo = AdaptadorOpenAI()
    assert adaptador.nome == "openai"
    assert adaptador.versao == "0.1.0"
    assert adaptador.suporta_seed is True


# --------------------------------------------------------------------------
# preparar: o mapeamento que a ADR 0002 existe para tornar auditavel
# --------------------------------------------------------------------------


def test_a_ferramenta_vai_no_envelope_duplo() -> None:
    """`{"type": "function", "function": {...}}`. Um nível a menos é 400.

    A documentação é explícita que o invólucro `function` é obrigatório. Este
    teste existe porque a forma do envelope é o tipo de detalhe que se
    "simplifica" numa refatoração e só quebra contra a API de verdade.
    """
    requisicao = AdaptadorOpenAI().preparar(
        modelo="modelo-x",
        mensagens=MENSAGENS,
        ferramentas=FERRAMENTAS,
        parametros=ParametrosDeAmostragem(),
    )
    ferramentas = requisicao.corpo["tools"]
    assert isinstance(ferramentas, list)
    primeira = ferramentas[0]
    assert isinstance(primeira, dict)
    assert primeira["type"] == "function"
    assert "name" not in primeira

    funcao = primeira["function"]
    assert isinstance(funcao, dict)
    assert funcao["name"] == "criar_transferencia"
    assert funcao["parameters"] == FERRAMENTA_TRANSFERENCIA["parameters"]


def test_strict_nao_e_enviado() -> None:
    """Ligar `strict` seria pedir ao provedor que consertasse o erro que medimos.

    Com `strict: true` a OpenAI força a saída a casar com o schema. Excelente em
    produção, desastroso num benchmark cuja pergunta é se o agente acerta o
    argumento **sozinho**.
    """
    requisicao = AdaptadorOpenAI().preparar(
        modelo="m",
        mensagens=MENSAGENS,
        ferramentas=FERRAMENTAS,
        parametros=ParametrosDeAmostragem(),
    )
    assert "strict" not in requisicao.literal()


def test_usa_max_completion_tokens_e_nao_o_nome_antigo() -> None:
    """`max_tokens` é rejeitado pelos modelos de raciocínio."""
    requisicao = AdaptadorOpenAI().preparar(
        modelo="m",
        mensagens=MENSAGENS,
        ferramentas=(),
        parametros=ParametrosDeAmostragem(temperature=0.7, max_tokens=256),
    )
    assert requisicao.corpo["max_completion_tokens"] == 256
    assert "max_tokens" not in requisicao.corpo
    assert requisicao.corpo["temperature"] == 0.7
    assert requisicao.url == URL


def test_a_seed_vai_para_a_openai() -> None:
    """Ao contrário da Anthropic, aqui o parâmetro existe e é aplicado."""
    requisicao = AdaptadorOpenAI().preparar(
        modelo="m",
        mensagens=MENSAGENS,
        ferramentas=(),
        parametros=ParametrosDeAmostragem(seed=42),
    )
    assert requisicao.corpo["seed"] == 42


def test_sem_seed_o_campo_nao_aparece() -> None:
    """`seed: null` e ausência de `seed` não são a mesma coisa."""
    requisicao = AdaptadorOpenAI().preparar(
        modelo="m", mensagens=MENSAGENS, ferramentas=(), parametros=ParametrosDeAmostragem()
    )
    assert "seed" not in requisicao.corpo


def test_o_system_vira_mensagem_na_frente_da_conversa() -> None:
    """Aqui não é campo de topo como na Anthropic — é a primeira mensagem."""
    requisicao = AdaptadorOpenAI().preparar(
        modelo="m",
        mensagens=MENSAGENS,
        ferramentas=(),
        parametros=ParametrosDeAmostragem(),
        system="voce e um assistente",
    )
    assert "system" not in requisicao.corpo
    conversa = requisicao.corpo["messages"]
    assert isinstance(conversa, list)
    assert conversa[0] == {"role": "system", "content": "voce e um assistente"}
    assert len(conversa) == len(MENSAGENS) + 1


def test_sem_system_a_conversa_fica_intocada() -> None:
    requisicao = AdaptadorOpenAI().preparar(
        modelo="m", mensagens=MENSAGENS, ferramentas=(), parametros=ParametrosDeAmostragem()
    )
    conversa = requisicao.corpo["messages"]
    assert isinstance(conversa, list)
    assert len(conversa) == len(MENSAGENS)


def test_tools_ausente_quando_nao_ha_ferramenta() -> None:
    requisicao = AdaptadorOpenAI().preparar(
        modelo="m", mensagens=MENSAGENS, ferramentas=(), parametros=ParametrosDeAmostragem()
    )
    assert "tools" not in requisicao.corpo


def test_preparar_e_puro() -> None:
    adaptador = AdaptadorOpenAI()
    argumentos: dict[str, Any] = {
        "modelo": "modelo-x",
        "mensagens": MENSAGENS,
        "ferramentas": FERRAMENTAS,
        "parametros": ParametrosDeAmostragem(temperature=0.3, max_tokens=99, seed=7),
        "system": "cabecalho",
    }
    assert adaptador.preparar(**argumentos) == adaptador.preparar(**argumentos)


# --------------------------------------------------------------------------
# converter: o literal dos argumentos, que e o dado
# --------------------------------------------------------------------------


def test_converter_le_a_chamada_e_o_uso() -> None:
    corpo = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "criar_transferencia",
                                "arguments": '{"valor_centavos": 123456}',
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
        "system_fingerprint": "fp_abc123",
    }
    resposta = converter(corpo)
    assert resposta.finish_reason == "tool_calls"
    assert resposta.prompt_tokens == 11
    assert resposta.completion_tokens == 7
    assert resposta.provider_fingerprint == "fp_abc123"
    assert len(resposta.tool_calls) == 1
    assert resposta.tool_calls[0].name == "criar_transferencia"
    assert resposta.tool_calls[0].args == {"valor_centavos": 123456}


def test_argumentos_invalidos_viram_dado_nao_erro() -> None:
    """O teste que sustenta o módulo.

    `{"valor_centavos": 1.234,56}` não é JSON válido — é exatamente o que um
    modelo faz ao ler um número brasileiro com a régua errada. Esse texto **é** o
    achado da trilha T2.

    Estourar aqui destruiria a evidência e ainda mentiria duas vezes: contaria
    erro do agente como erro de infraestrutura, e tiraria da rodada a única linha
    que explica *como* ele errou.
    """
    literal = '{"valor_centavos": 1.234,56, "favorecido": "Silva"}'
    corpo = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "tool_calls": [
                        {"function": {"name": "criar_transferencia", "arguments": literal}}
                    ]
                },
            }
        ]
    }
    with pytest.raises(json.JSONDecodeError):
        json.loads(literal)

    resposta = converter(corpo)
    chamada = resposta.tool_calls[0]
    assert chamada.args == {}
    assert chamada.raw_arguments == literal


def test_o_literal_e_preservado_byte_a_byte() -> None:
    """Sem reordenar chave, sem reformatar espaço.

    A fidelidade importa porque o espaçamento e a ordem que o modelo escolheu
    são parte do modo de erro.
    """
    literal = '{"b":  2,   "a": "ç"}'
    corpo = {
        "choices": [
            {"message": {"tool_calls": [{"function": {"name": "f", "arguments": literal}}]}}
        ]
    }
    assert converter(corpo).tool_calls[0].raw_arguments == literal


def test_argumento_que_e_json_valido_mas_nao_e_objeto() -> None:
    """`"[1, 2]"` decodifica e mesmo assim não são argumentos nomeados."""
    corpo = {
        "choices": [
            {"message": {"tool_calls": [{"function": {"name": "f", "arguments": "[1, 2]"}}]}}
        ]
    }
    chamada = converter(corpo).tool_calls[0]
    assert chamada.args == {}
    assert chamada.raw_arguments == "[1, 2]"


def test_resposta_de_texto_puro_sem_chamada() -> None:
    corpo = {
        "choices": [{"finish_reason": "stop", "message": {"content": "nao vou fazer isso"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 5},
    }
    resposta = converter(corpo)
    assert resposta.text == "nao vou fazer isso"
    assert resposta.tool_calls == ()
    assert resposta.finish_reason == "stop"


def test_sem_fingerprint_o_campo_fica_none() -> None:
    """Provedor compatível que não expõe o campo. A ausência também é dado."""
    corpo = {"choices": [{"message": {"content": "oi"}}]}
    assert converter(corpo).provider_fingerprint is None


def test_uso_ausente_nao_derruba_a_conversao() -> None:
    """Sem `usage` a rodada continua; o custo por acerto é que fica cego."""
    corpo = {"choices": [{"message": {"content": "oi"}}]}
    resposta = converter(corpo)
    assert resposta.prompt_tokens is None
    assert resposta.completion_tokens is None


def test_tool_calls_com_item_estranho_e_ignorado() -> None:
    corpo = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        "isto nao e objeto",
                        {"function": {"name": "f", "arguments": "{}"}},
                    ]
                }
            }
        ]
    }
    resposta = converter(corpo)
    assert len(resposta.tool_calls) == 1
    assert resposta.tool_calls[0].name == "f"


@pytest.mark.parametrize(
    ("corpo", "trecho"),
    [
        ("nao e objeto", "nao e objeto JSON"),
        ({"choices": "nao e lista"}, "sem `choices`"),
        ({"choices": []}, "sem `choices`"),
        ({"choices": ["nao e objeto"]}, "nao e objeto"),
    ],
)
def test_corpo_malformado_estoura(corpo: object, trecho: str) -> None:
    """Corpo malformado é erro de provedor.

    Ao contrário de argumento inválido, que é comportamento do modelo e vira
    dado. A fronteira entre as duas coisas é o que este arquivo inteiro protege.
    """
    with pytest.raises(ErroDoProvedor, match=trecho):
        converter(corpo)


def test_uso_e_mensagem_de_tipo_errado_nao_quebram() -> None:
    corpo = {"choices": [{"message": "nao e objeto"}], "usage": "nao e objeto"}
    resposta = converter(corpo)
    assert resposta.text is None
    assert resposta.tool_calls == ()


def test_token_booleano_nao_vira_inteiro() -> None:
    """`True` é `int` em Python. Contagem de token booleana é corpo malformado."""
    corpo = {"choices": [{"message": {}}], "usage": {"prompt_tokens": True}}
    assert converter(corpo).prompt_tokens is None


# --------------------------------------------------------------------------
# completar: transporte simulado
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_completar_envia_o_bearer() -> None:
    handler = _sucesso()
    adaptador = AdaptadorOpenAI()
    requisicao = adaptador.preparar(
        modelo="m",
        mensagens=MENSAGENS,
        ferramentas=FERRAMENTAS,
        parametros=ParametrosDeAmostragem(),
    )
    async with _cliente(handler) as cliente:
        resposta = await adaptador.completar(requisicao, chave=CHAVE, cliente=cliente)

    enviada: httpx.Request = handler.ultima
    assert enviada.headers["authorization"] == f"Bearer {CHAVE.get_secret_value()}"
    assert json.loads(enviada.content)["model"] == "m"
    assert resposta.provider_fingerprint == "fp_abc123"


@pytest.mark.asyncio
async def test_a_chave_nunca_entra_no_corpo_enviado() -> None:
    """Barreira 4 do SECURITY.md, conferida no que de fato foi para a rede."""
    handler = _sucesso()
    adaptador = AdaptadorOpenAI()
    requisicao = adaptador.preparar(
        modelo="m", mensagens=MENSAGENS, ferramentas=(), parametros=ParametrosDeAmostragem()
    )
    async with _cliente(handler) as cliente:
        await adaptador.completar(requisicao, chave=CHAVE, cliente=cliente)

    assert CHAVE.get_secret_value() not in handler.ultima.content.decode()
    assert CHAVE.get_secret_value() not in requisicao.literal()


@pytest.mark.asyncio
async def test_erro_http_vira_erro_do_provedor_redigido() -> None:
    """Corpo de erro é território alheio: passa por `redigir` antes de existir."""
    registrar_segredo(CHAVE.get_secret_value())
    try:

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text=f"chave invalida: {CHAVE.get_secret_value()}")

        adaptador = AdaptadorOpenAI()
        requisicao = adaptador.preparar(
            modelo="m", mensagens=MENSAGENS, ferramentas=(), parametros=ParametrosDeAmostragem()
        )
        async with _cliente(handler) as cliente:
            with pytest.raises(ErroDoProvedor) as capturado:
                await adaptador.completar(requisicao, chave=CHAVE, cliente=cliente)

        assert capturado.value.status == 401
        assert CHAVE.get_secret_value() not in str(capturado.value)
    finally:
        esquecer_segredos()


@pytest.mark.asyncio
async def test_falha_de_transporte_vira_erro_do_provedor() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        msg = "conexao caiu"
        raise httpx.ConnectError(msg)

    adaptador = AdaptadorOpenAI()
    requisicao = adaptador.preparar(
        modelo="m", mensagens=MENSAGENS, ferramentas=(), parametros=ParametrosDeAmostragem()
    )
    async with _cliente(handler) as cliente:
        with pytest.raises(ErroDoProvedor, match="falha de transporte"):
            await adaptador.completar(requisicao, chave=CHAVE, cliente=cliente)


@pytest.mark.asyncio
async def test_corpo_nao_json_vira_erro_do_provedor() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>proxy no meio do caminho</html>")

    adaptador = AdaptadorOpenAI()
    requisicao = adaptador.preparar(
        modelo="m", mensagens=MENSAGENS, ferramentas=(), parametros=ParametrosDeAmostragem()
    )
    async with _cliente(handler) as cliente:
        with pytest.raises(ErroDoProvedor, match="corpo nao e JSON"):
            await adaptador.completar(requisicao, chave=CHAVE, cliente=cliente)
