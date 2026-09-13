"""Tests for the Spotify search results picker."""

from smorg.integrations.spotify.pickers import search_picker
from smorg.integrations.spotify.source import Album, Playlist, SearchResults, Track


def track(name: str = "Mr. Brightside") -> Track:
    return Track(
        track=name,
        artists=("The Killers",),
        album="Hot Fuss",
        url=f"https://open.spotify.com/track/{name}",
        uri=f"spotify:track:{name}",
    )


def album(name: str = "Hot Fuss") -> Album:
    return Album(
        name=name,
        artists=("The Killers",),
        url=f"https://open.spotify.com/album/{name}",
        uri=f"spotify:album:{name}",
    )


def playlist(name: str = "This Is The Killers") -> Playlist:
    return Playlist(
        name=name,
        owner="Spotify",
        url=f"https://open.spotify.com/playlist/{name}",
        uri=f"spotify:playlist:{name}",
    )


def test_play_picker_lists_a_flat_mix_without_section_headings():
    results = SearchResults(items=(track(), album(), playlist(), track("Take On Me")))

    picker = search_picker(results, for_queue=False)
    text = "\n".join(picker.content_lines())

    assert picker._title == "play now"
    assert "songs" not in text
    assert "albums" not in text
    assert "playlists" not in text
    assert "Mr. Brightside · The Killers · song" in text
    assert "Hot Fuss · The Killers · album" in text
    assert "This Is The Killers · Spotify · playlist" in text
    assert "Take On Me · The Killers · song" in text


def test_queue_picker_keeps_songs_only():
    results = SearchResults(items=(track(), album(), playlist()))

    picker = search_picker(results, for_queue=True)
    text = "\n".join(picker.content_lines())

    assert picker._title == "add to queue"
    assert "Mr. Brightside · The Killers · song" in text
    assert "Hot Fuss" not in text
    assert "This Is The Killers" not in text
