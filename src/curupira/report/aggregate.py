"""Etapa 3: agregar. Sempre a partir do bruto, nunca durante a execução."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from curupira.core.enums import Trilha
from curupira.core.suite import Errata


class MetricasDaTrilha(BaseModel):
    """As métricas reportadas por trilha."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trilha: Trilha
    n_tarefas: int
    acuracia: float
    taxa_de_falha_silenciosa: float
    taxa_de_falha_silenciosa_rotulada: float
    taxa_de_abstencao_indevida: float
    taxa_de_instabilidade: float
    """Fração de tarefas cujo resultado variou entre repetições. Um acerto que só
    acontece às vezes não é competência."""

    consistencia_de_grupo: float | None = None
    """Fração de grupos de variantes acertados integralmente. Quem entende
    separador decimal acerta o grupo inteiro; quem casou padrão, um subconjunto."""

    custo_por_acerto_brl: float
    latencia_p50_ms: int
    latencia_p95_ms: int
    fracao_pontuada_por_juiz: float
    """Se passar de ~15% numa trilha, a tarefa está mal desenhada."""


def agregar(
    raw: Path, *, errata: Errata | None = None, saida: Path | None = None
) -> dict[str, MetricasDaTrilha]:
    """Agrega um `raw.jsonl` em métricas por trilha.

    Imprime sempre os **dois** números, com e sem errata, e as linhas de base
    triviais ao lado das notas.

    Args:
        raw: o arquivo de respostas cruas.
        errata: a errata a aplicar, quando houver.
        saida: onde gravar o `report.json`, quando desejado.

    Returns:
        Mapa de trilha para métricas.
    """
    raise NotImplementedError
