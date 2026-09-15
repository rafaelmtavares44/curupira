"""Placa veicular: Mercosul `LLLNLNN` e o formato antigo `LLLNNNN`.

Sem dígito verificador; a validação é expressão regular mais regras de conjunto
de caracteres. Placa identifica um veículo, e por tabela um proprietário, então
segue o mesmo tratamento de risco do CNPJ: nunca combinada com nome e endereço.

A armadilha que vale a tarefa: a conversão
------------------------------------------
Converter `ABC-1234` para Mercosul **não é reformatar**. A regra troca o
**segundo dígito** por uma letra, pelo mapa `0→A, 1→B, ... 9→J`, e mantém todo o
resto:

    ABC-1234  ->  ABC1C34
                     ^ o "2" virou "C"

Um agente que apenas remove o hífen produz `ABC1234`, que é uma placa antiga
perfeitamente válida — e por isso o erro **não é detectável pelo validador**.
É falha silenciosa em estado puro, e é o motivo de `converter_para_mercosul`
existir aqui em vez de virar prosa no enunciado da tarefa.

As letras A a J na quinta posição são, por construção, marca de placa convertida:
emplacamentos novos usam o alfabeto inteiro naquela casa.
"""

from __future__ import annotations

import re
import string
from typing import Final

from curupira.core.enums import Corrupcao
from curupira.formatos.base import Gerado, rng_de

TAMANHO: Final = 7

_MERCOSUL: Final = re.compile(r"^[A-Z]{3}\d[A-Z]\d{2}$")
_ANTIGA_NUA: Final = re.compile(r"^[A-Z]{3}\d{4}$")
_ANTIGA_MASCARADA: Final = re.compile(r"^[A-Z]{3}-\d{4}$")

LETRAS_DE_CONVERSAO: Final = "ABCDEFGHIJ"
"""Mapa do digito convertido: indice e o digito, valor e a letra."""

POSICAO_CONVERTIDA: Final = 4
"""Indice, na placa sem hifen, do caractere que a conversao troca."""


def e_mercosul(valor: str) -> bool:
    """Diz se a placa está no padrão Mercosul.

    Args:
        valor: a placa, em maiúsculas.

    Returns:
        `True` se casa com `LLLNLNN`.
    """
    return bool(_MERCOSUL.match(valor))


def e_antiga(valor: str) -> bool:
    """Diz se a placa está no padrão antigo, com ou sem hífen.

    Args:
        valor: a placa, em maiúsculas.

    Returns:
        `True` se casa com `LLLNNNN` ou `LLL-NNNN`.
    """
    return bool(_ANTIGA_NUA.match(valor) or _ANTIGA_MASCARADA.match(valor))


def validar(valor: str) -> bool:
    """Valida uma placa, nos formatos Mercosul e antigo.

    Exige **maiúsculas**. Minúscula não é variação de grafia aceita: o padrão
    Denatran é maiúsculo, e aceitar `abc1d23` tiraria de `MASCARA_ERRADA` o
    caso mais comum que um agente produz.

    Args:
        valor: a placa, com ou sem hífen.

    Returns:
        `True` se casa com um dos formatos aceitos.
    """
    return e_mercosul(valor) or e_antiga(valor)


def converter_para_mercosul(antiga: str) -> str:
    """Converte uma placa do padrão antigo para o Mercosul.

    O segundo dígito vira letra pelo mapa `0→A ... 9→J`; tudo mais permanece.

    Args:
        antiga: a placa antiga, com ou sem hífen.

    Returns:
        A placa no padrão Mercosul.

    Raises:
        ValueError: se a placa não estiver no padrão antigo.
    """
    if not e_antiga(antiga):
        msg = f"nao e uma placa do padrao antigo: {antiga!r}"
        raise ValueError(msg)
    nua = antiga.replace("-", "")
    digito = int(nua[POSICAO_CONVERTIDA])
    return nua[:POSICAO_CONVERTIDA] + LETRAS_DE_CONVERSAO[digito] + nua[POSICAO_CONVERTIDA + 1 :]


def gerar(rng_seed: int, *, mercosul: bool = True) -> Gerado:
    """Gera uma placa.

    Args:
        rng_seed: a seed.
        mercosul: formato Mercosul (`ABC1D23`) ou antigo (`ABC1234`).

    Returns:
        A placa gerada.
    """
    rng = rng_de(rng_seed)
    letras = "".join(rng.choice(string.ascii_uppercase) for _ in range(3))
    if mercosul:
        valor = (
            f"{letras}{rng.randrange(10)}"
            f"{rng.choice(string.ascii_uppercase)}"
            f"{rng.randrange(100):02d}"
        )
    else:
        valor = f"{letras}{rng.randrange(10000):04d}"
    return Gerado(valor=valor, valido=True, corrupcao=None, seed=rng_seed)


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe uma placa pelo modo pedido.

    Args:
        valor: uma placa válida.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        A placa corrompida.

    Raises:
        ValueError: se o valor não for válido, ou se o modo não se aplicar —
            placa não tem dígito verificador, então `DV_TROCADO`, `TRANSPOSICAO`
            e `FAIXA_INVALIDA` não são garantidamente detectáveis. Em particular,
            **não existe placa fora de faixa**: qualquer combinação que case o
            padrão é sintaticamente válida.
    """
    if not validar(valor):
        msg = f"nao da para corromper uma placa invalida: {valor!r}"
        raise ValueError(msg)

    rng = rng_de(rng_seed)
    nua = valor.replace("-", "")

    if modo is Corrupcao.MASCARA_ERRADA:
        # Minuscula numa placa Mercosul; hifen numa Mercosul tambem nao existe.
        corrompido = nua.lower() if e_mercosul(nua) else f"{nua[:3]}.{nua[3:]}"
    elif modo is Corrupcao.TAMANHO_ERRADO:
        corrompido = nua[:-1]
    elif modo is Corrupcao.CARACTERE_INVALIDO:
        posicao = rng.randrange(TAMANHO)
        corrompido = nua[:posicao] + "#" + nua[posicao + 1 :]
    elif modo is Corrupcao.SEQUENCIA_REPETIDA:
        # Sete letras iguais nao casam nem Mercosul nem o padrao antigo, porque
        # nos dois ha posicao obrigatoriamente numerica.
        corrompido = "A" * TAMANHO
    else:
        msg = (
            f"{modo.value} nao se aplica a placa: nao ha digito verificador nem "
            "faixa reservada, entao nao ha como garantir que o resultado seja "
            "reprovado"
        )
        raise ValueError(msg)

    return Gerado(valor=corrompido, valido=False, corrupcao=modo, seed=rng_seed)
