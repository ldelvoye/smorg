"""What a Linear issue page can open, the trail of pages visited, and the breadcrumb."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from rich.text import Text

from smorg.integrations.linear.source import Issue, IssueDetail

UNKNOWN_UPDATED_AT = datetime(1970, 1, 1, tzinfo=UTC)
TRAIL_ROOT = "issues"
BREADCRUMB_CAP = 5

_SEPARATOR = " › "
_ELLIPSIS = "…"


@dataclass(frozen=True)
class Target:
    id: str
    title: str
    status: str
    status_type: str
    priority: str
    url: str


TargetSection = tuple[str, tuple[Target, ...]]


@dataclass(frozen=True)
class Visit:
    issue: Issue
    scroll_y: int = 0
    picker_cursor: int = 0


class Trail:
    """The pages opened from the list, bottom to top; empty means the list itself."""

    def __init__(self) -> None:
        self.visits: list[Visit] = []

    def push(self, issue: Issue) -> None:
        self.visits.append(Visit(issue=issue))

    def pop(self) -> Visit | None:
        if not self.visits:
            return None
        return self.visits.pop()

    def pop_to(self, index: int) -> None:
        """Keep visits up to and including `index`; -1 empties the trail."""
        del self.visits[index + 1 :]

    def current(self) -> Issue | None:
        if not self.visits:
            return None
        return self.visits[-1].issue

    def depth(self) -> int:
        return len(self.visits)

    def remember(self, scroll_y: int, picker_cursor: int) -> None:
        if not self.visits:
            return
        self.visits[-1] = replace(self.visits[-1], scroll_y=scroll_y, picker_cursor=picker_cursor)


def targets_of(detail: IssueDetail) -> tuple[TargetSection, ...]:
    sections: list[TargetSection] = []
    if detail.parent is not None:
        parent = detail.parent
        parent_target = Target(
            id=parent.id,
            title=parent.title,
            status=parent.status,
            status_type=parent.status_type,
            priority="",
            url=parent.url,
        )
        sections.append(("parent", (parent_target,)))
    if detail.sub_issues:
        done = [child for child in detail.sub_issues if child.status_type == "completed"]
        children: list[Target] = []
        for child in detail.sub_issues:
            children.append(
                Target(
                    id=child.id,
                    title=child.title,
                    status=child.status,
                    status_type=child.status_type,
                    priority=child.priority,
                    url=child.url,
                )
            )
        sections.append((f"sub-issues ({len(done)}/{len(detail.sub_issues)})", tuple(children)))
    for heading, relations in (
        ("blocked by", detail.blocked_by),
        ("blocks", detail.blocks),
        ("related", detail.related),
    ):
        if not relations:
            continue
        targets: list[Target] = []
        for relation in relations:
            targets.append(
                Target(
                    id=relation.id,
                    title=relation.title,
                    status="",
                    status_type="",
                    priority="",
                    url=relation.url,
                )
            )
        sections.append((f"{heading} ({len(relations)})", tuple(targets)))
    return tuple(sections)


def issue_of_target(target: Target, items: tuple[Issue, ...]) -> tuple[Issue, bool]:
    """The list item for the target when there is one, else a synthetic issue; and which."""
    for item in items:
        if item.id == target.id:
            return item, True
    synthetic = Issue(
        id=target.id,
        updated_at=UNKNOWN_UPDATED_AT,
        url=target.url,
        title=target.title,
        status=target.status,
        status_type=target.status_type,
        team="",
        priority=target.priority,
        project="",
    )
    return synthetic, False


def format_trail(ids: tuple[str, ...], budget: int, cap: int = BREADCRUMB_CAP) -> Text:
    """The trail fitted to `budget` columns from the right: the current id always, then earlier
    ids while they fit (at most `cap`), the root when it still fits, `…` for anything elided.
    """
    total = len(ids)
    if total == 0:
        return Text(TRAIL_ROOT, style="dim")
    shown: list[str] = [ids[-1]]
    for earlier in reversed(ids[:-1]):
        if len(shown) >= cap:
            break
        candidate = _render(shown=[earlier, *shown], total=total, root=False, elided=True)
        if len(candidate) > budget:
            break
        shown.insert(0, earlier)
    all_shown = len(shown) == total
    with_root = _render(shown=shown, total=total, root=True, elided=not all_shown)
    if len(with_root) <= budget:
        return Text(with_root, style="dim")
    without_root = _render(shown=shown, total=total, root=False, elided=True)
    if len(without_root) <= budget:
        return Text(without_root, style="dim")
    return Text(f"{ids[-1]} ({total})", style="dim")


def _render(shown: list[str], total: int, root: bool, elided: bool) -> str:
    parts: list[str] = []
    if root:
        parts.append(TRAIL_ROOT)
    if elided:
        parts.append(_ELLIPSIS)
    parts.extend(shown)
    line = _SEPARATOR.join(parts)
    if elided:
        line = f"{line} ({total})"
    return line
