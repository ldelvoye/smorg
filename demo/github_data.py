"""Invented GitHub data for the demo harness: the same fictional team building Ferry."""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from typing import Any

from smorg.core.contract import Item, Newest
from smorg.integrations.github.source import (
    DAYS_PER_WEEK,
    PROFILE_ID,
    PUSHED_BRANCHES_ID,
    UNAVAILABLE_CHECKS,
    Category,
    CheckSummary,
    Comment,
    ContributionWeek,
    FileDiff,
    LineCounts,
    Profile,
    PullRequest,
    PullRequestDetail,
    PullRequestDiff,
    PushedBranch,
    PushedBranches,
    Reviewer,
    ReviewerState,
    diff_request_of,
)

NOW = datetime(2026, 9, 12, 16, 45, tzinfo=UTC)

_NO_COMMENTS: Newest[Comment] = Newest(items=(), hidden=0, hidden_is_lower_bound=False)

_ORG = "palisadehq"
_WEEK_COUNT = 53
_CONTRIBUTION_RNG = random.Random(20260912)
_WEEKDAY_WEIGHTS_WEEKEND = (35, 30, 20, 10, 5)
_WEEKDAY_WEIGHTS_WEEKDAY = (10, 20, 30, 25, 15)
_CONTRIBUTION_LEVELS = (0, 1, 2, 3, 4)


def _hours_ago(hours: int) -> datetime:
    return NOW - timedelta(hours=hours)


def _days_ago(days: int) -> datetime:
    return NOW - timedelta(days=days)


def _repository_url(repository: str, branch: str) -> str:
    return f"https://github.com/{repository}/tree/{branch}"


def _pull_request(
    repository: str,
    number: int,
    title: str,
    author: str,
    category: Category,
    updated_at: datetime,
) -> PullRequest:
    url = f"https://github.com/{repository}/pull/{number}"
    return PullRequest(
        id=f"{repository}#{number}",
        updated_at=updated_at,
        url=url,
        number=number,
        title=title,
        repository=repository,
        author=author,
        category=category,
    )


def _pushed_branch(
    repository: str, branch: str, headline: str, updated_at: datetime
) -> PushedBranch:
    return PushedBranch(
        id=f"{repository}:{branch}",
        updated_at=updated_at,
        url=_repository_url(repository, branch),
        repository=repository,
        branch=branch,
        headline=headline,
        compare_url=f"https://github.com/{repository}/pull/new/{branch}",
    )


def _sunday_on_or_before(day: date) -> date:
    days_since_sunday = (day.weekday() + 1) % 7
    return day - timedelta(days=days_since_sunday)


def _week_start(index: int, last_week_start: date) -> date:
    weeks_back = _WEEK_COUNT - 1 - index
    return last_week_start - timedelta(weeks=weeks_back)


def _weekday_level(weekday_index: int) -> int:
    if weekday_index in (0, 6):
        weights = _WEEKDAY_WEIGHTS_WEEKEND
    else:
        weights = _WEEKDAY_WEIGHTS_WEEKDAY
    chosen = _CONTRIBUTION_RNG.choices(_CONTRIBUTION_LEVELS, weights=weights, k=1)
    return chosen[0]


def _contribution_week(index: int, last_week_start: date) -> ContributionWeek:
    first_day = _week_start(index, last_week_start)
    levels: list[int] = []
    for weekday_index in range(DAYS_PER_WEEK):
        level = _weekday_level(weekday_index)
        levels.append(level)
    return ContributionWeek(first_day=first_day, levels=tuple(levels))


def _contribution_weeks() -> tuple[ContributionWeek, ...]:
    last_week_start = _sunday_on_or_before(NOW.date())
    weeks: list[ContributionWeek] = []
    for index in range(_WEEK_COUNT):
        weeks.append(_contribution_week(index, last_week_start))
    return tuple(weeks)


PROFILE = Profile(
    id=PROFILE_ID,
    updated_at=datetime(1970, 1, 1, tzinfo=UTC),
    url="https://github.com/dokafor",
    login="dokafor",
    total_contributions=1926,
    weeks=_contribution_weeks(),
)

