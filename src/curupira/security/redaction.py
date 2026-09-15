"""Redação de segredos em log e em qualquer saída textual.

Barreira 3 das seis descritas em SECURITY.md.

O `SecretStr` do Pydantic mascara em `repr` e em `str`, o que já resolve o
descuido comum. Ele **não** salva de `logger.debug(f"...{chave.get_secret_value()}")`
nem de um traceback que capture a variável. Por isso a redação aqui é **por
valor**: qualquer ocorrência de um segredo registrado é substituída, não importa
como chegou lá.

Duas ferramentas, com papéis diferentes:

- `FormatadorDeRedacao` é o **primário**. Redige a string final já formatada, o
  que cobre mensagem, argumentos e traceback de exceção de uma vez.
- `FiltroDeRedacao` é o **subsidiário**, para quando não se controla o formatador
  (biblioteca de terceiros, handler alheio). Cobre `msg` e `args`, mas **não**
  cobre um traceback formatado depois — limitação declarada de propósito.

Sobre concorrência
------------------
O registro de segredos é uma **tupla imutável trocada por rebind de atributo**,
não um `set` mutável. Isso não é preciosismo: `redigir` roda no caminho de log,
e iterar um `set` enquanto outra thread insere levanta `RuntimeError` — ou seja,
a barreira de segurança estouraria exatamente dentro do log, que é o pior lugar
possível para estourar. Com a tupla, `redigir` captura a referência uma vez e
itera algo que não pode mudar. De quebra, a ordenação por comprimento sai do
caminho quente (leitura) para o frio (registro).

Limitação conhecida, declarada
------------------------------
A redação é por **valor exato**. Se algum código imprimir apenas um pedaço da
chave (`chave[:8]` numa mensagem de erro, por exemplo), a redação não pega.
Não existe correção boa para isso aqui: registrar prefixos redigiria texto
legítimo e daria falsa sensação de cobertura. A barreira correta contra
truncamento é estrutural e vive nos adaptadores — nenhum adaptador constrói
mensagem de erro com pedaço de chave, e `corpo_literal_enviado` nunca inclui
headers (ADR 0002).
"""

from __future__ import annotations

import logging
import os
from typing import Final

from pydantic import SecretStr

MARCA_REDIGIDO: Final[str] = "[REDIGIDO]"

TAMANHO_MINIMO_DE_SEGREDO: Final[int] = 8
"""Segredos curtos demais fariam a redação destruir texto legítimo.

Uma chave de 3 caracteres registrada aqui transformaria toda ocorrência dessas 3
letras em `[REDIGIDO]`, inclusive dentro de palavras comuns. Recusar é mais
seguro do que aceitar e produzir log ilegível.
"""


class _Registro:
    """Porta-tupla. Existe para trocar o registro sem `global` e sem lock."""

    __slots__ = ("segredos",)

    def __init__(self) -> None:
        """Começa vazio."""
        self.segredos: tuple[str, ...] = ()


_REGISTRO: Final[_Registro] = _Registro()


def registrar_segredo(valor: str) -> None:
    """Registra um valor a ser redigido de toda saída textual.

    Ordena do mais longo para o mais curto já no registro, para que um segredo
    que seja prefixo de outro não deixe o sufixo exposto na hora de redigir.

    Args:
        valor: o segredo em claro.

    Raises:
        ValueError: se o valor for curto demais para ser redigido com segurança.
    """
    if len(valor) < TAMANHO_MINIMO_DE_SEGREDO:
        msg = (
            f"segredo com menos de {TAMANHO_MINIMO_DE_SEGREDO} caracteres nao pode "
            "ser registrado: a redacao por valor destruiria texto legitimo"
        )
        raise ValueError(msg)
    atual = _REGISTRO.segredos
    if valor in atual:
        return
    _REGISTRO.segredos = tuple(sorted({*atual, valor}, key=len, reverse=True))


