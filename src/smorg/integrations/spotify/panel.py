"""A Spotify-esque snapshot: what's playing now, what's queued next, and what played last."""

from __future__ import annotations

import webbrowser
from enum import StrEnum

from rich.cells import cell_len
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Input

from smorg.integrations.spotify.pickers import search_picker
from smorg.integrations.spotify.source import (
    FALLBACK_URL,
    Album,
    LastPlayed,
    NowPlaying,
    PlayerState,
    Playlist,
    SearchResults,
    Track,
    next_repeat_mode,
    pause_playback,
    play_context,
    play_track,
    queue_track,
    resume_playback,
    search,
    set_repeat,
    set_shuffle,
    skip_next,
    skip_previous,
)
from smorg.shell.format import age
from smorg.shell.panel import Panel

_DIM = "dim"

_PLAY_ICON = "▶"
_PAUSE_ICON = "⏸"
_PLAYING_STYLE = "green"
_PAUSED_STYLE = "yellow"

_QUEUE_DISPLAY_LIMIT = 10
# Aligns with the queue rows' title column: four number cells plus the two-cell gap.
_ROW_INDENT = "      "
# Separates transport columns; wide enough that adjacent glyphs never read as one label.
_CONTROL_GAP = "   "

_PLAY_NOW_PLACEHOLDER = "play now — search"
_ADD_TO_QUEUE_PLACEHOLDER = "add to queue — search"


class _SearchAction(StrEnum):
    PLAY = "play"
    QUEUE = "queue"


def _format_artists(artists: tuple[str, ...]) -> str:
    """("Tame Impala", "Kevin Parker") -> "Tame Impala, Kevin Parker" """
    return ", ".join(artists)


def _format_track(track: Track) -> Text:
    """ "Bromeliad · Aaron Cherof, Minecraft" — the title carries the weight, the artists dim."""
    row = Text(track.track)
    row.append(f" · {_format_artists(track.artists)}", style=_DIM)
    return row


def _format_context(kind: str, name: str | None) -> str:
    if kind == "autoplay":
        return "autoplay"
    if name is None:
        return kind
    return f"{kind} · {name}"


def _format_banner(now_playing: NowPlaying | None) -> list[Text]:
    if now_playing is None:
        return [Text("nothing playing", style=_DIM)]
    if now_playing.is_playing:
        icon = _PLAY_ICON
        icon_style = _PLAYING_STYLE
    else:
        icon = _PAUSE_ICON
        icon_style = _PAUSED_STYLE
    banner = Text()
    banner.append(f"{icon} ", style=icon_style)
    banner.append(now_playing.track.track, style="bold")
    banner.append(f" · {_format_artists(now_playing.track.artists)}", style=_DIM)
    context_label = _format_context(now_playing.context_kind, now_playing.context_name)
    context = Text(f"  {context_label}", style=_DIM)
    return [banner, context]


def _padded(cell: str, width: int) -> str:
    """cell widened to `width` terminal columns — emoji count as two, so ljust would under-pad."""
    return cell + " " * (width - cell_len(cell))


def _format_controls(shuffle: bool, repeat: str, is_playing: bool | None) -> list[Text]:
    """Transport bar: live state on the first line, each key hint under the glyph it drives."""
    if shuffle:
        shuffle_glyph = "⇄ on"
    else:
        shuffle_glyph = "⇄ off"
    if is_playing is True:
        transport = "⏸"
    elif is_playing is False:
        transport = "▶"
    else:
        transport = "■"
    if repeat == "track":
        repeat_glyph = "🔁 track"
    elif repeat == "context":
        repeat_glyph = "🔁 context"
    else:
        repeat_glyph = "🔁 off"

    columns = (
        (shuffle_glyph, "s shuffle"),
        ("⏮", ", prev"),
        (transport, "space play/pause"),
        ("⏭", ". next"),
        (repeat_glyph, "e repeat"),
    )
    state = Text(_ROW_INDENT[:2])
    hints = Text(_ROW_INDENT[:2], style=_DIM)
    for glyph, hint in columns:
        width = max(cell_len(glyph), cell_len(hint))
        state.append(_padded(glyph, width) + _CONTROL_GAP)
        hints.append(_padded(hint, width) + _CONTROL_GAP)
    return [Text(state.plain.rstrip()), Text(hints.plain.rstrip(), style=_DIM)]


