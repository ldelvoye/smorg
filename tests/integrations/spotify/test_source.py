"""Tests for the Spotify source: one player-state snapshot built from three GETs (plus a
graceful fourth, only for a playlist context).

No network: httpx.MockTransport routes each request to a recorded response by path.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from smorg.auth.store import Credentials
from smorg.core.contract import AccessNotAllowed, AuthExpired, Malformed, Unavailable
from smorg.integrations.spotify.source import (
    Album,
    Playlist,
    Track,
    fetch,
    next_repeat_mode,
    pause_playback,
    play_context,
    play_query,
    play_track,
    queue_query,
    queue_track,
    resume_playback,
    search,
    search_tracks,
    set_repeat,
    set_shuffle,
    skip_next,
    skip_previous,
)

FIXTURES = Path(__file__).parent / "fixtures"
PLAYER = json.loads((FIXTURES / "spotify_player.json").read_text())
QUEUE = json.loads((FIXTURES / "spotify_queue.json").read_text())
RECENTLY_PLAYED = json.loads((FIXTURES / "spotify_recently_played.json").read_text())
SEARCH = json.loads((FIXTURES / "spotify_search.json").read_text())
EMPTY_QUEUE = {"queue": []}
EMPTY_RECENTLY_PLAYED = {"items": []}
EMPTY_SEARCH = {"tracks": {"items": []}, "albums": {"items": []}, "playlists": {"items": []}}
TRACK_URI = "spotify:track:3n3Ppam7vgaVa1iaRUc9Lp"
ALBUM_URI = "spotify:album:1XkGORuUX2QGOEIL4EbJKm"
PLAYLIST_URI = "spotify:playlist:37i9dQZF1DX"

CREDENTIALS = Credentials(
    access_token="spotify-secret-token",
    refresh_token=None,
    expires_at=None,
    scope="user-read-currently-playing",
)


class _Server:
    """Recorded answers keyed by path, and a log of every request served. Player, queue, and
    recently-played all default to "nothing there yet" so a test only sets up what it needs.
    """

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._player: tuple[int, object | None] = (204, None)
        self._queue: tuple[int, object] = (200, EMPTY_QUEUE)
        self._recently_played: tuple[int, object] = (200, EMPTY_RECENTLY_PLAYED)
        self._playlists: dict[str, tuple[int, object]] = {}
        self._search: tuple[int, object] = (200, EMPTY_SEARCH)
        self._play: tuple[int, object | None] = (204, None)
        self._queue_write: tuple[int, object | None] = (204, None)
        self._shuffle: tuple[int, object | None] = (204, None)
        self._repeat: tuple[int, object | None] = (204, None)
        self._pause: tuple[int, object | None] = (204, None)
        self._resume: tuple[int, object | None] = (204, None)
        self._next: tuple[int, object | None] = (204, None)
        self._previous: tuple[int, object | None] = (204, None)

    def playing(self, payload: dict, status: int = 200) -> None:
        self._player = (status, payload)

    def nothing_playing(self) -> None:
        self._player = (204, None)

    def player_fails(self, status: int, payload: dict) -> None:
        self._player = (status, payload)

    def queued(self, payload: dict, status: int = 200) -> None:
        self._queue = (status, payload)

    def played(self, payload: dict, status: int = 200) -> None:
        self._recently_played = (status, payload)

    def playlist(self, playlist_id: str, payload: dict, status: int = 200) -> None:
        self._playlists[playlist_id] = (status, payload)

    def search_hits(self, payload: dict, status: int = 200) -> None:
        self._search = (status, payload)

    def play_result(self, status: int = 204, payload: object | None = None) -> None:
        self._play = (status, payload)

    def queue_write_result(self, status: int = 204, payload: object | None = None) -> None:
        self._queue_write = (status, payload)

    def shuffle_result(self, status: int = 204, payload: object | None = None) -> None:
        self._shuffle = (status, payload)

    def repeat_result(self, status: int = 204, payload: object | None = None) -> None:
        self._repeat = (status, payload)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/v1/me/player":
            status, payload = self._player
            if payload is None:
                return httpx.Response(status)
            return httpx.Response(status, json=payload)
        if path == "/v1/me/player/queue":
            if request.method == "POST":
                status, payload = self._queue_write
                if payload is None:
                    return httpx.Response(status)
                return httpx.Response(status, json=payload)
            status, payload = self._queue
            return httpx.Response(status, json=payload)
        if path == "/v1/me/player/play":
            if request.method == "PUT" and not request.content:
                status, payload = self._resume
            else:
                status, payload = self._play
            if payload is None:
                return httpx.Response(status)
            return httpx.Response(status, json=payload)
        if path == "/v1/me/player/pause":
            status, payload = self._pause
            if payload is None:
                return httpx.Response(status)
            return httpx.Response(status, json=payload)
        if path == "/v1/me/player/next":
            status, payload = self._next
            if payload is None:
                return httpx.Response(status)
            return httpx.Response(status, json=payload)
        if path == "/v1/me/player/previous":
            status, payload = self._previous
            if payload is None:
                return httpx.Response(status)
            return httpx.Response(status, json=payload)
        if path == "/v1/me/player/shuffle":
            status, payload = self._shuffle
            if payload is None:
                return httpx.Response(status)
            return httpx.Response(status, json=payload)
        if path == "/v1/me/player/repeat":
            status, payload = self._repeat
            if payload is None:
                return httpx.Response(status)
            return httpx.Response(status, json=payload)
        if path == "/v1/me/player/recently-played":
            status, payload = self._recently_played
            return httpx.Response(status, json=payload)
        if path == "/v1/search":
            status, payload = self._search
            return httpx.Response(status, json=payload)
        if path.startswith("/v1/playlists/"):
            playlist_id = path.rsplit("/", 1)[-1]
            if playlist_id not in self._playlists:
                raise AssertionError(f"no playlist response registered for {playlist_id}")
            status, payload = self._playlists[playlist_id]
            return httpx.Response(status, json=payload)
        raise AssertionError(f"unexpected request to {request.url}")


@pytest.fixture
def server() -> _Server:
    return _Server()


def fetch_with(server: _Server):
    http = httpx.Client(transport=httpx.MockTransport(server.handler))
    return fetch(CREDENTIALS, http)[0]


# --- Exactly one state, always ---


def test_fetch_returns_exactly_one_player_state(server):
    server.playing(PLAYER)
    result = fetch(CREDENTIALS, httpx.Client(transport=httpx.MockTransport(server.handler)))

    assert len(result) == 1


def test_nothing_playing_and_no_history_still_returns_one_idle_state(server):
    state = fetch_with(server)

    assert state.now_playing is None
    assert state.queue == ()
    assert state.last_played is None
    assert state.url == "https://open.spotify.com"


# --- What gets asked for ---


def test_a_full_snapshot_fetches_the_player_the_queue_and_recent_history(server):
    server.playing(PLAYER)
    server.queued(QUEUE)
    server.played(RECENTLY_PLAYED)

    fetch_with(server)

    paths = {request.url.path for request in server.requests}
    assert paths == {"/v1/me/player", "/v1/me/player/queue", "/v1/me/player/recently-played"}


# --- Now playing ---


def test_now_playing_carries_the_track_and_playback_state(server):
    server.playing(PLAYER)

    now_playing = fetch_with(server).now_playing

    assert now_playing is not None
    assert now_playing.track.track == "Mr. Brightside"
    assert now_playing.track.artists == ("The Killers",)
    assert now_playing.track.album == "Hot Fuss"
    assert now_playing.track.url == "https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp"
    assert now_playing.track.uri == TRACK_URI
    assert now_playing.is_playing is True


def test_fetch_carries_shuffle_and_repeat(server):
    server.playing(PLAYER | {"shuffle_state": True, "repeat_state": "context"})

    state = fetch_with(server)

    assert state.shuffle is True
    assert state.repeat == "context"


def test_the_state_id_and_url_reflect_the_now_playing_track(server):
    server.playing(PLAYER)

    state = fetch_with(server)

    assert state.id == "player"
    assert state.url == "https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp"


def test_a_204_response_means_nothing_is_playing(server):
    server.nothing_playing()

    state = fetch_with(server)

    assert state.now_playing is None
    assert state.url == "https://open.spotify.com"


def test_a_missing_is_playing_flag_degrades_to_true(server):
    payload = dict(PLAYER)
    del payload["is_playing"]
    server.playing(payload)

    now_playing = fetch_with(server).now_playing

    assert now_playing is not None
    assert now_playing.is_playing is True


def test_a_null_item_is_treated_as_nothing_playing(server):
    server.playing(PLAYER | {"item": None})

    assert fetch_with(server).now_playing is None


def test_an_episode_is_treated_as_nothing_playing(server):
    server.playing(PLAYER | {"currently_playing_type": "episode"})

    assert fetch_with(server).now_playing is None


# --- Context: what's driving playback ---


def test_a_null_context_reads_as_autoplay(server):
    server.playing(PLAYER | {"context": None})

    now_playing = fetch_with(server).now_playing

    assert now_playing is not None
    assert now_playing.context_kind == "autoplay"
    assert now_playing.context_name is None


def test_an_album_context_names_itself_from_the_track_with_no_extra_call(server):
    server.playing(PLAYER)

    now_playing = fetch_with(server).now_playing

    assert now_playing is not None
    assert now_playing.context_kind == "album"
    assert now_playing.context_name == "Hot Fuss"
    assert not any(request.url.path.startswith("/v1/playlists/") for request in server.requests)


def test_an_artist_context_names_itself_from_the_track_s_first_artist(server):
    artist_context = {"type": "artist", "uri": "spotify:artist:0C0XlULifJtAgn6ZNCW2eu"}
    server.playing(PLAYER | {"context": artist_context})

    now_playing = fetch_with(server).now_playing

    assert now_playing is not None
    assert now_playing.context_kind == "artist"
    assert now_playing.context_name == "The Killers"


def test_an_unrecognised_context_type_is_kept_verbatim_with_no_name(server):
    show_context = {"type": "show", "uri": "spotify:show:abc123"}
    server.playing(PLAYER | {"context": show_context})

    now_playing = fetch_with(server).now_playing

    assert now_playing is not None
    assert now_playing.context_kind == "show"
    assert now_playing.context_name is None


def test_a_playlist_context_resolves_its_name_from_a_second_call(server):
    playlist_context = {"type": "playlist", "uri": "spotify:playlist:37i9dQZF1xyz"}
    server.playing(PLAYER | {"context": playlist_context})
    server.playlist("37i9dQZF1xyz", {"name": "Friday Favorites"})

    now_playing = fetch_with(server).now_playing

    assert now_playing is not None
    assert now_playing.context_kind == "playlist"
    assert now_playing.context_name == "Friday Favorites"
    playlist_request = next(
        request for request in server.requests if request.url.path == "/v1/playlists/37i9dQZF1xyz"
    )
    assert playlist_request.url.params["fields"] == "name"


def test_a_failing_playlist_name_lookup_degrades_to_no_name_not_an_error(server):
    """A missing playlist name must not break the whole tab."""
    playlist_context = {"type": "playlist", "uri": "spotify:playlist:missing"}
    server.playing(PLAYER | {"context": playlist_context})
    server.playlist("missing", {"error": "not found"}, status=404)

    now_playing = fetch_with(server).now_playing

    assert now_playing is not None
    assert now_playing.context_kind == "playlist"
    assert now_playing.context_name is None


# --- The queue ---


def test_the_queue_is_parsed_in_order(server):
    server.playing(PLAYER)
    server.queued(QUEUE)

    queue = fetch_with(server).queue

    assert [track.track for track in queue] == ["Feel Good Inc.", "Take On Me"]
    assert queue[0].artists == ("Gorillaz", "De La Soul")


# --- Last played ---


def test_last_played_carries_the_track_and_when_it_played(server):
    server.playing(PLAYER)
    server.played(RECENTLY_PLAYED)

    last_played = fetch_with(server).last_played

    assert last_played is not None
    assert last_played.track.track == "Do I Wanna Know?"
    assert last_played.track.artists == ("Arctic Monkeys",)
    assert last_played.played_at == datetime(2026, 8, 20, 11, 30, tzinfo=UTC)


# --- Sanitization and url validity (shared helpers, exercised through the now-playing path) ---


def test_a_track_title_carrying_terminal_escapes_is_sanitised(server):
    hostile_item = PLAYER["item"] | {"name": "Mr\x1b[31m. Bright\x00side"}
    server.playing(PLAYER | {"item": hostile_item})

    now_playing = fetch_with(server).now_playing

    assert now_playing is not None
    assert "\x1b" not in now_playing.track.track
    assert "\x00" not in now_playing.track.track


def test_a_non_https_track_url_is_malformed(server):
    plain_http = {"spotify": "http://open.spotify.com/track/x"}
    hostile_item = PLAYER["item"] | {"external_urls": plain_http}
    server.playing(PLAYER | {"item": hostile_item})

    with pytest.raises(Malformed):
        fetch_with(server)


# --- Failures cross the seam as one of the four, from any of the three main calls ---


def test_a_rejected_token_on_the_player_call_is_auth_expired(server):
    server.player_fails(401, {"error": {"status": 401, "message": "The access token expired"}})

    with pytest.raises(AuthExpired):
        fetch_with(server)


def test_an_unallowlisted_account_on_the_player_call_is_access_not_allowed(server):
    message = "User not registered in the Developer Dashboard"
    server.player_fails(403, {"error": {"status": 403, "message": message}})

    with pytest.raises(AccessNotAllowed):
        fetch_with(server)


def test_spotify_being_down_on_the_player_call_is_unavailable(server):
    server.player_fails(500, {"error": {"status": 500, "message": "down"}})

    with pytest.raises(Unavailable):
        fetch_with(server)


def test_a_network_failure_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(Unavailable):
        fetch(CREDENTIALS, httpx.Client(transport=httpx.MockTransport(handler)))


def test_a_body_that_is_not_json_is_malformed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    with pytest.raises(Malformed):
        fetch(CREDENTIALS, httpx.Client(transport=httpx.MockTransport(handler)))


def test_a_failure_never_repeats_the_token(server):
    server.player_fails(401, {"error": {"status": 401}})

    with pytest.raises(AuthExpired) as raised:
        fetch_with(server)

    assert "spotify-secret-token" not in str(raised.value)


# --- Search, play, queue ---


def test_search_returns_the_first_hit(server):
    server.search_hits(SEARCH)
    http = httpx.Client(transport=httpx.MockTransport(server.handler))

    tracks = search_tracks(CREDENTIALS, http, "brightside")

    assert len(tracks) == 2
    assert tracks[0].track == "Mr. Brightside"
    assert tracks[0].uri == TRACK_URI
    assert server.requests[0].url.path == "/v1/search"
    assert server.requests[0].url.params["type"] == "track"
    assert server.requests[0].url.params["limit"] == "5"


def test_search_returns_songs_and_playlists(server):
    server.search_hits(SEARCH)
    http = httpx.Client(transport=httpx.MockTransport(server.handler))

    results = search(CREDENTIALS, http, "brightside")

    assert len(results.items) == 4
    first = results.items[0]
    second = results.items[1]
    third = results.items[2]
    assert isinstance(first, Track)
    assert first.track == "Mr. Brightside"
    assert isinstance(second, Album)
    assert second.name == "Hot Fuss"
    assert second.uri == ALBUM_URI
    assert isinstance(third, Playlist)
    assert third.name == "This Is The Killers"
    assert third.uri == PLAYLIST_URI
    assert server.requests[0].url.params["type"] == "track,album,playlist"


def test_search_skips_null_playlist_hits(server):
    server.search_hits(SEARCH)
    http = httpx.Client(transport=httpx.MockTransport(server.handler))

    results = search(CREDENTIALS, http, "brightside")

    assert all(getattr(item, "uri", None) for item in results.items)


def test_an_empty_search_query_is_malformed(server):
    http = httpx.Client(transport=httpx.MockTransport(server.handler))

    with pytest.raises(Malformed):
        search_tracks(CREDENTIALS, http, "   ")


def test_play_track_puts_the_uri(server):
    http = httpx.Client(transport=httpx.MockTransport(server.handler))

    play_track(CREDENTIALS, http, TRACK_URI)

    assert server.requests[0].method == "PUT"
    assert server.requests[0].url.path == "/v1/me/player/play"
    assert server.requests[0].content == b'{"uris":["spotify:track:3n3Ppam7vgaVa1iaRUc9Lp"]}'


def test_play_context_puts_the_playlist_uri(server):
    http = httpx.Client(transport=httpx.MockTransport(server.handler))

    play_context(CREDENTIALS, http, PLAYLIST_URI)

    assert server.requests[0].method == "PUT"
    assert server.requests[0].url.path == "/v1/me/player/play"
    assert server.requests[0].content == b'{"context_uri":"spotify:playlist:37i9dQZF1DX"}'


def test_queue_track_posts_the_uri(server):
    http = httpx.Client(transport=httpx.MockTransport(server.handler))

    queue_track(CREDENTIALS, http, TRACK_URI)

    assert server.requests[0].method == "POST"
    assert server.requests[0].url.path == "/v1/me/player/queue"
    assert server.requests[0].url.params["uri"] == TRACK_URI


def test_play_with_no_active_device_is_unavailable(server):
    server.play_result(404, {"error": {"status": 404, "message": "No active device"}})
    http = httpx.Client(transport=httpx.MockTransport(server.handler))

    with pytest.raises(Unavailable, match="no active Spotify device"):
        play_track(CREDENTIALS, http, TRACK_URI)


def test_play_query_searches_then_plays(server):
    server.search_hits(SEARCH)
    http = httpx.Client(transport=httpx.MockTransport(server.handler))

    track = play_query(CREDENTIALS, http, "brightside")

    assert track.uri == TRACK_URI
    paths = [request.url.path for request in server.requests]
    assert paths == ["/v1/search", "/v1/me/player/play"]


def test_queue_query_searches_then_queues(server):
    server.search_hits(SEARCH)
    http = httpx.Client(transport=httpx.MockTransport(server.handler))

    track = queue_query(CREDENTIALS, http, "brightside")

    assert track.uri == TRACK_URI
    paths = [request.url.path for request in server.requests]
    assert paths == ["/v1/search", "/v1/me/player/queue"]


def test_play_query_with_no_hits_is_unavailable(server):
    server.search_hits(EMPTY_SEARCH)
    http = httpx.Client(transport=httpx.MockTransport(server.handler))

    with pytest.raises(Unavailable, match="no tracks matched"):
        play_query(CREDENTIALS, http, "zzzz")


def test_set_shuffle_puts_the_state(server):
    http = httpx.Client(transport=httpx.MockTransport(server.handler))

    assert set_shuffle(CREDENTIALS, http, True) is True
    assert server.requests[0].method == "PUT"
    assert server.requests[0].url.path == "/v1/me/player/shuffle"
    assert server.requests[0].url.params["state"] == "true"


def test_set_repeat_puts_the_mode(server):
    http = httpx.Client(transport=httpx.MockTransport(server.handler))

    assert set_repeat(CREDENTIALS, http, "track") == "track"
    assert server.requests[0].method == "PUT"
    assert server.requests[0].url.path == "/v1/me/player/repeat"
    assert server.requests[0].url.params["state"] == "track"


def test_next_repeat_mode_cycles_off_context_track():
    assert next_repeat_mode("off") == "context"
    assert next_repeat_mode("context") == "track"
    assert next_repeat_mode("track") == "off"
    assert next_repeat_mode("weird") == "off"


def test_pause_and_resume_hit_the_player_endpoints(server):
    http = httpx.Client(transport=httpx.MockTransport(server.handler))

    pause_playback(CREDENTIALS, http)
    resume_playback(CREDENTIALS, http)

    assert [(request.method, request.url.path) for request in server.requests] == [
        ("PUT", "/v1/me/player/pause"),
        ("PUT", "/v1/me/player/play"),
    ]


def test_skip_next_and_previous_post(server):
    http = httpx.Client(transport=httpx.MockTransport(server.handler))

    skip_next(CREDENTIALS, http)
    skip_previous(CREDENTIALS, http)

    assert [(request.method, request.url.path) for request in server.requests] == [
        ("POST", "/v1/me/player/next"),
        ("POST", "/v1/me/player/previous"),
    ]
