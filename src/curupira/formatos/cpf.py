"""CPF: 9 dígitos base mais 2 dígitos verificadores.

DV1: pesos 10 a 2 sobre os 9 primeiros. DV2: pesos 11 a 2 sobre os 10 primeiros.
Módulo 11, com resto menor que 2 resultando em dígito 0.

**Armadilha obrigatória:** sequências repetidas (`111.111.111-11`) passam na
aritmética e mesmo assim são inválidas. Sem blacklist, o validador está errado —
e é exatamente esse o teste de propriedade que vale a pena escrever.

**Política de máscara, declarada:** são aceitas exatamente duas grafias — 11
dígitos nus, ou `000.000.000-00`. Qualquer outra pontuação é inválida. Sem essa
rigidez, `Corrupcao.MASCARA_ERRADA` não seria detectável, e metade da trilha T2
perderia o sentido.

**Ética:** o espaço de CPF tem cerca de 10⁹ combinações e o Brasil tem mais de
200 milhões emitidos, então colisão aritmética é inevitável e NÃO é evitável por
engenhosidade de geração. O que se evita é a identificação — ver SECURITY.md.
"""

from __future__ import annotations

import re
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

PESOS_DV1: Final = tuple(range(10, 1, -1))
PESOS_DV2: Final = tuple(range(11, 1, -1))

_NU: Final = re.compile(r"^\d{11}$")
_MASCARADO: Final = re.compile(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$")

REPETIDOS: Final = frozenset(str(d) * 11 for d in range(10))
"""Passam na aritmetica do modulo 11 e mesmo assim sao invalidos."""

TAMANHO: Final = 11
_TAMANHO_DA_BASE: Final = 9


def _digitos(valor: str) -> list[int] | None:
    """Extrai os 11 dígitos, se a grafia for uma das duas aceitas."""
    if not (_NU.match(valor) or _MASCARADO.match(valor)):
        return None
    return [int(c) for c in valor if c.isdigit()]


def _dvs(base: list[int]) -> tuple[int, int]:
    """Calcula os dois dígitos verificadores a partir dos 9 da base."""
    dv1 = modulo11(base, PESOS_DV1)
    dv2 = modulo11([*base, dv1], PESOS_DV2)
    return dv1, dv2


def validar(valor: str) -> bool:
    """Valida um CPF, nu ou com a máscara canônica.

    Args:
        valor: o CPF.

    Returns:
        `True` se formato e os dois dígitos verificadores conferem e o valor não
        é uma sequência repetida.
    """
    digitos = _digitos(valor)
    if digitos is None:
        return False
    if "".join(map(str, digitos)) in REPETIDOS:
        return False
    dv1, dv2 = _dvs(digitos[:_TAMANHO_DA_BASE])
    return digitos[9] == dv1 and digitos[10] == dv2


def mascarar(nu: str) -> str:
    """Aplica a máscara canônica a um CPF de 11 dígitos.

    Args:
        nu: os 11 dígitos.

    Returns:
        O CPF no formato `000.000.000-00`.

    Raises:
        ValueError: se não forem exatamente 11 dígitos.
    """
    if not _NU.match(nu):
        msg = f"mascarar espera 11 digitos, recebeu {nu!r}"
        raise ValueError(msg)
    return f"{nu[:3]}.{nu[3:6]}.{nu[6:9]}-{nu[9:]}"


def gerar(rng_seed: int, *, com_mascara: bool = False) -> Gerado:
    """Gera um CPF válido de forma determinística.

    Args:
        rng_seed: a seed, derivada do `task_id`.
        com_mascara: se verdadeiro, devolve `000.000.000-00`.

    Returns:
        O CPF gerado.
    """
    rng = rng_de(rng_seed)
    while True:
        base = [rng.randrange(10) for _ in range(_TAMANHO_DA_BASE)]
        dv1, dv2 = _dvs(base)
        nu = "".join(map(str, [*base, dv1, dv2]))
        if nu not in REPETIDOS:
            break
    valor = mascarar(nu) if com_mascara else nu
    return Gerado(valor=valor, valido=True, corrupcao=None, seed=rng_seed)


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe um CPF válido pelo modo pedido.

    Args:
        valor: um CPF válido.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        O CPF corrompido, que `validar` reprova.

    Raises:
        ValueError: se `valor` não for um CPF válido, ou se o modo não se aplicar.
    """
    if not validar(valor):
        msg = f"corromper espera um CPF valido, recebeu {valor!r}"
        raise ValueError(msg)
    rng = rng_de(rng_seed)
    nu = apenas_alfanumericos(valor)

    if modo is Corrupcao.DV_TROCADO:
        corrompido = trocar_caractere(nu, 10, incrementar_digito(nu[10]))
    elif modo is Corrupcao.TRANSPOSICAO:
        corrompido = _transpor(nu, rng_seed)
    elif modo is Corrupcao.MASCARA_ERRADA:
        # Digitos certos, pontuacao de CNPJ: o erro de quem reusa a mascara errada.
        corrompido = f"{nu[:2]}.{nu[2:5]}.{nu[5:8]}/{nu[8:10]}-{nu[10]}"
    elif modo is Corrupcao.TAMANHO_ERRADO:
        corrompido = nu[: rng.randrange(1, TAMANHO)]
    elif modo is Corrupcao.CARACTERE_INVALIDO:
        corrompido = trocar_caractere(nu, rng.randrange(TAMANHO), "X")
    elif modo is Corrupcao.SEQUENCIA_REPETIDA:
        corrompido = str(rng.randrange(10)) * TAMANHO
    else:
        msg = f"{modo} nao se aplica a CPF (nao ha faixa nem ordem a inverter)"
        raise ValueError(msg)

    return Gerado(valor=corrompido, valido=False, corrupcao=modo, seed=rng_seed)


def _transpor(nu: str, rng_seed: int) -> str:
    """Troca dois dígitos vizinhos da base, de forma verificadamente detectável.

    O módulo 11 tem um ponto cego (ver `modulo11`), então a escolha do par é
    confirmada com o próprio validador. Se nenhuma troca for detectável, cai no
    dígito verificador — alterar um único dígito sempre muda o resto em algo
    entre 2 e 9, fora da faixa cega.
    """
    candidato = transpor_detectavel(nu, _TAMANHO_DA_BASE, validar, rng_seed)
    if candidato is not None:
        return candidato
    return trocar_caractere(nu, 10, incrementar_digito(nu[10]))