def _format_queue(queue: tuple[Track, ...]) -> list[Text]:
    lines = [Text("  up next", style=_DIM)]
    if not queue:
        lines.append(Text(f"{_ROW_INDENT}queue is empty", style=_DIM))
        return lines
    for index, track in enumerate(queue[:_QUEUE_DISPLAY_LIMIT], start=1):
        row = Text()
        row.append(f"{index:>4}  ", style=_DIM)
        row.append_text(_format_track(track))
        lines.append(row)
    hidden = len(queue) - _QUEUE_DISPLAY_LIMIT
    if hidden > 0:
        lines.append(Text(f"{_ROW_INDENT}… {hidden} more", style=_DIM))
    return lines


def _format_last_played(last_played: LastPlayed | None) -> list[Text]:
    lines = [Text("  last played", style=_DIM)]
    if last_played is None:
        lines.append(Text(f"{_ROW_INDENT}nothing yet", style=_DIM))
        return lines
    row = Text(style=_DIM)
    row.append(_ROW_INDENT)
    row.append_text(_format_track(last_played.track))
    row.append(f"  {age(last_played.played_at)}")
    lines.append(row)
    return lines


class SpotifyPanel(Panel):
    DEFAULT_CSS = """
    SpotifyPanel > #player-search { dock: bottom; }
    """

    BINDINGS = [
        Binding("o", "open", "open in Spotify", show=False),
        Binding("p", "play_now", "play now", show=False),
        Binding("a", "add_to_queue", "add to queue", show=False),
        Binding("s", "toggle_shuffle", "shuffle", show=False),
        Binding("e", "cycle_repeat", "repeat", show=False),
        Binding("space", "toggle_playback", "play/pause", show=False),
        Binding("comma", "skip_previous", "previous", show=False),
        Binding("full_stop", "skip_next", "next", show=False),
    ]
    can_focus = True

    def __init__(self) -> None:
        super().__init__()
        self._search_action: _SearchAction | None = None
        self._work_pending = False

    def compose(self) -> ComposeResult:
        yield from super().compose()
        search_input = Input(id="player-search")
        search_input.display = False
        yield search_input

    def _state(self) -> PlayerState | None:
        if len(self.items) != 1:
            return None
        item = self.items[0]
        if isinstance(item, PlayerState):
            return item
        return None

    def ready_text(self) -> str:
        return self.render_ready().plain.strip()

    def render_ready(self) -> Text:
        state = self._state()
        lines: list[Text] = []
        if state is None:
            lines.append(Text("nothing playing", style=_DIM))
        else:
            lines.extend(_format_banner(state.now_playing))
            lines.append(Text())
            lines.extend(_format_queue(state.queue))
            lines.append(Text())
            lines.extend(_format_last_played(state.last_played))
            lines.append(Text())
            if state.now_playing is None:
                playing = None
            else:
                playing = state.now_playing.is_playing
            lines.extend(_format_controls(state.shuffle, state.repeat, playing))
        body = Text("\n").join(lines)
        # One row per track: a wrapped row spills into the next row's place and breaks the layout.
        body.no_wrap = True
        body.overflow = "ellipsis"
        return body

    def action_open(self) -> None:
        state = self._state()
        if state is None:
            webbrowser.open(FALLBACK_URL)
        else:
            webbrowser.open(state.url)

    def action_play_now(self) -> None:
        self._open_search(_SearchAction.PLAY, _PLAY_NOW_PLACEHOLDER)

    def action_add_to_queue(self) -> None:
        self._open_search(_SearchAction.QUEUE, _ADD_TO_QUEUE_PLACEHOLDER)

    def action_toggle_shuffle(self) -> None:
        if self._work_pending:
            return
        state = self._state()
        if state is None:
            self.notify("nothing to control yet", severity="warning")
            return
        enabled = not state.shuffle

        def work(credentials, http):
            return set_shuffle(credentials, http, enabled)

        if enabled:
            verb = "shuffle on"
        else:
            verb = "shuffle off"
        self._run_mode_change(work, verb)

    def action_cycle_repeat(self) -> None:
        if self._work_pending:
            return
        state = self._state()
        if state is None:
            self.notify("nothing to control yet", severity="warning")
            return
        mode = next_repeat_mode(state.repeat)

        def work(credentials, http):
            return set_repeat(credentials, http, mode)

        if mode == "off":
            verb = "repeat off"
        elif mode == "track":
            verb = "repeat track"
        else:
            verb = "repeat context"
        self._run_mode_change(work, verb)

    def action_toggle_playback(self) -> None:
        if self._work_pending:
            return
        state = self._state()
        if state is None:
            self.notify("nothing to control yet", severity="warning")
            return
        if state.now_playing is not None and state.now_playing.is_playing:
            verb = "paused"

            def pause_selected(credentials, http):
                pause_playback(credentials, http)
                return verb

            work = pause_selected
        else:
            verb = "playing"

            def resume_selected(credentials, http):
                resume_playback(credentials, http)
                return verb

            work = resume_selected

        self._run_mode_change(work, verb)

    def action_skip_next(self) -> None:
        if self._work_pending:
            return

        def work(credentials, http):
            skip_next(credentials, http)
            return "skipped"

        self._run_mode_change(work, "skipped next")

    def action_skip_previous(self) -> None:
        if self._work_pending:
            return

        def work(credentials, http):
            skip_previous(credentials, http)
            return "skipped"

        self._run_mode_change(work, "skipped previous")

    def _run_mode_change(self, work, verb: str) -> None:
        self._work_pending = True
        self.post_message(
            Panel.CredentialWorkRequested(
                self,
                work,
                on_success=lambda _result: self._on_mode_succeeded(verb),
                on_error=self._on_work_failed,
            )
        )

    def _on_mode_succeeded(self, verb: str) -> None:
        self._work_pending = False
        self.notify(verb)

    def _open_search(self, action: _SearchAction, placeholder: str) -> None:
        if self._work_pending:
            return
        self._search_action = action
        search_input = self.query_one("#player-search", Input)
        search_input.placeholder = placeholder
        search_input.value = ""
        search_input.display = True
        search_input.focus()

    def _close_search(self) -> None:
        search_input = self.query_one("#player-search", Input)
        search_input.display = False
        search_input.value = ""
        self._search_action = None
        self.focus()

    def on_key(self, event: events.Key) -> None:
        # Only intercepted while the search strip actually holds focus, so escape still reaches
        # whatever else would otherwise handle it (the help overlay, most notably) the rest of
        # the time.
        if event.key != "escape":
            return
        if self.query_one("#player-search", Input).has_focus:
            event.stop()
            self._close_search()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if self._work_pending:
            return
        action = self._search_action
        query = event.value.strip()
        if action is None:
            self._close_search()
            return
        if not query:
            self.notify("enter a search query", severity="warning")
            return
        include_contexts = action is _SearchAction.PLAY

        def work(credentials, http):
            return search(credentials, http, query, tracks_only=not include_contexts)

        self._work_pending = True
        self._close_search()
        self.post_message(
            Panel.CredentialWorkRequested(
                self,
                work,
                on_success=lambda result: self._on_search_ready(action, result),
                on_error=self._on_work_failed,
                refresh_on_success=False,
            )
        )

    def _on_search_ready(self, action: _SearchAction, result: object) -> None:
        self._work_pending = False
        if not isinstance(result, SearchResults):
            self.notify("search failed", severity="error")
            return
        for_queue = action is _SearchAction.QUEUE
        if for_queue:
            selectable = result.tracks
        else:
            selectable = result.items
        if not selectable:
            self.notify("no matches", severity="warning")
            return
        picker = search_picker(result, for_queue=for_queue)
        self.app.push_screen(picker, lambda chosen: self._on_pick(action, chosen))

    def _on_pick(self, action: _SearchAction, chosen: object) -> None:
        if chosen is None:
            self.focus()
            return
        if isinstance(chosen, Track):
            label = f"{chosen.track} · {_format_artists(chosen.artists)}"
            track = chosen
            if action is _SearchAction.PLAY:
                verb = "playing"

                def play_selected(credentials, http):
                    play_track(credentials, http, track.uri)
                    return track

                work = play_selected
            else:
                verb = "queued"

                def queue_selected(credentials, http):
                    queue_track(credentials, http, track.uri)
                    return track

                work = queue_selected
        elif isinstance(chosen, (Album, Playlist)):
            if action is _SearchAction.QUEUE:
                self.notify("only songs can be queued", severity="warning")
                self.focus()
                return
            if isinstance(chosen, Album):
                label = f"{chosen.name} · {_format_artists(chosen.artists)}"
            else:
                label = f"{chosen.name} · {chosen.owner}"
            verb = "playing"
            context = chosen

            def play_selected_context(credentials, http):
                play_context(credentials, http, context.uri)
                return context

            work = play_selected_context
        else:
            self.focus()
            return

        self._work_pending = True
        self.post_message(
            Panel.CredentialWorkRequested(
                self,
                work,
                on_success=lambda result: self._on_work_succeeded(verb, label, result),
                on_error=self._on_work_failed,
            )
        )

    def _on_work_succeeded(self, verb: str, label: str, result: object) -> None:
        self._work_pending = False
        self.notify(f"{verb} {label}")
        self.focus()

    def _on_work_failed(self, message: str) -> None:
        self._work_pending = False
        self.notify(message, severity="error")
        self.focus()