def carregar_chave(variavel: str) -> SecretStr:
    """Lê uma chave de API do ambiente e a registra para redação, num passo só.

    **Este é o único caminho sancionado para obter uma chave.** A razão é a
    janela: se o segredo for registrado depois da primeira linha de log, essa
    linha já vazou. Aqui não há como pegar a chave sem registrá-la — a barreira
    passa a ser estrutural em vez de disciplinar.

    Args:
        variavel: nome da variável de ambiente, ex.: `CURUPIRA_ANTHROPIC_API_KEY`.

    Returns:
        A chave, embrulhada em `SecretStr`.

    Raises:
        KeyError: se a variável não existir ou estiver vazia.
        ValueError: se o valor for curto demais para ser redigido com segurança.
    """
    valor = os.environ.get(variavel, "")
    if not valor:
        msg = f"variavel de ambiente {variavel} ausente ou vazia"
        raise KeyError(msg)
    registrar_segredo(valor)
    return SecretStr(valor)


def esquecer_segredos() -> None:
    """Limpa o registro de segredos. Usado entre testes."""
    _REGISTRO.segredos = ()


def redigir(texto: str) -> str:
    """Substitui toda ocorrência de segredo registrado pela marca de redação.

    Captura a tupla de segredos uma única vez, então é seguro chamar em paralelo
    com `registrar_segredo`.

    Args:
        texto: o texto a redigir.

    Returns:
        O texto com os segredos substituídos.
    """
    segredos = _REGISTRO.segredos
    if not segredos:
        return texto
    resultado = texto
    for segredo in segredos:
        resultado = resultado.replace(segredo, MARCA_REDIGIDO)
    return resultado


def contem_segredo(texto: str) -> bool:
    """Diz se algum segredo registrado aparece no texto.

    Serve para o caso em que redigir seria a decisão **errada**. O corpo da
    requisição gravado numa rodada nunca deveria conter a chave; se contiver, há
    um defeito no adaptador, e substituir por `[REDIGIDO]` esconderia o defeito
    atrás de um artefato aparentemente limpo. O runner usa esta função para
    **recusar** gravar, em vez de limpar.

    Args:
        texto: o texto a inspecionar.

    Returns:
        `True` se algum segredo registrado estiver presente.
    """
    segredos = _REGISTRO.segredos
    return any(segredo in texto for segredo in segredos)


class FormatadorDeRedacao(logging.Formatter):
    """Formatador que redige a saída final já montada.

    É o mecanismo **primário**: por atuar depois da formatação, cobre a mensagem,
    os argumentos e o traceback de exceção de uma só vez.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Formata o registro e redige os segredos da string resultante.

        Args:
            record: o registro de log.

        Returns:
            A linha formatada, sem segredos.
        """
        return redigir(super().format(record))


class FiltroDeRedacao(logging.Filter):
    """Filtro que redige mensagem e argumentos de um registro de log.

    Mecanismo **subsidiário**, para quando não se controla o formatador.

    Limitação declarada: não cobre traceback de exceção, que é formatado depois
    do filtro. Quando for possível escolher, use `FormatadorDeRedacao`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Redige o registro no lugar e deixa passar.

        Args:
            record: o registro de log.

        Returns:
            Sempre `True`: este filtro redige, não descarta.
        """
        if isinstance(record.msg, str):
            record.msg = redigir(record.msg)

        args = record.args
        if isinstance(args, tuple):
            record.args = tuple(redigir(a) if isinstance(a, str) else a for a in args)
        elif isinstance(args, dict):
            record.args = {
                chave: (redigir(v) if isinstance(v, str) else v) for chave, v in args.items()
            }
        return True


def instalar_redacao(logger: logging.Logger | None = None) -> None:
    """Instala a redação em todos os handlers de um logger.

    Envolve o formatador de cada handler com `FormatadorDeRedacao` e acrescenta o
    `FiltroDeRedacao` como rede de segurança.

    Args:
        logger: o logger a proteger. Sem argumento, protege o logger raiz.
    """
    alvo = logger if logger is not None else logging.getLogger()
    alvo.addFilter(FiltroDeRedacao())
    for handler in alvo.handlers:
        formato = handler.formatter._fmt if handler.formatter else None  # noqa: SLF001
        datefmt = handler.formatter.datefmt if handler.formatter else None
        handler.setFormatter(FormatadorDeRedacao(formato, datefmt))
        handler.addFilter(FiltroDeRedacao())
