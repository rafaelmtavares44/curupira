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

Por que não há scipy aqui
-------------------------
As três estatísticas de que precisamos cabem na biblioteca padrão:
`math.comb` resolve o McNemar exato, e `statistics.NormalDist` traz `cdf` e
`inv_cdf`, que é tudo o que o BCa pede. Somar ~30 MB de superfície de supply
chain — com janela de carência, lockfile com hash e pip-audit, como manda o
projeto — por três funções seria mau negócio.

O risco dessa escolha é óbvio: implementação própria erra. A mitigação é
`tests/test_delta.py`, onde os valores de referência foram **conferidos contra o
scipy** e congelados como constantes, com a versão e a data do conferimento.
O CI não ganha dependência; o número ganha testemunha.

**Sobre tamanho de amostra.** A fórmula de Connor (1987) para dados binários
pareados dá, com alfa de 0,05 bilateral e potência de 80%:

    n = [z_{a/2} * sqrt(pi_d) + z_b * sqrt(pi_d - delta^2)]^2 / delta^2

onde pi_d é a taxa de discordância. O driver não é o efeito, é pi_d — e pi_d é
desconhecido antes do piloto. Ordens de grandeza: detectar 10 pontos com pi_d de
0,20 exige cerca de 155 pares; 15 pontos com pi_d de 0,25, cerca de 85.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from statistics import NormalDist
from typing import Final

from pydantic import BaseModel, ConfigDict

_NORMAL: Final = NormalDist()

N_MINIMO_PARA_BCA: Final = 10
"""Abaixo disto o BCa não é estimável com honestidade.

A aceleração vem de um jackknife, e um jackknife com 3 pares estima a assimetria
da distribuição a partir de 3 pontos. O intervalo sai, tem duas casas decimais e
não significa nada. Aqui o método degrada para percentil e **diz o nome** no
campo `metodo_ic`, para que ninguém leia um número de piloto como se fosse
resultado.
"""

MAXIMO_PARA_WILCOXON_EXATO: Final = 20
"""Acima disto a enumeração exata de 2^n sinais sai de mão (2^20 ≈ 1 milhão)."""

