"""Invented Linear data for the demo harness: a fictional team building Ferry, a job scheduler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from smorg.core.contract import Item, Newest
from smorg.integrations.linear.source import (
    VIEWER_ID,
    Comment,
    Issue,
    IssueDetail,
    Link,
    Milestone,
    ParentSummary,
    Project,
    ProjectDetail,
    ProjectIssue,
    RelatedIssue,
    SubIssue,
    Transition,
    Viewer,
)

NOW = datetime(2026, 9, 12, 16, 45, tzinfo=UTC)

_NO_COMMENTS: Newest[Comment] = Newest(items=(), hidden=0, hidden_is_lower_bound=False)

_WORKSPACE = "palisade-labs"


def _hours_ago(hours: int) -> datetime:
    return NOW - timedelta(hours=hours)


def _days_ago(days: int) -> datetime:
    return NOW - timedelta(days=days)


def _slugify(title: str) -> str:
    lowered = title.lower()
    kept_characters: list[str] = []
    for character in lowered:
        is_word_character = character.isalnum() or character == " "
        if is_word_character:
            kept_characters.append(character)
    cleaned = "".join(kept_characters)
    slug = cleaned.strip().replace(" ", "-")
    return slug


def _issue_url(issue_id: str, title: str) -> str:
    slug = _slugify(title)
    return f"https://linear.app/{_WORKSPACE}/issue/{issue_id}/{slug}"


def _project_url(slug: str) -> str:
    return f"https://linear.app/{_WORKSPACE}/project/{slug}/overview"


def _issue(
    issue_id: str,
    title: str,
    status: str,
    status_type: str,
    team: str,
    priority: str,
    project: str,
    updated_at: datetime,
) -> Issue:
    url = _issue_url(issue_id, title)
    return Issue(
        id=issue_id,
        updated_at=updated_at,
        url=url,
        title=title,
        status=status,
        status_type=status_type,
        team=team,
        priority=priority,
        project=project,
    )


def _project_issue(
    issue_id: str,
    title: str,
    status: str,
    status_type: str,
    priority: str,
    assignee: str,
    parent_id: str = "",
) -> ProjectIssue:
    url = _issue_url(issue_id, title)
    return ProjectIssue(
        id=issue_id,
        title=title,
        status=status,
        status_type=status_type,
        priority=priority,
        url=url,
        assignee=assignee,
        parent_id=parent_id,
    )


def _sub_issue(issue_id: str, title: str, status: str, status_type: str, priority: str) -> SubIssue:
    url = _issue_url(issue_id, title)
    return SubIssue(
        id=issue_id,
        title=title,
        status=status,
        status_type=status_type,
        priority=priority,
        url=url,
    )


def _related_issue(issue_id: str, title: str) -> RelatedIssue:
    url = _issue_url(issue_id, title)
    return RelatedIssue(id=issue_id, title=title, url=url)


def _parent_summary(issue_id: str, title: str, status: str, status_type: str) -> ParentSummary:
    url = _issue_url(issue_id, title)
    return ParentSummary(id=issue_id, title=title, status=status, status_type=status_type, url=url)


def _light_detail(
    description: str,
    status: str,
    status_type: str,
    priority: str,
    team: str,
    assignee: str,
    creator: str,
    project: str,
    created_at: datetime,
    comments: Newest[Comment] = _NO_COMMENTS,
) -> IssueDetail:
    creation = Transition(status=status, status_type=status_type, at=created_at)
    return IssueDetail(
        description=description,
        status=status,
        status_type=status_type,
        priority=priority,
        team=team,
        assignee=assignee,
        creator=creator,
        labels=(),
        project=project,
        milestone="",
        due_date="",
        estimate="",
        parent=None,
        sub_issues=(),
        blocked_by=(),
        blocks=(),
        related=(),
        links=(),
        transitions=(creation,),
        comments=comments,
    )


VIEWER = Viewer(
    id=VIEWER_ID,
    updated_at=datetime(1970, 1, 1, tzinfo=UTC),
    url="https://linear.app",
    name="Dana Okafor",
    handle="dana",
)

_MILESTONE_DESIGN_REVIEW = Milestone(
    name="Design review signed off", target_date="2026-08-20", progress=100
)
_MILESTONE_CANARY_ROLLOUT = Milestone(
    name="Canary rollout to 10% of clusters", target_date="2026-09-25", progress=55
)
_MILESTONE_GA_ROLLOUT = Milestone(
    name="GA rollout to all clusters", target_date="2026-11-10", progress=0
)
_MILESTONE_COMMAND_SURFACE = Milestone(
    name="Finalize the command surface", target_date="2026-10-15", progress=0
)
_MILESTONE_BETA_PARTNERS = Milestone(
    name="Beta with three design partners", target_date="2026-12-01", progress=0
)
_MILESTONE_MIGRATE_CALLERS = Milestone(
    name="Migrate internal callers off the relay", target_date="2026-06-01", progress=100
)
_MILESTONE_DECOMMISSION_HOSTS = Milestone(
    name="Decommission the relay hosts", target_date="2026-07-15", progress=100
)
_MILESTONE_SCALING_SIGNALS = Milestone(
    name="Add per-zone scaling signals", target_date="2026-09-20", progress=40
)
_MILESTONE_PROD_ROLLOUT = Milestone(
    name="Roll out to production", target_date="2026-10-05", progress=0
)

PROJECT_BACKPRESSURE = Project(
    id="project-queue-backpressure",
    updated_at=_hours_ago(4),
    url=_project_url("queue-backpressure-rework"),
    name="Queue backpressure rework",
    summary="Give the intake queue a way to push back on producers before it fills up.",
    status="In Progress",
    status_type="started",
    priority="High",
    lead="Dana Okafor",
    teams=("RUN", "DAT"),
    start_date="2026-08-03",
    target_date="2026-11-15",
    target_resolution="quarter",
    milestones=(_MILESTONE_DESIGN_REVIEW, _MILESTONE_CANARY_ROLLOUT, _MILESTONE_GA_ROLLOUT),
)

PROJECT_CLI_V2 = Project(
    id="project-ferry-cli-v2",
    updated_at=_days_ago(1),
    url=_project_url("ferry-cli-v2-rewrite"),
    name="Ferry CLI v2 rewrite",
    summary="A from-scratch CLI with fewer prompts and scriptable output.",
    status="Planned",
    status_type="planned",
    priority="Medium",
    lead="Priya Nair",
    teams=("DX",),
    start_date="",
    target_date="2027-01-31",
    target_resolution="halfYear",
    milestones=(_MILESTONE_COMMAND_SURFACE, _MILESTONE_BETA_PARTNERS),
)

PROJECT_WEBHOOK_RETIREMENT = Project(
    id="project-webhook-retirement",
    updated_at=_days_ago(30),
    url=_project_url("legacy-webhook-relay-retirement"),
    name="Legacy webhook relay retirement",
    summary="Retire the standalone webhook relay now that every caller goes through Ferry.",
    status="Completed",
    status_type="completed",
    priority="Low",
    lead="Felix Brandt",
    teams=("RUN",),
    start_date="2026-05-01",
    target_date="2026-07-15",
    target_resolution="month",
    milestones=(_MILESTONE_MIGRATE_CALLERS, _MILESTONE_DECOMMISSION_HOSTS),
)

PROJECT_WORKER_AUTOSCALING = Project(
    id="project-worker-autoscaling",
    updated_at=_hours_ago(10),
    url=_project_url("worker-pool-autoscaling"),
    name="Worker pool autoscaling",
    summary="Scale worker pools per zone instead of paying for one global pool.",
    status="In Progress",
    status_type="started",
    priority="Medium",
    lead="Yuki Tanaka",
    teams=("RUN",),
    start_date="2026-08-25",
    target_date="2026-10-05",
    target_resolution="month",
    milestones=(_MILESTONE_SCALING_SIGNALS, _MILESTONE_PROD_ROLLOUT),
)

ISSUE_RUN_501 = _issue(
    "RUN-501",
    "Add backpressure signal to worker intake queue so producers slow down before the queue "
    "overflows and starts dropping jobs silently",
    "In Progress",
    "started",
    "Runtime",
    "Urgent",
    "Queue backpressure rework",
    _hours_ago(3),
)
ISSUE_RUN_502 = _issue(
    "RUN-502",
    "Cache compiled DAG plans across worker restarts",
    "In Progress",
    "started",
    "Runtime",
    "High",
    "Queue backpressure rework",
    _days_ago(1) - timedelta(hours=2),
)
ISSUE_RUN_503 = _issue(
    "RUN-503",
    "Pin scheduler workers to zone-local queues to cut cross-zone egress",
    "In Progress",
    "started",
    "Runtime",
    "Medium",
    "Worker pool autoscaling",
    _hours_ago(9),
)
ISSUE_RUN_504 = _issue(
    "RUN-504",
    "Replace polling watcher with an inotify-based one on Linux workers",
    "In Review",
    "started",
    "Runtime",
    "High",
    "",
    _hours_ago(5),
)
ISSUE_RUN_505 = _issue(
    "RUN-505",
    "Trim the scheduler's per-tick allocation churn",
    "In Review",
    "started",
    "Runtime",
    "Medium",
    "",
    _days_ago(2),
)
ISSUE_RUN_506 = _issue(
    "RUN-506",
    "Design a shutdown grace period for long-running jobs that catches SIGTERM, drains "
    "in-flight work, and reports partial progress back to the queue before the worker "
    "process actually exits",
    "Todo",
    "unstarted",
    "Runtime",
    "Urgent",
    "Queue backpressure rework",
    _hours_ago(14),
)
ISSUE_RUN_507 = _issue(
    "RUN-507",
    "Fix flaky shutdown hook ordering in the supervisor",
    "Blocked",
    "started",
    "Runtime",
    "Urgent",
    "",
    _hours_ago(20),
)
ISSUE_DX_201 = _issue(
    "DX-201",
    "Rework `ferry init` wizard to ask fewer questions up front",
    "In Progress",
    "started",
    "Developer Experience",
    "Medium",
    "Ferry CLI v2 rewrite",
    _hours_ago(7),
)
ISSUE_DX_202 = _issue(
    "DX-202",
    "Document the new retry budget configuration knobs and their defaults",
    "In Review",
    "started",
    "Developer Experience",
    "No priority",
    "Ferry CLI v2 rewrite",
    _hours_ago(11),
)
ISSUE_DX_203 = _issue(
    "DX-203",
    "Add shell completion for the ferry CLI's newer subcommands",
    "Todo",
    "unstarted",
    "Developer Experience",
    "Low",
    "Ferry CLI v2 rewrite",
    _days_ago(1) - timedelta(hours=1),
)
ISSUE_DX_204 = _issue(
    "DX-204",
    "Ship the CLI's offline mode for airplane-friendly demos",
    "Blocked",
    "started",
    "Developer Experience",
    "Low",
    "",
    _days_ago(5),
)
ISSUE_DAT_301 = _issue(
    "DAT-301",
    "Backfill retry_budget column for jobs created before the migration",
    "In Progress",
    "started",
    "Data Infra",
    "High",
    "Queue backpressure rework",
    _days_ago(1) - timedelta(hours=20),
)
ISSUE_DAT_302 = _issue(
    "DAT-302",
    "Evaluate ClickHouse vs Postgres for the job-history archive",
    "Todo",
    "unstarted",
    "Data Infra",
    "Low",
    "",
    _days_ago(3),
)
ISSUE_DAT_303 = _issue(
    "DAT-303",
    "Migrate job-history archive off the deprecated warm-storage cluster",
    "Blocked",
    "started",
    "Data Infra",
    "Medium",
    "",
    _days_ago(2) - timedelta(hours=6),
)
ISSUE_GRW_401 = _issue(
    "GRW-401",
    "Add usage-based billing hooks to the onboarding checklist",
    "In Review",
    "started",
    "Growth",
    "Low",
    "",
    _days_ago(1) - timedelta(hours=4),
)
ISSUE_GRW_402 = _issue(
    "GRW-402",
    "Spike a WASM sandbox for untrusted job code",
    "Todo",
    "unstarted",
    "Growth",
    "No priority",
    "",
    _days_ago(4),
)

ITEMS: tuple[Item, ...] = (
    VIEWER,
    PROJECT_BACKPRESSURE,
    PROJECT_CLI_V2,
    PROJECT_WEBHOOK_RETIREMENT,
    PROJECT_WORKER_AUTOSCALING,
    ISSUE_RUN_501,
    ISSUE_RUN_502,
    ISSUE_RUN_503,
    ISSUE_RUN_504,
    ISSUE_RUN_505,
    ISSUE_RUN_506,
    ISSUE_RUN_507,
    ISSUE_DX_201,
    ISSUE_DX_202,
    ISSUE_DX_203,
    ISSUE_DX_204,
    ISSUE_DAT_301,
    ISSUE_DAT_302,
    ISSUE_DAT_303,
    ISSUE_GRW_401,
    ISSUE_GRW_402,
)

_PARENT_RUN_500 = _parent_summary(
    "RUN-500", "Backpressure-aware intake queue", "In Progress", "started"
)
_SUB_RUN_508 = _sub_issue(
    "RUN-508", "Add config flag to toggle backpressure signaling", "Done", "completed", "Medium"
)
_SUB_RUN_509 = _sub_issue(
    "RUN-509",
    "Emit backpressure metric to the existing dashboard",
    "In Progress",
    "started",
    "High",
)
_BLOCKED_BY_DAT_304 = _related_issue(
    "DAT-304", "Expose queue depth from the storage layer's admin API"
)
_BLOCKS_RUN_510 = _related_issue(
    "RUN-510", "Auto-throttle noisy producers once backpressure engages"
)
_RELATED_GRW_403 = _related_issue(
    "GRW-403", "Add a customer-facing status page module for queue health"
)

DETAIL_RUN_501 = IssueDetail(
    description=(
        "The intake queue currently has no way to tell producers it is under pressure. Once "
        "the queue passes its high-water mark we start dropping the oldest jobs, which is a "
        "bad way to find out capacity ran out.\n\n"
        "This adds a `Signal()` method producers can poll before enqueueing:\n\n"
        "- `clear` below the low-water mark\n"
        "- `warning` between the two marks\n"
        "- `throttle` at or above the high-water mark\n\n"
        "Producers that ignore the signal keep working exactly as they do today, this is "
        "purely additive. The canary rollout plan is tracked in the linked runbook."
    ),
    status="In Progress",
    status_type="started",
    priority="Urgent",
    team="Runtime",
    assignee="Dana Okafor",
    creator="Dana Okafor",
    labels=("runtime", "reliability"),
    project="Queue backpressure rework",
    milestone="Canary rollout to 10% of clusters",
    due_date="2026-09-20",
    estimate="5",
    parent=_PARENT_RUN_500,
    sub_issues=(_SUB_RUN_508, _SUB_RUN_509),
    blocked_by=(_BLOCKED_BY_DAT_304,),
    blocks=(_BLOCKS_RUN_510,),
    related=(_RELATED_GRW_403,),
    links=(Link(title="Backpressure design doc", url="https://docs.palisade.dev/backpressure"),),
    transitions=(
        Transition(status="Todo", status_type="unstarted", at=_days_ago(9)),
        Transition(status="In Progress", status_type="started", at=_days_ago(2)),
    ),
    comments=Newest(
        items=(
            Comment(
                author="Marcus Webb",
                body="I can take the SDK-side follow-up once this lands.",
                created_at=_days_ago(1),
            ),
            Comment(
                author="Dana Okafor",
                body="Sounds good, filed `RUN-510` for the auto-throttle follow-up.",
                created_at=_hours_ago(20),
            ),
            Comment(
                author="Priya Nair",
                body=(
                    "Should the `warning` state also show up in the queue admin UI, or just "
                    "internally?"
                ),
                created_at=_hours_ago(6),
            ),
        ),
        hidden=0,
        hidden_is_lower_bound=False,
    ),
)

DETAIL_RUN_506 = IssueDetail(
    description=(
        "Long-running jobs get killed outright when a worker is recycled, which means any "
        "in-flight batch work is lost and has to restart from scratch.\n\n"
        "The plan is to give jobs a grace period on `SIGTERM`:\n\n"
        "- Stop pulling new batches immediately\n"
        "- Finish the current batch if it fits inside the grace window\n"
        "- Otherwise checkpoint progress and requeue the remainder\n\n"
        "Workers already expose a `Drain()` hook for maintenance, this reuses it instead of "
        "adding a second shutdown path."
    ),
    status="Todo",
    status_type="unstarted",
    priority="Urgent",
    team="Runtime",
    assignee="Dana Okafor",
    creator="Marcus Webb",
    labels=("runtime", "durability"),
    project="Queue backpressure rework",
    milestone="GA rollout to all clusters",
    due_date="2026-09-30",
    estimate="8",
    parent=None,
    sub_issues=(),
    blocked_by=(),
    blocks=(),
    related=(),
    links=(),
    transitions=(
        Transition(status="Backlog", status_type="backlog", at=_days_ago(20)),
        Transition(status="Todo", status_type="unstarted", at=_days_ago(9)),
    ),
    comments=Newest(
        items=(
            Comment(
                author="Marcus Webb",
                body=(
                    "Worth checking whether `Drain()` already respects a timeout, or if we "
                    "need to add one."
                ),
                created_at=_days_ago(3),
            ),
            Comment(
                author="Dana Okafor",
                body="It does not today. Added a `drain_timeout` field to the design doc.",
                created_at=_days_ago(2),
            ),
        ),
        hidden=0,
        hidden_is_lower_bound=False,
    ),
)

DETAIL_DAT_301 = IssueDetail(
    description=(
        "Jobs created before the retry-budget migration have a `null` `retry_budget`, which "
        'the new per-class accounting code treats as "no budget left" instead of "unset".\n\n'
        "Backfill plan:\n\n"
        "- Default every `null` row to the job class's configured budget\n"
        "- Run in batches of 5,000 rows to keep replication lag low\n"
        "- Skip rows already touched by a concurrent write\n\n"
        "The `retry_budget_backfill` script already handles batching, this just wires it into "
        "the migration runner."
    ),
    status="In Progress",
    status_type="started",
    priority="High",
    team="Data Infra",
    assignee="Dana Okafor",
    creator="Naomi Reyes",
    labels=("data", "migration"),
    project="Queue backpressure rework",
    milestone="",
    due_date="2026-09-15",
    estimate="3",
    parent=None,
    sub_issues=(),
    blocked_by=(),
    blocks=(),
    related=(),
    links=(),
    transitions=(
        Transition(status="Todo", status_type="unstarted", at=_days_ago(6)),
        Transition(status="In Progress", status_type="started", at=_days_ago(1)),
    ),
    comments=Newest(
        items=(
            Comment(
                author="Naomi Reyes",
                body=(
                    "Batches of 5,000 sound right based on the replication lag graphs from "
                    "last week."
                ),
                created_at=_hours_ago(30),
            ),
        ),
        hidden=0,
        hidden_is_lower_bound=False,
    ),
)

DETAIL_RUN_503 = _light_detail(
    "Scheduler workers currently pull from one global queue regardless of zone, which causes "
    "avoidable cross-zone egress on every job pickup.",
    "In Progress",
    "started",
    "Medium",
    "Runtime",
    "Dana Okafor",
    "Yuki Tanaka",
    "Worker pool autoscaling",
    _days_ago(6),
)
DETAIL_RUN_502 = _light_detail(
    "Compiled DAG plans are recomputed on every worker restart even though the source DAG "
    "has not changed, this caches the compiled plan keyed by DAG hash.",
    "In Progress",
    "started",
    "High",
    "Runtime",
    "Dana Okafor",
    "Marcus Webb",
    "Queue backpressure rework",
    _days_ago(4),
    Newest(
        items=(
            Comment(
                author="Elena Kowalski",
                body="The cold-start numbers on the benchmark dashboard already look better.",
                created_at=_hours_ago(30),
            ),
        ),
        hidden=0,
        hidden_is_lower_bound=False,
    ),
)
DETAIL_RUN_504 = _light_detail(
    "Swaps the polling file watcher for an inotify-based one on Linux so config reloads "
    "happen within milliseconds instead of the current five-second poll interval.",
    "In Review",
    "started",
    "High",
    "Runtime",
    "Dana Okafor",
    "Yuki Tanaka",
    "",
    _days_ago(5),
    Newest(
        items=(
            Comment(
                author="Yuki Tanaka",
                body="Filed a follow-up for the network-mount fallback so this doesn't block.",
                created_at=_hours_ago(28),
            ),
        ),
        hidden=0,
        hidden_is_lower_bound=False,
    ),
)
DETAIL_RUN_505 = _light_detail(
    "The scheduler allocates a new slice on every tick to build the ready set, this reuses a "
    "pooled slice instead.",
    "In Review",
    "started",
    "Medium",
    "Runtime",
    "Dana Okafor",
    "Elena Kowalski",
    "",
    _days_ago(4),
)
DETAIL_RUN_507 = _light_detail(
    "The supervisor sometimes runs the shutdown hooks out of order under load, which "
    "occasionally closes the queue connection before in-flight jobs finish draining.",
    "Blocked",
    "started",
    "Urgent",
    "Runtime",
    "Dana Okafor",
    "Marcus Webb",
    "",
    _days_ago(3),
    Newest(
        items=(
            Comment(
                author="Dana Okafor",
                body=(
                    "Reproduced locally with `go test -race`, still narrowing down which "
                    "hook fires late."
                ),
                created_at=_hours_ago(18),
            ),
        ),
        hidden=0,
        hidden_is_lower_bound=False,
    ),
)
DETAIL_DX_201 = _light_detail(
    "The `ferry init` wizard asks six questions before scaffolding a project, most answers "
    "can be inferred from the repo it is run in.",
    "In Progress",
    "started",
    "Medium",
    "Developer Experience",
    "Dana Okafor",
    "Priya Nair",
    "Ferry CLI v2 rewrite",
    _days_ago(5),
    Newest(
        items=(
            Comment(
                author="Priya Nair",
                body="Cut it from seven prompts down to three by inferring the default team.",
                created_at=_hours_ago(9),
            ),
        ),
        hidden=0,
        hidden_is_lower_bound=False,
    ),
)
DETAIL_DX_202 = _light_detail(
    "The retry budget configuration knobs shipped last week have no documentation page yet.",
    "In Review",
    "started",
    "No priority",
    "Developer Experience",
    "Dana Okafor",
    "Dana Okafor",
    "Ferry CLI v2 rewrite",
    _days_ago(2),
)
DETAIL_DX_203 = _light_detail(
    "The CLI's newer subcommands, `ferry replay` and `ferry drain`, have no shell completion "
    "entries.",
    "Todo",
    "unstarted",
    "Low",
    "Developer Experience",
    "Dana Okafor",
    "Priya Nair",
    "Ferry CLI v2 rewrite",
    _days_ago(6),
)
DETAIL_DX_204 = _light_detail(
    "Demos at conferences need the CLI to work without network access, falling back to "
    "cached schema and templates.",
    "Blocked",
    "started",
    "Low",
    "Developer Experience",
    "Dana Okafor",
    "Sam Whitfield",
    "",
    _days_ago(10),
)
DETAIL_DAT_302 = _light_detail(
    "The job-history archive is outgrowing its current Postgres table and needs a columnar "
    "store built for range scans.",
    "Todo",
    "unstarted",
    "Low",
    "Data Infra",
    "Dana Okafor",
    "Naomi Reyes",
    "",
    _days_ago(7),
    Newest(
        items=(
            Comment(
                author="Naomi Reyes",
                body="Leaning ClickHouse given how much of this is append-only range scans.",
                created_at=_hours_ago(40),
            ),
        ),
        hidden=0,
        hidden_is_lower_bound=False,
    ),
)
DETAIL_DAT_303 = _light_detail(
    "The warm-storage cluster backing the job-history archive is on the deprecation list and "
    "needs its data moved before the cluster is torn down.",
    "Blocked",
    "started",
    "Medium",
    "Data Infra",
    "Dana Okafor",
    "Felix Brandt",
    "",
    _days_ago(8),
)
DETAIL_GRW_401 = _light_detail(
    "New workspaces do not see usage-based billing terms until they hit a limit, this "
    "surfaces them earlier in onboarding.",
    "In Review",
    "started",
    "Low",
    "Growth",
    "Dana Okafor",
    "Grace Liu",
    "",
    _days_ago(4),
    Newest(
        items=(
            Comment(
                author="Grace Liu",
                body="Legal signed off on the billing disclosure copy this morning.",
                created_at=_hours_ago(14),
            ),
        ),
        hidden=0,
        hidden_is_lower_bound=False,
    ),
)
DETAIL_GRW_402 = _light_detail(
    "Untrusted job code currently runs with the same privileges as trusted jobs, a WASM "
    "sandbox would isolate it.",
    "Todo",
    "unstarted",
    "No priority",
    "Growth",
    "Dana Okafor",
    "Sam Whitfield",
    "",
    _days_ago(9),
)

DETAIL_RUN_500 = _light_detail(
    "Tracks every change needed to make the intake queue signal backpressure instead of "
    "silently dropping jobs once it fills up.",
    "In Progress",
    "started",
    "High",
    "Runtime",
    "Dana Okafor",
    "Dana Okafor",
    "",
    _days_ago(21),
)
DETAIL_RUN_508 = _light_detail(
    "Ships behind `backpressure_signal_enabled` so it can be turned off instantly if the "
    "canary misbehaves.",
    "Done",
    "completed",
    "Medium",
    "Runtime",
    "Marcus Webb",
    "Dana Okafor",
    "",
    _days_ago(15),
)
DETAIL_RUN_509 = _light_detail(
    "Wires `queue.Signal()` into the same metrics pipeline the queue depth graph already uses.",
    "In Progress",
    "started",
    "High",
    "Runtime",
    "Dana Okafor",
    "Marcus Webb",
    "",
    _days_ago(6),
)
DETAIL_DAT_304 = _light_detail(
    "The storage layer tracks queue depth internally but does not expose it yet, the "
    "backpressure signal needs to read it externally.",
    "In Progress",
    "started",
    "High",
    "Data Infra",
    "Naomi Reyes",
    "Dana Okafor",
    "",
    _days_ago(10),
)
DETAIL_RUN_510 = _light_detail(
    "Once the signal exists, the noisiest producers could be throttled automatically instead "
    "of relying on every client to poll it.",
    "Todo",
    "unstarted",
    "Medium",
    "Runtime",
    "",
    "Dana Okafor",
    "",
    _days_ago(2),
)
DETAIL_GRW_403 = _light_detail(
    "Customers currently only find out about queue slowdowns from support tickets.",
    "Todo",
    "unstarted",
    "Low",
    "Growth",
    "Grace Liu",
    "Dana Okafor",
    "",
    _days_ago(3),
)

PI_RUN_501 = _project_issue(
    "RUN-501", ISSUE_RUN_501.title, "In Progress", "started", "Urgent", "Dana Okafor"
)
PI_RUN_502 = _project_issue(
    "RUN-502", ISSUE_RUN_502.title, "In Progress", "started", "High", "Dana Okafor", PI_RUN_501.id
)
PI_RUN_511 = _project_issue(
    "RUN-511",
    "Add integration test for backpressure signal under load",
    "Todo",
    "unstarted",
    "Medium",
    "Marcus Webb",
    PI_RUN_502.id,
)
PI_RUN_512 = _project_issue(
    "RUN-512",
    "Handle backpressure signal in the Python SDK's async client",
    "Blocked",
    "started",
    "High",
    "",
    PI_RUN_502.id,
)
PI_RUN_513 = _project_issue(
    "RUN-513",
    "Unblock: confirm the async client's retry queue can pause without deadlocking",
    "In Review",
    "started",
    "Urgent",
    "Dana Okafor",
    PI_RUN_512.id,
)
PI_DAT_301 = _project_issue(
    "DAT-301", ISSUE_DAT_301.title, "In Progress", "started", "High", "Dana Okafor", PI_RUN_501.id
)
PI_DAT_305 = _project_issue(
    "DAT-305",
    "Add backpressure metrics to the nightly capacity report",
    "Todo",
    "unstarted",
    "Low",
    "Naomi Reyes",
    PI_RUN_501.id,
)
PI_RUN_506 = _project_issue(
    "RUN-506", ISSUE_RUN_506.title, "Todo", "unstarted", "Urgent", "Dana Okafor"
)
PI_RUN_514 = _project_issue(
    "RUN-514",
    "Prototype SIGTERM handling in the Go worker runtime",
    "In Progress",
    "started",
    "Medium",
    "Yuki Tanaka",
    PI_RUN_506.id,
)
PI_RUN_515 = _project_issue(
    "RUN-515",
    "Write a chaos test that SIGTERMs a worker mid-batch",
    "Todo",
    "unstarted",
    "Low",
    "",
    PI_RUN_514.id,
)
PI_RUN_516 = _project_issue(
    "RUN-516",
    "Document the shutdown grace period contract for job authors",
    "Todo",
    "unstarted",
    "No priority",
    "Priya Nair",
    PI_RUN_506.id,
)
PI_RUN_517 = _project_issue(
    "RUN-517",
    "Give the queue admin UI a live backpressure gauge",
    "In Review",
    "started",
    "Medium",
    "Dana Okafor",
)
PI_RUN_518 = _project_issue(
    "RUN-518",
    "Wire the gauge to the new backpressure metrics stream",
    "In Progress",
    "started",
    "Medium",
    "Elena Kowalski",
    PI_RUN_517.id,
)
PI_RUN_520 = _project_issue(
    "RUN-520", "Explore adaptive high-water marks per cluster size", "Backlog", "backlog", "Low", ""
)
PI_RUN_521 = _project_issue(
    "RUN-521",
    "Consider a gRPC streaming API for the signal instead of polling",
    "Backlog",
    "backlog",
    "No priority",
    "Felix Brandt",
)
PI_RUN_522 = _project_issue(
    "RUN-522",
    "Add backpressure signal docs to the runbook index",
    "Done",
    "completed",
    "Medium",
    "Marcus Webb",
)
PI_RUN_524 = _project_issue(
    "RUN-524",
    "Investigate one canary host reporting signal flaps every few minutes",
    "Triage",
    "triage",
    "",
    "",
)

DETAIL_RUN_511 = _light_detail(
    "Load-tests `queue.Signal()` transitions under a producer flood to make sure the "
    "thresholds hold up outside unit tests.",
    "Todo",
    "unstarted",
    "Medium",
    "Runtime",
    "Marcus Webb",
    "Dana Okafor",
    "Queue backpressure rework",
    _days_ago(4),
)
DETAIL_RUN_512 = _light_detail(
    "Blocked on the SDK's async client exposing a hook the signal can plug into without "
    "breaking existing callers.",
    "Blocked",
    "started",
    "High",
    "Runtime",
    "",
    "Marcus Webb",
    "Queue backpressure rework",
    _days_ago(3),
)
DETAIL_RUN_513 = _light_detail(
    "Spike to confirm pausing the async client's retry queue mid-flight does not deadlock "
    "against its own connection pool.",
    "In Review",
    "started",
    "Urgent",
    "Runtime",
    "Dana Okafor",
    "Marcus Webb",
    "Queue backpressure rework",
    _days_ago(1),
)
DETAIL_DAT_305 = _light_detail(
    "The nightly capacity report should show how often each cluster spent time in `warning` "
    "or `throttle`.",
    "Todo",
    "unstarted",
    "Low",
    "Data Infra",
    "Naomi Reyes",
    "Dana Okafor",
    "Queue backpressure rework",
    _days_ago(5),
)
DETAIL_RUN_514 = _light_detail(
    "Prototypes catching `SIGTERM`, finishing the current batch inside the grace window, and "
    "requeuing the remainder.",
    "In Progress",
    "started",
    "Medium",
    "Runtime",
    "Yuki Tanaka",
    "Marcus Webb",
    "Queue backpressure rework",
    _days_ago(6),
)
DETAIL_RUN_515 = _light_detail(
    "Exercises the new shutdown path by killing a worker mid-batch on a schedule in the "
    "staging cluster.",
    "Todo",
    "unstarted",
    "Low",
    "Runtime",
    "",
    "Yuki Tanaka",
    "Queue backpressure rework",
    _days_ago(2),
)
DETAIL_RUN_516 = _light_detail(
    "Job authors need to know what `Drain()` guarantees before they can rely on the grace period.",
    "Todo",
    "unstarted",
    "No priority",
    "Developer Experience",
    "Priya Nair",
    "Dana Okafor",
    "Queue backpressure rework",
    _days_ago(4),
)
DETAIL_RUN_517 = _light_detail(
    "Adds a live gauge to the internal admin UI so on-call can see backpressure state "
    "without querying metrics directly.",
    "In Review",
    "started",
    "Medium",
    "Runtime",
    "Dana Okafor",
    "Elena Kowalski",
    "Queue backpressure rework",
    _days_ago(3),
)
DETAIL_RUN_518 = _light_detail(
    "Connects the admin UI gauge to the metrics stream `RUN-509` publishes.",
    "In Progress",
    "started",
    "Medium",
    "Runtime",
    "Elena Kowalski",
    "Dana Okafor",
    "Queue backpressure rework",
    _days_ago(2),
)

PROJECT_DETAIL_BACKPRESSURE = ProjectDetail(
    description=(
        "Producers currently discover the intake queue is full only when their enqueue calls "
        "start failing. That is late: by the time we see failures, the queue has already been "
        "dropping jobs for a while.\n\n"
        "This project adds a backpressure signal producers can poll before enqueueing, plus "
        "the shutdown and cache changes needed to make workers cheaper to scale during a "
        "throttle event.\n\n"
        "Rollout is staged behind a config flag, region by region, starting with the canary "
        "cluster.\n\n"
        "## Why now\n\n"
        "Two of the last three capacity incidents began the same way: a burst of enqueues from "
        "one noisy tenant filled the intake queue, and the first anyone knew of it was a wave "
        "of dropped jobs in the nightly report. Both times the fix was manual and the same, "
        "throttle the tenant by hand and wait for the backlog to drain.\n\n"
        "## What counts as done\n\n"
        "- Producers can read a signal before enqueueing and slow themselves down\n"
        "- The signal is exported as a metric, so a throttle event is visible without a log "
        "dive\n"
        "- Workers shed load gracefully instead of dropping in-flight jobs on shutdown\n"
        "- The canary cluster runs a week with no manual throttling\n\n"
        "## Out of scope\n\n"
        "Per-tenant quotas. They are the obvious next step once producers can be told to wait, "
        "but they need a billing conversation we have not had yet, and the queue keeps dropping "
        "jobs in the meantime. Tracked separately so this work can ship without waiting on it."
    ),
    initiatives=("Platform reliability",),
    milestones=PROJECT_BACKPRESSURE.milestones,
    issues=(
        PI_RUN_501,
        PI_RUN_502,
        PI_RUN_511,
        PI_RUN_512,
        PI_RUN_513,
        PI_DAT_301,
        PI_DAT_305,
        PI_RUN_506,
        PI_RUN_514,
        PI_RUN_515,
        PI_RUN_516,
        PI_RUN_517,
        PI_RUN_518,
        PI_RUN_520,
        PI_RUN_521,
        PI_RUN_522,
        PI_RUN_524,
    ),
)

PI_DX_201 = _project_issue(
    "DX-201", ISSUE_DX_201.title, "In Progress", "started", "Medium", "Dana Okafor"
)
PI_DX_202 = _project_issue(
    "DX-202", ISSUE_DX_202.title, "In Review", "started", "No priority", "Dana Okafor"
)
PI_DX_203 = _project_issue("DX-203", ISSUE_DX_203.title, "Todo", "unstarted", "Low", "Dana Okafor")
PI_DX_205 = _project_issue(
    "DX-205",
    "Support a `--profile` flag for named config profiles",
    "Backlog",
    "backlog",
    "Low",
    "",
)
PI_DX_206 = _project_issue(
    "DX-206",
    "Explore a plugin API for third-party ferry subcommands",
    "Backlog",
    "backlog",
    "No priority",
    "Priya Nair",
)

PROJECT_DETAIL_CLI_V2 = ProjectDetail(
    description=(
        "The current CLI grew one flag at a time and now asks six questions before it does "
        "anything. This rewrite starts from the commands people actually run and works "
        "backward to the flags.\n\n"
        "Scope for v2:\n\n"
        "- A `ferry init` wizard that infers defaults from the repo instead of asking\n"
        "- Scriptable `--json` output on every subcommand\n"
        "- A single `ferry.toml` instead of three separate config files\n\n"
        "The CLI's `v1` command tree stays available behind `ferry legacy` during the "
        "migration."
    ),
    initiatives=(),
    milestones=PROJECT_CLI_V2.milestones,
    issues=(PI_DX_201, PI_DX_202, PI_DX_203, PI_DX_205, PI_DX_206),
)

PI_DAT_306 = _project_issue(
    "DAT-306",
    "Migrate the billing webhook caller off the relay",
    "Done",
    "completed",
    "Medium",
    "Felix Brandt",
)
PI_DAT_307 = _project_issue(
    "DAT-307",
    "Migrate the audit-log webhook caller off the relay",
    "Done",
    "completed",
    "Low",
    "Dana Okafor",
)
PI_DAT_308 = _project_issue(
    "DAT-308",
    "Decommission the relay's production hosts",
    "Done",
    "completed",
    "High",
    "Marcus Webb",
)
PI_DAT_309 = _project_issue(
    "DAT-309", "Archive the relay's Terraform module", "Done", "completed", "Medium", ""
)

PROJECT_DETAIL_WEBHOOK_RETIREMENT = ProjectDetail(
    description=(
        "The webhook relay was a standalone service that forwarded provider webhooks into "
        "Ferry before Ferry could ingest them directly. Ferry has supported direct ingestion "
        "since the platform release, so the relay had been redundant for a quarter.\n\n"
        "This project moved every remaining caller onto direct ingestion and decommissioned "
        "the relay hosts."
    ),
    initiatives=("Platform reliability",),
    milestones=PROJECT_WEBHOOK_RETIREMENT.milestones,
    issues=(PI_DAT_306, PI_DAT_307, PI_DAT_308, PI_DAT_309),
)

PI_RUN_503 = _project_issue(
    "RUN-503", ISSUE_RUN_503.title, "In Progress", "started", "Medium", "Dana Okafor"
)
PI_RUN_526 = _project_issue(
    "RUN-526",
    "Add per-zone scaling signal to the autoscaler config",
    "Todo",
    "unstarted",
    "Medium",
    "Dana Okafor",
    PI_RUN_503.id,
)
PI_RUN_527 = _project_issue(
    "RUN-527",
    "Load test the autoscaler against a simulated zone outage",
    "In Review",
    "started",
    "High",
    "Tomasz Kaczmarek",
    PI_RUN_503.id,
)
PI_RUN_528 = _project_issue(
    "RUN-528",
    "Consider bin-packing small jobs onto fewer nodes per zone",
    "Backlog",
    "backlog",
    "Low",
    "",
)
PI_RUN_529 = _project_issue(
    "RUN-529",
    "Add per-zone worker count to the capacity dashboard",
    "Done",
    "completed",
    "Medium",
    "Yuki Tanaka",
)

DETAIL_RUN_526 = _light_detail(
    "The autoscaler needs a per-zone queue-depth signal before it can size pools independently.",
    "Todo",
    "unstarted",
    "Medium",
    "Runtime",
    "Dana Okafor",
    "Yuki Tanaka",
    "Worker pool autoscaling",
    _days_ago(3),
)
DETAIL_RUN_527 = _light_detail(
    "Simulates one zone going fully unavailable to confirm the other pools absorb its "
    "traffic without over-scaling.",
    "In Review",
    "started",
    "High",
    "Runtime",
    "Tomasz Kaczmarek",
    "Yuki Tanaka",
    "Worker pool autoscaling",
    _days_ago(2),
)

PROJECT_DETAIL_WORKER_AUTOSCALING = ProjectDetail(
    description=(
        "Worker pools currently scale as one global pool sized for peak load across every "
        "zone, which means quiet zones pay for capacity they never use.\n\n"
        "This splits the pool per zone and scales each one against its own queue depth, using "
        "the same signal the backpressure work introduced."
    ),
    initiatives=("Platform reliability",),
    milestones=PROJECT_WORKER_AUTOSCALING.milestones,
    issues=(PI_RUN_503, PI_RUN_526, PI_RUN_527, PI_RUN_528, PI_RUN_529),
)

DETAILS: dict[str, Any] = {
    PROJECT_BACKPRESSURE.id: PROJECT_DETAIL_BACKPRESSURE,
    PROJECT_CLI_V2.id: PROJECT_DETAIL_CLI_V2,
    PROJECT_WEBHOOK_RETIREMENT.id: PROJECT_DETAIL_WEBHOOK_RETIREMENT,
    PROJECT_WORKER_AUTOSCALING.id: PROJECT_DETAIL_WORKER_AUTOSCALING,
    ISSUE_RUN_501.id: DETAIL_RUN_501,
    ISSUE_RUN_502.id: DETAIL_RUN_502,
    ISSUE_RUN_503.id: DETAIL_RUN_503,
    ISSUE_RUN_504.id: DETAIL_RUN_504,
    ISSUE_RUN_505.id: DETAIL_RUN_505,
    ISSUE_RUN_506.id: DETAIL_RUN_506,
    ISSUE_RUN_507.id: DETAIL_RUN_507,
    ISSUE_DX_201.id: DETAIL_DX_201,
    ISSUE_DX_202.id: DETAIL_DX_202,
    ISSUE_DX_203.id: DETAIL_DX_203,
    ISSUE_DX_204.id: DETAIL_DX_204,
    ISSUE_DAT_301.id: DETAIL_DAT_301,
    ISSUE_DAT_302.id: DETAIL_DAT_302,
    ISSUE_DAT_303.id: DETAIL_DAT_303,
    ISSUE_GRW_401.id: DETAIL_GRW_401,
    ISSUE_GRW_402.id: DETAIL_GRW_402,
    _PARENT_RUN_500.id: DETAIL_RUN_500,
    _SUB_RUN_508.id: DETAIL_RUN_508,
    _SUB_RUN_509.id: DETAIL_RUN_509,
    _BLOCKED_BY_DAT_304.id: DETAIL_DAT_304,
    _BLOCKS_RUN_510.id: DETAIL_RUN_510,
    _RELATED_GRW_403.id: DETAIL_GRW_403,
    PI_RUN_511.id: DETAIL_RUN_511,
    PI_RUN_512.id: DETAIL_RUN_512,
    PI_RUN_513.id: DETAIL_RUN_513,
    PI_DAT_305.id: DETAIL_DAT_305,
    PI_RUN_514.id: DETAIL_RUN_514,
    PI_RUN_515.id: DETAIL_RUN_515,
    PI_RUN_516.id: DETAIL_RUN_516,
    PI_RUN_517.id: DETAIL_RUN_517,
    PI_RUN_518.id: DETAIL_RUN_518,
    PI_RUN_526.id: DETAIL_RUN_526,
    PI_RUN_527.id: DETAIL_RUN_527,
}
