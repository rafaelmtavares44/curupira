"""Adaptador para a API Gemini do Google. Ver ADR 0002.

Esqueleto: a v0.1 do leaderboard precisa de mais de um provedor, e o contrato
que ele cumpre ja esta fixado em `base.py`. A implementacao entra na Entrega 5,
depois que o ensaio de ponta a ponta com a Anthropic tiver validado o caminho.
"""

from __future__ import annotations

from typing import Final

import httpx
from pydantic import SecretStr

from curupira.adapters.base import (
    Mensagem,
    ParametrosDeAmostragem,
    RequisicaoPreparada,
)
from curupira.core.result import RespostaCrua
from curupira.core.task import DefinicaoDeFerramenta

VERSAO_DO_ADAPTADOR: Final = "0.1.0"


class AdaptadorGoogle:
    """Fala com a API Gemini do Google."""

    @property
    def nome(self) -> str:
        """Identificador do provedor."""
        return "google"

    @property
    def versao(self) -> str:
        """Versao do adaptador, para a tupla de reprodutibilidade."""
        return VERSAO_DO_ADAPTADOR

    @property
    def suporta_seed(self) -> bool:
        """A confirmar contra a documentacao vigente antes de implementar."""
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
        """Monta o corpo da requisicao. Funcao pura, sem rede.

        Args:
            modelo: o identificador do modelo.
            mensagens: a conversa.
            ferramentas: as ferramentas oferecidas.
            parametros: temperatura, seed e limite de tokens.
            system: prompt de sistema, quando houver.

        Returns:
            A requisicao pronta, sem headers.
        """
        raise NotImplementedError

    async def completar(
        self,
        requisicao: RequisicaoPreparada,
        *,
        chave: SecretStr,
        cliente: httpx.AsyncClient,
    ) -> RespostaCrua:
        """Envia a requisicao e devolve a resposta crua.

        Args:
            requisicao: o corpo preparado.
            chave: a chave de API.
            cliente: cliente HTTP reusado pelo runner.

        Returns:
            A resposta crua.
        """
        raise NotImplementedError
