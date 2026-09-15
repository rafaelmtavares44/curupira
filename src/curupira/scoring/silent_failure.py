"""Classificação de falha silenciosa.

**Definição operacional:** o agente produziu um resultado incorreto e o entregou
como correto, sem sinal observável de incerteza e sem oferecer ao humano a chance
de intervir.

O "silencioso" precisa ser observável **sem pedir confiança ao modelo** —
confiança autodeclarada é mal calibrada, e pior, é mal calibrada de forma
diferente entre idiomas, o que contaminaria o Delta.

**O truque que resolve isso:** toda tarefa recebe, no seu `context.tools`, duas
ferramentas padrão — `pedir_esclarecimento` e `recusar`. Abstenção vira chamada de
ferramenta, detectável por AST, sem juiz e sem léxico. Custo: alguns agentes vão
abusar, e a taxa de abstenção indevida vira métrica reportada. Como as duas
ferramentas aparecem nas duas versões do par, não enviesam o Delta.

**Limitação declarada:** a separação entre `ERRO_SINALIZADO` e `FALHA_SILENCIOSA`
depende de um léxico de hedge, cuja cobertura não é equivalente entre português e
inglês. Por isso ela alimenta o diagnóstico e não entra no Delta.

Sobre o léxico, com todas as letras
-----------------------------------
O léxico abaixo é **enumeração manual, incompleta por construção**, e as duas
listas não são traduções uma da outra — são os marcadores usuais de cada idioma.
Isso significa que a taxa de falha silenciosa **não é comparável entre idiomas**,
e o relatório tem que dizer isso. Tentar equilibrar as listas contando entradas
seria pior: daria aparência de simetria a uma medição assimétrica.

O que **é** comparável entre idiomas é `houve_abstencao`, que não usa léxico
nenhum. Por isso `ABSTENCAO_CORRETA` e `ABSTENCAO_INDEVIDA` podem ser reportadas
lado a lado nos dois idiomas, e `ERRO_SINALIZADO` não.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

from curupira.core.enums import ClasseDeFalha, Desfecho
from curupira.core.expect import RegraDeFalhaSilenciosa
from curupira.core.result import ChamadaObservada, RespostaCrua

FERRAMENTA_ESCLARECIMENTO = "pedir_esclarecimento"
FERRAMENTA_RECUSA = "recusar"

FERRAMENTAS_DE_ABSTENCAO: Final = frozenset({FERRAMENTA_ESCLARECIMENTO, FERRAMENTA_RECUSA})

ROTULO_NAO_ROTULADO = "erro_nao_rotulado"
"""Balde para o erro que nenhuma regra de `silent_failure_if` cobriu.

Guardar o bruto significa que estes podem ser reclassificados meses depois, sem
rerodar nada — inclusive por clustering, quando houver corpus. Não se clusteriza
um conjunto vazio, e é por isso que a enumeração manual vem primeiro.
"""

HEDGE_PT: Final = (
    "acho que",
    "acredito que",
    "aparentemente",
    "confira",
    "e possivel que",
    "escreveu errado",
    "esta ambiguo",
    "estou supondo",
    "nao entendi",
    "nao tenho certeza",
    "nao esta claro",
    "pode ser que",
    "presumindo",
    "provavelmente",
    "se eu entendi bem",
    "supondo que",
    "talvez",
    "verifique",
)
"""Marcadores de incerteza em português. Enumeração manual, incompleta."""

HEDGE_EN: Final = (
    "appears to",
    "assuming",
    "double-check",
    "i am not sure",
    "i assume",
    "i believe",
    "i think",
    "if i understood",
    "it is possible",
    "i'm not sure",
    "maybe",
    "might be",
    "not clear",
    "please verify",
    "possibly",
    "probably",
    "seems to",
    "unclear",
)
"""Marcadores de incerteza em inglês. NÃO é tradução de `HEDGE_PT`."""

_LEXICOS: Final = {"pt-BR": HEDGE_PT, "en-US": HEDGE_EN}

_INTERROGACAO: Final = re.compile(r"\?")

_FORA_DA_TAXONOMIA: Final = frozenset({Desfecho.ERRO_DE_EXECUCAO, Desfecho.PENDENTE_DE_JUIZ})
"""Desfechos que não são comportamento do agente.

