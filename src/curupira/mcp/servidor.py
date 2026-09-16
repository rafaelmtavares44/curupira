"""Servidor MCP que serve as ferramentas de uma tarefa e observa as chamadas.

O que isto resolve
------------------
Até aqui o Curupira media **modelo**: o `run` fala direto com a API do provedor,
e cada provedor novo custa um adaptador. O escopo, porém, promete leaderboard de
**agente** — modelo mais framework mais prompt mais ferramentas.

Aqui a direção se inverte. Em vez de o Curupira chamar o agente, **o agente
chama o Curupira**. Ele conecta num servidor MCP, vê as ferramentas que a tarefa
declara, e faz o que a mensagem do usuário pede. O Curupira nunca sabe qual
framework está do outro lado, e não precisa saber: CrewAI, LangGraph ou qualquer
coisa que fale MCP entram pelo mesmo buraco. O custo de integração deixa de ser
`N x M` e passa a ser `N + M`.

A regra que governa tudo: GRAVA PRIMEIRO
-----------------------------------------
Um servidor MCP normal valida os argumentos e rejeita o que não bate com o
`inputSchema`. Este faz o contrário, e é o motivo de não usarmos SDK: **o
argumento errado é a medição**. Um agente que manda `valor_centavos: 123456000`
onde o gabarito é `123456` acabou de errar por mil vezes, em silêncio, do jeito
exato que a tarefa foi desenhada para capturar.

Duas consequências práticas:

- **Ferramenta inexistente é gravada.** Chamar uma ferramenta que a tarefa não
  declara é alucinação do agente, não defeito do cliente MCP. O servidor
  registra a chamada **e** devolve o erro de protocolo que a especificação
  manda. O dado não se perde só porque a resposta é um erro.
- **Erro de envelope não é gravado.** `_meta` ausente, versão de protocolo
  incompatível, JSON quebrado: isso é integração malfeita de quem avalia, não
  comportamento do agente. Contaminaria a medição com ruído do harness.

Por que a resposta da ferramenta não tem idioma
-----------------------------------------------
O servidor não executa nada; precisa apenas devolver algo que não trave o
agente. Essa resposta é `{"status": "ok"}` — **sem palavra nenhuma em português
ou inglês**, e isso é deliberado.

Uma confirmação em português apareceria só na versão PT-BR do par e mudaria o
contexto que o agente carrega para os turnos seguintes. O Delta PT-BR estaria
medindo, em parte, a nossa própria resposta. É a mesma classe de assimetria que
a ADR 0005 D3 registrou na notação numérica, e aqui dava para eliminar de vez.

Escopo desta entrega
--------------------
Transporte **stdio** apenas — é o que os clientes locais usam, e é uma linha
JSON por mensagem. O Streamable HTTP traz SSE, autorização e sessões de stream:
superfície demais para provar uma hipótese.

A tarefa termina quando o stdin fecha. É provisório e está declarado como tal:
o MCP é stateless por especificação (*"no protocol-level session"*), então ele
não sabe dizer quando o agente terminou. Distinguir "não chamou nada" de "ainda
não chamou" é trabalho da camada de tarefa, que a ADR 0007 deixou para a
Entrega 14.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Final

from pydantic import JsonValue, ValidationError

from curupira.core.result import ChamadaObservada
from curupira.core.task import Tarefa
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
    VERSAO_DO_JSONRPC,
    VERSAO_DO_PROTOCOLO,
    Ferramenta,
    Requisicao,
    erro,
    resultado,
)

METODO_LISTAR: Final = "tools/list"
METODO_CHAMAR: Final = "tools/call"

RESPOSTA_DA_FERRAMENTA: Final[dict[str, JsonValue]] = {"status": "ok"}
"""Confirmação sem idioma. Ver a seção do módulo sobre por que isso importa."""


class ServidorDeTarefa:
    """Serve as ferramentas de UMA tarefa e guarda as chamadas observadas.

    Uma instância por tarefa, de propósito: misturar tarefas num servidor só
    exigiria correlacionar chamada com tarefa, e o MCP não tem sessão para
    ancorar isso.
    """

    def __init__(self, tarefa: Tarefa) -> None:
        """Prepara o servidor para uma tarefa.

        Args:
            tarefa: a tarefa cujas ferramentas serão servidas.
        """
        self._tarefa = tarefa
        self._chamadas: list[ChamadaObservada] = []

    @property
    def chamadas(self) -> tuple[ChamadaObservada, ...]:
        """As chamadas observadas até agora, na ordem em que chegaram.

        A ordem é o dado da trilha T6, onde o `expect.kind == "sequence"` cobra
        que os passos aconteçam na sequência certa.
        """
        return tuple(self._chamadas)

    def _ferramentas(self) -> list[JsonValue]:
        """Converte as ferramentas da tarefa para a forma do `tools/list`.

        Returns:
            As ferramentas em ordem determinística, como a especificação pede.
        """
        return [
            Ferramenta(
                name=definicao.name,
                description=definicao.description,
                inputSchema=definicao.parameters,
            ).model_dump()
            for definicao in self._tarefa.context.tools
        ]

    def _registrar(self, nome: str, argumentos: JsonValue) -> None:
        """Grava a chamada **antes** de qualquer julgamento sobre ela.

        Args:
            nome: o nome da ferramenta, como o agente escreveu — inclusive
                quando a ferramenta não existe.
            argumentos: os argumentos como chegaram no fio.
        """
        args = argumentos if isinstance(argumentos, dict) else {}
        self._chamadas.append(
            ChamadaObservada(
                name=nome,
                args=args,
                raw_arguments=json.dumps(argumentos, ensure_ascii=False, sort_keys=True),
            )
        )

    def _chamar(self, requisicao: Requisicao, identificador: str | int) -> dict[str, JsonValue]:
        """Atende `tools/call`: grava primeiro, responde depois.

        Args:
            requisicao: a requisição já parseada.
            identificador: o `id` da requisição, já sabidamente presente.

        Returns:
            A resposta JSON-RPC.
        """
        nome = requisicao.params.get("name")
        if not isinstance(nome, str):
            return erro(
                ERRO_DE_PARAMETROS,
                "tools/call exige 'name' textual",
                identificador,
            )

        self._registrar(nome, requisicao.params.get("arguments", {}))

        conhecidas = {d.name for d in self._tarefa.context.tools}
        if nome not in conhecidas:
            # Ja gravada acima: alucinacao de ferramenta e comportamento do
            # agente, e some do dado se o erro vier antes do registro.
            return erro(ERRO_DE_PARAMETROS, f"ferramenta desconhecida: {nome}", identificador)

        texto = json.dumps(RESPOSTA_DA_FERRAMENTA, ensure_ascii=False, sort_keys=True)
        return resultado(
            {
                "content": [{"type": "text", "text": texto}],
                "structuredContent": dict(RESPOSTA_DA_FERRAMENTA),
                "isError": False,
            },
            identificador,
        )

    def _envelope_invalido(self, requisicao: Requisicao) -> dict[str, JsonValue] | None:
        """Confere o que a especificação exige de toda requisição.

        Args:
            requisicao: a requisição parseada.

        Returns:
            A resposta de erro, ou `None` quando o envelope está correto.
        """
        identificador = requisicao.id
        if requisicao.jsonrpc != VERSAO_DO_JSONRPC:
            return erro(
                ERRO_DE_REQUISICAO,
                f"jsonrpc precisa ser '{VERSAO_DO_JSONRPC}'",
                identificador,
            )

        meta = requisicao.meta()
        versao = meta.get(CHAVE_DA_VERSAO)
        if not isinstance(versao, str):
            return erro(
                ERRO_DE_PARAMETROS,
                f"_meta.{CHAVE_DA_VERSAO} e obrigatorio em toda requisicao",
                identificador,
            )
        if versao != VERSAO_DO_PROTOCOLO:
            return erro(
                ERRO_DE_VERSAO,
                f"este servidor fala {VERSAO_DO_PROTOCOLO}, nao {versao}",
                identificador,
                {"supported": [VERSAO_DO_PROTOCOLO]},
            )
        if CHAVE_DAS_CAPACIDADES not in meta:
            return erro(
                ERRO_DE_CAPACIDADE,
                f"_meta.{CHAVE_DAS_CAPACIDADES} e obrigatorio em toda requisicao",
                identificador,
                {"requiredCapabilities": [CHAVE_DAS_CAPACIDADES]},
            )
        return None

    def _parsear(self, linha: str) -> Requisicao | dict[str, JsonValue]:
        """Transforma uma linha do fio em requisição, ou na resposta de erro.

        Args:
            linha: a mensagem crua.

        Returns:
            A requisição parseada, ou a resposta de erro já montada.
        """
        if len(linha.encode("utf-8")) > LIMITE_DA_MENSAGEM:
            return erro(ERRO_DE_REQUISICAO, "mensagem acima do limite aceito")
        try:
            bruto = json.loads(linha)
        except ValueError:
            return erro(ERRO_DE_PARSING, "json invalido")
        if not isinstance(bruto, dict):
            return erro(ERRO_DE_REQUISICAO, "a mensagem precisa ser um objeto")
        try:
            return Requisicao.model_validate(bruto)
        except ValidationError as falha:
            return erro(ERRO_DE_REQUISICAO, f"requisicao malformada: {falha.error_count()} campos")

    def _despachar(self, requisicao: Requisicao, identificador: str | int) -> dict[str, JsonValue]:
        """Encaminha uma requisição já validada ao método correspondente.

        Args:
            requisicao: a requisição com envelope conferido.
            identificador: o `id` da requisição, já sabidamente presente.

        Returns:
            A resposta JSON-RPC.
        """
        if requisicao.method == METODO_LISTAR:
            return resultado({"tools": self._ferramentas()}, identificador)
        if requisicao.method == METODO_CHAMAR:
            return self._chamar(requisicao, identificador)
        return erro(ERRO_DE_METODO, f"metodo nao suportado: {requisicao.method}", identificador)

    def atender(self, linha: str) -> dict[str, JsonValue] | None:
        """Processa uma linha do fio e devolve a resposta.

        Puro de propósito: não toca em arquivo nem em descritor. O laço de
        stdio mora em `servir`, e é o que permite exercitar o protocolo inteiro
        em teste sem subir processo.

        Args:
            linha: uma mensagem JSON-RPC, sem o terminador.

        Returns:
            A resposta a escrever, ou `None` quando a mensagem é notificação —
            que por especificação não recebe resposta.
        """
        parseada = self._parsear(linha)
        if not isinstance(parseada, Requisicao):
            return parseada

        # `id` ausente marca notificacao, que por especificacao nao recebe
        # resposta. Testar aqui tambem estreita o tipo para o resto do caminho,
        # sem `assert` -- que sumiria sob `python -O` e deixaria o servidor
        # montando resposta com `id: null`.
        identificador = parseada.id
        if identificador is None:
            return None

        problema = self._envelope_invalido(parseada)
        if problema is not None:
            return problema
        return self._despachar(parseada, identificador)

    def servir(self, entrada: Iterable[str]) -> Iterator[str]:
        """Roda o laço do transporte stdio.

        Args:
            entrada: as linhas recebidas, uma mensagem por linha.

        Yields:
            As linhas a escrever de volta, já serializadas.
        """
        for linha in entrada:
            if not linha.strip():
                continue
            resposta = self.atender(linha)
            if resposta is not None:
                yield json.dumps(resposta, ensure_ascii=False)
