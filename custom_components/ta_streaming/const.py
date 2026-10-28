"""Constants for the T+A Streaming integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "ta_streaming"
MANUFACTURER: Final = "T+A"

CONF_DEVICE: Final = "device"
CONF_MAX_VOLUME: Final = "max_volume"
DEFAULT_MAX_VOLUME: Final = 100

# Full refresh as a safety net; changes arrive through the event queue in between.
SCAN_INTERVAL: Final = timedelta(seconds=30)
# How often to retry while the device does not answer.
RECONNECT_INTERVAL: Final = 10
EVENT_POLL_TIMEOUT: Final = 25
# Radio favourites change only when someone edits them in the T+A app.
FAVORITES_INTERVAL: Final = timedelta(minutes=5)
