# T+A Streaming for Home Assistant

[![HACS custom repository](https://img.shields.io/badge/HACS-custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)
[![Validate](https://github.com/zerostorypoints/t-and-a-home-assistant/actions/workflows/validate.yml/badge.svg)](https://github.com/zerostorypoints/t-and-a-home-assistant/actions/workflows/validate.yml)
[![Tests](https://github.com/zerostorypoints/t-and-a-home-assistant/actions/workflows/tests.yml/badge.svg)](https://github.com/zerostorypoints/t-and-a-home-assistant/actions/workflows/tests.yml)

Control a T+A HV series streamer from Home Assistant over your local network: power, volume,
mute, playback, now playing and the stream format. No cloud and no account.

> **Limited testing.** The API calls this integration makes were tried on one device, a
> PSD 3100 HV, on one day, with Spotify Connect playing. Several features are written from the
> streaming module the T+A shares with Hegel's amplifiers and have never run against a T+A. See
> [What is tested](#what-is-tested), and please
> [report what works on yours](https://github.com/zerostorypoints/t-and-a-home-assistant/issues/new?template=model_report.yml).

> **Brought to you by [HiFiSync](https://hifisync.com/?utm_source=github&utm_medium=readme&utm_campaign=ta_streaming)**, the hi-fi
> recommendation engine grounded in physics, not opinions.
> Check how well your system fits your speakers before you buy the next piece.

---

## Features

- **Found automatically.** The streamer announces itself on the network; Home Assistant offers
  to add it. Entering the IP address by hand works too.
- **Instant updates** through the streaming module's event queue, with a full refresh every 30
  seconds as a safety net.
- **Power on and network standby** from Home Assistant, automations and voice assistants.
- **Volume and mute.**
- **Playback**: play, pause, stop, next, previous (next and previous while the player offers
  them; Spotify Connect on a PSD 3100 HV does), with title, artist, album, cover art, streaming
  service, track length and position. Play on a Spotify stream resumes the Spotify session.
- **Radio favourites.** Stations in the airable radio favourites appear in the source list.
  Selecting one starts it.
- **Stream format sensors**: audio quality (Hi-Res, CD quality, Lossless, Lossy, DSD), codec,
  sample rate, bit depth, bitrate, streaming service.
- **Clear off state.** Standby and "not responding" both show the streamer as off. A Network
  sensor tells them apart, and the entities stay usable after a restart even if the streamer is
  switched off at the mains.
- **Volume limit.** Set a maximum volume so a slipped slider on a phone can never drive the
  system to full power.
- English and Polish translations. Diagnostics download for bug reports.

Not included: the **physical inputs** (optical, coaxial, AES/EBU, BNC, analog, HDMI, Bluetooth,
USB DAC). T+A's own controller owns them, not the streaming module, and the module's API neither
reports which one is selected nor switches between them. While an input plays, the media player
shows the streamer as on with nothing playing.

## Supported devices

T+A's HV series streamers run a StreamUnlimited streaming module, the same platform as Hegel's
streaming amplifiers. They announce themselves over mDNS as `_sues800device._tcp` with
`manufacturer=T+A`, and answer the module's local web API on port 80.

| Model | Firmware | Status |
|---|---|---|
| PSD 3100 HV | 1.14.0 | Partly tested, see below |
| Other T+A devices with this streaming module | | Expected to work, not tested |

A quick check: if
`http://<streamer-address>/api/getData?path=settings:/system/manufacturer&roles=value` answers
with `T+A`, the streamer runs this module.

If you own one, please
[report whether it works](https://github.com/zerostorypoints/t-and-a-home-assistant/issues/new?template=model_report.yml),
including the features marked untested below.

### What is tested

Seen working on a PSD 3100 HV (firmware 1.14.0) on 2026-10-27, with Spotify Connect playing.
The reads and commands were the same API calls this integration makes, sent from a Home
Assistant configuration; this integration as a whole has not run against a T+A.

| Feature | Status |
|---|---|
| mDNS announcement (`_sues800device._tcp`, `manufacturer=T+A`) | Seen |
| Reading power state, volume, mute, now playing, play position | Seen |
| Spotify Connect: title, artist, album, cover art, duration, next and previous offered | Seen |
| Audio quality for Spotify (`Lossless`, from the `spotifyHifi` flag) | Seen |
| Pause | Tested |
| Play (Spotify, through `spotify:/ui/resume`) | Tested |
| Next track | Tested |
| Volume set, volume up | Tested |
| Event queue (instant updates) | Not tested: written from the Hegel H400; without it, changes show within 30 seconds |
| Turn on, turn off (network standby), and how standby is reported | Not tested |
| Mute | Not tested (the mute state was read, not changed) |
| Previous track, stop | Not tested |
| Radio favourites | Not tested: written from the Hegel H400 |
| Codec, sample rate, bit depth, bitrate; Tidal, Qobuz, AirPlay, UPnP | Not tested: Spotify reports none of these |
| Discovery and setup in Home Assistant, the device id | Not tested: the id is read as on the Hegel H400 (`systemmanager:systemMember`) |

The automated tests in this repository run against recorded answers, not a device.

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=zerostorypoints&repository=t-and-a-home-assistant&category=integration)

Or by hand:

1. HACS → ⋮ → **Custom repositories**.
2. Repository `https://github.com/zerostorypoints/t-and-a-home-assistant`, type **Integration**.
3. Install **T+A Streaming** and restart Home Assistant.

### Manual

Copy `custom_components/ta_streaming` into the `custom_components` folder of your Home Assistant
configuration and restart.

Requires Home Assistant 2025.8 or newer.

## Setup

After the restart, Home Assistant lists the streamer under Settings → Devices & services →
**Discovered**. Click **Add**.

If it is not discovered (for example when Home Assistant runs in a separate network or VLAN), go
to Settings → Devices & services → Add integration → **T+A Streaming** and enter the streamer's IP
address. Setup accepts T+A devices only: Hegel and Naim streamers answer the same API and have
their own integrations.

**Give the streamer a fixed address.** Reserve its IP in your router (a DHCP reservation or
static lease). If the address changes anyway, discovery picks up the new one by itself and Home
Assistant shows a notice under Settings → System → Repairs. Without discovery (another VLAN),
use **Reconfigure** on the integration.

The streamer must be powered at the mains.

## Entities

For a streamer named `PSD3100HV`:

| Entity | What it does |
|---|---|
| `media_player.psd3100hv` | Power, volume, mute, radio favourites (source), playback, now playing |
| `sensor.psd3100hv_audio_quality` | `Hi-Res`, `CD quality`, `Lossless`, `Lossy`, `DSD` while the streamer plays |
| `sensor.psd3100hv_codec` | As reported by the stream (Spotify reports none) |
| `sensor.psd3100hv_sample_rate` | kHz |
| `sensor.psd3100hv_bit_depth` | bit |
| `sensor.psd3100hv_bitrate` | kbit/s |
| `sensor.psd3100hv_streaming_service` | e.g. `Spotify` |
| `binary_sensor.psd3100hv_network` | On while the streamer answers on the network, standby included |

### Off, standby and not responding

| Situation | Media player | Network |
|---|---|---|
| On | `on` / `playing` / `paused` / `buffering` | on |
| Network standby | `off` | on |
| Switched off at the mains, unplugged, network down | `off` | off |

Turning on from network standby is sent as the module's `powermanager:goOnline`, as on Hegel's
amplifiers; on a T+A it has not been tried. A streamer that does not answer cannot be woken over
the network; the turn-on action then says so.

### Radio favourites

Stations in the airable radio favourites are read while the streamer is on, at power on and
every five minutes, and form the source list. Selecting a station plays it. While a favourite
plays, the media player shows it as the current source. Untested on a T+A: if the streamer has
no airable radio, the source list stays empty.

### Stream format

The sensors have a value only while the streaming module plays or pauses, not on a physical
input. Spotify reports only that it is lossless, so codec, sample rate, bit depth and bitrate
stay empty for it.

## Options

Settings → Devices & services → T+A Streaming → **Configure**:

- **Maximum volume** (10–100, default 100). Home Assistant never sets the volume above it. The
  streamer's remote and knob are not limited. The API's scale is 0 to 100; the streamer's
  display shows 0 to 99.

## Examples

Dashboard card:

```yaml
type: media-control
entity: media_player.psd3100hv
```

Lower the volume in the evening:

```yaml
automation:
  - alias: T+A quieter at night
    triggers:
      - trigger: time
        at: "22:00:00"
    conditions:
      - condition: numeric_state
        entity_id: media_player.psd3100hv
        attribute: volume_level
        above: 0.3
    actions:
      - action: media_player.volume_set
        target:
          entity_id: media_player.psd3100hv
        data:
          volume_level: 0.3
```

Pause when the doorbell rings:

```yaml
automation:
  - alias: T+A pause on doorbell
    triggers:
      - trigger: state
        entity_id: binary_sensor.doorbell
        to: "on"
    conditions:
      - condition: state
        entity_id: media_player.psd3100hv
        state: playing
    actions:
      - action: media_player.media_pause
        target:
          entity_id: media_player.psd3100hv
```

## With DomoSenso

[DomoSenso](https://domosenso.org) is an open framework for building a home on Home Assistant
from tested components, made by the same team
([zerostorypoints/domosenso](https://github.com/zerostorypoints/domosenso) on GitHub). Its
`media` component feeds the music view of the DomoSenso Frame wall tablet from any media player
that meets its contract; it is tested with a Hegel H400 so far.

The catalog does not list a T+A yet, so a scan of your Home Assistant shows the streamer as
unmatched. DomoSenso's
[Integrate a device](https://github.com/zerostorypoints/domosenso/blob/main/docs/integrate-a-device.md)
guide adds one: point the `media` component at `media_player.<your streamer>` from this
integration.

## On HiFiSync

Components can be checked on HiFiSync before they go into a system: sourced specs, a comparison
with other models, and how well a streamer or amplifier fits your speakers. HiFiSync does not
list T+A yet; the brands it covers:
[brands on HiFiSync](https://hifisync.com/brands?utm_source=github&utm_medium=readme&utm_campaign=ta_streaming).

## Troubleshooting

- **Not discovered.** Discovery uses mDNS (`_sues800device._tcp`). It does not cross VLANs
  without an mDNS reflector. Add the streamer by IP address.
- **Shows off although it is on.** Open the quick-check address above from the Home Assistant
  host. If it does not answer, the network path is the problem.
- **Changes show only after up to 30 seconds.** The event queue does not work on your streamer;
  please open an issue with diagnostics.
- **Bug reports.** Download diagnostics from the device page and attach them to an
  [issue](https://github.com/zerostorypoints/t-and-a-home-assistant/issues). Debug logging:

  ```yaml
  logger:
    logs:
      custom_components.ta_streaming: debug
  ```

## Security

The streaming module's web API has no authentication: anything on your network can control it.
This integration only talks to the streamer on your local network. Keep it off networks you do
not trust.

## How it works

The integration uses the streaming module's local web API: `/api/getData`, `/api/getRows`,
`/api/setData` and the long-polling event queue under `/api/event`. A full refresh runs every 30
seconds as a safety net; changes arrive through the event queue in between.

T+A does not document this API. It was read from a PSD 3100 HV and from Hegel's amplifiers,
which run the same module; a firmware update may change it.

---

## About HiFiSync

[**HiFiSync**](https://hifisync.com/?utm_source=github&utm_medium=readme&utm_campaign=ta_streaming) is a hi-fi recommendation
engine that scores system synergy with physics instead of adjectives.

- **Match** — what fits the gear you already own.
- **Compare** — component A against component B, by the numbers.
- **Build** — a complete system from scratch in seven steps: topology, then a model for each slot.
- **Synergy score** — a deterministic readout of 21 physics-based checks across Signal, Room and
  Character, each one cited. No brand or dealer can buy a better score.
- **Sourced specs** — every spec links to a primary source, with manufacturer-confirmed and
  secondary data marked apart.
- **Built in Europe** — prices in local currencies and availability checked against EU
  distributors. A catalogue of 1,600+ components from 76 brands.

[Build your system on HiFiSync →](https://hifisync.com/?utm_source=github&utm_medium=readme&utm_campaign=ta_streaming)

## Credits

Made by [Zero Story Points](https://zerostorypoints.com), the team behind HiFiSync.

Not affiliated with or endorsed by T+A elektroakustik GmbH & Co. KG. T+A is a trademark of its
owner.

## License

[MIT](LICENSE)
