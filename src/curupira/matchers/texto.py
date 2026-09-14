"""Matchers de texto."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue


def exact_str(observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]) -> bool:
    """Igualdade exata de string, após normalização unicode NFC.

    Args:
        observado: o valor que o agente enviou.
        esperado: o valor de referência.
        params: `case_sensitive`, padrão verdadeiro.

    Returns:
        `True` se as strings normalizadas são iguais.
    """
    raise NotImplementedError


def one_of(observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]) -> bool:
    """Aceita qualquer valor de um conjunto de sinônimos declarado.

    Args:
        observado: o valor que o agente enviou.
        esperado: ignorado; o conjunto vem de `params`.
        params: `values`, a lista de valores aceitáveis.

    Returns:
        `True` se o observado está no conjunto.
    """
    raise NotImplementedError


def fuzzy_name(observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]) -> bool:
    """Compara nomes próprios com tolerância de similaridade.

    O limiar é chute até o piloto medir a discordância entre este matcher e a
    anotação humana numa amostra. Enquanto essa medição não existir, o valor
    padrão é uma hipótese, e o relatório deve dizer isso.

    Args:
        observado: o valor que o agente enviou.
        esperado: o nome de referência.
        params: `threshold`, padrão 0.9; `ignorar_acentos`.

    Returns:
        `True` se a similaridade atinge o limiar.
    """
    raise NotImplementedError


def por_validador(
    observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]
) -> bool:
    """Delega a um validador de formato registrado.

    Args:
        observado: o valor que o agente enviou.
        esperado: ignorado.
        params: `validador`, o nome registrado (ex.: `"cpf"`).

    Returns:
        `True` se o validador aprovar o valor observado.
    """
    raise NotImplementedError
