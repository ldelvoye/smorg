"""Fetch a snapshot of Spotify playback (now playing, the queue, and the last play) from the
REST API and map it to one typed player state. Also owns play/queue mutations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from smorg.auth.store import Credentials, now
from smorg.core.contract import (
    AccessNotAllowed,
    AuthExpired,
    IntegrationError,
    Item,
    Malformed,
    Unavailable,
)
from smorg.core.shape import required_string, timestamp
from smorg.core.text import sanitize_line

PLAYER_ENDPOINT = "https://api.spotify.com/v1/me/player"
QUEUE_ENDPOINT = "https://api.spotify.com/v1/me/player/queue"
PLAY_ENDPOINT = "https://api.spotify.com/v1/me/player/play"
PAUSE_ENDPOINT = "https://api.spotify.com/v1/me/player/pause"
NEXT_ENDPOINT = "https://api.spotify.com/v1/me/player/next"
PREVIOUS_ENDPOINT = "https://api.spotify.com/v1/me/player/previous"
SHUFFLE_ENDPOINT = "https://api.spotify.com/v1/me/player/shuffle"
REPEAT_ENDPOINT = "https://api.spotify.com/v1/me/player/repeat"
RECENTLY_PLAYED_ENDPOINT = "https://api.spotify.com/v1/me/player/recently-played"
PLAYLISTS_ENDPOINT = "https://api.spotify.com/v1/playlists"
SEARCH_ENDPOINT = "https://api.spotify.com/v1/search"

LAST_PLAYED_LIMIT = 1
SEARCH_LIMIT = 5
REPEAT_MODES = ("off", "context", "track")

# Where "o" opens when nothing is loaded on the player at all.
FALLBACK_URL = "https://open.spotify.com"


@dataclass(frozen=True)
class Track:
    track: str
    artists: tuple[str, ...]
    album: str
    url: str
    uri: str


@dataclass(frozen=True)
class Playlist:
    name: str
    owner: str
    url: str
    uri: str


@dataclass(frozen=True)
class Album:
    name: str
    artists: tuple[str, ...]
    url: str
    uri: str


SearchItem = Track | Album | Playlist


@dataclass(frozen=True)
class SearchResults:
    """A flat, Spotify-style mix of hits (not grouped by type)."""

    items: tuple[SearchItem, ...]

    @property
    def tracks(self) -> tuple[Track, ...]:
        return tuple(item for item in self.items if isinstance(item, Track))


@dataclass(frozen=True)
class NowPlaying:
    track: Track
    is_playing: bool
    # "album" | "playlist" | "artist" | "autoplay" | any other context type, verbatim.
    context_kind: str
    # None when there is nothing to name (autoplay, or a name that could not be resolved).
    context_name: str | None


@dataclass(frozen=True)
class LastPlayed:
    track: Track
    played_at: datetime


@dataclass(frozen=True)
class PlayerState(Item):
    """The whole tab's data in one snapshot — there is exactly one player, not a list of them."""

    now_playing: NowPlaying | None
    queue: tuple[Track, ...]
    last_played: LastPlayed | None
    shuffle: bool
    # "off" | "context" | "track"
    repeat: str


@dataclass(frozen=True)
class _PlaybackSnapshot:
    now_playing: NowPlaying | None
    shuffle: bool
    repeat: str


def fetch(credentials: Credentials, http: httpx.Client) -> tuple[PlayerState, ...]:
    """The player's current snapshot: what's playing, what's queued, and what played last."""
    playback = _fetch_playback(credentials, http)
    queue = _fetch_queue(credentials, http)
    last_played = _fetch_last_played(credentials, http)

    if playback.now_playing is not None:
        url = playback.now_playing.track.url
    else:
        url = FALLBACK_URL

    state = PlayerState(
        id="player",
        updated_at=now(),
        url=url,
        now_playing=playback.now_playing,
        queue=queue,
        last_played=last_played,
        shuffle=playback.shuffle,
        repeat=playback.repeat,
    )
    return (state,)


