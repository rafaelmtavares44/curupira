"""Suíte congelada e errata.

A suíte é o mecanismo principal de comparabilidade: `suites/v0.1.yaml` lista id +
`task_version` + `sha256` de cada tarefa, com `frozen_at`. Tarefa nova nunca
entra em suíte congelada; vai para a próxima. A v0.1 continua rodável para
sempre.

A errata resolve o engessamento sem quebrar a suíte: a suíte **não muda um byte**
e a errata, append-only, lista as tarefas defeituosas. O runner continua rodando
tarefas com errata e gravando o resultado; quem exclui é o agregador, que imprime
os dois números — com e sem errata.

Duas travas contra abuso, que são o ponto:

1. Errata exige defeito demonstrável, com teste que o reproduz. "O modelo X vai
   mal nessa tarefa" não é defeito.
2. **Teto de 5%.** Passando disso, a suíte está morta, não remendada: encerra-se
   e corta-se a próxima. Sem o teto, errata vira edição silenciosa com outro nome.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

_CFG = ConfigDict(extra="forbid", frozen=True)

TETO_DE_ERRATA = 0.05
"""Fração máxima de tarefas com errata antes de a suíte ser declarada morta."""


class EntradaDeSuite(BaseModel):
    """Uma tarefa congelada numa suíte."""

    model_config = _CFG

    task_id: str
    task_version: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Suite(BaseModel):
    """Uma suíte congelada.

    `delta_subset` é a lista explícita dos `pair_id` que entram no Delta PT-BR.
    Ela é declarada, não derivada: a base do Delta é cota de autoria, não sobra.
    """

    model_config = _CFG

    id: str
    frozen_at: datetime
    curupira_version: str
    entries: tuple[EntradaDeSuite, ...] = Field(min_length=1)
    delta_subset: tuple[str, ...] = ()


class EntradaDeErrata(BaseModel):
    """Uma tarefa marcada como defeituosa. Append-only: nunca se remove."""

    model_config = _CFG

    task_id: str
    task_version: int = Field(ge=1)
    date: date
    defect: str
    """Descrição do defeito. Gabarito errado, tarefa ambígua, matcher que aceita
    resposta incorreta. Desempenho ruim de um modelo NÃO é defeito."""

    test_ref: str
    """Caminho do teste que reproduz o defeito. Sem teste, não entra."""


class Errata(BaseModel):
    """A errata de uma suíte, versionada."""

    model_config = _CFG

    suite_id: str
    revision: int = Field(ge=0)
    entries: tuple[EntradaDeErrata, ...] = ()


def carregar_suite(caminho: Path) -> Suite:
    """Carrega uma suíte congelada do disco.

    Args:
        caminho: arquivo YAML da suíte.

    Returns:
        A suíte validada.
    """
    raise NotImplementedError


def carregar_errata(caminho: Path) -> Errata:
    """Carrega a errata de uma suíte.

    Args:
        caminho: arquivo YAML da errata.

    Returns:
        A errata validada.
    """
    raise NotImplementedError


def verificar_suite(suite: Suite, tarefas: dict[str, str]) -> list[str]:
    """Confere os hashes das tarefas contra os congelados na suíte.

    Se alguém alterar uma tarefa sem subir `task_version`, a rodada **falha** em
    vez de produzir número errado em silêncio.

    Args:
        suite: a suíte congelada.
        tarefas: mapa de `task_id` para hash de conteúdo calculado agora.

    Returns:
        Lista de mensagens de divergência. Vazia significa suíte íntegra.
    """
    raise NotImplementedError


def suite_esta_morta(suite: Suite, errata: Errata) -> bool:
    """Diz se a errata passou do teto de 5% e a suíte deve ser encerrada.

    Args:
        suite: a suíte congelada.
        errata: a errata vigente.

    Returns:
        `True` se a fração de tarefas com errata excede `TETO_DE_ERRATA`.
    """
    raise NotImplementedError
