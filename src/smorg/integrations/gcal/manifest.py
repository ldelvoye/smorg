"""Google Calendar's declaration; connects with the OAuth app smorg registered itself, and reads
the REST API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import httpx

from smorg.auth.oauth import BundledProvider, OAuthMethod, ServerMetadata
from smorg.auth.store import Credentials
from smorg.core.contract import Action, ActionClass, AuthPath, Item, Manifest
from smorg.integrations.gcal.panel import CalendarPanel
from smorg.integrations.gcal.source import fetch

# The app lives in the Google Cloud project "smorg", owned by the maintainer. Google treats an
# installed app's secret as public; it still never reaches output.
CLIENT_ID = "REPLACE-ME.apps.googleusercontent.com"
CLIENT_SECRET = "REPLACE-ME"

METHOD = OAuthMethod(
    provider=BundledProvider(
        metadata=ServerMetadata(
            authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
            token_endpoint="https://oauth2.googleapis.com/token",
            revocation_endpoint="https://oauth2.googleapis.com/revoke",
        ),
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
    ),
    scopes=("https://www.googleapis.com/auth/calendar.readonly",),
)

MANIFEST = Manifest(
    id="gcal",
    display_name="Google Calendar",
    connections=(AuthPath(id="oauth", method=METHOD),),
    stale_after=timedelta(minutes=5),
    actions=(
        Action(
            id="open", label="Open in Google Calendar", key="o", action_class=ActionClass.LAUNCH
        ),
        Action(id="today", label="Jump to today", key="t", action_class=ActionClass.LOCAL),
    ),
    experimental=True,
)


@dataclass(frozen=True)
class CalendarIntegration:
    manifest: Manifest = MANIFEST
    panel_class: type[CalendarPanel] = CalendarPanel

    def fetch(self, credentials: Credentials, http: httpx.Client) -> tuple[Item, ...]:
        return fetch(credentials, http)


INTEGRATION = CalendarIntegration()