def next_repeat_mode(current: str) -> str:
    """Cycle off → context → track → off."""
    try:
        index = REPEAT_MODES.index(current)
    except ValueError:
        return "off"
    return REPEAT_MODES[(index + 1) % len(REPEAT_MODES)]


def set_shuffle(credentials: Credentials, http: httpx.Client, enabled: bool) -> bool:
    """Set shuffle on the active device; returns the requested state."""
    if enabled:
        state = "true"
    else:
        state = "false"
    response = _request(
        credentials,
        http,
        "PUT",
        SHUFFLE_ENDPOINT,
        params={"state": state},
    )
    _require_mutation_ok(response)
    return enabled


def set_repeat(credentials: Credentials, http: httpx.Client, mode: str) -> str:
    """Set repeat on the active device; returns the requested mode."""
    if mode not in REPEAT_MODES:
        raise Malformed(f"unknown repeat mode {mode!r}")
    response = _request(
        credentials,
        http,
        "PUT",
        REPEAT_ENDPOINT,
        params={"state": mode},
    )
    _require_mutation_ok(response)
    return mode


def pause_playback(credentials: Credentials, http: httpx.Client) -> None:
    """Pause the active device."""
    response = _request(credentials, http, "PUT", PAUSE_ENDPOINT)
    _require_mutation_ok(response)


def resume_playback(credentials: Credentials, http: httpx.Client) -> None:
    """Resume playback on the active device."""
    response = _request(credentials, http, "PUT", PLAY_ENDPOINT)
    _require_mutation_ok(response)


def skip_next(credentials: Credentials, http: httpx.Client) -> None:
    """Skip to the next track on the active device."""
    response = _request(credentials, http, "POST", NEXT_ENDPOINT)
    _require_mutation_ok(response)


def skip_previous(credentials: Credentials, http: httpx.Client) -> None:
    """Skip to the previous track on the active device."""
    response = _request(credentials, http, "POST", PREVIOUS_ENDPOINT)
    _require_mutation_ok(response)


def search(
    credentials: Credentials,
    http: httpx.Client,
    query: str,
    *,
    tracks_only: bool = False,
) -> SearchResults:
    """Search hits matching query. Tracks only when queueing; otherwise songs, albums, and
    playlists interleaved into one flat list.
    """
    stripped = query.strip()
    if not stripped:
        raise Malformed("search query was empty")
    if tracks_only:
        type_param = "track"
    else:
        type_param = "track,album,playlist"
    response = _request(
        credentials,
        http,
        "GET",
        SEARCH_ENDPOINT,
        params={"q": stripped, "type": type_param, "limit": SEARCH_LIMIT},
    )
    _require_ok(response)
    payload = _json_object(response)
    tracks = _tracks_from_search(payload)
    if tracks_only:
        return SearchResults(items=tracks)
    albums = _albums_from_search(payload)
    playlists = _playlists_from_search(payload)
    return SearchResults(items=_interleave(tracks, albums, playlists))


def search_tracks(credentials: Credentials, http: httpx.Client, query: str) -> tuple[Track, ...]:
    """Tracks matching query, best match first. An empty query raises Malformed."""
    return search(credentials, http, query, tracks_only=True).tracks


def _interleave(*groups: tuple[SearchItem, ...]) -> tuple[SearchItem, ...]:
    """Round-robin across type buckets so the list feels mixed, not sectioned."""
    items: list[SearchItem] = []
    lengths = [len(group) for group in groups]
    if lengths:
        depth = max(lengths)
    else:
        depth = 0
    for index in range(depth):
        for group in groups:
            if index < len(group):
                items.append(group[index])
    return tuple(items)


def play_track(credentials: Credentials, http: httpx.Client, uri: str) -> None:
    """Start playing a track uri on the user's active device."""
    response = _request(
        credentials,
        http,
        "PUT",
        PLAY_ENDPOINT,
        json_body={"uris": [uri]},
    )
    _require_mutation_ok(response)


def play_context(credentials: Credentials, http: httpx.Client, uri: str) -> None:
    """Start playing a context uri (playlist, album, …) on the user's active device."""
    response = _request(
        credentials,
        http,
        "PUT",
        PLAY_ENDPOINT,
        json_body={"context_uri": uri},
    )
    _require_mutation_ok(response)


