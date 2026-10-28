"""API client tests."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.ta_streaming.api import (
    TAClient,
    TAConnectionError,
    TAError,
    TAQueueExpiredError,
    TAState,
    unwrap,
)

BASE = "http://device"


def test_unwrap() -> None:
    assert unwrap({"type": "i32_", "i32_": 35}) == 35
    assert unwrap({"type": "bool_", "bool_": False}) is False
    assert unwrap(7) == 7


def test_state_apply() -> None:
    state = TAState(reachable=True)
    assert state.apply(
        "powermanager:target", {"powerTarget": {"target": "online"}, "type": "powerTarget"}
    )
    assert state.is_on
    assert state.apply("player:volume", {"type": "i32_", "i32_": 22})
    assert state.volume == 22
    assert not state.apply("unknown:path", 1)
    state.apply(
        "powermanager:target", {"powerTarget": {"target": "networkStandby"}, "type": "powerTarget"}
    )
    assert not state.is_on


def _answer(aioclient_mock: AiohttpClientMocker, path: str, value: object) -> None:
    aioclient_mock.get(f"{BASE}/api/getData", params={"path": path, "roles": "value"}, json=[value])


async def test_get_state(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    _answer(
        aioclient_mock,
        "powermanager:target",
        {"powerTarget": {"target": "online"}, "type": "powerTarget"},
    )
    _answer(aioclient_mock, "player:volume", {"type": "i32_", "i32_": 49})
    _answer(aioclient_mock, "settings:/mediaPlayer/mute", {"type": "bool_", "bool_": True})
    _answer(aioclient_mock, "player:player/data", {"state": "playing"})
    _answer(aioclient_mock, "player:player/data/playTime", {"type": "i64_", "i64_": 5000})

    session = async_get_clientsession(hass)
    state = await TAClient("device", session).get_state()
    assert state.is_on and state.volume == 49 and state.muted
    assert state.player == {"state": "playing"}
    assert state.play_time_ms == 5000


async def test_device_info(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    _answer(
        aioclient_mock,
        "systemmanager:systemMember",
        {"type": "systemMember", "systemMember": {"id": "stream1955ta-1", "name": "PSD3100HV"}},
    )
    _answer(aioclient_mock, "settings:/system/productName", {"type": "string_", "string_": "X"})
    _answer(aioclient_mock, "settings:/system/manufacturer", {"type": "string_", "string_": "T+A"})
    _answer(aioclient_mock, "settings:/deviceName", {"type": "string_", "string_": "Living"})
    aioclient_mock.get(
        f"{BASE}/api/getData",
        params={"path": "settings:/version", "roles": "value"},
        json={"error": {"message": "Node does not exist"}},
    )
    session = async_get_clientsession(hass)
    device = await TAClient("device", session).get_device_info()
    assert device.unique_id == "stream1955ta-1"
    assert device.name == "Living"
    assert device.model == "X"
    assert device.manufacturer == "T+A"
    assert device.firmware is None


async def test_timeout_is_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE}/api/getData", exc=TimeoutError())
    session = async_get_clientsession(hass)
    with pytest.raises(TAConnectionError):
        await TAClient("device", session).get("player:volume")


async def test_expired_queue(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{BASE}/api/event/pollQueue", status=400, text="Unknown queue id!")
    session = async_get_clientsession(hass)
    with pytest.raises(TAQueueExpiredError):
        await TAClient("device", session).poll_queue("{dead}", 1)


async def test_power_on_payload(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(f"{BASE}/api/setData", text="null")
    session = async_get_clientsession(hass)
    await TAClient("device", session).power_on()
    assert aioclient_mock.mock_calls[-1][2] == {
        "path": "powermanager:goOnline",
        "role": "activate",
        "value": {},
    }


async def test_volume_payload(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(f"{BASE}/api/setData", text="null")
    session = async_get_clientsession(hass)
    await TAClient("device", session).set_volume(45)
    assert aioclient_mock.mock_calls[-1][2] == {
        "path": "player:volume",
        "role": "value",
        "value": {"type": "i32_", "i32_": 45},
    }


RADIOS = "airable:https://1.airable.io/airable/radios"
FAVORITES = f"{RADIOS}/favorites"
FOLK = "airable:https://1.airable.io/id/airable/radio/3318728303536773"
FOLK_STATION = {
    "title": "Folk Radio",
    "type": "audio",
    "audioType": "audioBroadcast",
    "id": "airable://airable/radio/3318728303536773",
    "path": FOLK,
    "mediaData": {
        "metaData": {"serviceID": "airableRadios"},
        "resources": [{"mimeType": "audio/mpeg", "data": "https://1.airable.io/play/1"}],
    },
}


def _rows(aioclient_mock: AiohttpClientMocker, path: str, **answer: object) -> None:
    aioclient_mock.get(
        f"{BASE}/api/getRows",
        params={"path": path, "roles": "@all", "from": 0, "to": 50},
        json=answer,
    )


async def test_radio_favorites(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    _rows(aioclient_mock, "airable:linkService_airable.radios", rows=[], rowsRedirect=RADIOS)
    _rows(
        aioclient_mock,
        RADIOS,
        rows=[
            {"title": "History", "id": "airable://airable.radios/directory/history"},
            {
                "title": "Favorites",
                "id": "airable://airable.radios/directory/favorites",
                "path": FAVORITES,
            },
        ],
    )
    _rows(
        aioclient_mock,
        FAVORITES,
        rows=[
            {"title": "Folk Radio", "type": "container", "path": FOLK},
            {"title": "Radio 2050", "type": "container", "path": f"{FOLK}0"},
        ],
    )
    session = async_get_clientsession(hass)
    assert await TAClient("device", session).get_radio_favorites() == {
        "Folk Radio": FOLK,
        "Radio 2050": f"{FOLK}0",
    }


async def test_radio_favorites_without_airable(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    _rows(aioclient_mock, "airable:linkService_airable.radios", rows=[])
    session = async_get_clientsession(hass)
    assert await TAClient("device", session).get_radio_favorites() == {}


async def test_play_radio(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    _rows(aioclient_mock, FOLK, rows=[FOLK_STATION])
    aioclient_mock.post(f"{BASE}/api/setData", text="6")
    session = async_get_clientsession(hass)
    await TAClient("device", session).play_radio(FOLK)
    assert aioclient_mock.mock_calls[-1][2] == {
        "path": "player:player/control",
        "role": "activate",
        "value": {
            "control": "play",
            "mediaRoles": FOLK_STATION,
            "trackRoles": FOLK_STATION,
            "index": 0,
        },
    }


async def test_play_radio_sends_nothing_without_a_station(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    _rows(aioclient_mock, FOLK, rows=[{"title": "Folk Radio", "type": "container"}])
    session = async_get_clientsession(hass)
    with pytest.raises(TAError, match="No playable station"):
        await TAClient("device", session).play_radio(FOLK)
    assert all(call[0] == "GET" for call in aioclient_mock.mock_calls)


async def test_rows_error(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(
        f"{BASE}/api/getRows",
        json={"error": {"message": "Node at path 'x:' does not exist"}},
    )
    session = async_get_clientsession(hass)
    with pytest.raises(TAError, match="does not exist"):
        await TAClient("device", session).get_rows("x:")
