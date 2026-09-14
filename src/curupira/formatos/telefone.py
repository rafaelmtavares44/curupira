"""Telefone brasileiro em E.164: `+55` + DDD (2) + assinante (8 ou 9).

Móvel tem 9 dígitos e começa em 9; fixo tem 8 e começa entre 2 e 5. Não há dígito
verificador; a validação é formato mais lista finita de DDDs existentes.

**Decisão de privacidade, declarada:** telefone é o campo de maior risco de
colisão útil, porque um número solto ainda é contactável. Para tarefas em que a
validade do DDD não é o objeto do teste, gere com DDD inexistente
(`ddd_inexistente=True`). Para tarefas que testam validação de DDD, use DDD real
e não combine o número com nome e endereço no mesmo registro.
"""

from __future__ import annotations

from curupira.core.enums import Corrupcao
from curupira.formatos.base import Gerado


def validar(valor: str) -> bool:
    """Valida um telefone brasileiro.

    Args:
        valor: o telefone, em E.164 ou grafia usual.

    Returns:
        `True` se DDD existe e o assinante tem tamanho e prefixo coerentes.
    """
    raise NotImplementedError


def gerar(
    rng_seed: int,
    *,
    movel: bool = True,
    ddd_inexistente: bool = False,
    formato_e164: bool = True,
) -> Gerado:
    """Gera um telefone brasileiro.

    Args:
        rng_seed: a seed.
        movel: móvel (9 dígitos) ou fixo (8).
        ddd_inexistente: usa um DDD que não existe, reduzindo risco de colisão
            útil quando a validade do DDD não é o objeto do teste.
        formato_e164: se verdadeiro, devolve `+5562999999999`.

    Returns:
        O telefone gerado.
    """
    raise NotImplementedError


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe um telefone pelo modo pedido.

    Modo de maior valor para o benchmark: móvel sem o nono dígito, que é o erro
    que um sistema desatualizado comete.

    Args:
        valor: um telefone válido.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        O telefone corrompido.

    Raises:
        ValueError: se o modo não se aplicar a telefone.
    """
    raise NotImplementedError
