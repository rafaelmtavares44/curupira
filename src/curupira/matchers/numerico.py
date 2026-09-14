"""Matchers numéricos, incluindo os que existem por causa do PT-BR.

`moeda_normalizada` é o matcher mais importante do projeto: `1.234,56` em
português é mil duzentos e trinta e quatro reais e cinquenta e seis centavos, e
em inglês seria mil duzentos e trinta e quatro *mil*. O erro é silencioso e de
três ordens de grandeza.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue


def exact_int(observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]) -> bool:
    """Igualdade exata de inteiro, sem coerção de string.

    Args:
        observado: o valor que o agente enviou.
        esperado: o valor de referência.
        params: ignorado.

    Returns:
        `True` se ambos são inteiros e iguais.
    """
    raise NotImplementedError


def tolerancia_numerica(
    observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]
) -> bool:
    """Igualdade numérica com tolerância absoluta ou relativa.

    Args:
        observado: o valor que o agente enviou.
        esperado: o valor de referência.
        params: `abs_tol` e/ou `rel_tol`.

    Returns:
        `True` se a diferença cabe na tolerância.
    """
    raise NotImplementedError


def moeda_normalizada(
    observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]
) -> bool:
    """Compara valores monetários em centavos, aceitando as grafias usuais.

    Args:
        observado: o valor que o agente enviou.
        esperado: o valor de referência, em centavos.
        params: `aceitar_string` para permitir `"1234,56"` além do inteiro.

    Returns:
        `True` se, normalizado a centavos, o valor confere.
    """
    raise NotImplementedError


def data_iso(observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]) -> bool:
    """Compara datas normalizadas para ISO 8601.

    `03/04/2026` é 3 de abril em português e 4 de março em inglês. A ambiguidade é
    o teste; a normalização é a régua.

    Args:
        observado: o valor que o agente enviou.
        esperado: a data de referência em ISO.
        params: `formatos_aceitos`.

    Returns:
        `True` se as datas normalizadas coincidem.
    """
    raise NotImplementedError
