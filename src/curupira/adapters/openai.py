"""Adaptador para a Chat Completions API da OpenAI. Ver ADR 0002 e ADR 0004.

Assinatura conferida na documentação vigente, não deduzida:

- `POST https://api.openai.com/v1/chat/completions`
- header `Authorization: Bearer <chave>`
- corpo: `model`, `messages`, `temperature`, `max_completion_tokens`, `seed`,
  `tools`
- ferramenta: `{"type": "function", "function": {name, description, parameters}}`
  — repare no **envelope duplo**. A documentação é explícita: *"The `function`
  wrapper is required; you cannot use `type: function` with `name` directly at
  the same level."* Um nível a menos é 400.
- resposta: `choices[0].message` com `content` e `tool_calls`, cada chamada
  `{id, type, function: {name, arguments}}`, e `usage` com `prompt_tokens` e
  `completion_tokens`.

**Por que Chat Completions e não a Responses API.** A OpenAI recomenda a
Responses para projetos novos e mantém a Chat Completions suportada, sem data de
fim. A escolha aqui é do Curupira, não da OpenAI: o formato Chat Completions
virou padrão de fato e é falado por dezenas de provedores. Um adaptador desses
mede muito mais **agentes** — e agente, não modelo, é a unidade deste
leaderboard. Está registrado na ADR 0004, com o gatilho de revisão.

O ACHADO que este adaptador traz, e que afeta a MEDIÇÃO
-------------------------------------------------------
`function.arguments` chega como **string JSON**, não como objeto. Isto é
diferente da Anthropic, onde `input` já vem decodificado.

A consequência não é estética. Um modelo que emita `{"valor_centavos": 1.234,56}`
produz algo que **não é JSON válido**. Na OpenAI esse texto chega inteiro e vira
`raw_arguments` exatamente como o modelo o escreveu — a evidência literal da
falha silenciosa que a trilha T2 existe para caçar. Na Anthropic, o mesmo erro
teria sido rejeitado ou normalizado antes de nós vermos, e `raw_arguments` é
reconstruído por nós a partir do objeto já decodificado.

Ou seja: **a fidelidade de `raw_arguments` não é equivalente entre provedores.**
Isso não afeta o Delta PT-BR, que usa apenas passou/não passou, mas afeta
qualquer comparação de *modo de erro* entre provedores. Está declarado aqui, e
`tests/test_adapters_openai.py::test_argumentos_invalidos_viram_dado_nao_erro`
fixa o comportamento.

Pela mesma razão, argumento que não decodifica **não é erro de transporte**. É
dado. Um `ErroDoProvedor` ali apagaria justamente a linha mais informativa da
rodada e ainda contaminaria a taxa de erro de infraestrutura com erro do agente.

Sobre `seed`: a OpenAI aceita o parâmetro e declara o efeito como *best-effort*.
Por isso `suporta_seed` é `True` — o parâmetro é de fato aplicado — e a resposta
carrega `system_fingerprint`, que é a única evidência verificável de que o
backend não mudou entre duas rodadas. Guardá-lo é o que separa reprodutibilidade
declarada de reprodutibilidade conferível.
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

URL: Final = "https://api.openai.com/v1/chat/completions"
VERSAO_DO_ADAPTADOR: Final = "0.1.0"

_PROVEDOR: Final = "openai"
_TIPO_FUNCAO: Final = "function"
_PAPEL_DO_SISTEMA: Final = "system"


def _ferramenta(definicao: DefinicaoDeFerramenta) -> JsonValue:
    """Traduz uma ferramenta do Curupira para o formato da OpenAI.

    Único ponto do adaptador onde a forma muda, pelo mesmo motivo do adaptador
    da Anthropic: concentrar a tradução é o que a torna auditável.

    O envelope `{"type": "function", "function": {...}}` é obrigatório. O campo
    `strict` **não** é enviado: ele faz a OpenAI forçar a saída a casar com o
    schema, o que é ótimo em produção e desastroso aqui — o benchmark mede
    justamente se o agente acerta o argumento sozinho. Ligar `strict` seria
    pedir ao provedor que consertasse o erro que queremos medir.

    Args:
        definicao: a ferramenta como o dataset a declara.

    Returns:
        O objeto no formato da Chat Completions.
    """
    traduzida: dict[str, JsonValue] = {
        "type": _TIPO_FUNCAO,
        "function": {
            "name": definicao.name,
            "description": definicao.description,
            "parameters": definicao.parameters,
        },
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


def _argumentos(literal: str | None) -> dict[str, JsonValue]:
    """Decodifica os argumentos, tratando texto inválido como dado.

    Ver a nota no topo do módulo: um argumento que não é JSON válido é o achado,
    não a falha. Devolver dicionário vazio e preservar o literal em
    `raw_arguments` mantém a evidência intacta e deixa o pontuador decidir.

    Args:
        literal: o texto de `function.arguments`, como veio.

    Returns:
        Os argumentos decodificados, ou `{}` se o texto não for um objeto JSON.
    """
    if literal is None:
        return {}
    try:
        decodificado = json.loads(literal)
    except ValueError:
        return {}
    return decodificado if isinstance(decodificado, dict) else {}


def _chamada(bruta: dict[str, object]) -> ChamadaObservada:
    """Converte um item de `tool_calls` numa chamada observada.

    Args:
        bruta: o item da lista `tool_calls`.

    Returns:
        A chamada, com o literal dos argumentos preservado byte a byte.
    """
    funcao = bruta.get("function")
    dados = funcao if isinstance(funcao, dict) else {}
    literal = _texto(dados.get("arguments"))
    return ChamadaObservada(
        name=_texto(dados.get("name")) or "",
        args=_argumentos(literal),
        raw_arguments=literal,
    )


def converter(corpo: object) -> RespostaCrua:
    """Converte o corpo de sucesso da OpenAI para `RespostaCrua`.

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

    escolhas = corpo.get("choices")
    if not isinstance(escolhas, list) or not escolhas:
        raise ErroDoProvedor(_PROVEDOR, None, "resposta de sucesso sem `choices`")

    primeira = escolhas[0]
    if not isinstance(primeira, dict):
        raise ErroDoProvedor(_PROVEDOR, None, "item de `choices` nao e objeto")

    bruta_mensagem = primeira.get("message")
    mensagem = bruta_mensagem if isinstance(bruta_mensagem, dict) else {}

    brutas = mensagem.get("tool_calls")
    chamadas = (
        [_chamada(c) for c in brutas if isinstance(c, dict)] if isinstance(brutas, list) else []
    )

    bruto_uso = corpo.get("usage")
    uso = bruto_uso if isinstance(bruto_uso, dict) else {}
    return RespostaCrua(
        text=_texto(mensagem.get("content")),
        tool_calls=tuple(chamadas),
        finish_reason=_texto(primeira.get("finish_reason")),
        prompt_tokens=_inteiro(uso.get("prompt_tokens")),
        completion_tokens=_inteiro(uso.get("completion_tokens")),
        provider_fingerprint=_texto(corpo.get("system_fingerprint")),
    )


