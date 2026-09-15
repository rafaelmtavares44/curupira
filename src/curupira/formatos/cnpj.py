"""CNPJ numérico e alfanumérico.

**Numérico:** 8 de raiz + 4 de ordem + 2 DV.

**Alfanumérico (em vigor desde julho de 2026):** os 12 primeiros caracteres podem
ser letras maiúsculas ou dígitos; os 2 DV continuam **numéricos**. Cada caractere
é convertido para `ASCII - 48` antes da soma ponderada, de modo que `A` vale 17 e
`Z` vale 42. Os pesos são os mesmos do numérico.

A implementação foi conferida contra o exemplo publicado: `AB12CD34EFGH` produz
soma 850 e DV1 8, depois soma 888 e DV2 3 — ou seja, `AB12CD34EFGH83`. O teste
`test_exemplo_da_especificacao` fixa isso.

**ACHADO: o DV alfanumérico é mais fraco contra transposição que o numérico.**

O módulo 11 detecta toda troca de dígitos vizinhos quando os valores vão de 0 a 9,
porque a soma muda em `(a-b)` e nenhuma diferença de dígitos distintos é múltiplo
de 11. No CNPJ alfanumérico os valores vão de 0 (`0`) a 42 (`Z`), e existem **43
pares** cuja diferença É múltiplo de 11 — `0`/`F`, `1`/`G`, `A`/`L`, e assim por
diante. Trocar dois vizinhos desses deixa a soma inalterada módulo 11, e o
dígito verificador aprova o CNPJ trocado.

Ou seja: a mudança de 2026 comprou espaço de numeração ao custo de uma garantia
que o formato antigo tinha. Isso não é defeito desta implementação — é do
formato — e é exatamente o tipo de armadilha que a trilha T2 existe para medir.
`transposicoes_indetectaveis()` enumera os pares, e `_transpor` os evita de
propósito, para que `Corrupcao.TRANSPOSICAO` continue significando "corrupção
detectável".

**Por que este módulo é o mais valioso do benchmark:** o CNPJ alfanumérico entrou
em vigor em julho de 2026, então é *matematicamente impossível* que esteja bem
representado em dado de treino de qualquer modelo servido hoje. Isso dá um
conjunto de tarefas que mede competência em vez de memorização, imune a
contaminação por construção.
"""

from __future__ import annotations

import re
import string
from typing import Final

from curupira.core.enums import Corrupcao
from curupira.formatos.base import (
    Gerado,
    apenas_alfanumericos,
    incrementar_digito,
    modulo11,
    rng_de,
    transpor_detectavel,
    trocar_caractere,
)

OFFSET_ASCII: Final = 48
"""Subtraido do codigo ASCII de cada caractere. '0' vira 0, 'A' vira 17."""

PESOS_DV1: Final = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
PESOS_DV2: Final = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)

ALFABETO: Final = string.digits + string.ascii_uppercase
TAMANHO: Final = 14
_TAMANHO_DA_BASE: Final = 12

_NU: Final = re.compile(r"^[0-9A-Z]{12}\d{2}$")
_MASCARADO: Final = re.compile(r"^[0-9A-Z]{2}\.[0-9A-Z]{3}\.[0-9A-Z]{3}/[0-9A-Z]{4}-\d{2}$")

REPETIDOS: Final = frozenset(c * TAMANHO for c in string.digits)
"""Passam na aritmetica e mesmo assim nao sao CNPJ de ninguem."""

_MODULO: Final = 11


def transposicoes_indetectaveis() -> frozenset[tuple[str, str]]:
    """Pares de caracteres cuja troca o dígito verificador NÃO detecta.

    A troca de dois vizinhos muda a soma ponderada em `(a-b) * (p_i - p_j)`. Se
    `(a-b)` for múltiplo de 11, a soma não muda módulo 11 e o DV aprova o valor
    trocado. Com valores de 0 a 42, isso acontece para 43 pares.

    Returns:
        Os pares, sempre em ordem alfabética dentro da tupla.
    """
    return frozenset(
        (a, b)
        for a in ALFABETO
        for b in ALFABETO
        if a < b and (_valor(b) - _valor(a)) % _MODULO == 0
    )


def _valor(caractere: str) -> int:
    """Converte um caractere para o valor numérico da especificação."""
    return ord(caractere) - OFFSET_ASCII


def _base(valor: str) -> str | None:
    """Extrai os 14 caracteres, se a grafia for uma das duas aceitas."""
    if not (_NU.match(valor) or _MASCARADO.match(valor)):
        return None
    return apenas_alfanumericos(valor)


def _dvs(base: str) -> tuple[int, int]:
    """Calcula os dois dígitos verificadores a partir dos 12 da base."""
    valores = [_valor(c) for c in base]
    dv1 = modulo11(valores, PESOS_DV1)
    dv2 = modulo11([*valores, dv1], PESOS_DV2)
    return dv1, dv2


def e_alfanumerico(valor: str) -> bool:
    """Diz se o CNPJ usa o formato alfanumérico vigente desde julho de 2026.

    Args:
        valor: o CNPJ.

    Returns:
        `True` se houver ao menos uma letra nos 12 primeiros caracteres.
    """
    base = _base(valor)
    return base is not None and not base[:_TAMANHO_DA_BASE].isdigit()


