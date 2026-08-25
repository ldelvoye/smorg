"""Wires the recorded GitHub server into the `github` fixture every test in this package uses."""

import pytest
from github.Requester import Requester

from .recorded import _LIVE, _HttpConnection, _HttpsConnection, _Server


@pytest.fixture
def github():
    server = _Server()
    _LIVE.append(server)
    Requester.injectConnectionClasses(_HttpConnection, _HttpsConnection)
    try:
        yield server
    finally:
        Requester.resetConnectionClasses()
        _LIVE.clear()
