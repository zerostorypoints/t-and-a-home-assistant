"""Network connectivity of the device."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import TAConfigEntry
from .entity import TAEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([TAConnectivity(entry.runtime_data)])


class TAConnectivity(TAEntity, BinarySensorEntity):
    """On while the device answers on the network, in standby too.

    Off means it is switched off at the mains, unplugged or not on the network.
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "network"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "network")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data and self.coordinator.data.reachable)