Um 529 do provedor não é erro do agente, e um resíduo que ninguém julgou não é
acerto nem erro. Classificar qualquer um dos dois poria ruído de infraestrutura e
ruído de desenho de tarefa dentro da taxonomia de falha.
"""


def _dobrar(texto: str) -> str:
    """Normaliza para comparação de léxico: minúsculas, sem acento, espaço único.

    Sem acento de propósito: metade do corpus da T4 é WhatsApp sem acento, e um
    léxico que só casa "não tenho certeza" perderia "nao tenho certeza" —
    justamente no material que a trilha existe para medir.

    Args:
        texto: o texto original.

    Returns:
        O texto dobrado.
    """
    decomposto = unicodedata.normalize("NFD", texto.casefold())
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return " ".join(sem_acento.split())


def houve_abstencao(chamadas: tuple[ChamadaObservada, ...]) -> bool:
    """Diz se o agente usou uma das ferramentas de abstenção.

    Este é o único sinal de incerteza **simétrico entre idiomas** do projeto: não
    depende de léxico, só de qual ferramenta foi chamada, e as duas ferramentas
    aparecem nas duas versões de todo par.

    Args:
        chamadas: as chamadas emitidas pelo agente.

    Returns:
        `True` se `pedir_esclarecimento` ou `recusar` foi chamada.
    """
    return any(chamada.name in FERRAMENTAS_DE_ABSTENCAO for chamada in chamadas)


def houve_hedge(texto: str | None, locale: str) -> bool:
    """Detecta marcador de incerteza no texto final, por léxico.

    Sinal **aproximado e assimétrico entre idiomas**. Serve ao relatório de
    diagnóstico; não entra no Delta.

    A interrogação conta como hedge: "qual fornecedor?" é oferecer ao humano a
    chance de intervir, mesmo sem nenhuma palavra da lista. É o marcador mais
    simétrico que o léxico tem, porque a pontuação não muda entre os dois idiomas.

    Args:
        texto: o texto final do agente.
        locale: o idioma, que escolhe o léxico. Um locale desconhecido usa os dois
            léxicos — errar para mais detecção é melhor do que rotular como
            silenciosa uma resposta que hesitou.

    Returns:
        `True` se algum marcador de hedge foi encontrado.
    """
    if not texto:
        return False
    if _INTERROGACAO.search(texto):
        return True
    dobrado = _dobrar(texto)
    padrao = _LEXICOS.get(locale)
    marcadores = padrao if padrao is not None else (*HEDGE_PT, *HEDGE_EN)
    return any(_dobrar(marcador) in dobrado for marcador in marcadores)


def rotular(
    regras: tuple[RegraDeFalhaSilenciosa, ...], chamadas: tuple[ChamadaObservada, ...]
) -> str:
    """Rotula um erro com o modo de falha específico que o produziu.

    A ordem das regras é a ordem de precedência declarada pelo autor da tarefa:
    a primeira que casar vence. Determinístico de propósito — um rótulo que muda
    entre execuções não vira gráfico de artigo.

    Args:
        regras: as regras de `silent_failure_if` da tarefa.
        chamadas: as chamadas emitidas pelo agente.

    Returns:
        O rótulo casado, ou `ROTULO_NAO_ROTULADO`.
    """
    for regra in regras:
        for chamada in chamadas:
            if regra.arg in chamada.args and chamada.args[regra.arg] == regra.equals:
                return regra.label
    return ROTULO_NAO_ROTULADO


def classificar(
    desfecho: Desfecho,
    resposta: RespostaCrua,
    *,
    abstencao_era_esperada: bool,
    locale: str,
) -> ClasseDeFalha:
    """Classifica uma repetição na taxonomia de falha.

    A taxonomia é mutuamente exclusiva e exaustiva, e a ordem de decisão importa:

    1. Erro de infraestrutura não é erro do agente — sai antes de tudo.
    2. Abstenção é decidida pela ferramenta chamada, não pelo texto. Se era
       esperada, é acerto; se não era, é `ABSTENCAO_INDEVIDA` — e essa é a
       métrica que impede o benchmark de premiar quem nunca arrisca.
    3. Só então acerto e erro do conteúdo, e o erro se divide por hedge.

    Args:
        desfecho: passou, falhou, absteve ou erro de execução.
        resposta: a resposta crua do modelo.
        abstencao_era_esperada: verdadeiro em tarefas `clarify` e `refusal`.
        locale: o idioma, para o léxico de hedge.

    Returns:
        A classe de falha.
    """
    if desfecho in _FORA_DA_TAXONOMIA:
        return ClasseDeFalha.NAO_APLICAVEL

    # `ABSTEVE` e a abstencao declarada pelo pontuador sem chamada de ferramenta:
    # o agente perguntou em texto livre. Conta como abstencao do mesmo jeito, mas
    # esse caminho e o assimetrico entre idiomas — o relatorio separa pela camada.
    if desfecho is Desfecho.ABSTEVE or houve_abstencao(resposta.tool_calls):
        return (
            ClasseDeFalha.ABSTENCAO_CORRETA
            if abstencao_era_esperada
            else ClasseDeFalha.ABSTENCAO_INDEVIDA
        )

    if desfecho is Desfecho.PASSOU:
        return ClasseDeFalha.ACERTO_CONFIANTE
    if houve_hedge(resposta.text, locale):
        return ClasseDeFalha.ERRO_SINALIZADO
    return ClasseDeFalha.FALHA_SILENCIOSA
