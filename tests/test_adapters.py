"""Os adaptadores: mapeamento de schema, conversão de resposta e não-vazamento.

Nenhum teste aqui toca a rede. O adaptador da Anthropic é exercitado com
`httpx.MockTransport`, que responde do próprio processo — o que permite fixar o
mapeamento `parameters` → `input_schema` sem chave e sem custo. É esse teste que
sustenta a ADR 0002: a tradução é auditável porque está num lugar só e porque
alguém a confere a cada commit.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import JsonValue, SecretStr

from curupira.adapters.anthropic import (
    URL,
    VERSAO_DA_API,
    AdaptadorAnthropic,
    converter,
)
from curupira.adapters.base import (
    AdaptadorDeModelo,
    ErroDoProvedor,
    Mensagem,
    ParametrosDeAmostragem,
    RequisicaoPreparada,
)
from curupira.adapters.falso import URL_FALSA, AdaptadorFalso, Politica
from curupira.adapters.google import AdaptadorGoogle
from curupira.adapters.openai import AdaptadorOpenAI
from curupira.core.result import RespostaCrua
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
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "modelo-x",
        "stop_reason": "tool_use",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "criar_transferencia",
                "input": {"valor_centavos": 123456, "favorecido": "Silva"},
            }
        ],
        "usage": {"input_tokens": 11, "output_tokens": 7},
    }
    padrao.update(corpo)

    def handler(request: httpx.Request) -> httpx.Response:
        handler.ultima = request  # type: ignore[attr-defined]
        return httpx.Response(200, json=padrao)

    return handler


# --------------------------------------------------------------------------
# Conformidade com o contrato
# --------------------------------------------------------------------------


def test_adaptadores_cumprem_o_protocolo() -> None:
    """A anotação é o teste: o mypy strict checa estruturalmente.

    Se um adaptador perder `suporta_seed` ou mudar a assinatura de `preparar`, a
    verificação de tipos quebra aqui — antes de a rodada quebrar em produção.
    """
    adaptadores: list[AdaptadorDeModelo] = [AdaptadorAnthropic(), AdaptadorFalso()]
    assert [a.versao for a in adaptadores] == ["0.1.0", "0.1.0"]
    assert [a.suporta_seed for a in adaptadores] == [False, True]


# --------------------------------------------------------------------------
# preparar: o mapeamento de schema, que a ADR 0002 existe para tornar auditavel
# --------------------------------------------------------------------------


def test_mapeia_parameters_para_input_schema() -> None:
    """O único campo que muda de nome entre o Curupira e a Anthropic."""
    requisicao = AdaptadorAnthropic().preparar(
        modelo="modelo-x",
        mensagens=MENSAGENS,
        ferramentas=FERRAMENTAS,
        parametros=ParametrosDeAmostragem(),
    )
    ferramentas = requisicao.corpo["tools"]
    assert isinstance(ferramentas, list)
    primeira = ferramentas[0]
    assert isinstance(primeira, dict)
    assert primeira["input_schema"] == FERRAMENTA_TRANSFERENCIA["parameters"]
    assert "parameters" not in primeira
    assert primeira["name"] == "criar_transferencia"


def test_preparar_nao_toca_a_rede_e_e_puro() -> None:
    adaptador = AdaptadorAnthropic()
    argumentos: dict[str, Any] = {
        "modelo": "modelo-x",
        "mensagens": MENSAGENS,
        "ferramentas": FERRAMENTAS,
        "parametros": ParametrosDeAmostragem(temperature=0.3, max_tokens=99),
    }
    assert adaptador.preparar(**argumentos) == adaptador.preparar(**argumentos)


def test_max_tokens_e_temperatura_entram_no_corpo() -> None:
    requisicao = AdaptadorAnthropic().preparar(
        modelo="modelo-x",
        mensagens=MENSAGENS,
        ferramentas=(),
        parametros=ParametrosDeAmostragem(temperature=0.7, max_tokens=256),
    )
    assert requisicao.corpo["max_tokens"] == 256
    assert requisicao.corpo["temperature"] == 0.7
    assert requisicao.url == URL


def test_seed_nao_vai_para_a_anthropic() -> None:
    """A Messages API não tem esse parâmetro; mandá-lo seria inventar API."""
    requisicao = AdaptadorAnthropic().preparar(
        modelo="modelo-x",
        mensagens=MENSAGENS,
        ferramentas=(),
        parametros=ParametrosDeAmostragem(seed=42),
    )
    assert "seed" not in requisicao.corpo


def test_system_so_aparece_quando_a_tarefa_declara() -> None:
    adaptador = AdaptadorAnthropic()
    sem = adaptador.preparar(
        modelo="m", mensagens=MENSAGENS, ferramentas=(), parametros=ParametrosDeAmostragem()
    )
    com = adaptador.preparar(
        modelo="m",
        mensagens=MENSAGENS,
        ferramentas=(),
        parametros=ParametrosDeAmostragem(),
        system="voce e um assistente",
    )
    assert "system" not in sem.corpo
    assert com.corpo["system"] == "voce e um assistente"


def test_tools_ausente_quando_nao_ha_ferramenta() -> None:
    """`tools: []` e ausência de `tools` não são a mesma coisa para o modelo."""
    requisicao = AdaptadorAnthropic().preparar(
        modelo="m", mensagens=MENSAGENS, ferramentas=(), parametros=ParametrosDeAmostragem()
    )
    assert "tools" not in requisicao.corpo


def test_literal_e_canonico_e_estavel() -> None:
    a = RequisicaoPreparada(url="u", corpo={"b": 1, "a": "ç"})
    b = RequisicaoPreparada(url="u", corpo={"a": "ç", "b": 1})
    assert a.literal() == b.literal() == '{"a":"ç","b":1}'


# --------------------------------------------------------------------------
# completar: transporte simulado
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_completar_envia_os_headers_documentados() -> None:
    handler = _sucesso()
    requisicao = AdaptadorAnthropic().preparar(
        modelo="m",
        mensagens=MENSAGENS,
        ferramentas=FERRAMENTAS,
        parametros=ParametrosDeAmostragem(),
    )
    async with _cliente(handler) as cliente:
        await AdaptadorAnthropic().completar(requisicao, chave=CHAVE, cliente=cliente)

    enviada: httpx.Request = handler.ultima
    assert enviada.headers["x-api-key"] == CHAVE.get_secret_value()
    assert enviada.headers["anthropic-version"] == VERSAO_DA_API
    assert json.loads(enviada.content)["model"] == "m"


@pytest.mark.asyncio
async def test_completar_converte_tool_use() -> None:
    requisicao = AdaptadorAnthropic().preparar(
        modelo="m",
        mensagens=MENSAGENS,
        ferramentas=FERRAMENTAS,
        parametros=ParametrosDeAmostragem(),
    )
    async with _cliente(_sucesso()) as cliente:
        resposta = await AdaptadorAnthropic().completar(requisicao, chave=CHAVE, cliente=cliente)

    assert resposta.finish_reason == "tool_use"
    assert len(resposta.tool_calls) == 1
    chamada = resposta.tool_calls[0]
    assert chamada.name == "criar_transferencia"
    assert chamada.args["valor_centavos"] == 123456
    assert resposta.prompt_tokens == 11
    assert resposta.completion_tokens == 7


@pytest.mark.asyncio
async def test_erro_http_vira_erro_do_provedor() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(429, text="rate limited")

    requisicao = AdaptadorAnthropic().preparar(
        modelo="m", mensagens=MENSAGENS, ferramentas=(), parametros=ParametrosDeAmostragem()
    )
    async with _cliente(handler) as cliente:
        with pytest.raises(ErroDoProvedor) as capturado:
            await AdaptadorAnthropic().completar(requisicao, chave=CHAVE, cliente=cliente)
    assert capturado.value.status == 429


@pytest.mark.asyncio
async def test_falha_de_transporte_vira_erro_do_provedor() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sem rota", request=request)

    requisicao = AdaptadorAnthropic().preparar(
        modelo="m", mensagens=MENSAGENS, ferramentas=(), parametros=ParametrosDeAmostragem()
    )
    async with _cliente(handler) as cliente:
        with pytest.raises(ErroDoProvedor, match="transporte"):
            await AdaptadorAnthropic().completar(requisicao, chave=CHAVE, cliente=cliente)


@pytest.mark.asyncio
async def test_corpo_nao_json_vira_erro_do_provedor() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, text="<html>proxy</html>")

    requisicao = AdaptadorAnthropic().preparar(
        modelo="m", mensagens=MENSAGENS, ferramentas=(), parametros=ParametrosDeAmostragem()
    )
    async with _cliente(handler) as cliente:
        with pytest.raises(ErroDoProvedor, match="nao e JSON"):
            await AdaptadorAnthropic().completar(requisicao, chave=CHAVE, cliente=cliente)


@pytest.mark.asyncio
async def test_a_mensagem_de_erro_nao_carrega_a_chave() -> None:
    """Defesa em profundidade: o corpo de erro é território do provedor.

    Se um proxy ecoar o header de autorização no corpo — e proxies fazem isso —
    a mensagem de erro seria o caminho mais curto até o log.
    """
    segredo = "chave-de-teste-nao-e-segredo-de-verdade"
    registrar_segredo(segredo)
    try:

        def handler(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(400, text=f"erro com {segredo} ecoado")

        requisicao = AdaptadorAnthropic().preparar(
            modelo="m", mensagens=MENSAGENS, ferramentas=(), parametros=ParametrosDeAmostragem()
        )
        async with _cliente(handler) as cliente:
            with pytest.raises(ErroDoProvedor) as capturado:
                await AdaptadorAnthropic().completar(requisicao, chave=CHAVE, cliente=cliente)
        assert segredo not in str(capturado.value)
        assert "[REDIGIDO]" in str(capturado.value)
    finally:
        esquecer_segredos()


# --------------------------------------------------------------------------
# converter: as formas de resposta que a documentacao descreve
# --------------------------------------------------------------------------


def test_converter_junta_blocos_de_texto() -> None:
    resposta = converter(
        {
            "content": [
                {"type": "text", "text": "primeira"},
                {"type": "text", "text": "segunda"},
            ],
            "stop_reason": "end_turn",
        }
    )
    assert resposta.text == "primeira\nsegunda"
    assert resposta.tool_calls == ()


def test_converter_preserva_os_argumentos_crus() -> None:
    """`raw_arguments` é o que rotula a falha silenciosa."""
    resposta = converter(
        {
            "content": [
                {"type": "tool_use", "name": "f", "input": {"valor": "1.234,56"}},
            ]
        }
    )
    assert resposta.tool_calls[0].raw_arguments == '{"valor": "1.234,56"}'


def test_converter_ignora_bloco_desconhecido() -> None:
    resposta = converter({"content": ["lixo", {"type": "thinking"}], "stop_reason": "end_turn"})
    assert resposta.text is None
    assert resposta.tool_calls == ()


def test_converter_tolera_usage_ausente_ou_torto() -> None:
    resposta = converter({"content": [], "usage": "nao e objeto"})
    assert resposta.prompt_tokens is None
    assert resposta.completion_tokens is None


def test_converter_recusa_corpo_sem_content() -> None:
    with pytest.raises(ErroDoProvedor, match="content"):
        converter({"stop_reason": "end_turn"})


def test_converter_recusa_corpo_que_nao_e_objeto() -> None:
    with pytest.raises(ErroDoProvedor, match="nao e objeto"):
        converter([1, 2, 3])


def test_converter_recusa_bool_como_contagem_de_tokens() -> None:
    """`isinstance(True, int)` é verdadeiro; um `True` em `input_tokens` é lixo."""
    resposta = converter({"content": [], "usage": {"input_tokens": True}})
    assert resposta.prompt_tokens is None


def test_converter_sem_input_nao_inventa_raw_arguments() -> None:
    resposta = converter({"content": [{"type": "tool_use", "name": "f"}]})
    assert resposta.tool_calls[0].raw_arguments is None
    assert resposta.tool_calls[0].args == {}


# --------------------------------------------------------------------------
# Esqueletos dos outros provedores
# --------------------------------------------------------------------------


def test_o_esqueleto_do_google_declara_identidade_e_estoura_alto() -> None:
    """O contrato já vale; a implementação está parada por decisão, não esquecimento.

    O Gemini tem duas APIs vigentes — `generateContent`, suportada, e
    Interactions, recomendada desde jun/2026 — e a escolha entre elas ainda não
    foi feita. Ver ADR 0004.

    Enquanto isso, o esqueleto **estoura**. Um esqueleto que devolvesse resposta
    vazia produziria uma coluna de zeros no leaderboard com cara de medição, o
    que é pior do que coluna nenhuma: zero se lê como "o agente errou tudo".
    """
    pendente: AdaptadorDeModelo = AdaptadorGoogle()
    assert pendente.nome == "google"
    assert pendente.versao == "0.1.0"
    assert pendente.suporta_seed is False
    with pytest.raises(NotImplementedError):
        pendente.preparar(
            modelo="m",
            mensagens=MENSAGENS,
            ferramentas=(),
            parametros=ParametrosDeAmostragem(),
        )


def test_a_openai_deixou_de_ser_esqueleto() -> None:
    """Contraparte do teste acima: o que saiu da lista de pendências funciona.

    Sem este par, apagar uma linha de `stubs_pendentes.txt` sem implementar nada
    passaria batido — o inventário confere a árvore, não o comportamento.
    """
    requisicao = AdaptadorOpenAI().preparar(
        modelo="m", mensagens=MENSAGENS, ferramentas=(), parametros=ParametrosDeAmostragem()
    )
    assert requisicao.corpo["model"] == "m"


# --------------------------------------------------------------------------
# Adaptador falso
# --------------------------------------------------------------------------


def _preparar_falso(adaptador: AdaptadorFalso, **extras: Any) -> RequisicaoPreparada:
    argumentos: dict[str, Any] = {
        "modelo": "falso-1",
        "mensagens": MENSAGENS,
        "ferramentas": FERRAMENTAS,
        "parametros": ParametrosDeAmostragem(),
    }
    argumentos.update(extras)
    return adaptador.preparar(**argumentos)


def test_falso_e_deterministico() -> None:
    adaptador = AdaptadorFalso()
    requisicao = _preparar_falso(adaptador)
    assert adaptador.responder(requisicao) == adaptador.responder(requisicao)


def test_falso_muda_com_a_seed() -> None:
    """Se a seed não mudasse a saída, `suporta_seed = True` seria mentira."""
    adaptador = AdaptadorFalso()
    a = adaptador.responder(_preparar_falso(adaptador, parametros=ParametrosDeAmostragem(seed=1)))
    b = adaptador.responder(_preparar_falso(adaptador, parametros=ParametrosDeAmostragem(seed=2)))
    assert a != b


def test_falso_chama_a_primeira_ferramenta() -> None:
    adaptador = AdaptadorFalso(Politica.PRIMEIRA_FERRAMENTA)
    resposta = adaptador.responder(_preparar_falso(adaptador))
    assert resposta.tool_calls[0].name == "criar_transferencia"
    assert isinstance(resposta.tool_calls[0].args["valor_centavos"], int)
    assert isinstance(resposta.tool_calls[0].args["favorecido"], str)


def test_falso_nunca_chama() -> None:
    adaptador = AdaptadorFalso(Politica.NUNCA_CHAMA)
    resposta = adaptador.responder(_preparar_falso(adaptador))
    assert resposta.tool_calls == ()
    assert resposta.text is not None


def test_falso_sempre_abstem() -> None:
    adaptador = AdaptadorFalso(Politica.SEMPRE_ABSTEM)
    resposta = adaptador.responder(_preparar_falso(adaptador))
    assert resposta.tool_calls[0].name == "pedir_esclarecimento"


def test_falso_segue_o_roteiro() -> None:
    combinada = RespostaCrua(text="combinado", finish_reason="end_turn")
    adaptador = AdaptadorFalso(Politica.ROTEIRO, {MENSAGENS[0].content: combinada})
    assert adaptador.responder(_preparar_falso(adaptador)) == combinada


def test_falso_fora_do_roteiro_cai_na_primeira_ferramenta() -> None:
    adaptador = AdaptadorFalso(Politica.ROTEIRO, {"outra coisa": RespostaCrua(text="x")})
    resposta = adaptador.responder(_preparar_falso(adaptador))
    assert resposta.tool_calls[0].name == "criar_transferencia"


def test_falso_sem_ferramentas() -> None:
    adaptador = AdaptadorFalso()
    resposta = adaptador.responder(_preparar_falso(adaptador, ferramentas=()))
    assert resposta.tool_calls == ()
    assert resposta.text == "sem ferramentas oferecidas"


def test_falso_tolera_corpo_torto() -> None:
    """O falso nunca estoura: um estouro dele seria confundido com falha do agente."""
    adaptador = AdaptadorFalso()
    tortos: list[dict[str, JsonValue]] = [
        {"messages": ["nao e objeto"], "tools": [{"name": "f"}]},
        {"messages": [{"content": 1}], "tools": ["nao e objeto"]},
        {"tools": [{"name": "f", "input_schema": "nao e objeto"}]},
    ]
    for corpo in tortos:
        resposta = adaptador.responder(RequisicaoPreparada(url="memory://x", corpo=corpo))
        assert resposta.text is not None or resposta.tool_calls


def test_falso_sem_mensagens() -> None:
    adaptador = AdaptadorFalso(Politica.ROTEIRO, {"": RespostaCrua(text="vazio")})
    resposta = adaptador.responder(_preparar_falso(adaptador, mensagens=()))
    assert resposta.text == "vazio"


def test_falso_nomeia_a_politica() -> None:
    assert AdaptadorFalso(Politica.NUNCA_CHAMA).nome == "falso:nunca_chama"


@pytest.mark.asyncio
async def test_falso_completar_nao_usa_cliente() -> None:
    """Passar `None` como cliente prova que não há rede no caminho."""
    adaptador = AdaptadorFalso()
    requisicao = _preparar_falso(adaptador)
    resposta = await adaptador.completar(requisicao, chave=SecretStr(""), cliente=None)  # type: ignore[arg-type]
    assert resposta.tool_calls
    assert requisicao.url == URL_FALSA