_REPO_FERRY = f"{_ORG}/ferry"
_REPO_FERRY_CLI = f"{_ORG}/ferry-cli"
_REPO_FERRY_DOCS = f"{_ORG}/ferry-docs"
_REPO_INFRA_TOOLING = f"{_ORG}/infra-tooling"

PR_412 = _pull_request(
    _REPO_FERRY,
    412,
    "Add backpressure signal to the worker intake queue",
    "mwebb",
    Category.NEEDS_YOUR_REVIEW,
    _hours_ago(2),
)
PR_398 = _pull_request(
    _REPO_FERRY,
    398,
    "Track retry budget per job class instead of globally",
    "pnair",
    Category.NEEDS_TEAM_REVIEW,
    _hours_ago(6),
)
PR_450 = _pull_request(
    _REPO_FERRY_CLI,
    450,
    "Draft: interactive ferry init wizard",
    "dokafor",
    Category.DRAFT,
    _days_ago(1),
)
PR_440 = _pull_request(
    _REPO_FERRY,
    440,
    "Cache compiled DAG plans across worker restarts",
    "dokafor",
    Category.WAITING,
    _hours_ago(9),
)
PR_421 = _pull_request(
    _REPO_FERRY,
    421,
    "Fix flaky shutdown hook ordering in the supervisor",
    "dokafor",
    Category.NEEDS_ACTION,
    _hours_ago(3),
)
PR_405 = _pull_request(
    _REPO_FERRY_DOCS,
    405,
    "Document the new retry budget configuration knobs",
    "dokafor",
    Category.READY_TO_MERGE,
    _hours_ago(28),
)
PR_388 = _pull_request(
    _REPO_INFRA_TOOLING,
    388,
    "Bump the canary cluster node pool to n2-standard-8",
    "fbrandt",
    Category.NEEDS_YOUR_REVIEW,
    _hours_ago(5),
)
PR_460 = _pull_request(
    _REPO_FERRY,
    460,
    "Replace polling watcher with an inotify-based one on Linux",
    "ytanaka",
    Category.WAITING,
    _days_ago(1),
)
PR_470 = _pull_request(
    _REPO_FERRY,
    470,
    "Draft: spike a WASM sandbox for untrusted job code",
    "dokafor",
    Category.DRAFT,
    _days_ago(2),
)
PR_455 = _pull_request(
    _REPO_FERRY,
    455,
    "Trim the scheduler's per-tick allocation churn",
    "ekowalski",
    Category.READY_TO_MERGE,
    _hours_ago(8),
)

PUSHED_BRANCH_AFFINITY = _pushed_branch(
    _REPO_FERRY,
    "dokafor/spike-worker-affinity",
    "Spike: pin workers to zone-local queues",
    _hours_ago(14),
)
PUSHED_BRANCH_INIT_ORDER = _pushed_branch(
    _REPO_FERRY_CLI,
    "dokafor/fix-init-prompt-order",
    "Fix prompt ordering in the init wizard",
    _days_ago(1),
)
PUSHED_BRANCH_TERRAFORM = _pushed_branch(
    _REPO_INFRA_TOOLING,
    "dokafor/bump-terraform-provider",
    "Bump the google-beta provider to 5.42",
    _days_ago(2),
)
PUSHED_BRANCH_NOTES = _pushed_branch(
    _REPO_FERRY,
    "dokafor/notes-on-backpressure",
    "WIP notes on backpressure thresholds",
    _days_ago(3),
)
PUSHED_BRANCH_RETRY_PAGE = _pushed_branch(
    _REPO_FERRY_DOCS,
    "dokafor/draft-retry-budget-page",
    "Draft the retry budget config page",
    _days_ago(4),
)

PUSHED_BRANCHES = PushedBranches(
    id=PUSHED_BRANCHES_ID,
    updated_at=datetime(1970, 1, 1, tzinfo=UTC),
    url="https://github.com",
    branches=(
        PUSHED_BRANCH_AFFINITY,
        PUSHED_BRANCH_INIT_ORDER,
        PUSHED_BRANCH_TERRAFORM,
        PUSHED_BRANCH_NOTES,
        PUSHED_BRANCH_RETRY_PAGE,
    ),
)

