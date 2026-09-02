"""The advertised gate must give the same answer on a clean clone as on a developer machine.

This exists because it once did not. `controlplane/eval/external_probes.py` imports matplotlib
inside a function, which is correct -- it is an optional extra behind a benchmark path that
downloads gigabytes -- but `mypy --strict` still resolves the import, and matplotlib was not in
the override list. Every developer machine had it installed as a transitive dependency of
something else, so `make check` was green everywhere it was ever run, and red the first time a
reviewer ran `run_submission.sh` on a fresh virtualenv.

The failure mode is worth naming precisely: a gate that only passes where it was written is
worse than no gate, because it is trusted. So this test derives the answer from the source
rather than from whatever happens to be importable right now.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "controlplane"

# Distribution names differ from import names often enough to be worth writing down.
IMPORT_NAME = {
    "PyYAML": "yaml",
    "python-dateutil": "dateutil",
    "presidio-analyzer": "presidio_analyzer",
    "scikit-learn": "sklearn",
}


def _pyproject() -> dict[str, object]:
    with (REPO / "pyproject.toml").open("rb") as handle:
        loaded = tomllib.load(handle)
    assert isinstance(loaded, dict)
    return loaded


def _requirement_import_names(specifiers: list[str]) -> set[str]:
    names: set[str] = set()
    for spec in specifiers:
        # "numpy>=1.26,<3" -> "numpy"; a bare "." is the project itself.
        head = spec.split(";")[0].strip()
        name = head.split("[")[0]
        for separator in (">=", "<=", "==", "!=", "~=", ">", "<"):
            name = name.split(separator)[0]
        name = name.strip()
        if not name or name == ".":
            continue
        names.add(IMPORT_NAME.get(name, name.replace("-", "_")))
    return names


def _top_level_imports() -> dict[str, set[str]]:
    """Every top-level module the package imports, mapped to the files that import it.

    Imports nested inside functions count. That is exactly where the optional ones live, and
    exactly the case that slipped through.
    """
    found: dict[str, set[str]] = {}
    for source in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                # A relative import stays inside the package, so it is never third party.
                if node.level or node.module is None:
                    continue
                modules = [node.module]
            else:
                continue
            for module in modules:
                root = module.split(".")[0]
                found.setdefault(root, set()).add(str(source.relative_to(REPO)))
    return found


@pytest.fixture(scope="module")
def third_party() -> dict[str, set[str]]:
    stdlib = set(sys.stdlib_module_names)
    return {
        module: files
        for module, files in _top_level_imports().items()
        if module not in stdlib and module != "controlplane"
    }


def test_every_third_party_import_is_declared_or_overridden(
    third_party: dict[str, set[str]],
) -> None:
    """Nothing may be imported that a clean install neither installs nor tells mypy to skip.

    An import that is in neither set is the bug this test was written for: it type-checks on a
    machine that happens to have the package and fails on a reviewer's fresh virtualenv.
    """
    config = _pyproject()
    project = config["project"]
    assert isinstance(project, dict)

    declared = _requirement_import_names(list(project["dependencies"]))  # type: ignore[arg-type]
    extras = project.get("optional-dependencies") or {}
    assert isinstance(extras, dict)
    for specifiers in extras.values():
        declared |= _requirement_import_names(list(specifiers))

    tool = config["tool"]
    assert isinstance(tool, dict)
    mypy = tool["mypy"]
    assert isinstance(mypy, dict)
    silenced: set[str] = set()
    for override in mypy.get("overrides", []):
        if not override.get("ignore_missing_imports"):
            continue
        for pattern in override.get("module", []):
            silenced.add(str(pattern).split(".")[0])

    # A module counts as accounted for if an extra installs it, or if the mypy override list
    # names it. The second case covers transitive dependencies that are never named directly:
    # `spacy` arrives with `presidio-analyzer` under the `models` extra, and pinning it here
    # as well would be a second place to keep in step with presidio's own requirements.
    undeclared = {
        module: sorted(files)
        for module, files in third_party.items()
        if module not in declared and module not in silenced
    }
    assert not undeclared, (
        "imported but neither declared in pyproject dependencies or an extra, nor listed in "
        f"the mypy overrides: {undeclared}"
    )

    # An import that a clean install does not provide must be silenced for mypy, or the gate
    # is green only where the extra happens to be installed.
    core = _requirement_import_names(list(project["dependencies"]))  # type: ignore[arg-type]
    optional_but_loud = {
        module: sorted(files)
        for module, files in third_party.items()
        if module not in core and module not in silenced
    }
    assert not optional_but_loud, (
        "optional imports that mypy --strict will fail on in a clean install. Add them to "
        "the [[tool.mypy.overrides]] module list in pyproject.toml: "
        f"{optional_but_loud}"
    )


def test_the_mypy_override_list_covers_matplotlib() -> None:
    """The specific regression, named, so it cannot come back unnoticed."""
    tool = _pyproject()["tool"]
    assert isinstance(tool, dict)
    mypy = tool["mypy"]
    assert isinstance(mypy, dict)
    modules = {
        str(pattern)
        for override in mypy.get("overrides", [])
        if override.get("ignore_missing_imports")
        for pattern in override.get("module", [])
    }
    assert "matplotlib" in modules
    assert "matplotlib.*" in modules
