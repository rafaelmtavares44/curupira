"""Confere que as ferramentas de qualidade instaladas sao as versoes pinadas.

Fecha a lacuna do `.pre-commit-config.yaml`: como os hooks rodam com
`language: system`, eles usam o que estiver no PATH. Se o commit sair de um
shell sem o venv ativo, o `mypy` que roda pode ser outro — e passar por engano.

Roda no pre-commit e no CI. Sem argumento, confere tudo.
"""

from __future__ import annotations

import re
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

FERRAMENTAS = ("ruff", "mypy", "bandit", "pytest", "detect-secrets", "coverage")
"""So as que decidem se um commit passa. Bibliotecas de runtime nao entram."""

_PIN = re.compile(r"^(?P<nome>[A-Za-z0-9._-]+)==(?P<versao>[^\s;]+)")


def pins_do_pyproject() -> dict[str, str]:
    """Le as versoes pinadas no extra `dev` do pyproject.

    Returns:
        Mapa de nome normalizado para versao pinada.
    """
    dados = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    dev: list[str] = dados["project"]["optional-dependencies"]["dev"]
    pins: dict[str, str] = {}
    for linha in dev:
        casou = _PIN.match(linha.strip())
        if casou:
            pins[casou["nome"].lower().replace("_", "-")] = casou["versao"]
    return pins


def divergencias() -> list[str]:
    """Compara o que esta instalado com o que esta pinado.

    Returns:
        Lista de mensagens. Vazia significa ambiente coerente.
    """
    pins = pins_do_pyproject()
    problemas: list[str] = []
    for nome in FERRAMENTAS:
        esperado = pins.get(nome)
        if esperado is None:
            problemas.append(f"{nome}: sem pin no pyproject [dev]")
            continue
        try:
            instalado = version(nome)
        except PackageNotFoundError:
            problemas.append(f"{nome}: nao instalado neste interpretador ({sys.executable})")
            continue
        if instalado != esperado:
            problemas.append(f"{nome}: instalado {instalado}, pinado {esperado}")
    return problemas


def main() -> int:
    """Imprime as divergencias e devolve o codigo de saida.

    Returns:
        0 se tudo confere, 1 caso contrario.
    """
    problemas = divergencias()
    if not problemas:
        return 0
    print("ferramentas fora da versao pinada:", file=sys.stderr)
    for p in problemas:
        print(f"  - {p}", file=sys.stderr)
    print(f"\ninterpretador: {sys.executable}", file=sys.stderr)
    print('corrija com: pip install -e ".[dev]" dentro do venv do projeto', file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
