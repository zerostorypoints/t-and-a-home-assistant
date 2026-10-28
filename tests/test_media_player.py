"""Media player, sensor and coordinator tests."""

from __future__ import annotations

import copy

from homeassistant.components.media_player import (
    ATTR_INPUT_SOURCE,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    DOMAIN as MP_DOMAIN,
    SERVICE_SELECT_SOURCE,
    MediaPlayerEntityFeature,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_MEDIA_NEXT_TRACK,
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_PLAY,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    SERVICE_VOLUME_MUTE,
    SERVICE_VOLUME_SET,
    SERVICE_VOLUME_UP,
    STATE_OFF,
    STATE_ON,
    STATE_PLAYING,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ta_streaming.api import TAConnectionError, TAError, TAState
from custom_components.ta_streaming.const import CONF_MAX_VOLUME

from .conftest import HOST, PLAYER_SPOTIFY, playing_state

PLAYER = "media_player.psd3100hv"


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_playing(hass: HomeAssistant, config_entry, client, no_event_loop) -> None:
    await setup(hass, config_entry)
    state = hass.states.get(PLAYER)
    assert state.state == STATE_PLAYING
    assert state.attributes["media_title"] == "Track title"
    assert state.attributes["media_artist"] == "Artist"
    assert state.attributes["app_name"] == "Spotify"
    assert state.attributes["entity_picture"]
    assert state.attributes["media_duration"] == 266
    assert state.attributes["media_position"] == 120
    assert state.attributes[ATTR_MEDIA_VOLUME_LEVEL] == 0.45
    # No radio favourites: no source list.
    assert "source_list" not in state.attributes
    assert hass.states.get("sensor.psd3100hv_audio_quality").state == "lossless"
    assert hass.states.get("sensor.psd3100hv_streaming_service").state == "Spotify"
    assert hass.states.get("binary_sensor.psd3100hv_network").state == STATE_ON


async def test_skin_icon_is_no_picture(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    player = copy.deepcopy(PLAYER_SPOTIFY)
    player["trackRoles"]["icon"] = "skin:iconAirplay"
    client.get_state.return_value = playing_state(player=player)
    await setup(hass, config_entry)
    assert "entity_picture" not in hass.states.get(PLAYER).attributes


async def test_standby_is_off(hass: HomeAssistant, config_entry, client, no_event_loop) -> None:
    client.get_state.return_value = TAState(reachable=True, power="networkStandby", volume=23)
    await setup(hass, config_entry)
    state = hass.states.get(PLAYER)
    assert state.state == STATE_OFF
    assert ATTR_MEDIA_VOLUME_LEVEL not in state.attributes
    assert hass.states.get("binary_sensor.psd3100hv_network").state == STATE_ON
    assert hass.states.get("sensor.psd3100hv_audio_quality").state == "unknown"

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            MP_DOMAIN,
            SERVICE_VOLUME_SET,
            {ATTR_ENTITY_ID: PLAYER, ATTR_MEDIA_VOLUME_LEVEL: 0.3},
            blocking=True,
        )
    await hass.services.async_call(
        MP_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: PLAYER}, blocking=True
    )
    client.power_on.assert_awaited_once()


async def test_not_responding_is_off(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    await setup(hass, config_entry)
    client.get_state.side_effect = TAConnectionError("timeout")
    await refresh(hass, config_entry)

    state = hass.states.get(PLAYER)
    assert state.state == STATE_OFF
    assert hass.states.get("binary_sensor.psd3100hv_network").state == STATE_OFF

    with pytest.raises(HomeAssistantError, match="not responding"):
        await hass.services.async_call(
            MP_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: PLAYER}, blocking=True
        )
    client.power_on.assert_not_awaited()

    client.get_state.side_effect = None
    await refresh(hass, config_entry)
    assert hass.states.get(PLAYER).state == STATE_PLAYING