METODO_BCA: Final = "bootstrap_bca"
METODO_PERCENTIL: Final = "bootstrap_percentil"
METODO_AMOSTRA_INSUFICIENTE: Final = "amostra_insuficiente"
METODO_DEGENERADO: Final = "sem_variacao"


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
        ValueError: se as sequências tiverem tamanhos diferentes, ou se alguma
            fração estiver fora de [0, 1] — o que significaria que o agregador
            montou os vetores errado, e um Delta sobre vetores errados é pior do
            que Delta nenhum.
    """
    if len(passou_en) != len(passou_pt):
        msg = (
            f"os vetores pareados tem tamanhos diferentes ({len(passou_en)} e "
            f"{len(passou_pt)}): isso nao e um pareamento"
        )
        raise ValueError(msg)
    fora = [v for v in (*passou_en, *passou_pt) if not 0.0 <= v <= 1.0]
    if fora:
        msg = f"fracao de repeticoes fora de [0, 1]: {fora[:3]}"
        raise ValueError(msg)
    return [en - pt for en, pt in zip(passou_en, passou_pt, strict=True)]


def mcnemar_exato(b: int, c: int) -> float:
    """Teste exato de McNemar, para k = 1.

    Binomial sobre b em b + c com p = 0,5, **não** a aproximação qui-quadrado: o
    número de discordantes vai ser pequeno, e a aproximação mente justamente aí.

    Args:
        b: pares em que EN passou e PT falhou.
        c: pares em que EN falhou e PT passou.

    Returns:
        O valor-p bilateral. Sem nenhum discordante o valor é 1,0: não há
        evidência de diferença, e não há como haver.

    Raises:
        ValueError: se `b` ou `c` for negativo.
    """
    if b < 0 or c < 0:
        msg = f"contagens de discordantes nao podem ser negativas (b={b}, c={c})"
        raise ValueError(msg)
    n = b + c
    if n == 0:
        return 1.0

    extremo = min(b, c)
    cauda = sum(math.comb(n, k) for k in range(extremo + 1)) / 2**n
    return float(min(1.0, 2 * cauda))


def _postos_com_empate(valores: Sequence[float]) -> tuple[list[float], bool]:
    """Postos de 1 a n, com posto médio nos empates.

    Args:
        valores: os valores a ordenar.

    Returns:
        Os postos na ordem original, e se houve algum empate.
    """
    ordenados = sorted(range(len(valores)), key=lambda i: valores[i])
    postos = [0.0] * len(valores)
    houve_empate = False
    inicio = 0
    while inicio < len(ordenados):
        fim = inicio
        while fim + 1 < len(ordenados) and (
            valores[ordenados[fim + 1]] == valores[ordenados[inicio]]
        ):
            fim += 1
        media = (inicio + fim) / 2 + 1
        if fim > inicio:
            houve_empate = True
        for posicao in range(inicio, fim + 1):
            postos[ordenados[posicao]] = media
        inicio = fim + 1
    return postos, houve_empate


def _wilcoxon_exato(postos: Sequence[float], estatistica: float) -> float:
    """Valor-p exato por enumeração dos 2^n padrões de sinal.

    Só é chamado quando não há empates, portanto os postos são inteiros e a
    distribuição é a soma de subconjuntos — resolvida por programação dinâmica.

    Args:
        postos: os postos, sem empates.
        estatistica: a soma dos postos positivos observada.

    Returns:
        O valor-p bilateral.
    """
    total = int(sum(postos))
    contagem = [0] * (total + 1)
    contagem[0] = 1
    for posto in postos:
        passo = int(posto)
        for soma in range(total, passo - 1, -1):
            contagem[soma] += contagem[soma - passo]

    combinacoes = 2 ** len(postos)
    alvo = min(estatistica, total - estatistica)
    cauda = sum(contagem[: int(alvo) + 1]) / combinacoes
    return float(min(1.0, 2 * cauda))


def wilcoxon_pareado(diferencas: Sequence[float]) -> float:
    """Wilcoxon signed-rank sobre as diferenças pareadas, para k maior que 1.

    Diferenças exatamente zero são **descartadas**, como manda a convenção do
    teste: um par em que os dois idiomas se saíram igual não é evidência a favor
    nem contra, e mantê-lo apenas encolheria o valor-p de graça.

    Sem empates nos postos, o valor-p é exato por enumeração até
    `MAXIMO_PARA_WILCOXON_EXATO` pares. Com empates — o caso comum quando k é
    pequeno e as frações se repetem — cai para a aproximação normal com correção
    de continuidade e de empates, porque a distribuição exata deixa de ser a soma
    de subconjuntos de inteiros.

    Args:
        diferencas: os d_i.

    Returns:
        O valor-p bilateral. Com todas as diferenças nulas devolve 1,0.
    """
    nao_nulas = [d for d in diferencas if d != 0.0]
    if not nao_nulas:
        return 1.0

    postos, houve_empate = _postos_com_empate([abs(d) for d in nao_nulas])
    positivos = sum(p for p, d in zip(postos, nao_nulas, strict=True) if d > 0)
    n = len(nao_nulas)

    if not houve_empate and n <= MAXIMO_PARA_WILCOXON_EXATO:
        return _wilcoxon_exato(postos, positivos)

    media = n * (n + 1) / 4
    correcao_de_empates = sum(p**3 - p for p in _contagens_de_empate(postos)) / 48
    variancia = n * (n + 1) * (2 * n + 1) / 24 - correcao_de_empates
    if variancia <= 0:
        return 1.0
    z = (abs(positivos - media) - 0.5) / math.sqrt(variancia)
    return min(1.0, 2 * (1 - _NORMAL.cdf(z)))


def _contagens_de_empate(postos: Sequence[float]) -> list[float]:
    """Tamanho de cada grupo de postos empatados."""
    grupos: dict[float, int] = {}
    for posto in postos:
        grupos[posto] = grupos.get(posto, 0) + 1
    return [float(t) for t in grupos.values() if t > 1]


def _percentil(ordenados: Sequence[float], fracao: float) -> float:
    """Percentil por interpolação linear numa amostra já ordenada."""
    if len(ordenados) == 1:
        return ordenados[0]
    posicao = fracao * (len(ordenados) - 1)
    baixo = math.floor(posicao)
    alto = math.ceil(posicao)
    if baixo == alto:
        return ordenados[baixo]
    return ordenados[baixo] + (posicao - baixo) * (ordenados[alto] - ordenados[baixo])


def _aceleracao(diferencas: Sequence[float]) -> float | None:
    """Aceleração do BCa, por jackknife.

    Returns:
        A aceleração, ou `None` quando a amostra não varia — nesse caso o
        denominador é zero e não há assimetria a corrigir.
    """
    n = len(diferencas)
    total = math.fsum(diferencas)
    medias = [(total - d) / (n - 1) for d in diferencas]
    media_das_medias = math.fsum(medias) / n
    desvios = [media_das_medias - m for m in medias]
    denominador = 6 * math.fsum(d**2 for d in desvios) ** 1.5
    if denominador == 0:
        return None
    return float(math.fsum(d**3 for d in desvios) / denominador)


def bootstrap_bca(
    diferencas: Sequence[float], *, replicas: int = 10_000, seed: int = 0, alfa: float = 0.05
) -> tuple[float, float, str]:
    """Intervalo de confiança BCa, reamostrando **pares**.

    O par é a unidade de clusterização: reamostrar repetições em vez de pares
    trataria as k repetições de uma tarefa como observações independentes, e elas
    não são — o intervalo sairia estreito demais, o que é o erro que mais engana.

    Seed fixa, porque um intervalo de confiança que muda a cada execução não é
    reprodutível, e o projeto inteiro existe para produzir número reprodutível.

    O método **degrada e declara**, nunca degrada em silêncio:

    - amostra sem variação alguma: o intervalo é o próprio ponto;
    - `z0` infinito (nenhuma réplica de um dos lados) ou aceleração indefinida:
      cai para percentil simples;
    - menos de `N_MINIMO_PARA_BCA` pares: percentil, rotulado como amostra
      insuficiente.

    Args:
        diferencas: os d_i.
        replicas: número de reamostragens.
        seed: seed do gerador.
        alfa: nível de significância.

    Returns:
        Limite inferior, limite superior e o nome do método que de fato produziu
        o intervalo.

    Raises:
        ValueError: se a lista estiver vazia ou `replicas` for menor que 1.
    """
    if not diferencas:
        msg = "nao ha intervalo de confianca sobre zero pares"
        raise ValueError(msg)
    if replicas < 1:
        msg = f"replicas precisa ser >= 1 (veio {replicas})"
        raise ValueError(msg)

    ponto = math.fsum(diferencas) / len(diferencas)
    if all(d == diferencas[0] for d in diferencas):
        return ponto, ponto, METODO_DEGENERADO

    # B311/S311 suprimido aqui e SO aqui: reamostragem estatistica nao e uso
    # criptografico, e a seed fixa e requisito — um gerador criptografico nem
    # aceitaria seed, e um IC que muda a cada execucao nao seria reprodutivel.
    # Supressao local em vez de `skips` global no pyproject, para que um uso
    # realmente inseguro de `random` continue sendo pego no resto do projeto.
    gerador = random.Random(seed)  # noqa: S311  # nosec B311
    n = len(diferencas)
    amostras = sorted(math.fsum(gerador.choices(diferencas, k=n)) / n for _ in range(replicas))

    abaixo = sum(1 for a in amostras if a < ponto)
    aceleracao = _aceleracao(diferencas)
    insuficiente = n < N_MINIMO_PARA_BCA

    if abaixo in (0, replicas) or aceleracao is None or insuficiente:
        metodo = METODO_AMOSTRA_INSUFICIENTE if insuficiente else METODO_PERCENTIL
        return _percentil(amostras, alfa / 2), _percentil(amostras, 1 - alfa / 2), metodo

    z0 = _NORMAL.inv_cdf(abaixo / replicas)
    z_baixo = _NORMAL.inv_cdf(alfa / 2)
    z_alto = _NORMAL.inv_cdf(1 - alfa / 2)
    fracoes = [_NORMAL.cdf(z0 + (z0 + z) / (1 - aceleracao * (z0 + z))) for z in (z_baixo, z_alto)]
    limites = [_percentil(amostras, min(max(f, 0.0), 1.0)) for f in fracoes]
    return min(limites), max(limites), METODO_BCA


def _discordantes(passou_en: Sequence[float], passou_pt: Sequence[float]) -> tuple[int, int] | None:
    """Conta b e c quando os dados são binários, para o McNemar exato.

    Returns:
        `(b, c)` se toda fração é 0 ou 1 (ou seja, k = 1 ou concordância total),
        senão `None` — e aí o teste certo é o de Wilcoxon.
    """
    if any(v not in (0.0, 1.0) for v in (*passou_en, *passou_pt)):
        return None
    b = sum(1 for en, pt in zip(passou_en, passou_pt, strict=True) if en > pt)
    c = sum(1 for en, pt in zip(passou_en, passou_pt, strict=True) if pt > en)
    return b, c


def calcular(
    agent_id: str,
    suite_id: str,
    errata_revision: int,
    passou_en: Sequence[float],
    passou_pt: Sequence[float],
) -> ResultadoDelta:
    """Calcula o Delta PT-BR com intervalo de confiança.

    O produto é "o Delta do agente X é 12 pontos, IC 95% [6, 18]", não
    "p < 0,05". O IC é o principal; o valor-p é secundário, e o campo `metodo_ic`
    diz por qual caminho o intervalo saiu.

    A escolha do teste é automática e segue os dados, não a preferência de quem
    escreve: com frações binárias (k = 1, ou concordância total em todas as
    repetições) o teste é McNemar exato; com frações intermediárias, Wilcoxon.

    Args:
        agent_id: o agente sendo pontuado.
        suite_id: a suíte.
        errata_revision: a revisão de errata aplicada.
        passou_en: fração de repetições que passaram em inglês, por par.
        passou_pt: idem em português.

    Returns:
        O resultado completo.

    Raises:
        ValueError: se não houver par nenhum, ou se os vetores não parearem.
    """
    if not passou_en:
        msg = (
            "o subconjunto do Delta esta vazio: nao ha par strict com as duas "
            "versoes decididas. Sem pares nao ha Delta, e um Delta de zero pares "
            "seria um numero inventado"
        )
        raise ValueError(msg)

    diferencas = diferencas_pareadas(passou_en, passou_pt)
    inferior, superior, metodo = bootstrap_bca(diferencas)

    contagens = _discordantes(passou_en, passou_pt)
    if contagens is not None:
        b, c = contagens
        p_valor, teste = mcnemar_exato(b, c), "mcnemar_exato"
    else:
        p_valor, teste = wilcoxon_pareado(diferencas), "wilcoxon_pareado"

    return ResultadoDelta(
        agent_id=agent_id,
        suite_id=suite_id,
        errata_revision=errata_revision,
        n_pares=len(diferencas),
        acuracia_en=math.fsum(passou_en) / len(passou_en),
        acuracia_pt=math.fsum(passou_pt) / len(passou_pt),
        delta=math.fsum(diferencas) / len(diferencas),
        ic_inferior=inferior,
        ic_superior=superior,
        metodo_ic=metodo,
        p_valor=p_valor,
        teste=teste,
    )
