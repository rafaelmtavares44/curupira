"""Adaptador para a Messages API da Anthropic. Ver ADR 0002.

Assinatura conferida na documentação vigente, não deduzida:

- `POST https://api.anthropic.com/v1/messages`
- headers `x-api-key`, `anthropic-version: 2023-06-01`, `content-type`
- corpo: `model`, `max_tokens` (**obrigatório**), `messages`, `system`,
  `temperature`, `tools`
- ferramenta: `{name, description, input_schema}` — repare em **input_schema**,
  não `parameters`. O mapeamento está em `_ferramenta`, num lugar só, e o teste
  `test_mapeia_parameters_para_input_schema` o fixa.
- resposta: `content` com blocos `text` e `tool_use` (`id`, `name`, `input`),
  `stop_reason` igual a `tool_use` quando há chamada, e `usage` com
  `input_tokens` e `output_tokens`.

**Não há parâmetro de seed.** Por isso `suporta_seed` é `False`: a repetição com
`k` execuções continua medindo não-determinismo, mas a rodada não é reproduzível
bit a bit neste provedor. O registro grava `seed_aplicada=False` em vez de
fingir que uma seed foi honrada.
"""

from __future__ import annotations

import json
from typing import Final

import httpx
from pydantic import JsonValue, SecretStr

from curupira.adapters.base import (
    ErroDoProvedor,
    Mensagem,
    ParametrosDeAmostragem,
    RequisicaoPreparada,
    mensagens_em_json,
)
from curupira.core.result import ChamadaObservada, RespostaCrua
from curupira.core.task import DefinicaoDeFerramenta

URL: Final = "https://api.anthropic.com/v1/messages"
VERSAO_DA_API: Final = "2023-06-01"
VERSAO_DO_ADAPTADOR: Final = "0.1.0"

_TIPO_TEXTO: Final = "text"
_TIPO_CHAMADA: Final = "tool_use"
_PROVEDOR: Final = "anthropic"


def _ferramenta(definicao: DefinicaoDeFerramenta) -> JsonValue:
    """Traduz uma ferramenta do Curupira para o formato da Anthropic.

    É o único ponto do adaptador onde um nome de campo muda. Concentrar aqui é o
    que permite auditar a tradução — o argumento central da ADR 0002.

    Args:
        definicao: a ferramenta como o dataset a declara.

    Returns:
        O objeto `{name, description, input_schema}`.
    """
    traduzida: dict[str, JsonValue] = {
        "name": definicao.name,
        "description": definicao.description,
        "input_schema": definicao.parameters,
    }
    return traduzida


def _texto(valor: object) -> str | None:
    """Devolve o valor se for string, senão `None`."""
    return valor if isinstance(valor, str) else None


def _inteiro(valor: object) -> int | None:
    """Devolve o valor se for inteiro de verdade (`bool` não conta)."""
    if isinstance(valor, bool):
        return None
    return valor if isinstance(valor, int) else None


def _literal(entrada: object) -> str | None:
    """Serializa os argumentos como o modelo os emitiu.

    `raw_arguments` é o que rotula a falha silenciosa: um `"1.234,56"` cru diz
    *como* o agente errou, e é essa informação que vira gráfico no artigo.

    Sem `try`: `entrada` vem sempre de um decodificador JSON, então é
    serializável por construção. Um `except` aqui seria um ramo que nenhum teste
    consegue alcançar honestamente — e ramo inalcançável é ruído que ensina a
    confiar em cobertura que não existe.

    Args:
        entrada: o campo `input` do bloco `tool_use`, já decodificado.

    Returns:
        O JSON literal, ou `None` se não houver entrada.
    """
    if entrada is None:
        return None
    return json.dumps(entrada, ensure_ascii=False, sort_keys=True)


def _bloco_de_chamada(bloco: dict[str, object]) -> ChamadaObservada:
    """Converte um bloco `tool_use` numa chamada observada.

    Args:
        bloco: o bloco `tool_use` da resposta.

    Returns:
        A chamada, com os argumentos crus preservados.
    """
    entrada = bloco.get("input")
    return ChamadaObservada(
        name=_texto(bloco.get("name")) or "",
        args=entrada if isinstance(entrada, dict) else {},
        raw_arguments=_literal(entrada),
    )


