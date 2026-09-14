"""CEP: 8 dígitos, no formato `NNNNN-NNN`.

**Não tem dígito verificador.** A validade real é existência na base dos
Correios, que não consultamos e não devemos consultar. Aqui validamos formato e
faixa regional (o primeiro dígito indica a região).

Nota de privacidade: CEP identifica um logradouro, não uma pessoa. Um CEP real
associado a um nome fictício não é dado pessoal de ninguém. O risco mora na
combinação, não no campo. Ver SECURITY.md.
"""

from __future__ import annotations

from curupira.core.enums import Corrupcao
from curupira.formatos.base import Gerado


def validar(valor: str) -> bool:
    """Valida formato e faixa regional de um CEP.

    Args:
        valor: o CEP, com ou sem hífen.

    Returns:
        `True` se tem 8 dígitos e a região é plausível.
    """
    raise NotImplementedError


def gerar(rng_seed: int, *, uf: str | None = None, com_mascara: bool = True) -> Gerado:
    """Gera um CEP de formato válido.

    Args:
        rng_seed: a seed.
        uf: se informada, restringe à faixa da unidade federativa.
        com_mascara: se verdadeiro, devolve `00000-000`.

    Returns:
        O CEP gerado.
    """
    raise NotImplementedError


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe um CEP pelo modo pedido.

    Args:
        valor: um CEP de formato válido.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        O CEP corrompido.

    Raises:
        ValueError: se o modo não se aplicar a CEP (não há DV para trocar).
    """
    raise NotImplementedError
