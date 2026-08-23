from datetime import UTC, datetime, timedelta

from smorg.shell.format import age, merge_key_display, symbolize_key_display

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def test_age_of_a_future_timestamp_reads_now(monkeypatch):
    """A future stamp is clock skew, not something to render as a large past age."""
    monkeypatch.setattr("smorg.shell.format.now", lambda: NOW)
    assert age(NOW + timedelta(seconds=1)) == "now"


def test_age_of_a_moment_ago_reads_now(monkeypatch):
    monkeypatch.setattr("smorg.shell.format.now", lambda: NOW)
    assert age(NOW - timedelta(seconds=30)) == "now"


def test_age_scales_from_minutes_to_days(monkeypatch):
    monkeypatch.setattr("smorg.shell.format.now", lambda: NOW)
    assert age(NOW - timedelta(minutes=5)) == "5m"
    assert age(NOW - timedelta(hours=3)) == "3h"
    assert age(NOW - timedelta(days=2)) == "2d"


def test_a_shared_modifier_is_stated_once():
    assert merge_key_display("⇧ + ↑", "⇧ + ↓") == "⇧ + ↑/↓"


def test_two_unmodified_keys_merge_with_no_prefix_to_repeat():
    assert merge_key_display("↑", "↓") == "↑/↓"


def test_two_different_modifiers_stay_fully_spelled_out():
    assert merge_key_display("^ + a", "⇧ + b") == "^ + a/⇧ + b"


def test_a_lone_shift_binding_symbolizes_even_when_unmerged():
    assert symbolize_key_display("shift+x") == "⇧ + x"


def test_symbolize_expands_a_fused_caret_with_an_explicit_plus():
    assert symbolize_key_display("^p") == "^ + p"


def test_symbolize_maps_the_command_modifier_to_its_glyph():
    assert symbolize_key_display("super+k") == "⌘ + k"
