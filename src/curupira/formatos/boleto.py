"""Linha digitável do boleto: 47 dígitos, e o código de barras de 44.

Os 47 dígitos são 43 de dados mais 4 verificadores, distribuídos em cinco campos:

- Campo 1 (10): banco (3) + moeda (1) + posições 20-24 do código de barras (5)
  + DV por módulo 10.
- Campo 2 (11): posições 25-34 do código de barras + DV por módulo 10.
- Campo 3 (11): posições 35-44 do código de barras + DV por módulo 10.
- Campo 4 (1): DV geral do código de barras, por módulo 11.
- Campo 5 (14): fator de vencimento (4) + valor em centavos (10), sem formatação.

**FATOR DE VENCIMENTO — a melhor armadilha de falha silenciosa do projeto.**
A data-base original era 07/10/1997. O fator atingiu o limite 9999 em 21/02/2025 e
foi reiniciado para 1000 em 22/02/2025, seguindo o incremento diário.

Um agente que use a data-base antiga para decodificar o fator 1569 responde
23/01/2002 para um boleto que vence em 14/09/2026: erra por cerca de 24 anos, com
confiança total e sem sinal nenhum. Rótulo: `usou_data_base_antiga_1997`.
"""

from __future__ import annotations

from datetime import date

from curupira.core.enums import Corrupcao
from curupira.formatos.base import Gerado

DATA_BASE_ANTIGA = date(1997, 10, 7)
"""Data-base original. Mantida aqui para GERAR a resposta errada rotulada."""

DATA_BASE_NOVA = date(2025, 2, 22)
"""Data em que o fator foi reiniciado para 1000."""

FATOR_NO_REINICIO = 1000


def fator_para_data(fator: int) -> date:
    """Converte um fator de vencimento em data, pela regra vigente.

    Args:
        fator: o fator de 4 dígitos.

    Returns:
        A data de vencimento.
    """
    raise NotImplementedError


def data_para_fator(vencimento: date) -> int:
    """Converte uma data de vencimento em fator, pela regra vigente.

    Args:
        vencimento: a data.

    Returns:
        O fator de 4 dígitos.

    Raises:
        ValueError: se a data cair fora da faixa representável.
    """
    raise NotImplementedError


def validar(linha: str) -> bool:
    """Valida uma linha digitável de 47 dígitos.

    Confere os três DVs de campo (módulo 10) e o DV geral (módulo 11).

    Args:
        linha: a linha digitável, com ou sem máscara.

    Returns:
        `True` se todos os dígitos verificadores conferem.
    """
    raise NotImplementedError


def gerar(
    rng_seed: int,
    *,
    vencimento: date,
    valor_centavos: int,
    banco: str = "001",
    com_mascara: bool = False,
) -> Gerado:
    """Gera uma linha digitável válida.

    Args:
        rng_seed: a seed.
        vencimento: a data de vencimento.
        valor_centavos: o valor, em centavos, sem formatação.
        banco: código do banco, 3 dígitos.
        com_mascara: se verdadeiro, aplica pontos e espaços da grafia usual.

    Returns:
        A linha digitável gerada.
    """
    raise NotImplementedError


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe uma linha digitável pelo modo pedido.

    O modo `TRANSPOSICAO` aplicado a um campo protegido por módulo 10 é
    deliberadamente escolhido: o módulo 10 não detecta todas as transposições, e
    um agente que confia no DV de campo passa direto.

    Args:
        valor: uma linha digitável válida.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        A linha corrompida.

    Raises:
        ValueError: se o modo não se aplicar à linha digitável.
    """
    raise NotImplementedError
