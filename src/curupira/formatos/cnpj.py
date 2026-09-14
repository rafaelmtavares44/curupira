"""CNPJ numérico e alfanumérico.

**Numérico:** 8 de raiz + 4 de ordem + 2 DV. Módulo 11, pesos do DV1
`5,4,3,2,9,8,7,6,5,4,3,2` e do DV2 `6,5,4,3,2,9,8,7,6,5,4,3,2`.

**Alfanumérico (em vigor desde julho de 2026):** os 12 primeiros caracteres podem
ser letras ou dígitos; os 2 DV continuam numéricos. Cada caractere é convertido
para `ASCII - 48` antes da soma ponderada, de modo que `A` vale 17 e `Z` vale 42.
Os pesos são os mesmos.

Por que este módulo é o mais valioso do benchmark: o CNPJ alfanumérico entrou em
vigor em julho de 2026, então é **matematicamente impossível** que esteja bem
representado em dado de treino de qualquer modelo servido hoje. Isso dá um
conjunto de tarefas que mede competência em vez de memorização, imune a
contaminação por construção. Ver o card do dataset.
"""

from __future__ import annotations

from curupira.core.enums import Corrupcao
from curupira.formatos.base import Gerado

OFFSET_ASCII = 48
"""Subtraído do código ASCII de cada caractere no CNPJ alfanumérico."""

PESOS_DV1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
PESOS_DV2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def validar(valor: str) -> bool:
    """Valida um CNPJ, numérico ou alfanumérico, com ou sem máscara.

    Args:
        valor: o CNPJ, em qualquer grafia usual.

    Returns:
        `True` se formato e dígitos verificadores conferem.
    """
    raise NotImplementedError


def gerar(rng_seed: int, *, alfanumerico: bool = False, com_mascara: bool = False) -> Gerado:
    """Gera um CNPJ válido de forma determinística.

    Args:
        rng_seed: a seed, derivada do `task_id`.
        alfanumerico: se verdadeiro, usa o formato vigente desde julho de 2026.
        com_mascara: se verdadeiro, devolve `00.000.000/0000-00`.

    Returns:
        O CNPJ gerado.
    """
    raise NotImplementedError


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe um CNPJ válido pelo modo pedido.

    Modos específicos do alfanumérico que valem tarefa: letra minúscula nos 12
    primeiros caracteres, e DV alfanumérico (o DV é sempre numérico — erro
    clássico de quem leu a mudança por alto).

    Args:
        valor: um CNPJ válido.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        O CNPJ corrompido.

    Raises:
        ValueError: se o modo não se aplicar a CNPJ.
    """
    raise NotImplementedError
