# Roadmap

## New integrations

- Claude Code stats (may require disk read permissions)
- Google Calendar
- Slack
- Sentry
- Datadog
- Notion
- GCP


## Existing integrations

### Github

- Add line change, CI status (+ which runs failed, if any), and show comment details
- Revamp pull request UI
- Add gh login auth method
- Per-panel refresh stages: report fetch stages to the panel (initial fetch included), shell
  indicator stays the default renderer; the loading takeover gains a live status line
  ("connecting…" / "waiting on GitHub…"), and integrations can own their refresh display


### Spotify

- `add to queue` and `play now` features


## General capabilities

- Restricted write permissions
- Enable drop-in self-coded plugins
- Homebrew download


## Deferred refactors

Filed by the stage-2 quality sweep (2026-08-25); each is its own PR-sized unit.

- github: split `source.py` — the list fetch, the GraphQL profile, and the five-request
  detail have outgrown one file, and the detail helpers no longer read in the order of the
  constructor they feed
- shell: extract the split detail pane out of the base `Panel` (a subclass or linear-owned)
  — only linear composes it, and the `query("#detail")` guards it now needs are
  transitional, not the design
- linear: adopt the theme-aware `StatusColors` and the shared hidden-line idiom the github
  tab introduced — two styling systems coexist across tabs today


## Patches

- Show update progress