ITEMS: tuple[Item, ...] = (
    PROFILE,
    PR_412,
    PR_398,
    PR_450,
    PR_440,
    PR_421,
    PR_405,
    PR_388,
    PR_460,
    PR_470,
    PR_455,
    PUSHED_BRANCHES,
)

DETAIL_PR_412 = PullRequestDetail(
    body=(
        "This teaches the intake queue to publish a backpressure signal once depth crosses "
        "the configured high-water mark, so producers can slow down before we start dropping "
        "jobs.\n\n"
        "Behavior:\n\n"
        "- Below `low_water_mark`: signal is `clear`\n"
        "- Between the two marks: signal is `warning`\n"
        "- At or above `high_water_mark`: signal is `throttle`\n\n"
        "Producers already poll `queue.Signal()` for the retry backoff, so this is additive "
        "and should not require a client bump."
    ),
    base="main",
    head="mwebb/backpressure-signal",
    reviewers=(
        Reviewer(name="dokafor", state=ReviewerState.REQUESTED, submitted_at=None),
        Reviewer(name="ekowalski", state=ReviewerState.LEFT_COMMENTS, submitted_at=_hours_ago(20)),
    ),
    comments=Newest(
        items=(
            Comment(
                author="ekowalski",
                submitted_at=_hours_ago(19),
                body=(
                    "Do we need a metric for how long a producer spends in `throttle` before "
                    "backing off? Seems useful for the canary dashboards."
                ),
            ),
        ),
        hidden=0,
        hidden_is_lower_bound=False,
    ),
    counts=LineCounts(additions=142, deletions=37, changed_files=6, commits=4),
    checks=CheckSummary(passed=9, failed=0, running=1, failed_names=()),
)

DETAIL_PR_398 = PullRequestDetail(
    body=(
        "Retry budget is currently one global counter shared by every job class, so a noisy "
        "class can exhaust the budget for everyone else.\n\n"
        "This moves the counter onto the `retry_budget` table, keyed by `(job_class, window)`, "
        "and reads the class's own remaining budget before scheduling a retry.\n\n"
        "The `retry_budget_backfill` script fills in history for classes that predate this "
        "table."
    ),
    base="main",
    head="pnair/per-class-retry-budget",
    reviewers=(
        Reviewer(name="#runtime-reviewers", state=ReviewerState.REQUESTED, submitted_at=None),
    ),
    comments=_NO_COMMENTS,
    counts=LineCounts(additions=210, deletions=64, changed_files=9, commits=6),
    checks=CheckSummary(passed=6, failed=0, running=3, failed_names=()),
)

DETAIL_PR_450 = PullRequestDetail(
    body=(
        "Early draft of a `ferry init` wizard that infers defaults from the repo instead of "
        "asking for them.\n\n"
        "Open questions:\n\n"
        "- Should `--json` output skip the wizard entirely and require flags?\n"
        "- Do we still need the `v1` prompt order behind `ferry legacy init`?"
    ),
    base="main",
    head="dokafor/init-wizard-draft",
    reviewers=(),
    comments=_NO_COMMENTS,
    counts=LineCounts(additions=88, deletions=5, changed_files=4, commits=2),
    checks=UNAVAILABLE_CHECKS,
)

DETAIL_PR_440 = PullRequestDetail(
    body=(
        "Compiled DAG plans are recomputed on every worker restart even though the source DAG "
        "has not changed.\n\n"
        "This caches the compiled plan on disk keyed by `dag_hash`, and invalidates the entry "
        "whenever the source DAG's checksum changes.\n\n"
        "Cold start on the benchmark worker drops from about 4s to under 400ms."
    ),
    base="main",
    head="dokafor/cache-compiled-dags",
    reviewers=(
        Reviewer(name="mwebb", state=ReviewerState.APPROVED, submitted_at=_hours_ago(5)),
        Reviewer(name="tkaczmarek", state=ReviewerState.REQUESTED, submitted_at=None),
    ),
    comments=Newest(
        items=(
            Comment(
                author="mwebb",
                submitted_at=_hours_ago(5),
                body=("LGTM once CI is green. Nice reduction in cold-start time on the benchmark."),
            ),
        ),
        hidden=0,
        hidden_is_lower_bound=False,
    ),
    counts=LineCounts(additions=176, deletions=52, changed_files=8, commits=5),
    checks=CheckSummary(passed=7, failed=0, running=4, failed_names=()),
)

