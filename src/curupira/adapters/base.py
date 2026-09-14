"""O contrato que todo adaptador de provedor cumpre."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, SecretStr

from curupira.core.result import RespostaCrua
from curupira.core.task import DefinicaoDeFerramenta


class ParametrosDeAmostragem(BaseModel):
    """Parâmetros que entram na tupla de reprodutibilidade."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: float = 0.0
    seed: int | None = None
    max_tokens: int = 4096


class Mensagem(BaseModel):
    """Uma mensagem da conversa, no formato interno do Curupira."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str
    content: str


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

    async def completar(
        self,
        *,
        mensagens: tuple[Mensagem, ...],
        ferramentas: tuple[DefinicaoDeFerramenta, ...],
        parametros: ParametrosDeAmostragem,
        chave: SecretStr,
    ) -> RespostaCrua:
        """Faz uma chamada ao provedor e devolve a resposta crua.

        Args:
            mensagens: a conversa até aqui.
            ferramentas: as ferramentas oferecidas ao modelo.
            parametros: temperatura, seed e limite de tokens.
            chave: a chave de API.

        Returns:
            A resposta, preservada sem normalização destrutiva.
        """
        ...


def corpo_literal_enviado(
    mensagens: tuple[Mensagem, ...],
    ferramentas: tuple[DefinicaoDeFerramenta, ...],
    parametros: ParametrosDeAmostragem,
) -> str:
    """Devolve o corpo JSON literal que seria enviado ao provedor.

    Existe para que uma rodada seja auditável por terceiros: quem quiser conferir
    o número precisa poder ver exatamente o que foi enviado. Nenhum header entra
    aqui — headers carregam a chave.

    Args:
        mensagens: a conversa.
        ferramentas: as ferramentas oferecidas.
        parametros: os parâmetros de amostragem.

    Returns:
        O corpo JSON, serializado canonicamente.
    """
    raise NotImplementedError
