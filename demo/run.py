"""Boots smorg on invented data: `uv run demo/run.py linear github`.

Tabs appear in the order named, and the first one is active, which is what a recording of a
single integration needs. See AGENTS.md.
"""

from __future__ import annotations

import sys

import github_data
import linear_data
from harness import DemoIntegration, run

from smorg.integrations.github.manifest import MANIFEST as GITHUB_MANIFEST
from smorg.integrations.github.panel import GitHubPanel
from smorg.integrations.linear.manifest import MANIFEST as LINEAR_MANIFEST
from smorg.integrations.linear.panel import LinearPanel

DEMOS = {
    "linear": DemoIntegration(
        manifest=LINEAR_MANIFEST,
        panel_class=LinearPanel,
        items=linear_data.ITEMS,
        details=linear_data.DETAILS,
    ),
    "github": DemoIntegration(
        manifest=GITHUB_MANIFEST,
        panel_class=GitHubPanel,
        items=github_data.ITEMS,
        details=github_data.DETAILS,
    ),
}


def main(argv: list[str]) -> int:
    names = argv[1:]
    if not names:
        names = ["linear"]
    unknown = [name for name in names if name not in DEMOS]
    if unknown:
        print(f"unknown integration(s): {unknown}; known: {sorted(DEMOS)}")
        return 1
    demos = tuple(DEMOS[name] for name in names)
    run(demos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
