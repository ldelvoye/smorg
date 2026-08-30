import pytest


@pytest.fixture(autouse=True)
def reset_negotiated_version():
    """The handshake cache is process-lifetime state; tests must not leak it."""
    from smorg.core.mcp import reset_negotiated_versions

    reset_negotiated_versions()


@pytest.fixture(autouse=True)
def isolated_config_dir(monkeypatch, tmp_path):
    """Tests must never read or write the user's real smorg config directory."""
    monkeypatch.setenv("SMORG_CONFIG_DIR", str(tmp_path / "smorg-config"))