DETAIL_PR_421 = PullRequestDetail(
    body=(
        "Under load, the supervisor sometimes runs `on_close` before `on_drain` finishes, "
        "which closes the queue connection while jobs are still draining.\n\n"
        "This orders the hooks explicitly instead of relying on registration order:\n\n"
        "- `on_drain` always runs to completion first\n"
        "- `on_close` only runs once `on_drain` returns\n\n"
        "Reproduced with `go test -race` under `internal/lifecycle`."
    ),
    base="main",
    head="dokafor/fix-shutdown-hook-order",
    reviewers=(
        Reviewer(name="ytanaka", state=ReviewerState.CHANGES_REQUESTED, submitted_at=_hours_ago(2)),
    ),
    comments=Newest(
        items=(
            Comment(
                author="ytanaka",
                submitted_at=_hours_ago(2),
                body=(
                    "The new ordering still races if `on_drain` panics before `on_close` "
                    "runs. Can we wrap it in a `recover`?"
                ),
            ),
        ),
        hidden=0,
        hidden_is_lower_bound=False,
    ),
    counts=LineCounts(additions=58, deletions=21, changed_files=3, commits=3),
    checks=CheckSummary(
        passed=5,
        failed=2,
        running=0,
        failed_names=("supervisor_shutdown_race_test", "integration/worker_lifecycle_test"),
    ),
)

DETAIL_PR_405 = PullRequestDetail(
    body=(
        "Adds a docs page for the retry budget configuration knobs shipped last week:\n\n"
        "- `retry_budget.window`\n"
        "- `retry_budget.per_class_default`\n"
        "- `retry_budget.overrides`\n\n"
        "Includes a worked example for tightening the budget on one noisy job class."
    ),
    base="main",
    head="dokafor/document-retry-budget",
    reviewers=(Reviewer(name="nreyes", state=ReviewerState.APPROVED, submitted_at=_hours_ago(22)),),
    comments=_NO_COMMENTS,
    counts=LineCounts(additions=64, deletions=3, changed_files=2, commits=1),
    checks=CheckSummary(passed=3, failed=0, running=0, failed_names=()),
)

DETAIL_PR_388 = PullRequestDetail(
    body=(
        "The canary cluster's node pool is undersized for the backpressure rollout's load "
        "test.\n\n"
        "Bumps `google_container_node_pool.canary` from `n2-standard-4` to `n2-standard-8`. "
        "No other clusters are affected."
    ),
    base="main",
    head="fbrandt/canary-node-pool-bump",
    reviewers=(Reviewer(name="dokafor", state=ReviewerState.REQUESTED, submitted_at=None),),
    comments=_NO_COMMENTS,
    counts=LineCounts(additions=14, deletions=14, changed_files=1, commits=1),
    checks=CheckSummary(passed=4, failed=0, running=0, failed_names=()),
)

DETAIL_PR_460 = PullRequestDetail(
    body=(
        "Config reloads currently poll the filesystem every five seconds, which makes local "
        "development feel sluggish.\n\n"
        "Switches to an inotify-based watcher on Linux, falling back to the existing poller "
        "everywhere else."
    ),
    base="main",
    head="ytanaka/inotify-watcher",
    reviewers=(
        Reviewer(name="dokafor", state=ReviewerState.LEFT_COMMENTS, submitted_at=_hours_ago(26)),
        Reviewer(name="swhitfield", state=ReviewerState.REQUESTED, submitted_at=None),
    ),
    comments=Newest(
        items=(
            Comment(
                author="dokafor",
                submitted_at=_hours_ago(26),
                body=(
                    "Does this fall back to polling on filesystems that don't support "
                    "inotify, like some network mounts?"
                ),
            ),
        ),
        hidden=0,
        hidden_is_lower_bound=False,
    ),
    counts=LineCounts(additions=131, deletions=48, changed_files=5, commits=4),
    checks=CheckSummary(passed=6, failed=0, running=2, failed_names=()),
)

