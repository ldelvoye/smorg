"""The menu view: the Linear tab's landing, the mark under a starry sky and the way in."""

from __future__ import annotations

import math
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.text import Text
from textual import events
from textual.app import RenderResult
from textual.binding import Binding
from textual.widgets import Static

from smorg.integrations.linear.glyphs import status_color, status_disc, status_rank
from smorg.integrations.linear.mark import (
    Mark,
    mark_for,
    mark_lines,
    paint_breathe,
    paint_dim,
    paint_draw_in,
    paint_flash,
    paint_resting,
    paint_sweep,
)
from smorg.integrations.linear.palette import Glow
from smorg.integrations.linear.sky import LOOP_SECONDS, Star, build_sky, paint_sky
from smorg.integrations.linear.source import Issue, Viewer
from smorg.integrations.linear.views import LinearView
from smorg.shell.animation import FrameClock
from smorg.shell.braille import SUB_COLUMNS, SUB_ROWS, Dots
from smorg.shell.cards import CHANGED_MARK, SELECTED_MARK
from smorg.shell.cursor import step_cursor
from smorg.shell.format import plain_lines
from smorg.shell.panel import PanelState
from smorg.shell.terminal_palette import StatusColors
from smorg.shell.view_host import HostedView

if TYPE_CHECKING:
    from smorg.integrations.linear.panel import LinearPanel

_FPS = 10

# The arrival at ten frames a second: a beat on the destinations, the draw-in, a rest, then
# the twinkle.
_HOLD = 0.3
_DRAW = 1.3
_REST = 0.7
_TWINKLE_STARTS = _HOLD + _DRAW + _REST

_SWEEP_SECONDS = 1.6
_FLASH_SECONDS = 0.9
_BREATHE_SECONDS = 2.6
_TWINKLE_SECONDS = LOOP_SECONDS

_PANEL_COLUMNS = 31
_PANEL_BAND_COLUMNS = 40
_COLUMN_GAP = 4
_MARGIN_ROWS = 2
_MARGIN_COLUMNS = 4
_MIN_MARK_ROWS = 8
_SKY_SEED = 8821

_PANEL_START = 0.25
_PANEL_END = 0.8
_CASCADE_SECONDS = _DRAW * (_PANEL_END - _PANEL_START)
_CASCADE_FROM_MOUNT = _HOLD + _DRAW * _PANEL_START

# The panel's band beside the mark: an 8-row head that cascades in over a 4-row tail that never
# moves.
_PANEL_ROWS = 13
_TAIL_ROWS = 4
_HEAD_ROWS = _PANEL_ROWS - _TAIL_ROWS - 1
_LEGEND_ROWS = _HEAD_ROWS - 3
_STALE_LEGEND_ROWS = _HEAD_ROWS - 4

# Past this the panel's unseen count takes the bold accent, so it peaks with the head.
_UNSEEN_PEAK = 0.5

_LABEL_WIDTH = 13
_COUNT_WIDTH = 3
_PANEL_INDENT = "   "
_ENTER_GLYPH = "⏎"

_DESTINATIONS: tuple[tuple[str, LinearView], ...] = (("issues", LinearView.ISSUES),)

_LANDED_STATES = (PanelState.READY, PanelState.EMPTY)


@dataclass(frozen=True)
class _Block:
    """Where the mark and the panel sit on the tab, in cells."""

    left: int
    mark_columns: int
    mark_top: int
    panel_left: int
    panel_top: int


def _fitted_rows(width: int, height: int) -> int:
    rows = height - 2 * _MARGIN_ROWS
    if rows < _MIN_MARK_ROWS:
        return _MIN_MARK_ROWS
    room = width - _COLUMN_GAP - _PANEL_COLUMNS - 2 * _MARGIN_COLUMNS
    while rows > _MIN_MARK_ROWS:
        mark = mark_for(rows)
        if mark.columns <= room:
            return rows
        # A proportional step lands within a row or two; a one-row walk would stall a resize.
        rows = rows * room // mark.columns
    return _MIN_MARK_ROWS


