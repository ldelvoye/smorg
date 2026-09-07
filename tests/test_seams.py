"""The seams the whole design rests on, enforced over every integration rather than trusted."""

import re
from pathlib import Path

INTEGRATIONS = Path("src") / "smorg" / "integrations"

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
