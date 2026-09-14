"""Adaptador para a API da OpenAI. Ver ADR 0002."""

from __future__ import annotations

from pydantic import SecretStr

from curupira.adapters.base import Mensagem, ParametrosDeAmostragem
from curupira.core.result import RespostaCrua
from curupira.core.task import DefinicaoDeFerramenta

VERSAO_DO_ADAPTADOR = "0.1.0"


class AdaptadorOpenAI:
    """Fala com a API de chat completions da OpenAI."""

    @property
    def nome(self) -> str:
        """Identificador do provedor."""
        return "openai"

    @property
    def versao(self) -> str:
        """Versão do adaptador, para a tupla de reprodutibilidade."""
        return VERSAO_DO_ADAPTADOR

    async def completar(
        self,
        *,
        mensagens: tuple[Mensagem, ...],
        ferramentas: tuple[DefinicaoDeFerramenta, ...],
        parametros: ParametrosDeAmostragem,
        chave: SecretStr,
    ) -> RespostaCrua:
        """Faz uma chamada e devolve a resposta crua.

        Args:
            mensagens: a conversa até aqui.
            ferramentas: as ferramentas oferecidas ao modelo.
            parametros: temperatura, seed e limite de tokens.
            chave: a chave de API.

        Returns:
            A resposta crua.
        """
        raise NotImplementedError
