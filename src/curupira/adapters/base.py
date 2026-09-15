"""O contrato que todo adaptador de provedor cumpre. Ver ADR 0002.

Por que `preparar` é separado de `completar`
-------------------------------------------
`preparar` é **puro**: transforma a tarefa no corpo JSON exato que vai para o
provedor, sem tocar na rede. Isso torna testável, sem chave e sem custo, a parte
que mais importa para a medição — o mapeamento entre o nosso modelo de tarefa e
o formato de cada provedor.

Essa separação é o que faz a ADR 0002 valer na prática. O argumento contra usar
uma camada pronta não era segurança, era *confounding*: se a normalização de
schema difere por provedor e ninguém vê, parte do Delta PT-BR passa a medir a
camada em vez do agente. Aqui o corpo literal é um artefato inspecionável,
gravado em cada linha da rodada, e um teste fixa o mapeamento campo a campo.

Headers ficam fora de `RequisicaoPreparada` **de propósito**: é neles que a chave
de API viaja, e este objeto é serializado no arquivo de resultado (SECURITY.md,
barreira 4).
"""

from __future__ import annotations

import json
from typing import Final, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, JsonValue, SecretStr

from curupira.core.result import RespostaCrua
from curupira.core.task import DefinicaoDeFerramenta
from curupira.security import redigir

_CFG = ConfigDict(extra="forbid", frozen=True)

LIMITE_DE_DETALHE: Final = 500
"""Quanto do corpo de erro do provedor entra na mensagem de exceção.

Corpo de erro pode vir com uma página HTML inteira de um proxy no meio do
caminho. Truncar mantém o log legível sem perder a linha que diagnostica.
"""


class ParametrosDeAmostragem(BaseModel):
    """Parâmetros que entram na tupla de reprodutibilidade."""

    model_config = _CFG

    temperature: float = 0.0

    seed: int | None = None
    """Nem todo provedor aceita seed.

    A Messages API da Anthropic, por exemplo, não tem esse parâmetro. Quando o
    adaptador declara `suporta_seed = False`, o registro da execução grava
    `seed_aplicada=False` — porque uma tupla de reprodutibilidade que lista uma
    seed jamais aplicada é uma tupla que mente.
    """

    max_tokens: int = 4096


class Mensagem(BaseModel):
    """Uma mensagem da conversa, no formato interno do Curupira."""

    model_config = _CFG

    role: str
    content: str


class RequisicaoPreparada(BaseModel):
    """O corpo exato que será enviado, sem headers."""

    model_config = _CFG

    url: str
    corpo: dict[str, JsonValue]

    def literal(self) -> str:
        """Serializa o corpo canonicamente, para gravar no registro da rodada.

        Mesma convenção de `curupira.core.hashing`: chaves ordenadas, separadores
        compactos, sem escapar não-ASCII. Assim o corpo gravado é comparável byte
        a byte entre máquinas — e serve de chave de cache estável.

        Returns:
            O corpo em JSON canônico.
        """
        return json.dumps(
            self.corpo,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )


class ErroDoProvedor(RuntimeError):
    """Falha ao falar com o provedor.

    A mensagem passa por `redigir` antes de existir: o corpo de erro de um
    provedor é território alheio, e ecoar território alheio sem filtro é
    exatamente como um segredo acaba num log. Nenhum header entra aqui.
    """

    def __init__(self, provedor: str, status: int | None, detalhe: str) -> None:
        """Monta o erro.

        Args:
            provedor: nome do adaptador.
            status: código HTTP, quando houver.
            detalhe: corpo da resposta de erro. É truncado e redigido.
        """
        self.provedor = provedor
        self.status = status
        self.detalhe = redigir(detalhe[:LIMITE_DE_DETALHE])
        super().__init__(f"{provedor}: HTTP {status}: {self.detalhe}")


class AdaptadorDeModelo(Protocol):
    """Um provedor de modelo.

    Implementações **nunca** registram a chave em log, cache ou resultado. A
    chave é `SecretStr` e o processo que a segura não executa nada que o modelo
    produziu (ADR 0003).
    """

    @property
    def nome(self) -> str:
        """Identificador do provedor, como aparece no leaderboard."""
        ...

    @property
    def versao(self) -> str:
        """Versão do adaptador. Entra na tupla de reprodutibilidade."""
        ...

    @property
    def suporta_seed(self) -> bool:
        """Se o provedor aceita, de fato, uma seed de amostragem."""
        ...

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

        Args:
            modelo: o identificador do modelo no provedor.
            mensagens: a conversa até aqui.
            ferramentas: as ferramentas oferecidas ao modelo.
            parametros: temperatura, seed e limite de tokens.
            system: prompt de sistema, quando a tarefa declarar um.

        Returns:
            A requisição pronta, sem headers.
        """
        ...

    async def completar(
        self,
        requisicao: RequisicaoPreparada,
        *,
        chave: SecretStr,
        cliente: httpx.AsyncClient,
    ) -> RespostaCrua:
        """Envia a requisição e devolve a resposta crua.

        Args:
            requisicao: o corpo preparado.
            chave: a chave de API.
            cliente: cliente HTTP reusado pelo runner.

        Returns:
            A resposta, preservada sem normalização destrutiva.

        Raises:
            ErroDoProvedor: em erro HTTP ou corpo inesperado.
        """
        ...


def mensagens_em_json(mensagens: tuple[Mensagem, ...]) -> list[JsonValue]:
    """Converte a conversa interna para a forma que os três provedores aceitam.

    Args:
        mensagens: a conversa.

    Returns:
        A lista de objetos `{role, content}`.
    """
    saida: list[JsonValue] = []
    for mensagem in mensagens:
        item: dict[str, JsonValue] = {"role": mensagem.role, "content": mensagem.content}
        saida.append(item)
    return saida
