"""Contrato comum aos geradores de identificador brasileiro."""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import NamedTuple, Protocol

from curupira.core.enums import Corrupcao

_RESTO_QUE_VIRA_ZERO = 2
"""Modulo 11: resto 0 ou 1 resulta em digito verificador 0."""

_MAIOR_PRODUTO_DE_UM_DIGITO = 9
"""Modulo 10: produto acima disso tem os algarismos somados (o mesmo que -9)."""

_PESO_DOBRADO = 2
_PESO_SIMPLES = 1


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


def rng_de(seed: int) -> random.Random:
    """Cria um gerador pseudoaleatório determinístico a partir da seed.

    O Mersenne Twister do `random` é estável entre versões de Python e entre
    plataformas — verificado em 3.11 e 3.13. É isso que torna o dataset
    regenerável a partir de `generator_seed` mais `generator_version`, e permite
    que o CI confira a regeneração contra os hashes da suíte.

    Args:
        seed: a seed, derivada do `task_id`.

    Returns:
        O gerador.
    """
    # Gerador nao-criptografico e o CERTO aqui. O dataset precisa ser
    # REPRODUZIVEL a partir da seed; um gerador criptografico nao tem essa
    # propriedade, e nao ha segredo nenhum a proteger num CPF sintetico.
    return random.Random(seed)  # noqa: S311  # nosec B311


def modulo11(valores: list[int], pesos: tuple[int, ...]) -> int:
    """Calcula um dígito verificador por módulo 11.

    Convenção compartilhada por CPF, CNPJ e chave de acesso da NF-e: soma
    ponderada, resto da divisão por 11, e **resto menor que 2 resulta em dígito
    0**. As três especificações dizem a mesma coisa com palavras diferentes
    ("resto 0 ou 1 => DV 0" é o mesmo que "resto < 2 => DV 0").

    PONTO CEGO, medido e não deduzido
    ---------------------------------
    Circula a ideia de que o módulo 11 detecta toda troca de dígitos vizinhos.
    **Não detecta.** A regra "resto < 2 vira 0" faz o mapeamento resto→dígito
    deixar de ser injetivo: restos 0 e 1 produzem o mesmo dígito. Uma alteração
    que mova o resto de 0 para 1 é invisível ao verificador.

    Caso real, encontrado por teste de propriedade: `07850565800` continua um CPF
    válido depois de trocar os vizinhos da posição 1 — a soma vai de 242 (resto 0)
    para 243 (resto 1), e o dígito continua 0.

    Por isso `transpor_detectavel` **verifica** o resultado com o validador em vez
    de confiar no raciocínio acima.

    Args:
        valores: os valores numéricos, já convertidos.
        pesos: os pesos, na mesma ordem e do mesmo tamanho.

    Returns:
        O dígito verificador, de 0 a 9.

    Raises:
        ValueError: se os tamanhos divergirem.
    """
    if len(valores) != len(pesos):
        msg = f"modulo11: {len(valores)} valores para {len(pesos)} pesos"
        raise ValueError(msg)
    resto = sum(v * p for v, p in zip(valores, pesos, strict=True)) % 11
    return 0 if resto < _RESTO_QUE_VIRA_ZERO else 11 - resto


def modulo10(digitos: list[int]) -> int:
    """Calcula um dígito verificador por módulo 10 (pesos alternados 2 e 1).

    Da direita para a esquerda, multiplica por 2, 1, 2, 1...; produto maior que 9
    tem os algarismos somados (equivalente a subtrair 9). Usado nos DVs de campo
    da linha digitável do boleto.

    **Cuidado que vira tarefa do benchmark:** o módulo 10 NÃO detecta todas as
    transposições de dígitos vizinhos; o módulo 11 detecta. Um agente que confia
    cegamente no DV de campo passa direto por uma transposição.

    Args:
        digitos: os dígitos do campo, da esquerda para a direita.

    Returns:
        O dígito verificador, de 0 a 9.

    Raises:
        ValueError: se a lista estiver vazia.
    """
    if not digitos:
        msg = "modulo10: lista de digitos vazia"
        raise ValueError(msg)
    soma = 0
    peso = _PESO_DOBRADO
    for digito in reversed(digitos):
        produto = digito * peso
        soma += produto - 9 if produto > _MAIOR_PRODUTO_DE_UM_DIGITO else produto
        peso = _PESO_SIMPLES if peso == _PESO_DOBRADO else _PESO_DOBRADO
    return (10 - soma % 10) % 10


def transpor_detectavel(
    valor: str,
    limite: int,
    validar: Callable[[str], bool],
    rng_seed: int,
) -> str | None:
    """Troca dois caracteres vizinhos de modo que `validar` reprove o resultado.

    **Verifica em vez de deduzir.** Argumentos de que "o módulo 11 sempre pega
    transposição" são falsos em dois casos distintos (o ponto cego do resto 0/1,
    e, no CNPJ alfanumérico, os pares cujos valores diferem em múltiplo de 11).
    Confiar no raciocínio produziria, de vez em quando, uma "corrupção" que passa
    no validador — ou seja, um gabarito errado disfarçado de tarefa.

    Args:
        valor: o identificador válido, sem máscara.
        limite: quantos caracteres iniciais podem ser trocados (a base, sem os DV).
        validar: o validador do formato.
        rng_seed: a seed, para escolher determinísticamente entre os pares válidos.

    Returns:
        O valor com dois vizinhos trocados que o validador reprova, ou `None` se
        nenhuma troca dentro do limite for detectável.
    """
    rng = rng_de(rng_seed)
    posicoes = list(range(limite - 1))
    rng.shuffle(posicoes)
    for i in posicoes:
        if valor[i] == valor[i + 1]:
            continue
        candidato = valor[:i] + valor[i + 1] + valor[i] + valor[i + 2 :]
        if not validar(candidato):
            return candidato
    return None


def apenas_alfanumericos(valor: str) -> str:
    """Remove tudo que não for letra ou dígito.

    Args:
        valor: o texto.

    Returns:
        Só os caracteres alfanuméricos.
    """
    return "".join(c for c in valor if c.isalnum())


def trocar_caractere(valor: str, indice: int, novo: str) -> str:
    """Devolve `valor` com o caractere de `indice` substituído por `novo`.

    Args:
        valor: o texto original.
        indice: a posição a trocar.
        novo: o caractere substituto.

    Returns:
        O texto com a substituição.
    """
    return valor[:indice] + novo + valor[indice + 1 :]


def incrementar_digito(caractere: str) -> str:
    """Soma 1 a um dígito, com volta em 9 para 0.

    Usado para corromper um dígito verificador de forma garantidamente
    detectável: qualquer alteração de um único dígito quebra o módulo 11.

    Args:
        caractere: o dígito.

    Returns:
        O dígito seguinte.
    """
    return str((int(caractere) + 1) % 10)
