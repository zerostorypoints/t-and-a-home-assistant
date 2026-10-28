"""Client for the web API of T+A HV streaming devices.

T+A's HV series streamers run a StreamUnlimited streaming module (read from a PSD 3100 HV,
firmware 1.14.0), the platform Hegel's streaming amplifiers use too. Its web server exposes:

    GET  /api/getData?path=<path>&roles=value         read a node
    GET  /api/getRows?path=<path>&roles=@all&from&to  read a list node
    POST /api/setData {"path", "role", "value"}       write a node (role "value")
                                                      or run an action (role "activate")
    POST /api/event/modifyQueue                       create or change an event queue
    GET  /api/event/pollQueue?queueId&timeout         long-poll the queue for changes

Values are typed: {"type": "i32_", "i32_": 35}. A list node may answer with no rows and a
"rowsRedirect" to the node that holds them.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

PATH_POWER = "powermanager:target"
PATH_POWER_ON = "powermanager:goOnline"
PATH_POWER_STANDBY = "powermanager:goNetworkStandby"
PATH_VOLUME = "player:volume"
PATH_MUTE = "settings:/mediaPlayer/mute"
PATH_PLAYER_DATA = "player:player/data"
PATH_PLAYER_CONTROL = "player:player/control"
PATH_PLAY_TIME = "player:player/data/playTime"
# Spotify Connect: on Hegel's amplifiers, which run the same module, "play" after a pause ends
# the Spotify session with "Directory is empty", while this action resumes it.
PATH_SPOTIFY_RESUME = "spotify:/ui/resume"
# airable internet radio. The service redirects to a device-specific host,
# e.g. airable:https://2880507696.airable.io/airable/radios. Its favourites are the stations
# added with "Add to Radio favorites".
PATH_RADIOS = "airable:linkService_airable.radios"
RADIO_FAVORITES_ID = "airable://airable.radios/directory/favorites"
PATH_MEMBER = "systemmanager:systemMember"
PATH_MODEL = "settings:/system/productName"
PATH_MANUFACTURER = "settings:/system/manufacturer"
PATH_DEVICE_NAME = "settings:/deviceName"
PATH_VERSION = "settings:/version"

# Paths whose changes are pushed through the event queue. The play time is not
# subscribed: it fires about four times a second.
EVENT_PATHS = (PATH_POWER, PATH_VOLUME, PATH_MUTE, PATH_PLAYER_DATA)

POWER_ONLINE = "online"
MAX_REDIRECTS = 3


class TAError(Exception):
    """Base error."""


class TAConnectionError(TAError):
    """The device did not answer."""


class TAQueueExpiredError(TAError):
    """The event queue is gone and has to be created again."""


def unwrap(value: Any) -> Any:
    """Return the payload of a typed value, e.g. 35 for {"type": "i32_", "i32_": 35}."""
    if isinstance(value, dict) and isinstance(value.get("type"), str):
        return value.get(value["type"], value)
    return value


@dataclass(slots=True)
class TADeviceInfo:
    """Static facts about the device."""

    unique_id: str
    name: str
    model: str
    manufacturer: str
    firmware: str | None


@dataclass(slots=True)
class TAState:
    """Current state of the device."""

    reachable: bool = False
    power: str | None = None
    volume: int | None = None
    muted: bool | None = None
    player: dict[str, Any] = field(default_factory=dict)
    play_time_ms: int | None = None
    play_time_at: datetime | None = None

    @property
    def is_on(self) -> bool:
        """True when the device is reachable and not in standby."""
        return self.reachable and self.power == POWER_ONLINE

    def apply(self, path: str, value: Any) -> bool:
        """Apply a pushed or polled value. Return True when the path is known."""
        value = unwrap(value)
        if path == PATH_POWER:
            self.power = (value or {}).get("target") if isinstance(value, dict) else None
        elif path == PATH_VOLUME:
            self.volume = int(value) if value is not None else None
        elif path == PATH_MUTE:
            self.muted = bool(value) if value is not None else None
        elif path == PATH_PLAYER_DATA:
            self.player = value if isinstance(value, dict) else {}
        elif path == PATH_PLAY_TIME:
            self.play_time_ms = int(value) if value is not None else None
            self.play_time_at = datetime.now(UTC)
        else:
            return False
        return True


class TAClient:
    """Async client for one device."""

    def __init__(self, host: str, session: aiohttp.ClientSession, timeout: float = 5) -> None:
        self.host = host
        self._session = session
        self._timeout = timeout
        self._base = f"http://{host}"

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        timeout: float | None = None,
    ) -> Any:
        try:
            async with self._session.request(
                method,
                f"{self._base}{endpoint}",
                params=params,
                json=json,
                timeout=aiohttp.ClientTimeout(total=timeout or self._timeout),
            ) as resp:
                text = await resp.text()
                if resp.status == 400 and "queue" in text.lower():
                    raise TAQueueExpiredError(text)
                if resp.status >= 400:
                    raise TAError(f"{method} {endpoint} returned {resp.status}: {text[:200]}")
                return await resp.json(content_type=None) if text else None
        except (TimeoutError, aiohttp.ClientError) as err:
            raise TAConnectionError(f"{self.host} did not answer: {err}") from err

    async def get(self, path: str) -> Any:
        """Read the value of a node, unwrapped."""
        data = await self._request("GET", "/api/getData", params={"path": path, "roles": "value"})
        if isinstance(data, list):
            return unwrap(data[0]) if data else None
        if isinstance(data, dict) and "error" in data:
            raise TAError(data["error"].get("message", "API error"))
        return unwrap(data)

    async def get_rows(self, path: str, limit: int = 50) -> list[dict[str, Any]]:
        """Read the rows of a list node, following redirects."""
        for _ in range(MAX_REDIRECTS + 1):
            data = await self._request(
                "GET",
                "/api/getRows",
                params={"path": path, "roles": "@all", "from": 0, "to": limit},
            )
            data = data or {}
            if "error" in data:
                raise TAError(data["error"].get("message", "API error"))
            if data.get("rows") or not data.get("rowsRedirect"):
                return list(data.get("rows", []))
            path = data["rowsRedirect"]
        raise TAError(f"Too many redirects reading {path}")

    async def set_value(self, path: str, value: dict[str, Any]) -> None:
        """Write a typed value to a node."""
        await self._request(
            "POST", "/api/setData", json={"path": path, "role": "value", "value": value}
        )

    async def activate(self, path: str, value: dict[str, Any] | None = None) -> None:
        """Run an action node."""
        await self._request(
            "POST",
            "/api/setData",
            json={"path": path, "role": "activate", "value": value or {}},
        )

    # High-level calls

    async def get_device_info(self) -> TADeviceInfo:
        """Read identity and firmware."""
        member = await self.get(PATH_MEMBER)
        member = (member or {}).get("systemMember", member) if isinstance(member, dict) else {}
        unique_id = member.get("id")
        if not unique_id:
            raise TAError("Device did not report a system member id")
        model = await self._get_optional(PATH_MODEL)
        return TADeviceInfo(
            unique_id=unique_id,
            name=await self._get_optional(PATH_DEVICE_NAME) or member.get("name") or model or "T+A",
            model=model or member.get("name") or "T+A",
            manufacturer=await self._get_optional(PATH_MANUFACTURER) or "",
            firmware=await self._get_optional(PATH_VERSION),
        )

    async def _get_optional(self, path: str) -> Any:
        try:
            return await self.get(path)
        except TAConnectionError:
            raise
        except TAError:
            return None

    async def get_state(self) -> TAState:
        """Read the full state. Raises TAConnectionError when the device does not answer."""
        state = TAState(reachable=True)
        state.apply(PATH_POWER, await self.get(PATH_POWER))
        for path in (PATH_VOLUME, PATH_MUTE, PATH_PLAYER_DATA):
            state.apply(path, await self.get(path))
        if state.is_on:
            state.apply(PATH_PLAY_TIME, await self._get_optional(PATH_PLAY_TIME))
        return state

    async def power_on(self) -> None:
        await self.activate(PATH_POWER_ON)

    async def power_standby(self) -> None:
        await self.activate(PATH_POWER_STANDBY)

    async def set_volume(self, volume: int) -> None:
        await self.set_value(PATH_VOLUME, {"type": "i32_", "i32_": int(volume)})

    async def set_mute(self, mute: bool) -> None:
        await self.set_value(PATH_MUTE, {"type": "bool_", "bool_": bool(mute)})

    async def control(self, command: str) -> None:
        """Send a player command: play, pause, stop, next, previous."""
        await self.activate(PATH_PLAYER_CONTROL, {"control": command})

    async def spotify_resume(self) -> None:
        """Resume Spotify Connect playback."""
        await self.activate(PATH_SPOTIFY_RESUME)

    async def get_radio_favorites(self) -> dict[str, str]:
        """airable radio favourites as {station name: path}, in the device's order."""
        directory = next(
            (
                row
                for row in await self.get_rows(PATH_RADIOS)
                if row.get("id") == RADIO_FAVORITES_ID
            ),
            None,
        )
        if directory is None:
            return {}
        return {
            row["title"]: row["path"]
            for row in await self.get_rows(directory["path"])
            if row.get("title") and row.get("path")
        }

    async def play_radio(self, path: str) -> None:
        """Start a favourite station.

        A favourite is a container holding the playable station. The player takes only that
        station as the device lists it (on Hegel's amplifiers a row from the play history fails
        with "Playback Url is empty"), and a failed play stops what was playing, so nothing is
        sent without a station.
        """
        station = next(
            (row for row in await self.get_rows(path) if row.get("type") == "audio"), None
        )
        if station is None:
            raise TAError(f"No playable station at {path}")
        await self.activate(
            PATH_PLAYER_CONTROL,
            {"control": "play", "mediaRoles": station, "trackRoles": station, "index": 0},
        )

    # Events

    async def create_queue(self, paths: tuple[str, ...] = EVENT_PATHS) -> str:
        """Create an event queue subscribed to the given paths."""
        queue_id = await self._request(
            "POST",
            "/api/event/modifyQueue",
            json={
                "queueId": "",
                "subscribe": [{"path": p, "type": "itemWithValue"} for p in paths],
                "unsubscribe": [],
            },
        )
        if not isinstance(queue_id, str) or not queue_id:
            raise TAError(f"Unexpected queue id: {queue_id!r}")
        return queue_id

    async def poll_queue(self, queue_id: str, timeout: int = 25) -> list[dict[str, Any]]:
        """Wait up to `timeout` seconds for events."""
        events = await self._request(
            "GET",
            "/api/event/pollQueue",
            params={"queueId": queue_id, "timeout": timeout},
            timeout=timeout + 10,
        )
        return events if isinstance(events, list) else []


async def async_probe(host: str, session: aiohttp.ClientSession) -> TADeviceInfo:
    """Connect once and return the device info. Used by the config flow."""
    client = TAClient(host, session)
    async with asyncio.timeout(15):
        return await client.get_device_info()