class AdaptadorOpenAI:
    """Fala com a API de chat completions da OpenAI."""

    @property
    def nome(self) -> str:
        """Identificador do provedor."""
        return _PROVEDOR

    @property
    def versao(self) -> str:
        """Versao do adaptador, para a tupla de reprodutibilidade."""
        return VERSAO_DO_ADAPTADOR

    @property
    def suporta_seed(self) -> bool:
        """A API da OpenAI aceita `seed`, com reproducibilidade declarada como best-effort."""
        return True

    def preparar(
        self,
        *,
        modelo: str,
        mensagens: tuple[Mensagem, ...],
        ferramentas: tuple[DefinicaoDeFerramenta, ...],
        parametros: ParametrosDeAmostragem,
        system: str | None = None,
    ) -> RequisicaoPreparada:
        """Monta o corpo da requisicao. Funcao pura, sem rede.

        Duas escolhas de campo que valem explicação:

        `max_completion_tokens` em vez de `max_tokens`. O segundo é o nome
        antigo, rejeitado pelos modelos de raciocínio. Usar o nome atual evita
        que o adaptador funcione com metade do catálogo e falhe com a outra.

        O prompt de sistema vira uma **mensagem** de papel `system`, na frente da
        conversa — não um campo de topo como na Anthropic. Os modelos mais novos
        também aceitam o papel `developer`; ficamos em `system`, que todo
        provedor compatível com este formato entende.

        Args:
            modelo: o identificador do modelo.
            mensagens: a conversa.
            ferramentas: as ferramentas oferecidas.
            parametros: temperatura, seed e limite de tokens.
            system: prompt de sistema, quando houver.

        Returns:
            A requisicao pronta, sem headers.
        """
        conversa = mensagens_em_json(mensagens)
        if system is not None:
            cabecalho: dict[str, JsonValue] = {"role": _PAPEL_DO_SISTEMA, "content": system}
            conversa = [cabecalho, *conversa]

        corpo: dict[str, JsonValue] = {
            "model": modelo,
            "max_completion_tokens": parametros.max_tokens,
            "temperature": parametros.temperature,
            "messages": conversa,
        }
        if parametros.seed is not None:
            corpo["seed"] = parametros.seed
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
        """Envia a requisicao e converte a resposta para o formato interno.

        Args:
            requisicao: o corpo preparado.
            chave: a chave de API.
            cliente: cliente HTTP reusado pelo runner.

        Returns:
            A resposta crua.

        Raises:
            ErroDoProvedor: em erro HTTP, corpo nao-JSON ou corpo inesperado.
        """
        try:
            resposta = await cliente.post(
                requisicao.url,
                json=requisicao.corpo,
                headers={
                    "authorization": f"Bearer {chave.get_secret_value()}",
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