def queue_track(credentials: Credentials, http: httpx.Client, uri: str) -> None:
    """Append uri to the user's playback queue."""
    response = _request(
        credentials,
        http,
        "POST",
        QUEUE_ENDPOINT,
        params={"uri": uri},
    )
    _require_mutation_ok(response)


def play_query(credentials: Credentials, http: httpx.Client, query: str) -> Track:
    """Search for query and play the first track hit; returns that track."""
    track = _first_search_hit(credentials, http, query)
    play_track(credentials, http, track.uri)
    return track


def queue_query(credentials: Credentials, http: httpx.Client, query: str) -> Track:
    """Search for query and queue the first track hit; returns that track."""
    track = _first_search_hit(credentials, http, query)
    queue_track(credentials, http, track.uri)
    return track


def _first_search_hit(credentials: Credentials, http: httpx.Client, query: str) -> Track:
    tracks = search_tracks(credentials, http, query)
    if not tracks:
        raise Unavailable(f"no tracks matched {query.strip()!r}")
    return tracks[0]


def _tracks_from_search(payload: dict[str, Any]) -> tuple[Track, ...]:
    tracks_block = payload.get("tracks")
    if tracks_block is None:
        return ()
    if not isinstance(tracks_block, dict):
        raise Malformed("'tracks' was missing or not an object")
    raw_items = tracks_block.get("items")
    if not isinstance(raw_items, list):
        raise Malformed("'tracks.items' was missing or not a list")
    tracks: list[Track] = []
    for raw in raw_items:
        if raw is None:
            continue
        if not isinstance(raw, dict):
            raise Malformed(f"a search hit was {type(raw).__name__}, expected an object")
        tracks.append(_track_of(raw))
    return tuple(tracks)


def _playlists_from_search(payload: dict[str, Any]) -> tuple[Playlist, ...]:
    playlists_block = payload.get("playlists")
    if playlists_block is None:
        return ()
    if not isinstance(playlists_block, dict):
        raise Malformed("'playlists' was missing or not an object")
    raw_items = playlists_block.get("items")
    if not isinstance(raw_items, list):
        raise Malformed("'playlists.items' was missing or not a list")
    playlists: list[Playlist] = []
    for raw in raw_items:
        if raw is None:
            continue
        if not isinstance(raw, dict):
            raise Malformed(f"a playlist hit was {type(raw).__name__}, expected an object")
        playlists.append(_playlist_of(raw))
    return tuple(playlists)


def _albums_from_search(payload: dict[str, Any]) -> tuple[Album, ...]:
    albums_block = payload.get("albums")
    if albums_block is None:
        return ()
    if not isinstance(albums_block, dict):
        raise Malformed("'albums' was missing or not an object")
    raw_items = albums_block.get("items")
    if not isinstance(raw_items, list):
        raise Malformed("'albums.items' was missing or not a list")
    albums: list[Album] = []
    for raw in raw_items:
        if raw is None:
            continue
        if not isinstance(raw, dict):
            raise Malformed(f"an album hit was {type(raw).__name__}, expected an object")
        albums.append(_album_of(raw))
    return tuple(albums)


def _playlist_of(raw: dict[str, Any]) -> Playlist:
    owner = raw.get("owner")
    if not isinstance(owner, dict):
        raise Malformed(f"'owner' was {type(owner).__name__}, expected an object")
    return Playlist(
        name=sanitize_line(required_string(raw, "name")),
        owner=sanitize_line(required_string(owner, "display_name")),
        url=_external_spotify_url(raw, "playlist"),
        uri=_typed_uri(raw, "playlist"),
    )


def _album_of(raw: dict[str, Any]) -> Album:
    return Album(
        name=sanitize_line(required_string(raw, "name")),
        artists=_artists_of(raw),
        url=_external_spotify_url(raw, "album"),
        uri=_typed_uri(raw, "album"),
    )


def _typed_uri(raw: dict[str, Any], kind: str) -> str:
    prefix = f"spotify:{kind}:"
    uri = raw.get("uri")
    if isinstance(uri, str) and uri.startswith(prefix):
        return uri
    item_id = raw.get("id")
    if isinstance(item_id, str) and item_id:
        return f"{prefix}{item_id}"
    raise Malformed(f"a {kind} had no usable uri or id")


