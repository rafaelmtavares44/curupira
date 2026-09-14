"""Contrato comum aos geradores de identificador brasileiro."""

from __future__ import annotations

from typing import NamedTuple, Protocol

from curupira.core.enums import Corrupcao


class Gerado(NamedTuple):
    """Um identificador gerado, com a proveniência necessária para auditar."""

    valor: str
    valido: bool
    corrupcao: Corrupcao | None
    seed: int


class GeradorDeFormato(Protocol):
    """O que todo módulo de `curupira.formatos` expõe."""

    def validar(self, valor: str) -> bool:
        """Diz se o valor é válido, considerando formato e dígito verificador."""
        ...

    def gerar(self, rng_seed: int) -> Gerado:
        """Gera um valor válido de forma determinística a partir da seed."""
        ...

    def corromper(self, valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
        """Corrompe um valor válido pelo modo pedido."""
        ...


def modulo11(digitos: list[int], pesos: list[int]) -> int:
    """Calcula um dígito verificador por módulo 11.

    Convenção usada por CPF, CNPJ e chave de acesso da NF-e: soma ponderada,
    resto da divisão por 11, e resto menor que 2 resulta em dígito 0.

    Args:
        digitos: os valores numéricos, já convertidos.
        pesos: os pesos, na mesma ordem e do mesmo tamanho.

    Returns:
        O dígito verificador, de 0 a 9.

    Raises:
        ValueError: se os tamanhos divergirem.
    """
    raise NotImplementedError


def modulo10(digitos: list[int]) -> int:
    """Calcula um dígito verificador por módulo 10 (pesos alternados 2 e 1).

    Usado nos DVs de campo da linha digitável do boleto.

    **Cuidado que vira tarefa do benchmark:** o módulo 10 NÃO detecta todas as
    transposições de dígitos vizinhos; o módulo 11 detecta. Um agente que confia
    cegamente no DV de campo passa direto por uma transposição.

    Args:
        digitos: os dígitos do campo, da esquerda para a direita.

    Returns:
        O dígito verificador, de 0 a 9.
    """
    raise NotImplementedError
