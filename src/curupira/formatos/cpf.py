"""CPF: 9 dígitos base mais 2 dígitos verificadores.

DV1: pesos 10 a 2 sobre os 9 primeiros. DV2: pesos 11 a 2 sobre os 10 primeiros.
Módulo 11, com resto menor que 2 resultando em dígito 0.

**Armadilha obrigatória:** sequências repetidas (`111.111.111-11`) passam na
aritmética e mesmo assim são inválidas. Sem blacklist, o validador está errado —
e é exatamente esse o teste de propriedade que vale a pena escrever.
"""

from __future__ import annotations

from curupira.core.enums import Corrupcao
from curupira.formatos.base import Gerado


def validar(valor: str) -> bool:
    """Valida um CPF, com ou sem máscara.

    Args:
        valor: o CPF, em qualquer grafia usual.

    Returns:
        `True` se o formato e os dois dígitos verificadores conferem e o valor
        não está na blacklist de sequências repetidas.
    """
    raise NotImplementedError


def gerar(rng_seed: int, *, com_mascara: bool = False) -> Gerado:
    """Gera um CPF válido de forma determinística.

    Args:
        rng_seed: a seed, derivada do `task_id`.
        com_mascara: se verdadeiro, devolve `000.000.000-00`.

    Returns:
        O CPF gerado.
    """
    raise NotImplementedError


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe um CPF válido pelo modo pedido.

    Args:
        valor: um CPF válido.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        O CPF corrompido, que `validar` deve reprovar.

    Raises:
        ValueError: se o modo não se aplicar a CPF.
    """
    raise NotImplementedError
