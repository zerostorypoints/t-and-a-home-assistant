"""Media player entity: power, volume, mute, radio favourites and playback."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import contextlib

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import TAError
from .const import CONF_MAX_VOLUME, DEFAULT_MAX_VOLUME, DOMAIN
from .coordinator import TAConfigEntry, TACoordinator
from .entity import TAEntity

PARALLEL_UPDATES = 1

PLAYER_STATES = {
    "playing": MediaPlayerState.PLAYING,
    "paused": MediaPlayerState.PAUSED,
    "buffering": MediaPlayerState.BUFFERING,
    "transitioning": MediaPlayerState.BUFFERING,
}

BASE_FEATURES = (
    MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
)
# Offered while the player offers them (its "controls"). The module spells next "next_" for
# some services (Spotify Connect on a PSD 3100 HV) and "next" for others.
SKIP_FEATURES = MediaPlayerEntityFeature.NEXT_TRACK | MediaPlayerEntityFeature.PREVIOUS_TRACK


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([TAMediaPlayer(entry.runtime_data)])


def _offers_skip(controls: object) -> bool:
    if not isinstance(controls, dict):
        return True
    return any(controls.get(key) for key in ("next", "next_", "previous"))


class TAMediaPlayer(TAEntity, MediaPlayerEntity):
    """The device."""

    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_media_image_remotely_accessible = False
    _attr_volume_step = 0.01
    _attr_supported_features = BASE_FEATURES | SKIP_FEATURES

    def __init__(self, coordinator: TACoordinator) -> None:
        super().__init__(coordinator)
        options = coordinator.config_entry.options
        self._max_volume = int(options.get(CONF_MAX_VOLUME, DEFAULT_MAX_VOLUME))
        self._update_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attrs()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        # A device that does not answer is shown as off, not unavailable.
        return self.coordinator.data is not None

    def _update_attrs(self) -> None:
        state = self.coordinator.data
        if state is None or not state.is_on:
            self._attr_state = MediaPlayerState.OFF
            self._attr_volume_level = None
            self._attr_is_volume_muted = None
            self._attr_source = None
            self._attr_source_list = None
            self._clear_media()
            return

        self._attr_source_list = list(self.coordinator.radio_favorites) or None
        self._attr_source = self._playing_favorite(state.player)
        self._attr_volume_level = state.volume / 100 if state.volume is not None else None
        self._attr_is_volume_muted = state.muted

        player = state.player
        self._attr_state = PLAYER_STATES.get(player.get("state"), MediaPlayerState.ON)
        self._attr_supported_features = BASE_FEATURES | (
            SKIP_FEATURES if _offers_skip(player.get("controls")) else MediaPlayerEntityFeature(0)
        )
        track = player.get("trackRoles") or {}
        if not track.get("title"):
            self._clear_media()
            return
        meta = (track.get("mediaData") or {}).get("metaData") or {}
        self._attr_media_content_type = MediaType.MUSIC
        self._attr_media_title = track.get("title")
        self._attr_media_artist = meta.get("artist")
        self._attr_media_album_name = meta.get("album")
        icon = track.get("icon")
        # A "skin:" icon is the module's own, not a URL.
        self._attr_media_image_url = icon if isinstance(icon, str) and "://" in icon else None
        self._attr_app_name = meta.get("serviceName") or (player.get("mediaRoles") or {}).get(
            "title"
        )
        duration = (player.get("status") or {}).get("duration")
        self._attr_media_duration = round(duration / 1000) if duration else None
        if state.play_time_ms is not None:
            self._attr_media_position = round(state.play_time_ms / 1000)
            self._attr_media_position_updated_at = state.play_time_at
        else:
            self._attr_media_position = None
            self._attr_media_position_updated_at = None

    def _playing_favorite(self, player: dict) -> str | None:
        """The favourite station being played, matched by the path it is played from."""
        path = (player.get("mediaRoles") or {}).get("path")
        if not path or player.get("state") not in PLAYER_STATES:
            return None
        return next(
            (name for name, fav in self.coordinator.radio_favorites.items() if fav == path), None
        )

    def _clear_media(self) -> None:
        self._attr_media_content_type = None
        self._attr_media_title = None
        self._attr_media_artist = None
        self._attr_media_album_name = None
        self._attr_media_image_url = None
        self._attr_app_name = None
        self._attr_media_duration = None
        self._attr_media_position = None
        self._attr_media_position_updated_at = None

    async def _call(self, func: Callable[[], Awaitable[None]], *, needs_on: bool = True) -> None:
        state = self.coordinator.data
        if state is None or not state.reachable:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_responding",
                translation_placeholders={"host": self.coordinator.client.host},
            )
        if needs_on and not state.is_on:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="turned_off")
        try:
            await func()
        except TAError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self._call(self.coordinator.client.power_on, needs_on=False)

    async def async_turn_off(self) -> None:
        await self._call(self.coordinator.client.power_standby, needs_on=False)

    async def async_set_volume_level(self, volume: float) -> None:
        level = min(round(volume * 100), self._max_volume)
        await self._call(lambda: self.coordinator.client.set_volume(level))

    async def async_volume_up(self) -> None:
        current = self.coordinator.data.volume or 0
        await self.async_set_volume_level((current + 1) / 100)

    async def async_volume_down(self) -> None:
        current = self.coordinator.data.volume or 0
        await self.async_set_volume_level(max(current - 1, 0) / 100)

    async def async_mute_volume(self, mute: bool) -> None:
        await self._call(lambda: self.coordinator.client.set_mute(mute))

    async def async_select_source(self, source: str) -> None:
        path = self.coordinator.radio_favorites.get(source)
        if path is None and self.coordinator.data and self.coordinator.data.is_on:
            # A station added since the last read, or a list not read yet right after power on.
            with contextlib.suppress(TAError):
                await self.coordinator.async_read_favorites(force=True)
            path = self.coordinator.radio_favorites.get(source)
        if path is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_source",
                translation_placeholders={"source": source},
            )
        await self._call(lambda: self.coordinator.client.play_radio(path))

    @property
    def _service_id(self) -> str | None:
        """The streaming service behind the current track, e.g. "spotify"."""
        player = self.coordinator.data.player if self.coordinator.data else {}
        for roles in ("trackRoles", "mediaRoles"):
            meta = ((player.get(roles) or {}).get("mediaData") or {}).get("metaData") or {}
            if meta.get("serviceID"):
                return meta["serviceID"]
        return None

    async def async_media_play(self) -> None:
        if self._service_id == "spotify":
            await self._call(self.coordinator.client.spotify_resume)
            return
        await self._call(lambda: self.coordinator.client.control("play"))

    async def async_media_pause(self) -> None:
        await self._call(lambda: self.coordinator.client.control("pause"))

    async def async_media_stop(self) -> None:
        await self._call(lambda: self.coordinator.client.control("stop"))

    async def async_media_next_track(self) -> None:
        await self._call(lambda: self.coordinator.client.control("next"))

    async def async_media_previous_track(self) -> None:
        await self._call(lambda: self.coordinator.client.control("previous"))
