"""Placa veicular: Mercosul `LLLNLNN` e o formato antigo `LLLNNNN`.

Sem dígito verificador; a validação é expressão regular mais regras de conjunto
de caracteres. Placa identifica um veículo, e por tabela um proprietário, então
segue o mesmo tratamento de risco do CNPJ: nunca combinada com nome e endereço.
"""

from __future__ import annotations

from curupira.core.enums import Corrupcao
from curupira.formatos.base import Gerado


def validar(valor: str) -> bool:
    """Valida uma placa, nos formatos Mercosul e antigo.

    Args:
        valor: a placa, com ou sem hífen.

    Returns:
        `True` se casa com um dos formatos aceitos.
    """
    raise NotImplementedError


def gerar(rng_seed: int, *, mercosul: bool = True) -> Gerado:
    """Gera uma placa.

    Args:
        rng_seed: a seed.
        mercosul: formato Mercosul (`ABC1D23`) ou antigo (`ABC1234`).

    Returns:
        A placa gerada.
    """
    raise NotImplementedError


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe uma placa pelo modo pedido.

    Args:
        valor: uma placa válida.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        A placa corrompida.

    Raises:
        ValueError: se o modo não se aplicar a placa.
    """
    raise NotImplementedError
