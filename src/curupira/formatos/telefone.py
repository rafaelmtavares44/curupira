"""Telefone brasileiro em E.164: `+55` + DDD (2) + assinante (8 ou 9).

Móvel tem 9 dígitos e começa em 9; fixo tem 8 e começa entre 2 e 5. Não há dígito
verificador; a validação é formato mais lista finita de DDDs existentes.

Os 67 DDDs, e os 22 buracos
---------------------------
De 11 a 99 existem 89 combinações possíveis, e apenas 67 estão em uso. Os 22
restantes — 20, 23, 25, 26, 29, 30, 36, 39, 40, 50, 52, 56, 57, 58, 59, 60, 70,
72, 76, 78, 80 e 90 — nunca foram atribuídos. Isso faz de `FAIXA_INVALIDA` uma
corrupção genuinamente detectável, o que é raro num formato sem DV.

**Decisão de privacidade, declarada:** telefone é o campo de maior risco de
colisão útil, porque um número solto ainda é contactável. Para tarefas em que a
validade do DDD não é o objeto do teste, gere com DDD inexistente
(`ddd_inexistente=True`): o número fica sintaticamente plausível e não alcança
ninguém. Para tarefas que testam validação de DDD, use DDD real e não combine o
número com nome e endereço no mesmo registro.
"""

from __future__ import annotations

import re
from typing import Final

from curupira.core.enums import Corrupcao
from curupira.formatos.base import Gerado, rng_de

DDDS_VALIDOS: Final = frozenset(
    {
        11, 12, 13, 14, 15, 16, 17, 18, 19,
        21, 22, 24, 27, 28,
        31, 32, 33, 34, 35, 37, 38,
        41, 42, 43, 44, 45, 46, 47, 48, 49,
        51, 53, 54, 55,
        61, 62, 63, 64, 65, 66, 67, 68, 69,
        71, 73, 74, 75, 77, 79,
        81, 82, 83, 84, 85, 86, 87, 88, 89,
        91, 92, 93, 94, 95, 96, 97, 98, 99,
    }
)  # fmt: skip
"""Os 67 DDDs em uso no Brasil. Fonte: plano de numeracao da Anatel, set/2026."""

DDDS_INEXISTENTES: Final = tuple(sorted(d for d in range(11, 100) if d not in DDDS_VALIDOS))
"""Os 22 codigos de dois digitos que nunca foram atribuidos."""

TAMANHO_MOVEL: Final = 9
TAMANHO_FIXO: Final = 8
PRIMEIRO_DIGITO_MOVEL: Final = "9"
PRIMEIROS_DIGITOS_FIXO: Final = "2345"

_E164: Final = re.compile(r"^\+55(\d{2})(\d{8,9})$")
_MASCARADO: Final = re.compile(r"^\((\d{2})\) (\d{4,5})-(\d{4})$")


def _partes(valor: str) -> tuple[int, str] | None:
    """Extrai DDD e assinante, se a grafia for uma das duas aceitas.

    Duas grafias, e só elas: E.164 (`+5562999998888`) ou a usual brasileira
    (`(62) 99999-8888`). A rigidez torna `MASCARA_ERRADA` detectável.
    """
    casou = _E164.match(valor)
    if casou:
        return int(casou.group(1)), casou.group(2)
    casou = _MASCARADO.match(valor)
    if casou:
        return int(casou.group(1)), casou.group(2) + casou.group(3)
    return None


def _assinante_coerente(assinante: str) -> bool:
    """Diz se o número do assinante tem tamanho e prefixo coerentes."""
    if len(assinante) == TAMANHO_MOVEL:
        return assinante[0] == PRIMEIRO_DIGITO_MOVEL
    if len(assinante) == TAMANHO_FIXO:
        return assinante[0] in PRIMEIROS_DIGITOS_FIXO
    return False


def validar(valor: str) -> bool:
    """Valida um telefone brasileiro.

    Args:
        valor: o telefone, em E.164 ou grafia usual.

    Returns:
        `True` se DDD existe e o assinante tem tamanho e prefixo coerentes.
    """
    partes = _partes(valor)
    if partes is None:
        return False
    ddd, assinante = partes
    return ddd in DDDS_VALIDOS and _assinante_coerente(assinante)


def e_movel(valor: str) -> bool:
    """Diz se o telefone é de linha móvel.

    Args:
        valor: um telefone válido.

    Returns:
        `True` se o assinante tem nove dígitos começando em 9.
    """
    partes = _partes(valor)
    return partes is not None and len(partes[1]) == TAMANHO_MOVEL