DETAIL_PR_470 = PullRequestDetail(
    body=(
        "Exploratory spike for running untrusted job code inside a WASM sandbox instead of "
        "the shared process.\n\n"
        "Tradeoffs so far:\n\n"
        "- `wasmtime` starts fast enough for short jobs, host calls are the bottleneck\n"
        "- Filesystem access needs an explicit capability list per job\n"
        "- No answer yet for jobs that need a real network socket\n\n"
        "Not ready for review, mostly here so the numbers are visible."
    ),
    base="main",
    head="dokafor/wasm-sandbox-spike",
    reviewers=(),
    comments=_NO_COMMENTS,
    counts=LineCounts(additions=340, deletions=2, changed_files=11, commits=8),
    checks=UNAVAILABLE_CHECKS,
)

DETAIL_PR_455 = PullRequestDetail(
    body=(
        "The scheduler allocates a new slice on every tick to build the ready set.\n\n"
        "This reuses a pooled slice sized to the previous tick's ready count instead of "
        "allocating fresh each time.\n\n"
        "About 18% fewer allocations per tick on the synthetic load test, no change to the "
        "ready set's ordering."
    ),
    base="main",
    head="ekowalski/reduce-tick-allocations",
    reviewers=(
        Reviewer(name="mwebb", state=ReviewerState.APPROVED, submitted_at=_hours_ago(10)),
        Reviewer(name="pnair", state=ReviewerState.DISMISSED, submitted_at=_hours_ago(30)),
    ),
    comments=Newest(
        items=(
            Comment(
                author="mwebb",
                submitted_at=_hours_ago(9),
                body=(
                    "Benchmarks look great, about 18% fewer allocations per tick on the "
                    "synthetic load test."
                ),
            ),
        ),
        hidden=0,
        hidden_is_lower_bound=False,
    ),
    counts=LineCounts(additions=95, deletions=61, changed_files=4, commits=3),
    checks=CheckSummary(passed=8, failed=0, running=0, failed_names=()),
)

DIFF_PR_412 = PullRequestDiff(
    files=(
        FileDiff(
            path="services/scheduler/internal/queue/backpressure/producer_throttle_controller.go",
            previous_path="",
            additions=88,
            deletions=12,
            patch=(
                "@@ -10,6 +10,19 @@ func (q *Queue) Depth() int {\n"
                "     return q.depth\n"
                " }\n"
                " \n"
                "+func (q *Queue) Signal() BackpressureSignal {\n"
                "+\tif q.depth >= q.highWaterMark {\n"
                "+\t\treturn SignalThrottle\n"
                "+\t}\n"
                "+\tif q.depth >= q.lowWaterMark {\n"
                "+\t\treturn SignalWarning\n"
                "+\t}\n"
                "+\treturn SignalClear\n"
                "+}"
            ),
        ),
        FileDiff(
            path=(
                "services/scheduler/internal/queue/backpressure/"
                "producer_throttle_controller_test.go"
            ),
            previous_path="",
            additions=46,
            deletions=0,
            patch=(
                "@@ -0,0 +1,46 @@\n"
                "+package backpressure\n"
                "+\n"
                "+func TestSignalThresholds(t *testing.T) {\n"
                "+\tq := newTestQueue(100, 60)\n"
                "+\tq.depth = 40\n"
                "+\tassertSignal(t, q, SignalClear)\n"
                "+\tq.depth = 75\n"
                "+\tassertSignal(t, q, SignalWarning)\n"
                "+\tq.depth = 120\n"
                "+\tassertSignal(t, q, SignalThrottle)\n"
                "+}"
            ),
        ),
        FileDiff(
            path="docs/runbooks/queue-backpressure.md",
            previous_path="",
            additions=8,
            deletions=0,
            patch=(
                "@@ -0,0 +1,8 @@\n"
                "+# Queue backpressure\n"
                "+\n"
                "+`queue.Signal()` returns `clear`, `warning`, or `throttle` based on depth.\n"
                "+Producers should back off on `throttle` and resume normally on `clear`."
            ),
        ),
    ),
    truncated=False,
)