async def test_setup_retries_when_not_responding(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    client.get_device_info.side_effect = TAConnectionError("timeout")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_starts_off_when_seen_before(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    await setup(hass, config_entry)
    assert config_entry.data["device"]["model"] == "PSD3100HV"
    assert await hass.config_entries.async_unload(config_entry.entry_id)

    client.get_device_info.side_effect = TAConnectionError("timeout")
    client.get_state.side_effect = TAConnectionError("timeout")
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(PLAYER).state == STATE_OFF
    assert hass.states.get("binary_sensor.psd3100hv_network").state == STATE_OFF


async def test_commands(hass: HomeAssistant, config_entry, client, no_event_loop) -> None:
    await setup(hass, config_entry)

    async def call(service: str, **data) -> None:
        await hass.services.async_call(
            MP_DOMAIN, service, {ATTR_ENTITY_ID: PLAYER, **data}, blocking=True
        )

    await call(SERVICE_VOLUME_SET, **{ATTR_MEDIA_VOLUME_LEVEL: 0.4})
    client.set_volume.assert_awaited_with(40)
    await call(SERVICE_VOLUME_UP)
    client.set_volume.assert_awaited_with(46)
    await call(SERVICE_VOLUME_MUTE, **{ATTR_MEDIA_VOLUME_MUTED: True})
    client.set_mute.assert_awaited_with(True)
    await call(SERVICE_MEDIA_PAUSE)
    client.control.assert_awaited_with("pause")
    await call(SERVICE_MEDIA_NEXT_TRACK)
    client.control.assert_awaited_with("next")
    await call(SERVICE_TURN_OFF)
    client.power_standby.assert_awaited_once()


async def test_command_rejected(hass: HomeAssistant, config_entry, client, no_event_loop) -> None:
    await setup(hass, config_entry)
    client.control.side_effect = TAError("Control is not supported")
    with pytest.raises(HomeAssistantError, match="Control is not supported"):
        await hass.services.async_call(
            MP_DOMAIN, SERVICE_MEDIA_NEXT_TRACK, {ATTR_ENTITY_ID: PLAYER}, blocking=True
        )


async def test_spotify_play_resumes(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    """Play on a Spotify stream goes through spotify:/ui/resume."""
    await setup(hass, config_entry)
    await hass.services.async_call(
        MP_DOMAIN, SERVICE_MEDIA_PLAY, {ATTR_ENTITY_ID: PLAYER}, blocking=True
    )
    client.spotify_resume.assert_awaited_once()
    client.control.assert_not_awaited()


async def test_play_other_services(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    player = copy.deepcopy(PLAYER_SPOTIFY)
    player["trackRoles"]["mediaData"]["metaData"]["serviceID"] = "tidal"
    client.get_state.return_value = playing_state(player=player)
    await setup(hass, config_entry)
    await hass.services.async_call(
        MP_DOMAIN, SERVICE_MEDIA_PLAY, {ATTR_ENTITY_ID: PLAYER}, blocking=True
    )
    client.control.assert_awaited_with("play")
    client.spotify_resume.assert_not_awaited()


async def test_skip_follows_the_player_controls(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    """Next and previous are offered only while the player offers them."""
    await setup(hass, config_entry)
    features = hass.states.get(PLAYER).attributes[ATTR_SUPPORTED_FEATURES]
    assert features & MediaPlayerEntityFeature.NEXT_TRACK
    assert features & MediaPlayerEntityFeature.PREVIOUS_TRACK

    player = copy.deepcopy(PLAYER_SPOTIFY)
    player["controls"] = {"pause": True}
    config_entry.runtime_data.async_set_updated_data(playing_state(player=player))
    await hass.async_block_till_done()
    features = hass.states.get(PLAYER).attributes[ATTR_SUPPORTED_FEATURES]
    assert not features & MediaPlayerEntityFeature.NEXT_TRACK
    assert not features & MediaPlayerEntityFeature.PREVIOUS_TRACK
    assert features & MediaPlayerEntityFeature.PAUSE


async def test_nothing_streaming(hass: HomeAssistant, config_entry, client, no_event_loop) -> None:
    client.get_state.return_value = playing_state(
        player={"state": "stopped", "trackRoles": {"mediaData": {"metaData": {}}}}
    )
    await setup(hass, config_entry)
    state = hass.states.get(PLAYER)
    assert state.state == STATE_ON
    assert "media_title" not in state.attributes
    assert hass.states.get("sensor.psd3100hv_audio_quality").state == "unknown"


async def test_volume_limit(hass: HomeAssistant, client, no_event_loop) -> None:
    entry = MockConfigEntry(
        domain="ta_streaming", unique_id="x", data={"host": HOST}, options={CONF_MAX_VOLUME: 60}
    )
    await setup(hass, entry)
    await hass.services.async_call(
        MP_DOMAIN,
        SERVICE_VOLUME_SET,
        {ATTR_ENTITY_ID: PLAYER, ATTR_MEDIA_VOLUME_LEVEL: 1.0},
        blocking=True,
    )
    client.set_volume.assert_awaited_with(60)


async def test_push_events(hass: HomeAssistant, config_entry, client, no_event_loop) -> None:
    await setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    client.get.return_value = 30_000

    await coordinator._async_handle_events(
        [
            {
                "path": "player:volume",
                "itemType": "update",
                "itemValue": {"type": "i32_", "i32_": 20},
            },
            {
                "path": "player:player/data",
                "itemType": "update",
                "itemValue": {**playing_state().player, "state": "paused"},
            },
        ]
    )
    await hass.async_block_till_done()
    state = hass.states.get(PLAYER)
    assert state.attributes[ATTR_MEDIA_VOLUME_LEVEL] == 0.2
    assert state.state == "paused"
    assert state.attributes["media_position"] == 30

    await coordinator._async_handle_events(
        [
            {
                "path": "powermanager:target",
                "itemType": "update",
                "itemValue": {"powerTarget": {"target": "networkStandby"}, "type": "powerTarget"},
            },
        ]
    )
    await hass.async_block_till_done()
    assert hass.states.get(PLAYER).state == STATE_OFF


FOLK = "airable:https://1.airable.io/id/airable/radio/3318728303536773"
RADIO_2050 = "airable:https://1.airable.io/id/airable/radio/1"


def radio_state(path: str = FOLK) -> TAState:
    """Playing an airable station (trimmed)."""
    player = {
        "state": "playing",
        "controls": {"next_": False, "previous": False},
        "mediaRoles": {"title": "Folk Radio", "path": path, "audioType": "audioBroadcast"},
        "trackRoles": {
            "title": "Song",
            "path": path,
            "mediaData": {"metaData": {"serviceName": "airable Radio"}},
        },
    }
    return playing_state(player=player)


async def test_radio_favorites(hass: HomeAssistant, config_entry, client, no_event_loop) -> None:
    """Favourite stations are the source list; selecting one plays it."""
    client.get_radio_favorites.return_value = {"Folk Radio": FOLK, "Radio 2050": RADIO_2050}
    client.get_state.return_value = radio_state()
    await setup(hass, config_entry)

    state = hass.states.get(PLAYER)
    assert state.attributes["source_list"] == ["Folk Radio", "Radio 2050"]
    assert state.attributes[ATTR_INPUT_SOURCE] == "Folk Radio"
    assert not state.attributes[ATTR_SUPPORTED_FEATURES] & MediaPlayerEntityFeature.NEXT_TRACK

    await hass.services.async_call(
        MP_DOMAIN,
        SERVICE_SELECT_SOURCE,
        {ATTR_ENTITY_ID: PLAYER, ATTR_INPUT_SOURCE: "Radio 2050"},
        blocking=True,
    )
    client.play_radio.assert_awaited_once_with(RADIO_2050)


async def test_radio_outside_favorites(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    client.get_radio_favorites.return_value = {"Radio 2050": RADIO_2050}
    client.get_state.return_value = radio_state()
    await setup(hass, config_entry)
    assert ATTR_INPUT_SOURCE not in hass.states.get(PLAYER).attributes


async def test_radio_favorites_read_sparingly(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    """The list is read once per FAVORITES_INTERVAL, again at power on, and kept on errors."""
    client.get_radio_favorites.return_value = {"Radio 2050": RADIO_2050}
    await setup(hass, config_entry)
    await refresh(hass, config_entry)
    assert client.get_radio_favorites.await_count == 1

    client.get_radio_favorites.side_effect = TAError("airable did not answer")
    await config_entry.runtime_data._async_handle_events(
        [
            {
                "path": "powermanager:target",
                "itemType": "update",
                "itemValue": {"powerTarget": {"target": "online"}, "type": "powerTarget"},
            },
        ]
    )
    await hass.async_block_till_done()
    assert client.get_radio_favorites.await_count == 2
    assert hass.states.get(PLAYER).state == STATE_PLAYING
    assert "Radio 2050" in hass.states.get(PLAYER).attributes["source_list"]


async def test_new_favorite_is_read_on_select(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    """A station added since the last read plays without waiting."""
    await setup(hass, config_entry)
    client.get_radio_favorites.return_value = {"Radio 2050": RADIO_2050}
    await hass.services.async_call(
        MP_DOMAIN,
        SERVICE_SELECT_SOURCE,
        {ATTR_ENTITY_ID: PLAYER, ATTR_INPUT_SOURCE: "Radio 2050"},
        blocking=True,
    )
    client.play_radio.assert_awaited_once_with(RADIO_2050)

    with pytest.raises(ServiceValidationError, match="Phono"):
        await hass.services.async_call(
            MP_DOMAIN,
            SERVICE_SELECT_SOURCE,
            {ATTR_ENTITY_ID: PLAYER, ATTR_INPUT_SOURCE: "Phono"},
            blocking=True,
        )


async def test_radio_favorites_not_read_in_standby(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    client.get_state.return_value = TAState(reachable=True, power="networkStandby")
    await setup(hass, config_entry)
    client.get_radio_favorites.assert_not_awaited()


async def test_diagnostics_and_unload(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    from custom_components.ta_streaming.diagnostics import async_get_config_entry_diagnostics

    await setup(hass, config_entry)
    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    assert diag["device"]["model"] == "PSD3100HV"
    assert diag["state"]["volume"] == 45

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_icons_file_matches_entities() -> None:
    """Every translation key has an icon, and no icon points at a missing entity."""
    import json
    from pathlib import Path

    from custom_components.ta_streaming.sensor import QUALITY_OPTIONS, SENSORS

    root = Path(__file__).parent.parent / "custom_components" / "ta_streaming"
    icons = json.loads((root / "icons.json").read_text())["entity"]
    assert set(icons["sensor"]) == {d.translation_key for d in SENSORS}
    assert set(icons["sensor"]["audio_quality"]["state"]) == set(QUALITY_OPTIONS)
    assert set(icons["binary_sensor"]) == {"network"}


async def test_translations_match() -> None:
    """The Polish file has every key the English one has."""
    import json
    from pathlib import Path

    root = Path(__file__).parent.parent / "custom_components" / "ta_streaming" / "translations"

    def keys(node: object, prefix: str = "") -> set[str]:
        if not isinstance(node, dict):
            return {prefix}
        return set().union(*(keys(v, f"{prefix}/{k}") for k, v in node.items()))

    en = json.loads((root / "en.json").read_text())
    pl = json.loads((root / "pl.json").read_text())
    assert keys(en) == keys(pl)