def validar(valor: str) -> bool:
    """Valida um CNPJ, numérico ou alfanumérico, nu ou com a máscara canônica.

    Args:
        valor: o CNPJ.

    Returns:
        `True` se formato e dígitos verificadores conferem.
    """
    base = _base(valor)
    if base is None or base in REPETIDOS:
        return False
    dv1, dv2 = _dvs(base[:_TAMANHO_DA_BASE])
    return base[12] == str(dv1) and base[13] == str(dv2)


def mascarar(nu: str) -> str:
    """Aplica a máscara canônica a um CNPJ de 14 caracteres.

    Args:
        nu: os 14 caracteres.

    Returns:
        O CNPJ no formato `00.000.000/0000-00`.

    Raises:
        ValueError: se a grafia nua não for válida.
    """
    if not _NU.match(nu):
        msg = f"mascarar espera 12 alfanumericos mais 2 digitos, recebeu {nu!r}"
        raise ValueError(msg)
    return f"{nu[:2]}.{nu[2:5]}.{nu[5:8]}/{nu[8:12]}-{nu[12:]}"


def gerar(rng_seed: int, *, alfanumerico: bool = False, com_mascara: bool = False) -> Gerado:
    """Gera um CNPJ válido de forma determinística.

    A ordem (os 4 caracteres de filial) é sempre `0001`, a matriz — é o caso
    esmagadoramente comum e mantém o dado plausível sem inventar estrutura.

    Args:
        rng_seed: a seed, derivada do `task_id`.
        alfanumerico: usa o formato vigente desde julho de 2026.
        com_mascara: se verdadeiro, devolve `00.000.000/0000-00`.

    Returns:
        O CNPJ gerado.
    """
    rng = rng_de(rng_seed)
    alfabeto = ALFABETO if alfanumerico else string.digits
    while True:
        raiz = "".join(rng.choice(alfabeto) for _ in range(8))
        base = f"{raiz}0001"
        dv1, dv2 = _dvs(base)
        nu = f"{base}{dv1}{dv2}"
        if nu not in REPETIDOS and (not alfanumerico or not raiz.isdigit()):
            break
    valor = mascarar(nu) if com_mascara else nu
    return Gerado(valor=valor, valido=True, corrupcao=None, seed=rng_seed)


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe um CNPJ válido pelo modo pedido.

    `CARACTERE_INVALIDO` num CNPJ alfanumérico usa **letra minúscula**, que é o
    erro clássico de quem leu a mudança de 2026 por alto: o formato aceita letras,
    mas só maiúsculas, e o DV continua numérico.

    Args:
        valor: um CNPJ válido.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        O CNPJ corrompido, que `validar` reprova.

    Raises:
        ValueError: se `valor` não for válido, ou se o modo não se aplicar.
    """
    if not validar(valor):
        msg = f"corromper espera um CNPJ valido, recebeu {valor!r}"
        raise ValueError(msg)
    rng = rng_de(rng_seed)
    nu = apenas_alfanumericos(valor)
    alfa = not nu[:_TAMANHO_DA_BASE].isdigit()

    if modo is Corrupcao.DV_TROCADO:
        corrompido = trocar_caractere(nu, 13, incrementar_digito(nu[13]))
    elif modo is Corrupcao.TRANSPOSICAO:
        corrompido = _transpor(nu, rng_seed)
    elif modo is Corrupcao.MASCARA_ERRADA:
        corrompido = f"{nu[:3]}.{nu[3:6]}.{nu[6:9]}-{nu[9:12]}.{nu[12:]}"
    elif modo is Corrupcao.TAMANHO_ERRADO:
        corrompido = nu[: rng.randrange(1, TAMANHO)]
    elif modo is Corrupcao.CARACTERE_INVALIDO:
        corrompido = (
            trocar_caractere(nu, rng.randrange(_TAMANHO_DA_BASE), "a")
            if alfa
            else trocar_caractere(nu, 13, "A")
        )
    elif modo is Corrupcao.SEQUENCIA_REPETIDA:
        corrompido = str(rng.randrange(10)) * TAMANHO
    else:
        msg = f"{modo} nao se aplica a CNPJ"
        raise ValueError(msg)

    return Gerado(valor=corrompido, valido=False, corrupcao=modo, seed=rng_seed)


def _transpor(nu: str, rng_seed: int) -> str:
    """Troca dois caracteres vizinhos da base, de forma verificadamente detectável.

    Dois pontos cegos se somam aqui: o do resto 0/1 do módulo 11 (ver
    `modulo11`) e o dos 43 pares de caracteres cujos valores diferem em múltiplo
    de 11 (ver `transposicoes_indetectaveis`). Em vez de raciocinar sobre a
    interseção dos dois, o candidato é confirmado com o validador.
    """
    candidato = transpor_detectavel(nu, _TAMANHO_DA_BASE, validar, rng_seed)
    if candidato is not None:
        return candidato
    return trocar_caractere(nu, 13, incrementar_digito(nu[13]))
