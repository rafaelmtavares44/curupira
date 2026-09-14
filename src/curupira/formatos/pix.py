"""As cinco formas de chave PIX.

CPF, CNPJ, e-mail, telefone em E.164 e chave aleatória (EVP), que é um UUID
versão 4. Cada tipo delega ao validador correspondente.

**Armadilha de alto valor:** pedir ao agente que "gere uma chave aleatória" e
verificar se o UUID produzido é de fato versão 4 — nibble de versão igual a 4 e
bits de variante `10xx`, ou seja, o 17º caractere em `8 9 a b`. Um UUID v1 passa
por aleatório para quem não olha.
"""

from __future__ import annotations

from enum import StrEnum

from curupira.core.enums import Corrupcao
from curupira.formatos.base import Gerado


class TipoDeChavePix(StrEnum):
    """Os cinco tipos de chave PIX."""

    CPF = "cpf"
    CNPJ = "cnpj"
    EMAIL = "email"
    TELEFONE = "telefone"
    ALEATORIA = "aleatoria"


def detectar_tipo(valor: str) -> TipoDeChavePix | None:
    """Infere o tipo de uma chave PIX pelo formato.

    Args:
        valor: a chave.

    Returns:
        O tipo, ou `None` se não casar com nenhum.
    """
    raise NotImplementedError


def validar(valor: str) -> bool:
    """Valida uma chave PIX, inferindo o tipo pelo formato.

    A chave de CPF e a de CNPJ são **sem pontuação** — uma chave mascarada é
    inválida, e esse é um erro que modelos cometem com frequência.

    Args:
        valor: a chave.

    Returns:
        `True` se a chave é válida para algum dos cinco tipos.
    """
    raise NotImplementedError


def validar_como(valor: str, tipo: TipoDeChavePix) -> bool:
    """Valida uma chave PIX forçando um tipo específico.

    Args:
        valor: a chave.
        tipo: o tipo a assumir.

    Returns:
        `True` se a chave é válida para esse tipo.
    """
    raise NotImplementedError


def gerar(rng_seed: int, tipo: TipoDeChavePix) -> Gerado:
    """Gera uma chave PIX válida do tipo pedido.

    Args:
        rng_seed: a seed.
        tipo: o tipo de chave.

    Returns:
        A chave gerada.
    """
    raise NotImplementedError


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe uma chave PIX pelo modo pedido.

    Args:
        valor: uma chave válida.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        A chave corrompida.

    Raises:
        ValueError: se o modo não se aplicar ao tipo da chave.
    """
    raise NotImplementedError
