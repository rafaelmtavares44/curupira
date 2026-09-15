"""Adaptador falso: determinístico, sem rede, sem custo.

Não é andaime de teste descartável — é infraestrutura permanente, por três razões:

1. **O CI precisa testar o runner.** Um runner só exercitado contra a API de
   verdade é um runner testado em lugar nenhum: o CI não tem chave, e não deveria
   ter.
2. **Ensaio antes de gastar.** Rodar a suíte inteira contra o falso valida
   caminho de arquivo, concorrência, cache e formato do bruto antes de a primeira
   chamada paga sair.
3. **Linha de base trivial.** As políticas degeneradas de `report/baselines.py`
   precisam de um agente que nunca chama nada, ou que sempre chama a primeira
   ferramenta oferecida. Este é esse agente — e uma trilha onde o agente trivial
   vai bem é uma trilha mal desenhada, o que só se descobre medindo.

Determinístico por construção: a resposta depende **apenas** do corpo da
requisição, via SHA-256. Como a seed entra no corpo, o falso honra seed de
verdade — e por isso pode declarar `suporta_seed = True` sem mentir.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from enum import StrEnum
from typing import Final

import httpx
from pydantic import JsonValue, SecretStr

from curupira.adapters.base import (
    Mensagem,
    ParametrosDeAmostragem,
    RequisicaoPreparada,
    mensagens_em_json,
)
from curupira.core.result import ChamadaObservada, RespostaCrua
from curupira.core.task import DefinicaoDeFerramenta

VERSAO_DO_ADAPTADOR: Final = "0.1.0"
URL_FALSA: Final = "memory://falso"
_DIGITOS_DA_SEMENTE: Final = 8


class Politica(StrEnum):
    """Como o adaptador falso responde."""

    PRIMEIRA_FERRAMENTA = "primeira_ferramenta"
    """Chama a primeira ferramenta oferecida, com argumentos derivados do hash."""

    NUNCA_CHAMA = "nunca_chama"
    """Responde só texto. É a linha de base trivial da deteccao de irrelevancia."""

    SEMPRE_ABSTEM = "sempre_abstem"
    """Chama `pedir_esclarecimento`. Linha de base da abstencao indevida."""

    ROTEIRO = "roteiro"
    """Devolve a resposta declarada para a ultima mensagem do usuario."""


class AdaptadorFalso:
    """Responde de forma determinística, sem tocar na rede."""

    def __init__(
        self,
        politica: Politica = Politica.PRIMEIRA_FERRAMENTA,
        roteiro: Mapping[str, RespostaCrua] | None = None,
    ) -> None:
        """Monta o adaptador.

        Args:
            politica: como responder.
            roteiro: mapa da última mensagem do usuário para a resposta, usado
                com `Politica.ROTEIRO`. Uma mensagem fora do roteiro cai na
                política `PRIMEIRA_FERRAMENTA`.
        """
        self.politica = politica
        self.roteiro: Mapping[str, RespostaCrua] = roteiro or {}

    @property
    def nome(self) -> str:
        """Identificador do provedor, com a política embutida."""
        return f"falso:{self.politica.value}"

    @property
    def versao(self) -> str:
        """Versão do adaptador."""
        return VERSAO_DO_ADAPTADOR

    @property
    def suporta_seed(self) -> bool:
        """A seed entra no corpo e muda o hash, então é honrada de fato."""
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
        """Monta um corpo com a mesma forma de um real, para exercitar o caminho.

        Args:
            modelo: o identificador do modelo.
            mensagens: a conversa.
            ferramentas: as ferramentas oferecidas.
            parametros: temperatura, seed e limite de tokens.
            system: prompt de sistema, quando houver.

        Returns:
            A requisição, com destino em memória.
        """
        corpo: dict[str, JsonValue] = {
            "model": modelo,
            "max_tokens": parametros.max_tokens,
            "temperature": parametros.temperature,
            "seed": parametros.seed,
            "system": system,
            "messages": mensagens_em_json(mensagens),
            "tools": [_ferramenta(f) for f in ferramentas],
        }
        return RequisicaoPreparada(url=URL_FALSA, corpo=corpo)

    async def completar(
        self,
        requisicao: RequisicaoPreparada,
        *,
        chave: SecretStr,
        cliente: httpx.AsyncClient,
    ) -> RespostaCrua:
        """Devolve a resposta determinística da política escolhida.

        Args:
            requisicao: o corpo preparado.
            chave: ignorada — o adaptador falso nunca recebe chave de verdade.
            cliente: ignorado — não há rede.

        Returns:
            A resposta crua.
        """
        del chave, cliente
        return self.responder(requisicao)

    def responder(self, requisicao: RequisicaoPreparada) -> RespostaCrua:
        """Calcula a resposta a partir do corpo, sem efeito colateral e sem I/O.

        Args:
            requisicao: o corpo preparado.

        Returns:
            A resposta crua.
        """
        semente = _semente(requisicao.literal())
        ultima = _ultima_do_usuario(requisicao.corpo)

        if self.politica is Politica.ROTEIRO and ultima in self.roteiro:
            return self.roteiro[ultima]
        if self.politica is Politica.NUNCA_CHAMA:
            return RespostaCrua(text=f"resposta falsa {semente}", finish_reason="end_turn")
        if self.politica is Politica.SEMPRE_ABSTEM:
            return RespostaCrua(
                tool_calls=(
                    ChamadaObservada(
                        name="pedir_esclarecimento",
                        args={"campo_faltante": "indefinido", "pergunta": "pode detalhar?"},
                    ),
                ),
                finish_reason="tool_use",
            )
        return _chamar_a_primeira(requisicao.corpo, semente)


def _ferramenta(definicao: DefinicaoDeFerramenta) -> JsonValue:
    """Espelha o formato da Anthropic, para o corpo falso ter a mesma forma."""
    traduzida: dict[str, JsonValue] = {
        "name": definicao.name,
        "description": definicao.description,
        "input_schema": definicao.parameters,
    }
    return traduzida


def _semente(literal: str) -> int:
    """Deriva um inteiro estável do corpo da requisição.

    Args:
        literal: o corpo em JSON canônico.

    Returns:
        Um inteiro determinístico, igual em qualquer máquina e qualquer versão
        do Python — `hash()` embutido não serve, porque é randomizado por
        processo.
    """
    digest = hashlib.sha256(literal.encode("utf-8")).hexdigest()
    return int(digest[:_DIGITOS_DA_SEMENTE], 16)


def _ultima_do_usuario(corpo: Mapping[str, JsonValue]) -> str:
    """Extrai o conteúdo da última mensagem do corpo preparado.

    Args:
        corpo: o corpo da requisição.

    Returns:
        O texto, ou string vazia se não houver mensagem legível.
    """
    mensagens = corpo.get("messages")
    if not isinstance(mensagens, list) or not mensagens:
        return ""
    alvo = mensagens[-1]
    if not isinstance(alvo, dict):
        return ""
    conteudo = alvo.get("content")
    return conteudo if isinstance(conteudo, str) else ""


def _chamar_a_primeira(corpo: Mapping[str, JsonValue], semente: int) -> RespostaCrua:
    """Chama a primeira ferramenta oferecida, com argumentos derivados da semente.

    Args:
        corpo: o corpo da requisição.
        semente: o inteiro derivado do corpo.

    Returns:
        A resposta crua.
    """
    ferramentas = corpo.get("tools")
    if not isinstance(ferramentas, list) or not ferramentas:
        return RespostaCrua(text="sem ferramentas oferecidas", finish_reason="end_turn")

    primeira = ferramentas[0]
    if not isinstance(primeira, dict):
        return RespostaCrua(text="ferramenta malformada", finish_reason="end_turn")

    schema = primeira.get("input_schema")
    propriedades = schema.get("properties") if isinstance(schema, dict) else None
    args: dict[str, JsonValue] = {}
    if isinstance(propriedades, dict):
        for nome, definicao in propriedades.items():
            tipo = definicao.get("type") if isinstance(definicao, dict) else None
            args[str(nome)] = semente if tipo == "integer" else f"valor-{semente}"

    nome_da_ferramenta = primeira.get("name")
    return RespostaCrua(
        tool_calls=(
            ChamadaObservada(
                name=nome_da_ferramenta if isinstance(nome_da_ferramenta, str) else "",
                args=args,
            ),
        ),
        finish_reason="tool_use",
    )
