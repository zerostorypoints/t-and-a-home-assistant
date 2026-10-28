"""Fixtures."""

from __future__ import annotations

from collections.abc import Generator
import copy
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ta_streaming.api import TADeviceInfo, TAState
from custom_components.ta_streaming.const import DOMAIN

HOST = "192.168.1.50"
UNIQUE_ID = "stream1955ta-00000000-1111-2222-3333-444444444444"

DEVICE = TADeviceInfo(
    unique_id=UNIQUE_ID,
    name="PSD3100HV",
    model="PSD3100HV",
    manufacturer="T+A",
    firmware="1.14.0.0",
)

# The shape of a PSD 3100 HV's player data while playing Spotify Connect: next and previous are
# offered (next spelled "next_"), the only quality field is spotifyHifi.
PLAYER_SPOTIFY: dict[str, Any] = {
    "state": "playing",
    "controls": {
        "pause": True,
        "next_": True,
        "previous": True,
        "seekTime": True,
        "playMode": True,
    },
    "mediaRoles": {"title": "Playlist"},
    "status": {"duration": 265546},
    "trackRoles": {
        "title": "Track title",
        "icon": "https://i.scdn.co/image/cover.jpg",
        "mediaData": {
            "activeResource": {"mimeType": "audio/unknown", "quality": {"spotifyHifi": True}},
            "metaData": {
                "album": "Album",
                "artist": "Artist",
                "serviceName": "Spotify",
                "serviceID": "spotify",
            },
        },
    },
}


def playing_state(**changes: Any) -> TAState:
    state = TAState(
        reachable=True,
        power="online",
        volume=45,
        muted=False,
        player=copy.deepcopy(PLAYER_SPOTIFY),
        play_time_ms=120_000,
    )
    for key, value in changes.items():
        setattr(state, key, value)
    return state


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components in every test."""


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN, title="PSD3100HV", unique_id=UNIQUE_ID, data={"host": HOST}
    )


@pytest.fixture
def client() -> Generator[AsyncMock]:
    """A TAClient mock, used by the integration setup."""
    with patch("custom_components.ta_streaming.TAClient", autospec=True) as cls:
        mock = cls.return_value
        mock.host = HOST
        mock.get_device_info.return_value = DEVICE
        mock.get_state.return_value = playing_state()
        mock.get_radio_favorites.return_value = {}
        yield mock


@pytest.fixture
def no_event_loop() -> Generator[None]:
    with patch(
        "custom_components.ta_streaming.coordinator.TACoordinator.async_run_event_loop",
        new=AsyncMock(return_value=None),
    ):
        yield
