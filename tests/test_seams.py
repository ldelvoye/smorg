"""The seams the whole design rests on, enforced over every integration rather than trusted."""

import re
from pathlib import Path

from smorg.core.registry import manifests

# Anchored to this file, not the working directory: a relative path finds nothing when pytest
# runs from anywhere else, and every check below then passes having read no source at all.
INTEGRATIONS = Path(__file__).parents[1] / "src" / "smorg" / "integrations"

# The manifest is the seam itself: it hands fetch through to the source.
_SEAM_MODULES = {"manifest.py", "__init__.py"}
_FETCH_CALL = re.compile(r"\bfetch(?:_detail|_with_progress)?\(")


def _source_modules() -> list[Path]:
    single = INTEGRATIONS.glob("*/source.py")
    packaged = INTEGRATIONS.glob("*/source/**/*.py")
    return sorted([*single, *packaged])


def _display_modules() -> list[Path]:
    """Every integration module that is neither its source nor its manifest."""
    sources = set(_source_modules())
    modules: list[Path] = []
    for module in INTEGRATIONS.glob("*/**/*.py"):
        if module in sources or module.name in _SEAM_MODULES:
            continue
        modules.append(module)
    return sorted(modules)


def _package_source(integration_id: str) -> str:
    """One integration's whole package as text, for checks that read source instead of importing."""
    package = INTEGRATIONS / integration_id
    modules = sorted(package.glob("**/*.py"))
    texts = [module.read_text() for module in modules]
    return "\n".join(texts)


def test_every_declared_action_key_is_bound():
    offenders: list[str] = []
    for manifest in manifests():
        source = _package_source(manifest.id)
        for action in manifest.actions:
            binding = f'Binding("{action.key}"'
            if binding not in source:
                offenders.append(f"{manifest.id} declares {action.key!r}")
    assert offenders == [], f"the help overlay advertises keys no panel binds: {offenders}"


def test_panels_and_views_never_fetch():
    offenders: list[str] = []
    for module in _display_modules():
        source = module.read_text()
        if "httpx" in source or "McpSession" in source or "import requests" in source:
            offenders.append(str(module))
        elif _FETCH_CALL.search(source) or "shell.app" in source:
            offenders.append(str(module))
    assert offenders == [], f"display code reaches the network or the app: {offenders}"


def test_sources_never_format():
    offenders: list[str] = []
    for module in _source_modules():
        source = module.read_text()
        if re.search(r"^(?:from|import) (?:rich|textual|smorg\.shell)\b", source, re.M):
            offenders.append(str(module))
    assert offenders == [], f"source code draws or imports the shell: {offenders}"
