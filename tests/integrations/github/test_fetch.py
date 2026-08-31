from __future__ import annotations

import importlib

from smorg.integrations.github.source.fetch import FETCH_PHASES, fetch_with_progress

from .recorded import CREDENTIALS, graphql_http


def test_fetch_with_progress_reports_each_phase_before_its_query(monkeypatch):
    events: list[str] = []

    def stub_query_prs(credentials, http):
        events.append("query_prs")
        return ()

    def stub_query_profile(credentials, http):
        events.append("query_profile")
        return object()

    def stub_query_pushed_branches(credentials, http):
        events.append("query_pushed_branches")
        return object()

    # The package's `from .fetch import fetch` shadows the submodule's name, so a plain import or
    # dotted setattr target resolves to the function; pull the module from sys.modules instead.
    fetch_module = importlib.import_module("smorg.integrations.github.source.fetch")
    monkeypatch.setattr(fetch_module, "query_prs", stub_query_prs)
    monkeypatch.setattr(fetch_module, "query_profile", stub_query_profile)
    monkeypatch.setattr(fetch_module, "query_pushed_branches", stub_query_pushed_branches)

    reported: list[int] = []

    def report(index: int) -> None:
        events.append(f"report({index})")
        reported.append(index)

    fetch_with_progress(CREDENTIALS, graphql_http(), report)

    assert reported == list(range(len(FETCH_PHASES)))
    assert events == [
        "report(0)",
        "query_prs",
        "report(1)",
        "query_profile",
        "report(2)",
        "query_pushed_branches",
    ]
