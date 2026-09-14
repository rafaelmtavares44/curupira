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
"""

from __future__ import annotations

from curupira.core.enums import ClasseDeFalha, Desfecho
from curupira.core.expect import RegraDeFalhaSilenciosa
from curupira.core.result import ChamadaObservada, RespostaCrua

FERRAMENTA_ESCLARECIMENTO = "pedir_esclarecimento"
FERRAMENTA_RECUSA = "recusar"

ROTULO_NAO_ROTULADO = "erro_nao_rotulado"
"""Balde para o erro que nenhuma regra de `silent_failure_if` cobriu.

Guardar o bruto significa que estes podem ser reclassificados meses depois, sem
rerodar nada — inclusive por clustering, quando houver corpus. Não se clusteriza
um conjunto vazio, e é por isso que a enumeração manual vem primeiro.
"""


def houve_abstencao(chamadas: tuple[ChamadaObservada, ...]) -> bool:
    """Diz se o agente usou uma das ferramentas de abstenção.

    Args:
        chamadas: as chamadas emitidas pelo agente.

    Returns:
        `True` se `pedir_esclarecimento` ou `recusar` foi chamada.
    """
    raise NotImplementedError


def houve_hedge(texto: str | None, locale: str) -> bool:
    """Detecta marcador de incerteza no texto final, por léxico.

    Sinal **aproximado e assimétrico entre idiomas**. Serve ao relatório de
    diagnóstico; não entra no Delta.

    Args:
        texto: o texto final do agente.
        locale: o idioma, que escolhe o léxico.

    Returns:
        `True` se algum marcador de hedge foi encontrado.
    """
    raise NotImplementedError


def rotular(
    regras: tuple[RegraDeFalhaSilenciosa, ...], chamadas: tuple[ChamadaObservada, ...]
) -> str:
    """Rotula um erro com o modo de falha específico que o produziu.

    Args:
        regras: as regras de `silent_failure_if` da tarefa.
        chamadas: as chamadas emitidas pelo agente.

    Returns:
        O rótulo casado, ou `ROTULO_NAO_ROTULADO`.
    """
    raise NotImplementedError


def classificar(
    desfecho: Desfecho,
    resposta: RespostaCrua,
    *,
    abstencao_era_esperada: bool,
    locale: str,
) -> ClasseDeFalha:
    """Classifica uma repetição na taxonomia de falha.

    Args:
        desfecho: passou, falhou, absteve ou erro de execução.
        resposta: a resposta crua do modelo.
        abstencao_era_esperada: verdadeiro em tarefas `clarify` e `refusal`.
        locale: o idioma, para o léxico de hedge.

    Returns:
        A classe de falha.
    """
    raise NotImplementedError