def _block_for(mark: Mark, width: int, height: int) -> _Block:
    block_columns = mark.columns + _COLUMN_GAP + _PANEL_COLUMNS
    side_slack = width - block_columns
    left = max(0, side_slack // 2)
    block_rows = max(mark.rows, _PANEL_ROWS)
    row_slack = height - block_rows
    top = max(0, row_slack // 2)
    mark_top = top + (block_rows - mark.rows) // 2
    panel_top = top + (block_rows - _PANEL_ROWS) // 2
    panel_left = left + mark.columns + _COLUMN_GAP
    return _Block(left, mark.columns, mark_top, panel_left, panel_top)


def _ink_columns(mark: Mark) -> dict[int, tuple[int, int]]:
    spans: dict[int, tuple[int, int]] = {}
    for dot_row, dot_column in mark.dots:
        cell_row = dot_row // SUB_ROWS
        cell_column = dot_column // SUB_COLUMNS
        span = spans.get(cell_row)
        if span is None:
            spans[cell_row] = (cell_column, cell_column)
            continue
        first, last = span
        leftmost = min(first, cell_column)
        rightmost = max(last, cell_column)
        spans[cell_row] = (leftmost, rightmost)
    return spans


def _taken_places(mark: Mark, block: _Block, width: int) -> set[tuple[int, int]]:
    taken: set[tuple[int, int]] = set()
    spans = _ink_columns(mark)
    for cell_row, span in spans.items():
        first, last = span
        for column in range(first, last + 1):
            taken.add((block.mark_top + cell_row, block.left + column))
    # Panel lines are fitted to the band, so a long stale line never lands under a star.
    band_end = min(width, block.panel_left + _PANEL_BAND_COLUMNS)
    for row in range(_PANEL_ROWS):
        for column in range(block.panel_left, band_end):
            taken.add((block.panel_top + row, column))
    return taken


def _fitted_line(line: Text, width: int) -> Text:
    fitted = line.copy()
    fitted.truncate(width, overflow="ellipsis", pad=True)
    return fitted


def _compose_tab(
    mark_rows: list[Text], panel_rows: list[Text], block: _Block, width: int, height: int
) -> list[Text]:
    indent = " " * block.left
    gap = " " * _COLUMN_GAP
    blank_mark = " " * block.mark_columns
    panel_room = width - block.panel_left
    panel_width = min(_PANEL_BAND_COLUMNS, panel_room)
    rows: list[Text] = []
    for index in range(height):
        row = Text(indent)
        mark_index = index - block.mark_top
        if 0 <= mark_index < len(mark_rows):
            row.append_text(mark_rows[mark_index])
        else:
            row.append(blank_mark)
        row.append(gap)
        panel_index = index - block.panel_top
        if 0 <= panel_index < len(panel_rows):
            panel_row = panel_rows[panel_index]
            fitted_panel = _fitted_line(panel_row, panel_width)
            row.append_text(fitted_panel)
        fitted_row = _fitted_line(row, width)
        rows.append(fitted_row)
    return rows


def _format_stars(canvas: list[Text], stars: dict[tuple[int, int], tuple[str, str]]) -> list[Text]:
    by_row: dict[int, list[tuple[int, str, str]]] = {}
    for place, star in stars.items():
        row, column = place
        glyph, style = star
        placed = by_row.setdefault(row, [])
        placed.append((column, glyph, style))
    painted: list[Text] = []
    for index, row in enumerate(canvas):
        placed = by_row.get(index)
        if placed is None:
            painted.append(row)
            continue
        placed.sort()
        lit = Text()
        cursor = 0
        for column, glyph, style in placed:
            lit.append_text(row[cursor:column])
            lit.append(glyph, style=style)
            cursor = column + 1
        lit.append_text(row[cursor:])
        painted.append(lit)
    return painted


def _paint_head_dim(mark: Mark, glow: Glow) -> Dots:
    head = mark.strokes[0]
    return {dot: glow.dim for dot in head}


def _swell(phase: float) -> float:
    turn = 2 * math.pi * phase
    wave = math.cos(turn)
    return (1 - wave) / 2


def _panel_rows_shown(phase: float, total: int) -> int:
    if phase <= _PANEL_START:
        return 1
    if phase >= _PANEL_END:
        return total
    span = _PANEL_END - _PANEL_START
    grown = (phase - _PANEL_START) / span
    after_greeting = total - 1
    arrived = round(after_greeting * grown)
    return 1 + arrived


def _band_rows(head: list[Text], tail: list[Text]) -> list[Text]:
    blank = Text(" " * _PANEL_COLUMNS)
    band = list(head[:_HEAD_ROWS])
    above_tail = _PANEL_ROWS - _TAIL_ROWS
    while len(band) < above_tail:
        band.append(blank)
    band.extend(tail)
    return band


def _status_groups(issues: tuple[Issue, ...]) -> list[tuple[str, str, list[Issue]]]:
    members: dict[str, list[Issue]] = {}
    for issue in issues:
        group = members.setdefault(issue.status, [])
        group.append(issue)
    order: list[tuple[int, str, str]] = []
    for status, group in members.items():
        rank = status_rank(status, group[0].status_type)
        order.append((rank, status.casefold(), status))
    order.sort()
    groups: list[tuple[str, str, list[Issue]]] = []
    for _, _, status in order:
        group = members[status]
        groups.append((status, group[0].status_type, group))
    return groups


def _changed_count(issues: list[Issue], changed: frozenset[str]) -> int:
    counted = [issue for issue in issues if issue.id in changed]
    return len(counted)


def _format_greeting(viewer: Viewer | None) -> Text:
    if viewer is None:
        return Text("welcome back", style="bold")
    return Text(f"welcome back, {viewer.handle}", style="bold")


def _format_changed_line(changed: int, accent: str, glow: Glow, is_flash: bool) -> Text:
    if changed == 0:
        return Text("you're all caught up", style="dim")
    body = f"{changed} changed since you looked"
    if is_flash:
        return Text(f"{CHANGED_MARK} {body}", style=glow.lit)
    line = Text()
    line.append(f"{CHANGED_MARK} ", style=accent)
    line.append(body, style="dim")
    return line


def _format_stale_lines(as_of: datetime | None, message: str) -> list[Text]:
    if as_of is None:
        stamp = "earlier"
    else:
        stamp = as_of.strftime("%H:%M")
    stamped = Text(f"showing data as of {stamp}", style="dim")
    return [stamped, Text(message, style="dim")]


def _format_legend(
    groups: list[tuple[str, str, list[Issue]]],
    changed: frozenset[str],
    colors: StatusColors,
    accent: str,
    room: int,
) -> list[Text]:
    if len(groups) > room:
        listed = groups[: room - 1]
    else:
        listed = groups
    rows: list[Text] = []
    for status, status_type, group in listed:
        disc = status_disc(status, status_type)
        color = status_color(status, status_type, colors, accent)
        row = Text()
        row.append(disc, style=color)
        row.append("  ")
        label = status.casefold()
        row.append(label.ljust(_LABEL_WIDTH), style="dim")
        count = str(len(group))
        row.append(count.rjust(_COUNT_WIDTH))
        changed_here = _changed_count(group, changed)
        if changed_here:
            row.append(f"  {CHANGED_MARK} {changed_here}", style=accent)
        rows.append(row)
    hidden = len(groups) - len(listed)
    if hidden:
        rows.append(Text(f"·  {hidden} more", style="dim"))
    return rows


def _format_projects_row() -> Text:
    row = Text(_PANEL_INDENT)
    row.append("projects".ljust(_LABEL_WIDTH), style="dim")
    row.append("coming soon", style="dim")
    return row


def _format_destinations(issue_count: int, unseen: int, unseen_style: str) -> list[Text]:
    issues_row = Text()
    issues_row.append(f"{SELECTED_MARK}  ", style="bold")
    issues_row.append("issues".ljust(_LABEL_WIDTH), style="bold")
    issue_total = str(issue_count)
    issues_row.append(issue_total.rjust(_COUNT_WIDTH), style="bold")
    if unseen:
        issues_row.append(f"  {CHANGED_MARK} {unseen} unseen", style=unseen_style)
    projects_row = _format_projects_row()
    return [issues_row, projects_row]


def _format_bare_destinations(issues_style: str) -> list[Text]:
    issues_row = Text()
    issues_row.append(f"{SELECTED_MARK}  ", style=issues_style)
    issues_row.append("issues", style=issues_style)
    projects_row = _format_projects_row()
    return [issues_row, projects_row]


def _format_open_hint() -> Text:
    return Text(f"{_PANEL_INDENT}{_ENTER_GLYPH} to open", style="dim")


def _format_tail_rows(destinations: list[Text], hint: Text) -> list[Text]:
    tail = list(destinations)
    tail.append(Text())
    tail.append(hint)
    return tail


def _format_loading_tail() -> list[Text]:
    destinations = _format_bare_destinations("dim")
    hint = Text(f"{_PANEL_INDENT}loading…", style="dim")
    return _format_tail_rows(destinations, hint)


def _format_error_tail() -> list[Text]:
    destinations = _format_bare_destinations("bold")
    hint = _format_open_hint()
    return _format_tail_rows(destinations, hint)


def _format_error_head(viewer: Viewer | None, message: str) -> list[Text]:
    reason = Text(f"could not load: {message}", style="dim")
    if viewer is None:
        return [reason]
    greeting = _format_greeting(viewer)
    return [greeting, reason]


class LinearMenu(Static, HostedView):
    """The landing: the mark under a starry sky, the greeting and counts beside it, and the way
    in."""

    BINDINGS = [
        Binding("up", "previous_destination", "select destination", show=False),
        Binding("down", "next_destination", "select destination", show=False),
        Binding("enter", "open_destination", "open the selected view", show=False),
        Binding("o", "open_home", "open Linear in the browser", show=False),
    ]
    can_focus = True

    DEFAULT_CSS = """
    LinearMenu { height: 1fr; }
    """

    def __init__(self, panel: LinearPanel) -> None:
        super().__init__(markup=False)
        self.panel = panel
        self.destination_cursor = 0
        self._clock = FrameClock(self, fps=_FPS, on_tick=self.tick)
        self._elapsed = 0.0
        self._arrived = False
        self._data_landed_at: float | None = None
        self._fetching = False
        self._sweep_started_at: float | None = None
        self._sweep_ends_at: float | None = None
        self._flash_started_at: float | None = None
        self._changed_ids: frozenset[str] | None = None
        self._changes_waiting = False
        self._sky: tuple[Star, ...] = ()
        self._mark: Mark | None = None
        self._fitted = (0, 0)

    def on_mount(self) -> None:
        self._clock.start()

    def on_show(self) -> None:
        self._clock.resume()

    def on_hide(self) -> None:
        self._clock.pause()

    def on_resize(self, event: events.Resize) -> None:
        self.refresh()

    def tick(self, elapsed: float) -> None:
        """One frame at `elapsed` seconds since mount; public so tests drive time by hand."""
        self._elapsed = elapsed
        self._note_data()
        draw_phase = self._draw_phase(elapsed)
        if draw_phase >= 1.0:
            self._arrived = True
        self.refresh()

    def refresh_content(self) -> None:
        """New data or state on the panel: the changed set moves, a flash may start."""
        self._note_data()
        changed = self._changed()
        if self._changed_ids is None:
            self._changed_ids = changed
        else:
            arrived = changed - self._changed_ids
            self._changed_ids = changed
            if arrived:
                self._flash_started_at = self._elapsed
                self._changes_waiting = True
            if not changed:
                self._changes_waiting = False
        self.refresh()

    def fetch_started(self) -> None:
        self._fetching = True
        self._sweep_started_at = self._elapsed
        self._sweep_ends_at = None
        self.refresh()

    def fetch_finished(self) -> None:
        self._fetching = False
        if self._sweep_started_at is not None:
            run = self._elapsed - self._sweep_started_at
            passes = math.floor(run / _SWEEP_SECONDS) + 1
            self._sweep_ends_at = self._sweep_started_at + passes * _SWEEP_SECONDS
        self.refresh()

    def acknowledge_changes(self) -> None:
        self._changes_waiting = False
        self.refresh()

    @property
    def twinkling(self) -> bool:
        if self.panel.state not in _LANDED_STATES:
            return False
        if self._data_landed_at is None:
            return False
        issues = self.panel.issues()
        if not issues:
            return False
        starts = self._twinkle_starts()
        return self._elapsed >= starts

    @property
    def flashing(self) -> bool:
        phase = self._flash_phase(self._elapsed)
        return phase is not None

    @property
    def breathing(self) -> bool:
        return self._changes_waiting

    def render(self) -> RenderResult:
        return self._format_tab(self.size.width, self.size.height)

    def content_lines(self) -> list[str]:
        """What the tab shows, as plain rows of the widget's width."""
        return self.content_lines_at(self.size.width, self.size.height)

    def content_lines_at(self, width: int, height: int) -> list[str]:
        tab = self._format_tab(width, height)
        return plain_lines(tab, width)

    def mark_styles_at(self, width: int, height: int) -> set[str]:
        dots = self._dots_at(width, height)
        styles = dots.values()
        return set(styles)

    def mark_dot_count_at(self, width: int, height: int) -> int:
        dots = self._dots_at(width, height)
        return len(dots)

    def resting_dot_count_at(self, width: int, height: int) -> int:
        mark = self._fitted_mark(width, height)
        return len(mark.dots)

    def action_previous_destination(self) -> None:
        self._move(-1)

    def action_next_destination(self) -> None:
        self._move(1)

    def _move(self, offset: int) -> None:
        self.destination_cursor = step_cursor(self.destination_cursor, offset, len(_DESTINATIONS))
        self.refresh()

    def action_open_destination(self) -> None:
        _, destination = _DESTINATIONS[self.destination_cursor]
        self.panel.show_view(destination)

    def action_open_home(self) -> None:
        home = self.panel.home_url()
        webbrowser.open(home)

    def _note_data(self) -> None:
        if self.panel.state not in _LANDED_STATES:
            return
        if self._data_landed_at is None:
            self._data_landed_at = self._elapsed

    def _changed(self) -> frozenset[str]:
        panel = self.panel
        changed: set[str] = set()
        for issue in panel.issues():
            if panel.seen.is_changed(panel.integration_id, issue):
                changed.add(issue.id)
        return frozenset(changed)

    def _draw_phase(self, elapsed: float) -> float:
        walked = (elapsed - _HOLD) / _DRAW
        if walked > 1.0:
            return 1.0
        return walked

    def _cascade_start(self) -> float | None:
        landed = self._data_landed_at
        if landed is None:
            return None
        return max(_CASCADE_FROM_MOUNT, landed)

    def _head_shown(self, elapsed: float, total: int) -> int:
        start = self._cascade_start()
        if start is None:
            return 0
        walked = (elapsed - start) / _CASCADE_SECONDS
        if walked < 0.0:
            return 0
        phase = min(1.0, walked)
        return _panel_rows_shown(phase, total)

    def _twinkle_starts(self) -> float:
        start = self._cascade_start()
        if start is None:
            return _TWINKLE_STARTS
        settled = start + _CASCADE_SECONDS + _REST
        return max(_TWINKLE_STARTS, settled)

    def _flash_phase(self, elapsed: float) -> float | None:
        if self._flash_started_at is None:
            return None
        run = elapsed - self._flash_started_at
        if run < 0.0 or run >= _FLASH_SECONDS:
            return None
        return run / _FLASH_SECONDS

    def _sweep_phase(self, elapsed: float) -> float | None:
        if self._sweep_started_at is None:
            return None
        if not self._fetching:
            if self._sweep_ends_at is None:
                return None
            if elapsed >= self._sweep_ends_at:
                return None
        run = elapsed - self._sweep_started_at
        return (run / _SWEEP_SECONDS) % 1.0

    def _breathe_swell(self, elapsed: float) -> float:
        if not self._changes_waiting:
            return 0.0
        flash_phase = self._flash_phase(elapsed)
        if flash_phase is not None:
            return 0.0
        phase = (elapsed / _BREATHE_SECONDS) % 1.0
        return _swell(phase)

    def _sky_phase(self, elapsed: float) -> float:
        if not self.twinkling:
            return -1.0
        starts = self._twinkle_starts()
        run = elapsed - starts
        return (run / _TWINKLE_SECONDS) % 1.0

    def _fitted_mark(self, width: int, height: int) -> Mark:
        cached = self._mark
        if cached is not None and self._fitted == (width, height):
            return cached
        rows = _fitted_rows(width, height)
        mark = mark_for(rows)
        block = _block_for(mark, width, height)
        taken = _taken_places(mark, block, width)
        self._mark = mark
        self._fitted = (width, height)
        self._sky = build_sky(taken, height, width, seed=_SKY_SEED)
        return mark

    def _dots_at(self, width: int, height: int) -> Dots:
        mark = self._fitted_mark(width, height)
        glow = self.panel.glow()
        return self._paint_mark(mark, glow, self._elapsed)

    def _paint_mark(self, mark: Mark, glow: Glow, elapsed: float) -> Dots:
        state = self.panel.state
        if state is PanelState.ERROR:
            return _paint_head_dim(mark, glow)
        if state is PanelState.STALE:
            return paint_dim(mark, glow)
        if not self._arrived:
            draw_phase = self._draw_phase(elapsed)
            if draw_phase < 0.0:
                return {}
            return paint_draw_in(mark, glow, draw_phase)
        flash_phase = self._flash_phase(elapsed)
        if flash_phase is not None:
            return paint_flash(mark, glow, flash_phase)
        sweep_phase = self._sweep_phase(elapsed)
        if sweep_phase is not None:
            return paint_sweep(mark, glow, sweep_phase)
        if self._changes_waiting:
            breathe_phase = (elapsed / _BREATHE_SECONDS) % 1.0
            return paint_breathe(mark, glow, breathe_phase)
        return paint_resting(mark, glow)

    def _format_panel(self, accent: str, glow: Glow, elapsed: float) -> list[Text]:
        panel = self.panel
        if panel.state is PanelState.LOADING:
            loading_tail = _format_loading_tail()
            return _band_rows([], loading_tail)
        if panel.state is PanelState.ERROR:
            viewer = panel.viewer()
            error_head = _format_error_head(viewer, panel.message)
            error_tail = _format_error_tail()
            return _band_rows(error_head, error_tail)
        changed = self._changed()
        head = self._format_head(changed, accent, glow)
        tail = self._format_tail(changed, accent, glow, elapsed)
        if panel.state is PanelState.STALE:
            return _band_rows(head, tail)
        shown = self._head_shown(elapsed, len(head))
        arriving = head[:shown]
        return _band_rows(arriving, tail)

    def _format_head(self, changed: frozenset[str], accent: str, glow: Glow) -> list[Text]:
        panel = self.panel
        viewer = panel.viewer()
        rows: list[Text] = []
        if panel.state is PanelState.STALE:
            if viewer is not None:
                rows.append(_format_greeting(viewer))
            rows.extend(_format_stale_lines(panel.as_of, panel.message))
            legend_room = _STALE_LEGEND_ROWS
        else:
            rows.append(_format_greeting(viewer))
            changed_count = len(changed)
            rows.append(_format_changed_line(changed_count, accent, glow, self.flashing))
            legend_room = _LEGEND_ROWS
        rows.append(Text())
        groups = _status_groups(panel.issues())
        if groups:
            colors = panel.status_colors()
            rows.extend(_format_legend(groups, changed, colors, accent, legend_room))
        else:
            rows.append(Text("nothing assigned to you", style="dim"))
        return rows

    def _format_tail(
        self, changed: frozenset[str], accent: str, glow: Glow, elapsed: float
    ) -> list[Text]:
        issues = self.panel.issues()
        swell = self._breathe_swell(elapsed)
        if swell > _UNSEEN_PEAK:
            unseen_style = glow.lit
        else:
            unseen_style = accent
        issue_count = len(issues)
        changed_count = len(changed)
        destinations = _format_destinations(issue_count, changed_count, unseen_style)
        hint = _format_open_hint()
        return _format_tail_rows(destinations, hint)

    def _format_tab(self, width: int, height: int) -> RenderableType:
        if width <= 0 or height <= 0:
            return Text()
        mark = self._fitted_mark(width, height)
        accent = self.panel.accent()
        glow = self.panel.glow()
        elapsed = self._elapsed
        dots = self._paint_mark(mark, glow, elapsed)
        mark_rows = mark_lines(mark, dots)
        panel_rows = self._format_panel(accent, glow, elapsed)
        block = _block_for(mark, width, height)
        canvas = _compose_tab(mark_rows, panel_rows, block, width, height)
        sky_phase = self._sky_phase(elapsed)
        stars = paint_sky(self._sky, sky_phase, glow)
        lit = _format_stars(canvas, stars)
        return Group(*lit)