DIFF_PR_440 = PullRequestDiff(
    files=(
        FileDiff(
            path="services/scheduler/internal/plan/cache.go",
            previous_path="",
            additions=120,
            deletions=18,
            patch=(
                "@@ -1,5 +1,14 @@\n"
                " package plan\n"
                " \n"
                "+type diskCache struct {\n"
                "+\tdir string\n"
                "+}\n"
                "+\n"
                "+func (c *diskCache) Get(hash string) (*Compiled, bool) {\n"
                "+\treturn c.readEntry(hash)\n"
                "+}"
            ),
        ),
        FileDiff(
            path="services/scheduler/internal/plan/cache_test.go",
            previous_path="",
            additions=64,
            deletions=0,
            patch=(
                "@@ -0,0 +1,64 @@\n"
                "+package plan\n"
                "+\n"
                "+func TestCacheInvalidatesOnChecksumChange(t *testing.T) {\n"
                "+\tc := newTestCache(t)\n"
                '+\tc.Put("dag-1", checksum("a"), compiled)\n'
                '+\t_, ok := c.Get("dag-1")\n'
                "+\tassertTrue(t, ok)\n"
                "+}"
            ),
        ),
        FileDiff(
            path="services/scheduler/cmd/worker/main.go",
            previous_path="",
            additions=6,
            deletions=4,
            patch=(
                "@@ -22,7 +22,9 @@ func main() {\n"
                "-\tplan := compilePlan(dag)\n"
                "+\tcache := plan.NewDiskCache(cacheDir)\n"
                "+\tplan := cache.CompileOrLoad(dag)"
            ),
        ),
        FileDiff(
            path=(
                "services/scheduler/internal/plan/fixtures/"
                "large_dag_with_conditional_branches_and_retries.json"
            ),
            previous_path="",
            additions=210,
            deletions=0,
            patch='@@ -0,0 +1,210 @@\n+{\n+  "nodes": [\n+    { "id": "ingest" }\n+  ]\n+}',
        ),
    ),
    truncated=False,
)

DIFF_PR_421 = PullRequestDiff(
    files=(
        FileDiff(
            path="services/worker/internal/lifecycle/supervisor.go",
            previous_path="",
            additions=34,
            deletions=19,
            patch=(
                "@@ -40,12 +40,17 @@ func (s *Supervisor) Shutdown(ctx context.Context) {\n"
                "-\ts.onClose()\n"
                "-\ts.onDrain(ctx)\n"
                "+\ts.onDrain(ctx)\n"
                "+\ts.onClose()"
            ),
        ),
        FileDiff(
            path="services/worker/internal/lifecycle/supervisor_shutdown_race_test.go",
            previous_path="",
            additions=22,
            deletions=2,
            patch=(
                "@@ -5,7 +5,9 @@ func TestShutdownOrder(t *testing.T) {\n"
                "-\t// TODO: assert ordering\n"
                "+\torder := s.Shutdown(context.Background())\n"
                '+\tassertEqual(t, order, []string{"drain", "close"})'
            ),
        ),
        FileDiff(
            path="services/worker/internal/lifecycle/hooks.go",
            previous_path="",
            additions=2,
            deletions=0,
            patch=(
                "@@ -1,3 +1,5 @@\n"
                " type Hook func(ctx context.Context) error\n"
                "+\n"
                '+var ErrHookPanic = errors.New("hook panicked")'
            ),
        ),
    ),
    truncated=False,
)

DETAILS: dict[str, Any] = {
    PR_412.id: DETAIL_PR_412,
    PR_398.id: DETAIL_PR_398,
    PR_450.id: DETAIL_PR_450,
    PR_440.id: DETAIL_PR_440,
    PR_421.id: DETAIL_PR_421,
    PR_405.id: DETAIL_PR_405,
    PR_388.id: DETAIL_PR_388,
    PR_460.id: DETAIL_PR_460,
    PR_470.id: DETAIL_PR_470,
    PR_455.id: DETAIL_PR_455,
    diff_request_of(PR_412).id: DIFF_PR_412,
    diff_request_of(PR_440).id: DIFF_PR_440,
    diff_request_of(PR_421).id: DIFF_PR_421,
}