def converter(corpo: object) -> RespostaCrua:
    """Converte o corpo de sucesso da Anthropic para `RespostaCrua`.

    Público de propósito: é a função que um terceiro precisa poder rodar sobre um
    corpo gravado para conferir a interpretação que demos à resposta.

    Args:
        corpo: o JSON já decodificado.

    Returns:
        A resposta no formato interno.

    Raises:
        ErroDoProvedor: se o corpo não tiver a forma documentada.
    """
    if not isinstance(corpo, dict):
        msg = f"corpo de sucesso nao e objeto JSON: {type(corpo).__name__}"
        raise ErroDoProvedor(_PROVEDOR, None, msg)

    blocos = corpo.get("content")
    if not isinstance(blocos, list):
        raise ErroDoProvedor(_PROVEDOR, None, "resposta de sucesso sem lista `content`")

    textos: list[str] = []
    chamadas: list[ChamadaObservada] = []
    for bloco in blocos:
        if not isinstance(bloco, dict):
            continue
        tipo = bloco.get("type")
        conteudo = _texto(bloco.get("text"))
        if tipo == _TIPO_TEXTO and conteudo is not None:
            textos.append(conteudo)
        elif tipo == _TIPO_CHAMADA:
            chamadas.append(_bloco_de_chamada(bloco))

    bruto_uso = corpo.get("usage")
    uso = bruto_uso if isinstance(bruto_uso, dict) else {}
    return RespostaCrua(
        text="\n".join(textos) if textos else None,
        tool_calls=tuple(chamadas),
        finish_reason=_texto(corpo.get("stop_reason")),
        prompt_tokens=_inteiro(uso.get("input_tokens")),
        completion_tokens=_inteiro(uso.get("output_tokens")),
    )


class AdaptadorAnthropic:
    """Fala com a Messages API da Anthropic."""

    @property
    def nome(self) -> str:
        """Identificador do provedor."""
        return _PROVEDOR

    @property
    def versao(self) -> str:
        """Versão do adaptador, para a tupla de reprodutibilidade."""
        return VERSAO_DO_ADAPTADOR

    @property
    def suporta_seed(self) -> bool:
        """A Messages API não expõe parâmetro de seed."""
        return False

    def preparar(
        self,
        *,
        modelo: str,
        mensagens: tuple[Mensagem, ...],
        ferramentas: tuple[DefinicaoDeFerramenta, ...],
        parametros: ParametrosDeAmostragem,
        system: str | None = None,
    ) -> RequisicaoPreparada:
        """Monta o corpo da requisição. Função pura, sem rede.

        `seed` **não** entra no corpo: o provedor não tem esse parâmetro, e
        mandá-lo assim mesmo seria um 400 na melhor hipótese e um campo ignorado
        em silêncio na pior.

        Args:
            modelo: o identificador do modelo.
            mensagens: a conversa.
            ferramentas: as ferramentas oferecidas.
            parametros: temperatura e limite de tokens.
            system: prompt de sistema, quando houver.

        Returns:
            A requisição pronta, sem headers.
        """
        corpo: dict[str, JsonValue] = {
            "model": modelo,
            "max_tokens": parametros.max_tokens,
            "temperature": parametros.temperature,
            "messages": mensagens_em_json(mensagens),
        }
        if system is not None:
            corpo["system"] = system
        if ferramentas:
            corpo["tools"] = [_ferramenta(f) for f in ferramentas]
        return RequisicaoPreparada(url=URL, corpo=corpo)

    async def completar(
        self,
        requisicao: RequisicaoPreparada,
        *,
        chave: SecretStr,
        cliente: httpx.AsyncClient,
    ) -> RespostaCrua:
        """Envia a requisição e converte a resposta para o formato interno.

        Args:
            requisicao: o corpo preparado.
            chave: a chave de API.
            cliente: cliente HTTP reusado pelo runner.

        Returns:
            A resposta crua.

        Raises:
            ErroDoProvedor: em erro HTTP, corpo não-JSON ou corpo inesperado.
        """
        try:
            resposta = await cliente.post(
                requisicao.url,
                json=requisicao.corpo,
                headers={
                    "x-api-key": chave.get_secret_value(),
                    "anthropic-version": VERSAO_DA_API,
                    "content-type": "application/json",
                },
            )
        except httpx.HTTPError as erro:
            raise ErroDoProvedor(_PROVEDOR, None, f"falha de transporte: {erro}") from erro

        if resposta.status_code != httpx.codes.OK:
            raise ErroDoProvedor(_PROVEDOR, resposta.status_code, resposta.text)

        try:
            corpo = resposta.json()
        except ValueError as erro:
            raise ErroDoProvedor(_PROVEDOR, resposta.status_code, "corpo nao e JSON") from erro
        return converter(corpo)
