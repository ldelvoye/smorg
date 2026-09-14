"""The selected-event card under a ruler."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.text import Text

from smorg.integrations.gcal.chips import rsvp_glyph
from smorg.integrations.gcal.source import Event, Response
from smorg.shell.cards import format_box, format_count
from smorg.shell.format import truncating

_RESPONSE_LABELS = {
    Response.ACCEPTED: "accepted",
    Response.TENTATIVE: "tentative",
    Response.NEEDS_ACTION: "needs action",
    Response.DECLINED: "declined",
    Response.NONE: "",
}


def _format_head(event: Event) -> Text:
    head = Text()
    if event.all_day:
        head.append("all day", style="dim")
    else:
        head.append(f"{event.start.strftime('%H:%M')}–{event.end.strftime('%H:%M')}", style="dim")
    head.append(f"  {event.title}", style="bold")
    label = _RESPONSE_LABELS[event.my_response]
    if label:
        head.append(f"  {rsvp_glyph(event.my_response)} {label}", style="dim")
    return truncating(head)


def _format_meta(event: Event, calendar_name: str) -> Text:
    pieces = [calendar_name]
    if event.meet_url:
        pieces.append("meet link")
    if event.location:
        pieces.append(event.location)
    if event.attendees:
        attendee_count = len(event.attendees)
        attendee_label = format_count(attendee_count, "attendee")
        pieces.append(attendee_label)
    joined = " · ".join(pieces)
    meta = Text(joined, style="dim")
    return truncating(meta)


def format_footer(event: Event, calendar_name: str, bordered: bool) -> RenderableType:
    lines = [_format_head(event), _format_meta(event, calendar_name)]
    if bordered:
        return format_box(list(lines))
    return Group(*lines)
