"""O Delta PT-BR: a métrica-assinatura.

Por agente A, por suíte S, sobre o subconjunto D dos pares `parity: strict`, com
k repetições por tarefa:

    x_i = fração de repetições que passaram na versão EN do par i
    y_i = fração de repetições que passaram na versão PT-BR do par i
    d_i = x_i - y_i
    Delta = média de d_i sobre os n pares

Com k = 1 isso degenera em (b - c) / n, onde b são os pares EN-passa/PT-falha e c
o inverso — território clássico de McNemar.

**Três invariantes que este módulo impõe, não sugere:**

1. O Delta **nunca** agrega entre agentes. Delta é por agente. Um "Delta do
   estado da arte" exige modelo de efeitos mistos, e isso é v0.3.
2. Comparar Deltas de suítes ou de revisões de errata diferentes é **erro da
   ferramenta**, não pegadinha para o leitor.
3. Nenhuma tarefa pontuada por juiz entra em D.

**Sobre tamanho de amostra.** A fórmula de Connor (1987) para dados binários
pareados dá, com alfa de 0,05 bilateral e potência de 80%:

    n = [z_{a/2} * sqrt(pi_d) + z_b * sqrt(pi_d - delta^2)]^2 / delta^2

onde pi_d é a taxa de discordância. O driver não é o efeito, é pi_d — e pi_d é
desconhecido antes do piloto. Ordens de grandeza: detectar 10 pontos com pi_d de
0,20 exige cerca de 155 pares; 15 pontos com pi_d de 0,25, cerca de 85.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict


class ResultadoDelta(BaseModel):
    """O Delta PT-BR de um agente numa suíte, com o intervalo de confiança."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str
    suite_id: str
    errata_revision: int
    n_pares: int
    acuracia_en: float
    acuracia_pt: float
    delta: float
    ic_inferior: float
    ic_superior: float
    metodo_ic: str
    p_valor: float | None = None
    teste: str | None = None


def diferencas_pareadas(passou_en: Sequence[float], passou_pt: Sequence[float]) -> list[float]:
    """Calcula d_i para cada par.

    Args:
        passou_en: fração de repetições que passaram em inglês, por par.
        passou_pt: idem em português.

    Returns:
        A lista de diferenças.

    Raises:
        ValueError: se as sequências tiverem tamanhos diferentes.
    """
    raise NotImplementedError


def mcnemar_exato(b: int, c: int) -> float:
    """Teste exato de McNemar, para k = 1.

    Binomial sobre b em b + c, **não** a aproximação qui-quadrado: o número de
    discordantes vai ser pequeno, e a aproximação mente justamente aí.

    Args:
        b: pares em que EN passou e PT falhou.
        c: pares em que EN falhou e PT passou.

    Returns:
        O valor-p bilateral.
    """
    raise NotImplementedError


def wilcoxon_pareado(diferencas: Sequence[float]) -> float:
    """Wilcoxon signed-rank sobre as diferenças pareadas, para k maior que 1.

    Args:
        diferencas: os d_i.

    Returns:
        O valor-p bilateral.
    """
    raise NotImplementedError


def bootstrap_bca(
    diferencas: Sequence[float], *, replicas: int = 10_000, seed: int = 0, alfa: float = 0.05
) -> tuple[float, float]:
    """Intervalo de confiança BCa, reamostrando **pares**.

    O par é a unidade de clusterização. Seed fixa, porque um intervalo de
    confiança que muda a cada execução não é reprodutível.

    Args:
        diferencas: os d_i.
        replicas: número de reamostragens.
        seed: seed do gerador.
        alfa: nível de significância.

    Returns:
        Os limites inferior e superior.
    """
    raise NotImplementedError


def calcular(
    agent_id: str,
    suite_id: str,
    errata_revision: int,
    passou_en: Sequence[float],
    passou_pt: Sequence[float],
) -> ResultadoDelta:
    """Calcula o Delta PT-BR com intervalo de confiança.

    O produto é "o Delta do agente X é 12 pontos, IC 95% [6, 18]", não
    "p < 0,05". O IC é o principal; o valor-p é secundário.

    Args:
        agent_id: o agente sendo pontuado.
        suite_id: a suíte.
        errata_revision: a revisão de errata aplicada.
        passou_en: fração de repetições que passaram em inglês, por par.
        passou_pt: idem em português.

    Returns:
        O resultado completo.
    """
    raise NotImplementedError