def _external_spotify_url(raw: dict[str, Any], kind: str) -> str:
    external_urls = raw.get("external_urls")
    if not isinstance(external_urls, dict):
        raise Malformed(f"'external_urls' was {type(external_urls).__name__}, expected an object")
    url = required_string(external_urls, "spotify")
    if urlsplit(url).scheme != "https":
        raise Malformed(f"a {kind}'s Spotify url was not https")
    return url


def _request(
    credentials: Credentials,
    http: httpx.Client,
    method: str,
    url: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> httpx.Response:
    try:
        response = http.request(
            method,
            url,
            params=params or {},
            json=json_body,
            headers={"Authorization": f"Bearer {credentials.access_token}"},
        )
    except httpx.HTTPError as error:
        raise Unavailable("could not reach Spotify") from error
    if response.status_code == 401:
        raise AuthExpired("Spotify rejected the stored token; it may have expired or been revoked")
    if response.status_code == 403:
        # A dev-mode Spotify app only serves users the developer added to its allowlist in the
        # dashboard; a 403 here usually means the connected account isn't on it.
        raise AccessNotAllowed(
            "Spotify refused access; the connected account may need to be added to the app's "
            "allowlist at the Spotify dashboard"
        )
    return response


def _require_ok(response: httpx.Response) -> None:
    if response.status_code != 200:
        raise Unavailable(f"Spotify returned HTTP {response.status_code}")


def _require_mutation_ok(response: httpx.Response) -> None:
    if response.status_code in {200, 204}:
        return
    if response.status_code == 404:
        raise Unavailable("no active Spotify device; open Spotify on a phone or computer first")
    raise Unavailable(f"Spotify returned HTTP {response.status_code}")


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise Malformed("Spotify returned a body that is not JSON") from error
    if not isinstance(payload, dict):
        raise Malformed(f"Spotify returned {type(payload).__name__}, expected an object")
    return payload


def _fetch_playback(credentials: Credentials, http: httpx.Client) -> _PlaybackSnapshot:
    response = _request(credentials, http, "GET", PLAYER_ENDPOINT)
    if response.status_code == 204:
        return _PlaybackSnapshot(now_playing=None, shuffle=False, repeat="off")
    _require_ok(response)
    payload = _json_object(response)
    return _PlaybackSnapshot(
        now_playing=_now_playing_of(payload, credentials, http),
        shuffle=_shuffle_of(payload),
        repeat=_repeat_of(payload),
    )


def _now_playing_of(
    payload: dict[str, Any], credentials: Credentials, http: httpx.Client
) -> NowPlaying | None:
    item = payload.get("item")
    if item is None or payload.get("currently_playing_type") != "track":
        return None
    if not isinstance(item, dict):
        raise Malformed(f"'item' was {type(item).__name__}, expected an object")
    track = _track_of(item)
    context_kind, context_name = _context_of(payload.get("context"), track, credentials, http)
    return NowPlaying(
        track=track,
        is_playing=_is_playing_of(payload),
        context_kind=context_kind,
        context_name=context_name,
    )


def _shuffle_of(payload: dict[str, Any]) -> bool:
    value = payload.get("shuffle_state")
    if isinstance(value, bool):
        return value
    return False


def _repeat_of(payload: dict[str, Any]) -> str:
    value = payload.get("repeat_state")
    if isinstance(value, str) and value in REPEAT_MODES:
        return value
    return "off"


def _is_playing_of(payload: dict[str, Any]) -> bool:
    value = payload.get("is_playing")
    if isinstance(value, bool):
        return value
    # A missing or oddly-typed flag is informational, not load-bearing: degrade to "playing"
    # rather than breaking the whole tab over it.
    return True


def _context_of(
    context: object, track: Track, credentials: Credentials, http: httpx.Client
) -> tuple[str, str | None]:
    if context is None:
        return "autoplay", None
    if not isinstance(context, dict):
        raise Malformed(f"'context' was {type(context).__name__}, expected an object or null")
    kind = sanitize_line(required_string(context, "type"))
    if kind == "album":
        return kind, track.album
    if kind == "artist":
        if track.artists:
            name = track.artists[0]
        else:
            name = None
        return kind, name
    if kind == "playlist":
        return kind, _playlist_name_of(context.get("uri"), credentials, http)
    return kind, None


def _playlist_name_of(uri: object, credentials: Credentials, http: httpx.Client) -> str | None:
    """The playlist's own name, or None on any failure — a missing name must not break the tab."""
    if not isinstance(uri, str) or ":" not in uri:
        return None
    playlist_id = uri.rsplit(":", 1)[-1]
    try:
        response = _request(
            credentials,
            http,
            "GET",
            f"{PLAYLISTS_ENDPOINT}/{playlist_id}",
            params={"fields": "name"},
        )
        _require_ok(response)
        name = required_string(_json_object(response), "name")
    except IntegrationError:
        return None
    return sanitize_line(name)


def _fetch_queue(credentials: Credentials, http: httpx.Client) -> tuple[Track, ...]:
    response = _request(credentials, http, "GET", QUEUE_ENDPOINT)
    _require_ok(response)
    payload = _json_object(response)
    raw_queue = payload.get("queue")
    if not isinstance(raw_queue, list):
        raise Malformed("'queue' was missing or not a list")
    tracks: list[Track] = []
    for raw in raw_queue:
        if not isinstance(raw, dict):
            raise Malformed(f"a queued track was {type(raw).__name__}, expected an object")
        tracks.append(_track_of(raw))
    return tuple(tracks)


def _fetch_last_played(credentials: Credentials, http: httpx.Client) -> LastPlayed | None:
    response = _request(
        credentials, http, "GET", RECENTLY_PLAYED_ENDPOINT, params={"limit": LAST_PLAYED_LIMIT}
    )
    _require_ok(response)
    payload = _json_object(response)
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise Malformed("'items' was missing or not a list")
    if not raw_items:
        return None
    raw = raw_items[0]
    if not isinstance(raw, dict):
        raise Malformed(f"a play was {type(raw).__name__}, expected an object")
    raw_track = raw.get("track")
    if not isinstance(raw_track, dict):
        raise Malformed(f"'track' was {type(raw_track).__name__}, expected an object")
    return LastPlayed(track=_track_of(raw_track), played_at=timestamp(raw, "played_at"))


def _track_of(raw: dict[str, Any]) -> Track:
    return Track(
        track=sanitize_line(required_string(raw, "name")),
        artists=_artists_of(raw),
        album=sanitize_line(_album_name(raw)),
        url=_track_url(raw),
        uri=_track_uri(raw),
    )


def _track_uri(track: dict[str, Any]) -> str:
    uri = track.get("uri")
    if isinstance(uri, str) and uri.startswith("spotify:track:"):
        return uri
    track_id = track.get("id")
    if isinstance(track_id, str) and track_id:
        return f"spotify:track:{track_id}"
    raise Malformed("a track had no usable uri or id")


def _track_url(track: dict[str, Any]) -> str:
    external_urls = track.get("external_urls")
    if not isinstance(external_urls, dict):
        raise Malformed(f"'external_urls' was {type(external_urls).__name__}, expected an object")
    url = required_string(external_urls, "spotify")
    if urlsplit(url).scheme != "https":
        raise Malformed("a track's Spotify url was not https")
    return url


def _artists_of(track: dict[str, Any]) -> tuple[str, ...]:
    artists = track.get("artists")
    if not isinstance(artists, list):
        raise Malformed(f"'artists' was {type(artists).__name__}, expected a list")
    names: list[str] = []
    for artist in artists:
        if not isinstance(artist, dict):
            raise Malformed(f"an artist was {type(artist).__name__}, expected an object")
        names.append(sanitize_line(required_string(artist, "name")))
    return tuple(names)


def _album_name(track: dict[str, Any]) -> str:
    album = track.get("album")
    if not isinstance(album, dict):
        raise Malformed(f"'album' was {type(album).__name__}, expected an object")
    return required_string(album, "name")
