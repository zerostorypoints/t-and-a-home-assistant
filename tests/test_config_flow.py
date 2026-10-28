"""Config flow tests."""

from __future__ import annotations

from dataclasses import replace
from ipaddress import ip_address
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ta_streaming.api import TAConnectionError, TAError
from custom_components.ta_streaming.const import CONF_MAX_VOLUME, DOMAIN

from .conftest import DEVICE, HOST, UNIQUE_ID

PROBE = "custom_components.ta_streaming.config_flow.async_probe"
SETUP = "custom_components.ta_streaming.async_setup_entry"

ZEROCONF = ZeroconfServiceInfo(
    ip_address=ip_address(HOST),
    ip_addresses=[ip_address(HOST)],
    hostname="stream1955ta-000000000000.local.",
    name=f"{UNIQUE_ID}._sues800device._tcp.local.",
    port=80,
    type="_sues800device._tcp.local.",
    properties={
        "name": "PSD3100HV-000000",
        "uuid": UNIQUE_ID,
        "manufacturer": "T+A",
        "ip": HOST,
    },
)


async def test_user_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with patch(PROBE, return_value=DEVICE), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": f" {HOST} "}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "PSD3100HV"
    assert result["data"] == {"host": HOST}
    assert result["result"].unique_id == UNIQUE_ID


async def test_user_flow_cannot_connect(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PROBE, side_effect=TAConnectionError("timeout")):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    with patch(PROBE, return_value=DEVICE), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_other_brand(hass: HomeAssistant) -> None:
    """A Hegel or Naim runs the same streaming module and answers the same API."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PROBE, return_value=replace(DEVICE, manufacturer="Hegel")):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "not_ta"}


async def test_user_flow_not_the_api(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PROBE, side_effect=TAError("no system member id")):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["errors"] == {"base": "not_ta"}


async def test_user_flow_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PROBE, return_value=DEVICE):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.168.1.99"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data["host"] == "192.168.1.99"


async def test_zeroconf_flow(hass: HomeAssistant) -> None:
    with patch(PROBE, return_value=DEVICE):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=ZEROCONF
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"host": HOST}


async def test_zeroconf_updates_host(hass: HomeAssistant) -> None:
    config_entry = MockConfigEntry(domain=DOMAIN, unique_id=UNIQUE_ID, data={"host": "10.0.0.2"})
    config_entry.add_to_hass(hass)
    probe = AsyncMock(return_value=DEVICE)
    with patch(PROBE, probe):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=ZEROCONF
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data["host"] == HOST
    probe.assert_not_called()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"address_changed_{config_entry.entry_id}")
    assert issue is not None
    assert issue.translation_placeholders == {
        "name": config_entry.title,
        "old_host": "10.0.0.2",
        "new_host": HOST,
    }


async def test_zeroconf_same_host_no_issue(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=ZEROCONF
    )
    assert result["reason"] == "already_configured"
    assert not ir.async_get(hass).issues


async def test_zeroconf_other_brand(hass: HomeAssistant) -> None:
    info = ZeroconfServiceInfo(
        ip_address=ZEROCONF.ip_address,
        ip_addresses=ZEROCONF.ip_addresses,
        hostname=ZEROCONF.hostname,
        name=ZEROCONF.name,
        port=80,
        type=ZEROCONF.type,
        properties={**ZEROCONF.properties, "manufacturer": "Hegel"},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=info
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_ta"


async def test_reconfigure(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    with patch(PROBE, return_value=DEVICE), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.168.1.77"}
        )
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data["host"] == "192.168.1.77"


async def test_reconfigure_wrong_device(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    with patch(PROBE, return_value=replace(DEVICE, unique_id="stream1955ta-other")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.168.1.77"}
        )
    assert result["reason"] == "wrong_device"
    assert config_entry.data["host"] == HOST


async def test_options_flow(
    hass: HomeAssistant, config_entry: MockConfigEntry, client, no_event_loop
) -> None:
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"]["zsp_url"].startswith("https://zerostorypoints.com/")
    assert result["description_placeholders"]["hifisync_url"].startswith("https://hifisync.com/")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MAX_VOLUME: 60}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_MAX_VOLUME: 60}
