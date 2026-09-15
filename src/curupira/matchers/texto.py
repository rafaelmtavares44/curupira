"""Matchers de texto."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from difflib import SequenceMatcher
from typing import Final

from pydantic import JsonValue

from curupira.core.registry import obter_validador

LIMIAR_PADRAO: Final = 0.9


def normalizar(texto: str, *, ignorar_acentos: bool = False) -> str:
    """Normaliza texto para comparação: NFC, espaços colapsados, opcional sem acento.

    Args:
        texto: o texto original.
        ignorar_acentos: se verdadeiro, remove os diacríticos.

    Returns:
        O texto normalizado.
    """
    resultado = unicodedata.normalize("NFC", texto).strip()
    resultado = " ".join(resultado.split())
    if ignorar_acentos:
        decomposto = unicodedata.normalize("NFD", resultado)
        resultado = "".join(c for c in decomposto if not unicodedata.combining(c))
    return resultado


def exact_str(observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]) -> bool:
    """Igualdade exata de string, após normalização unicode NFC.

    Args:
        observado: o valor que o agente enviou.
        esperado: o valor de referência.
        params: `case_sensitive`, padrão verdadeiro.

    Returns:
        `True` se as strings normalizadas são iguais.
    """
    if not isinstance(observado, str) or not isinstance(esperado, str):
        return False
    a, b = normalizar(observado), normalizar(esperado)
    if params.get("case_sensitive") is False:
        return a.casefold() == b.casefold()
    return a == b


def one_of(observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]) -> bool:
    """Aceita qualquer valor de um conjunto de sinônimos declarado.

    O conjunto vem de `params["values"]`, e o valor de referência da tarefa entra
    nele automaticamente — declarar sinônimos não deveria obrigar a repetir o
    valor canônico.

    Args:
        observado: o valor que o agente enviou.
        esperado: o valor de referência, sempre aceito.
        params: `values`, a lista de valores aceitáveis.

    Returns:
        `True` se o observado está no conjunto.
    """
    bruto = params.get("values")
    aceitos: list[JsonValue] = list(bruto) if isinstance(bruto, list) else []
    aceitos.append(esperado)
    for aceito in aceitos:
        if isinstance(observado, str) and isinstance(aceito, str):
            if normalizar(observado) == normalizar(aceito):
                return True
        elif observado == aceito:
            return True
    return False


def similaridade(a: str, b: str) -> float:
    """Razão de similaridade entre dois textos, de 0 a 1.

    Usa `difflib.SequenceMatcher`, da biblioteca padrão: determinístico, sem
    dependência nova e sem modelo no meio. Num benchmark, um matcher que precisa
    de rede não é um matcher.

    Args:
        a: primeiro texto.
        b: segundo texto.

    Returns:
        A razão de similaridade.
    """
    return SequenceMatcher(None, a, b).ratio()


def fuzzy_name(observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]) -> bool:
    """Compara nomes próprios com tolerância de similaridade.

    **O limiar padrão é uma hipótese, não uma medição.** Ele só vira número
    defensável depois que o piloto comparar este matcher com anotação humana numa
    amostra; até lá o relatório deve dizer isso.

    Args:
        observado: o valor que o agente enviou.
        esperado: o nome de referência.
        params: `threshold` (padrão 0.9) e `ignorar_acentos` (padrão verdadeiro).

    Returns:
        `True` se a similaridade atinge o limiar.
    """
    if not isinstance(observado, str) or not isinstance(esperado, str):
        return False
    limiar_bruto = params.get("threshold", LIMIAR_PADRAO)
    limiar = float(limiar_bruto) if isinstance(limiar_bruto, int | float) else LIMIAR_PADRAO
    ignorar = params.get("ignorar_acentos") is not False
    a = normalizar(observado, ignorar_acentos=ignorar).casefold()
    b = normalizar(esperado, ignorar_acentos=ignorar).casefold()
    return a == b or similaridade(a, b) >= limiar


def por_validador(
    observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]
) -> bool:
    """Delega a um validador de formato registrado.

    Args:
        observado: o valor que o agente enviou.
        esperado: ignorado — quem julga é o validador.
        params: `validador`, o nome registrado (ex.: `"cpf"`).

    Returns:
        `True` se o validador aprovar o valor observado.

    Raises:
        KeyError: se o validador não estiver registrado. O lint do dataset pega
            isso antes de a rodada começar.
    """
    del esperado
    nome = params.get("validador")
    if not isinstance(nome, str) or not isinstance(observado, str):
        return False
    return obter_validador(nome)(observado)
