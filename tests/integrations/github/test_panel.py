"""Tests for the GitHub host panel: view delegation, never the network."""

from pathlib import Path

from smorg.core.state import SeenState

from .helpers import panel_with, pull


def test_the_panel_and_its_views_never_fetch():
    """The seam the whole design rests on, enforced rather than trusted."""
    github_dir = Path("src") / "smorg" / "integrations" / "github"
    files = [github_dir / "panel.py"] + sorted(github_dir.glob("views/*.py"))
    for file in files:
        source = file.read_text()
        assert "httpx" not in source, file
        assert "Github(" not in source, file
        assert "import requests" not in source, file
        assert "fetch" not in source, file
        assert "shell.app" not in source, file


def test_an_unmounted_host_has_no_selection():
    assert panel_with(pull(42)).selected_item() is None


def test_mark_all_seen_only_stores_pull_requests(tmp_path, monkeypatch):
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path))
    seen = SeenState({})
    panel = panel_with(pull(42), seen=seen)
    panel.mark_all_seen()
    assert not seen.is_changed("github", pull(42))
