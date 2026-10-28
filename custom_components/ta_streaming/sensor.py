"""Stream format sensors: quality, codec, sample rate, bit depth, bitrate, service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfDataRate, UnitOfFrequency
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import TAState
from .coordinator import TAConfigEntry
from .entity import TAEntity

PARALLEL_UPDATES = 0

QUALITY_OPTIONS = ["hi_res", "cd", "lossless", "lossy", "dsd"]


def _resource(state: TAState) -> dict[str, Any]:
    if not state.is_on or state.player.get("state") not in ("playing", "paused"):
        return {}
    track = state.player.get("trackRoles") or {}
    return (track.get("mediaData") or {}).get("activeResource") or {}


def quality(state: TAState) -> str | None:
    """Classify the stream: hi_res, cd, lossless, lossy or dsd."""
    res = _resource(state)
    if not res:
        return None
    codec = (res.get("codec") or "").lower()
    rate = res.get("sampleFrequency") or 0
    bits = res.get("bitsPerSample") or 0
    flags = res.get("quality") or {}
    if "dsd" in codec:
        return "dsd"
    if flags.get("qobuzHiRes") or bits > 16 or rate > 48000:
        return "hi_res"
    if bits == 16 and rate in (44100, 48000):
        return "cd"
    # Spotify reports no format, only this flag.
    if flags.get("spotifyHifi"):
        return "lossless"
    if codec:
        return "lossy"
    return None


def _service(state: TAState) -> str | None:
    if not state.is_on:
        return None
    meta = ((state.player.get("trackRoles") or {}).get("mediaData") or {}).get("metaData") or {}
    return meta.get("serviceName") or (state.player.get("mediaRoles") or {}).get("title")


def _number(key: str, scale: float = 1) -> Callable[[TAState], float | None]:
    def get(state: TAState) -> float | None:
        value = _resource(state).get(key)
        return round(value / scale, 1) if isinstance(value, (int, float)) and value else None

    return get


@dataclass(frozen=True, kw_only=True)
class TASensorDescription(SensorEntityDescription):
    value_fn: Callable[[TAState], Any]


SENSORS: tuple[TASensorDescription, ...] = (
    TASensorDescription(
        key="audio_quality",
        translation_key="audio_quality",
        device_class=SensorDeviceClass.ENUM,
        options=QUALITY_OPTIONS,
        value_fn=quality,
    ),
    TASensorDescription(
        key="codec",
        translation_key="codec",
        value_fn=lambda s: _resource(s).get("codec") or None,
    ),
    TASensorDescription(
        key="sample_rate",
        translation_key="sample_rate",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.KILOHERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_number("sampleFrequency", 1000),
    ),
    TASensorDescription(
        key="bit_depth",
        translation_key="bit_depth",
        native_unit_of_measurement="bit",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_number("bitsPerSample"),
    ),
    TASensorDescription(
        key="bitrate",
        translation_key="bitrate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_number("bitRate", 1000),
    ),
    TASensorDescription(
        key="streaming_service",
        translation_key="streaming_service",
        value_fn=_service,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(TASensor(entry.runtime_data, d) for d in SENSORS)


class TASensor(TAEntity, SensorEntity):
    entity_description: TASensorDescription

    def __init__(self, coordinator, description: TASensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
