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

- Add gh login auth method

- View diffs from `pushed branches`
- Enable creating PRs from `pushed branches` (need write access)
- Enable reviewing PRs (need write access)


### Spotify

- Allow users to add songs to playlists


## General capabilities

- Restricted write permissions (Spotify REMOTE actions ship ahead of this; the
  shell's credential-worker message is the seam to wrap)
- Enable drop-in self-coded plugins


## Patches

- Show update progress