def mascarar(ddd: int, assinante: str) -> str:
    """Formata na grafia usual brasileira.

    Args:
        ddd: o código de área.
        assinante: os 8 ou 9 dígitos do assinante.

    Returns:
        O telefone em `(00) 00000-0000`.
    """
    return f"({ddd:02d}) {assinante[:-4]}-{assinante[-4:]}"


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
        O telefone gerado. Com `ddd_inexistente`, `valido` é `False` — porque o
        validador de fato o reprova, e um `Gerado` que se declara válido quando
        não é seria a pior mentira possível neste módulo.
    """
    rng = rng_de(rng_seed)
    ddd = rng.choice(DDDS_INEXISTENTES) if ddd_inexistente else rng.choice(sorted(DDDS_VALIDOS))
    if movel:
        assinante = PRIMEIRO_DIGITO_MOVEL + f"{rng.randrange(10**8):08d}"
    else:
        assinante = rng.choice(PRIMEIROS_DIGITOS_FIXO) + f"{rng.randrange(10**7):07d}"

    valor = f"+55{ddd:02d}{assinante}" if formato_e164 else mascarar(ddd, assinante)
    return Gerado(
        valor=valor,
        valido=not ddd_inexistente,
        corrupcao=Corrupcao.FAIXA_INVALIDA if ddd_inexistente else None,
        seed=rng_seed,
    )


def _encurtar(assinante: str) -> str:
    """Tira um dígito do assinante, garantindo que o resultado seja reprovado.

    ACHADO, encontrado testando e não raciocinando
    ----------------------------------------------
    "Móvel sem o nono dígito" parece uma corrupção segura: tira-se o `9` da
    frente e sobram oito dígitos. Só que os oito que sobram começam pelo
    **segundo** dígito do móvel, e se ele for 2, 3, 4 ou 5 o resultado é um
    **telefone fixo perfeitamente válido**. Em cerca de 40% dos móveis a
    "corrupção" produziria um valor que o validador aprova — ou seja, um gabarito
    errado disfarçado de tarefa.

    Isso não é defeito do formato: é precisamente por isso que perder o nono
    dígito é um erro perigoso no mundo real. O número continua discável e chama
    outra pessoa. Como armadilha de tarefa, é ótimo; como corrupção declarada,
    viola o contrato deste módulo.

    A saída é a mesma de `transpor_detectavel`: **verificar**. Tenta-se o corte
    realista primeiro e, quando ele produz um número válido, remove-se o último
    dígito, que nunca produz.

    Args:
        assinante: os 8 ou 9 dígitos do assinante.

    Returns:
        O assinante encurtado de forma garantidamente inválida.
    """
    if len(assinante) == TAMANHO_MOVEL:
        sem_o_nono = assinante[1:]
        if not _assinante_coerente(sem_o_nono):
            return sem_o_nono
    return assinante[:-1]


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe um telefone pelo modo pedido.

    Modo de maior valor para o benchmark: `TAMANHO_ERRADO` em linha móvel, que
    tira o nono dígito. É o erro que um sistema desatualizado comete, e o
    resultado — oito dígitos começando em 9 — parece um telefone fixo malformado
    para quem não conhece a regra brasileira.

    Args:
        valor: um telefone válido.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        O telefone corrompido.

    Raises:
        ValueError: se o valor não for válido, ou se o modo não se aplicar —
            telefone não tem dígito verificador, então `DV_TROCADO` e
            `TRANSPOSICAO` não são garantidamente detectáveis.
    """
    partes = _partes(valor)
    if partes is None or not validar(valor):
        msg = f"nao da para corromper um telefone invalido: {valor!r}"
        raise ValueError(msg)

    ddd, assinante = partes
    rng = rng_de(rng_seed)
    e164 = valor.startswith("+")

    def montar(novo_ddd: int, novo_assinante: str) -> str:
        if e164:
            return f"+55{novo_ddd:02d}{novo_assinante}"
        return mascarar(novo_ddd, novo_assinante)

    if modo is Corrupcao.FAIXA_INVALIDA:
        corrompido = montar(rng.choice(DDDS_INEXISTENTES), assinante)
    elif modo is Corrupcao.TAMANHO_ERRADO:
        corrompido = montar(ddd, _encurtar(assinante))
    elif modo is Corrupcao.MASCARA_ERRADA:
        corrompido = f"{ddd:02d} {assinante}"
    elif modo is Corrupcao.CARACTERE_INVALIDO:
        posicao = rng.randrange(len(assinante))
        corrompido = montar(ddd, assinante[:posicao] + "X" + assinante[posicao + 1 :])
    elif modo is Corrupcao.SEQUENCIA_REPETIDA:
        # Prefixo 0 nao existe nem em movel nem em fixo, entao a repeticao de
        # zeros e reprovada pelo teste de prefixo, nao por blacklist.
        corrompido = montar(ddd, "0" * len(assinante))
    else:
        msg = (
            f"{modo.value} nao se aplica a telefone: nao ha digito verificador, "
            "entao nao ha como garantir que o resultado seja reprovado"
        )
        raise ValueError(msg)

    return Gerado(valor=corrompido, valido=False, corrupcao=modo, seed=rng_seed)
