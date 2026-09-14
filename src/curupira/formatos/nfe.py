"""Chave de acesso da NF-e: 44 dígitos.

Composição: cUF (2) + AAMM (4) + CNPJ (14) + modelo (2) + série (3) + número (9)
+ tipo de emissão (1) + código numérico (8) + DV (1).

O DV usa módulo 11 com pesos de 2 a 9, aplicados da direita para a esquerda sobre
os 43 primeiros dígitos; resto 0 ou 1 resulta em dígito 0.

**PENDÊNCIA DECLARADA:** a chave tem 14 posições numéricas para o CNPJ, e o CNPJ
alfanumérico entrou em vigor em julho de 2026. O tratamento está definido em Nota
Técnica da Receita, que ainda NÃO foi lida. Até que seja, `gerar` recusa emitente
alfanumérico. Não inventar o mecanismo é requisito, não cautela.
"""

from __future__ import annotations

from curupira.core.enums import Corrupcao
from curupira.formatos.base import Gerado

PESOS_DV = (2, 3, 4, 5, 6, 7, 8, 9)
"""Ciclo de pesos, aplicado da direita para a esquerda."""

MODELO_NFE = "55"
MODELO_NFCE = "65"


def validar(chave: str) -> bool:
    """Valida uma chave de acesso de 44 dígitos.

    Args:
        chave: a chave, com ou sem separadores.

    Returns:
        `True` se o DV confere e os campos estruturais são plausíveis (cUF
        existente, mês de 1 a 12, modelo conhecido).
    """
    raise NotImplementedError


def gerar(
    rng_seed: int,
    *,
    cnpj_emitente: str,
    cuf: int,
    ano: int,
    mes: int,
    modelo: str = MODELO_NFE,
) -> Gerado:
    """Gera uma chave de acesso válida.

    Args:
        rng_seed: a seed.
        cnpj_emitente: CNPJ **numérico** do emitente, 14 dígitos.
        cuf: código IBGE da unidade federativa.
        ano: ano de emissão, 4 dígitos.
        mes: mês de emissão, 1 a 12.
        modelo: `"55"` para NF-e, `"65"` para NFC-e.

    Returns:
        A chave gerada.

    Raises:
        NotImplementedError: se `cnpj_emitente` for alfanumérico — ver a pendência
            declarada no topo deste módulo.
    """
    raise NotImplementedError


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe uma chave de acesso pelo modo pedido.

    Args:
        valor: uma chave válida.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        A chave corrompida.

    Raises:
        ValueError: se o modo não se aplicar à chave.
    """
    raise NotImplementedError
