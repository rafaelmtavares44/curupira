"""As formas de fio do MCP, na revisão 2026-07-28.

Escrito à mão, sem SDK, e o motivo **não** é que seja pouca coisa — é que o
Curupira precisa do comportamento oposto ao de um servidor MCP normal.

A especificação manda: *"Servers MUST validate all tool inputs"*. Um servidor
comum valida os argumentos contra o `inputSchema` e **rejeita** o que não bate.
Aqui o argumento errado **é o dado**: um agente que manda `valor_centavos:
123456000` onde o gabarito é `123456` acabou de produzir a falha silenciosa que
o benchmark existe para medir. Um SDK que rejeitasse antes de chegar ao nosso
código apagaria a medição.

Daí a regra que atravessa este módulo e o `servidor`:

    **GRAVA PRIMEIRO, VALIDA DEPOIS.**

Nomes de classe em português, como no resto do projeto; nomes de **campo** em
inglês, porque são as formas do protocolo e não do nosso domínio. Renomeá-los
obrigaria a um mapa de alias que só teria a função de esconder o que vai no fio.

Escopo declarado
----------------
Este módulo cobre o que um servidor de ferramentas precisa: `tools/list`,
`tools/call`, os erros e o `_meta` obrigatório. **Não** cobre resources,
prompts, subscriptions, progress, cancelamento nem o transporte Streamable
HTTP. Nada disso é necessário para medir tool calling, e cada um seria
superfície a manter contra uma especificação que ainda se move.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from curupira import __version__

VERSAO_DO_PROTOCOLO: Final = "2026-07-28"
"""A revisão que este servidor implementa.

Declarada, não inferida. Um cliente que peça outra revisão recebe
`UNSUPPORTED_PROTOCOL_VERSION` em vez de uma conversa que quase funciona.
"""

VERSAO_DO_JSONRPC: Final = "2.0"

PREFIXO_MCP: Final = "io.modelcontextprotocol/"
CHAVE_DA_VERSAO: Final = f"{PREFIXO_MCP}protocolVersion"
CHAVE_DAS_CAPACIDADES: Final = f"{PREFIXO_MCP}clientCapabilities"
CHAVE_DO_CLIENTE: Final = f"{PREFIXO_MCP}clientInfo"
CHAVE_DO_SERVIDOR: Final = f"{PREFIXO_MCP}serverInfo"

RESULTADO_COMPLETO: Final = "complete"
"""O único `resultType` que este servidor emite.

`input_required` pertence ao padrão de múltiplos turnos, que é decisão da
camada de tarefa — ver ADR 0007, pendência da Entrega 14.
"""

# Erros do JSON-RPC 2.0.
ERRO_DE_PARSING: Final = -32700
ERRO_DE_REQUISICAO: Final = -32600
ERRO_DE_METODO: Final = -32601
ERRO_DE_PARAMETROS: Final = -32602

# Erros próprios do MCP, na faixa reservada à especificação.
ERRO_DE_CAPACIDADE: Final = -32021
ERRO_DE_VERSAO: Final = -32022

LIMITE_DA_MENSAGEM: Final = 1_048_576
"""Um mebibyte por linha. Acima disso, `ERRO_DE_REQUISICAO`.

A especificação pede limites explícitos contra exaustão de recurso. Uma tarefa
do Curupira tem poucos quilobytes; um megabyte já é folga de duas ordens de
grandeza, e sem teto um cliente defeituoso derruba o servidor com uma linha.
"""

_CFG = ConfigDict(extra="allow", frozen=True)
"""`extra="allow"` de propósito, ao contrário do resto do projeto.

Nos modelos de domínio o `extra="forbid"` protege contra campo inventado. Aqui
o interlocutor é software de terceiros falando um protocolo em evolução:
recusar um campo que a próxima revisão acrescentar transformaria compatibilidade
futura em erro. Guardamos o que não conhecemos em vez de rejeitar.
"""


class Ferramenta(BaseModel):
    """Uma ferramenta como o `tools/list` a devolve.

    O `inputSchema` recebe, sem conversão nenhuma, o `parameters` que a tarefa
    já declara no YAML — os dois são JSON Schema. Que tenha dado certo assim não
    é sorte: o modelo de dados da Parte A e o MCP foram desenhados para o mesmo
    mundo.
    """

    model_config = _CFG

    name: str
    description: str
    inputSchema: dict[str, JsonValue]  # noqa: N815 - nome de campo do protocolo


class Requisicao(BaseModel):
    """Uma requisição JSON-RPC recebida.

    `id` ausente marca uma **notificação**, que por especificação não recebe
    resposta. `method` e `params` são deixados frouxos de propósito: quem decide
    se a requisição é válida é o servidor, depois de gravar o que chegou.
    """

    model_config = _CFG

    jsonrpc: str = VERSAO_DO_JSONRPC
    id: str | int | None = None
    method: str = ""
    params: dict[str, Any] = Field(default_factory=dict)

    def meta(self) -> dict[str, Any]:
        """Extrai o `_meta` dos parâmetros.

        Returns:
            O mapa de metadados, vazio quando ausente ou malformado.
        """
        bruto = self.params.get("_meta")
        return bruto if isinstance(bruto, dict) else {}


def resultado(corpo: dict[str, JsonValue], identificador: str | int) -> dict[str, JsonValue]:
    """Monta uma resposta de sucesso.

    Args:
        corpo: os campos próprios do resultado, sem `resultType`.
        identificador: o `id` da requisição correspondente.

    Returns:
        A resposta JSON-RPC completa.
    """
    return {
        "jsonrpc": VERSAO_DO_JSONRPC,
        "id": identificador,
        "result": {
            "resultType": RESULTADO_COMPLETO,
            **corpo,
            "_meta": {CHAVE_DO_SERVIDOR: {"name": "curupira", "version": __version__}},
        },
    }


def erro(
    codigo: int,
    mensagem: str,
    identificador: str | int | None = None,
    dados: JsonValue | None = None,
) -> dict[str, JsonValue]:
    """Monta uma resposta de erro.

    Args:
        codigo: o código JSON-RPC ou MCP.
        mensagem: a explicação, legível por humano.
        identificador: o `id` da requisição, ou `None` quando não foi possível lê-lo.
        dados: informação estruturada adicional, quando a especificação pedir.

    Returns:
        A resposta JSON-RPC completa.
    """
    conteudo: dict[str, JsonValue] = {"code": codigo, "message": mensagem}
    if dados is not None:
        conteudo["data"] = dados
    return {"jsonrpc": VERSAO_DO_JSONRPC, "id": identificador, "error": conteudo}
