# Running the servers (`run_servers.py`)

`scripts/run_servers.py` brings up the whole asyncroscopy stack in **Tango
database mode** from a single terminal: it clears stale processes, starts the
Tango database, registers every device, launches each device server, starts the
Tiled HTTP server, and finally starts the microscope (which depends on the
others). It is interactive — it asks a short list of questions with sensible
defaults, then stays running so you can use the servers.

## TL;DR

```bash
uv run scripts/run_servers.py            # real microscope (ThermoMicroscope), interactive prompts
uv run scripts/run_servers.py --microscope dt   # digital twin (DigitalTwin), interactive prompts

# Headless: start straight from a YAML config, no prompts (see "Configs" below)
uv run scripts/run_servers.py --yaml configs/Spectra300.yaml
uv run scripts/run_servers.py --yaml configs\ThinkPad-utkarsh-covalent-setup.yaml
uv run scripts/run_servers.py --yaml configs/Spectra300.yaml --microscope dt
```

- Press **Enter** at every prompt to accept the value in `[brackets]`.
- Leave the terminal **open** while you work. Press **Ctrl+C** to stop everything
  (it also stops the Tiled server it started).
- Then connect from a notebook with plain `DeviceProxy` calls — see
  [notebooks/02_Image_Acquisition.ipynb](../../notebooks/02_Image_Acquisition.ipynb).

## What it starts

| Order | Device(s) | Tango name |
|-------|-----------|------------|
| 1 | support devices | `asyncroscopy/{camera,corrector,data,eds,flucam,scan,stage}/default` |
| 2 | Tiled HTTP server | started via the `data` device |
| 3 | microscope (last, depends on the rest) | `asyncroscopy/microscope/default` |

The microscope is started last and given the addresses of the support devices as
database properties, so it can find them via `DeviceProxy`. In `real` mode it
also receives the AutoScript host/port.

## Configs (`--yaml`)

The script's startup values — which devices to launch, the microscope class, and
the hosts/ports/paths — live in a YAML file under [configs/](../../configs). Two
ship today:

| File | For |
|------|-----|
| [configs/Spectra300.yaml](../../configs/Spectra300.yaml) | The real Spectra 300 (the default config). |
| [configs/ThinkPad-utkarsh-covalent-setup.yaml](../../configs/ThinkPad-utkarsh-covalent-setup.yaml) | A localhost-everywhere setup for local testing. |

Each file has a `microscope:` block (real) and an optional `digital_twin:` block;
`--microscope {real,dt}` chooses between them. Device `class_name` defaults to the
key upper-cased (`scan` → `SCAN`). A `microscope.host`/`port` becomes the
microscope's `autoscript_host_ip`/`_port`. The `mcp:` block is reserved — the
script does not start MCP yet.

**Two ways to run:**

- **Interactive** (no `--yaml`): the bundled default config seeds the prompt
  defaults; you confirm or override each at the prompt.
- **Headless** (`--yaml <file>`): no prompts — the file is the single source of
  truth (clear/start-DB/register all run; Tiled follows `tiled.autostart`). This
  is the path the GUI will use.

To make your own, copy `Spectra300.yaml` and edit the hosts/ports/devices.

## The prompts

Used only in interactive mode (no `--yaml`). Answered top to bottom; the defaults
shown come from the active config (`configs/Spectra300.yaml` unless overridden).

| Prompt | Default | What it controls |
|--------|---------|------------------|
| Tango database host | `10.46.217.241` | `TANGO_HOST`. Use `localhost` for local dev. |
| Tango database port | `9094` | Database port. |
| Tiled HTTP host | from `ASYNCROSCOPY_TILED_URI`, else the DB host | Where Tiled serves. |
| Tiled HTTP port | `9091` | Tiled port. |
| Acquisition save path | `outputs/tiled_acquisitions` | Directory written and served by Tiled. |
| Start Tiled HTTP server | `Y` | Start Tiled, or skip if one already runs. |
| Clear old processes first | `Y` | Kill stale servers / free the ports before starting. |
| Start Tango database | `Y` | Start the DB, or attach to one already running. |
| Register devices | `Y` | Add device entries + microscope properties to the DB. |
| Device startup timeout (s) | `120` | How long to wait for each device to answer a ping. |
| AutoScript host IP / port | `10.46.217.241` / `9095` | `real` mode only — the microscope PC. Point at a simulator here. |

## The five stages

The run prints progress as five sections:

1. **Clearing old processes** — frees the database/Tiled ports and kills any
   leftover device servers (skipped if you answered no).
2. **Starting Tango database** — starts it and waits until it answers, or waits
   for an existing one.
3. **Registering devices** — writes each device into the DB and sets the
   microscope's `*_device_address` (and AutoScript) properties.
4. **Starting device servers** — launches the support devices, waits for each to
   ping, starts Tiled, then starts the microscope last.
5. **Startup summary** — prints `TANGO_HOST`, each server's PID and ready time,
   and the Tiled URI / serving path.

## When something goes wrong

- **Startup failed.** The script prints a **Debug output** block with each
  server's command, PID, return code, and captured stdout/stderr. Read the one
  that didn't come up — that's almost always the real error.
- **"address already in use" / DB won't start.** Re-run and answer **yes** to
  *Clear old processes first* (or a server from a previous run is still alive).
- **A device "did not become ready".** Increase *Device startup timeout*, or fix
  the underlying import/connection error shown in the debug block. In `real`
  mode this is often an unreachable AutoScript host — check VPN and the
  host/port you entered.
- **Tiled failed to start.** Check the save path is writable and the Tiled port
  is free; the failure message comes from the `data` device.

## `--debug`: per-server log files

By default each server's output is captured but only shown as a one-shot snapshot
*if startup fails*. Pass `--debug` to stream every server's output (stdout and
stderr merged) **live** to a per-device log file, so you can `tail` whichever
server is misbehaving while the stack runs:

```bash
uv run scripts/run_servers.py --debug
uv run scripts/run_servers.py --yaml configs/Spectra300.yaml --debug   # headless + logs
```

Each run gets its own timestamped folder, one file per device:

```
output_tango_devices_logs/2026-06-14_08-30-15/
  database.log
  scan.log
  camera.log
  ...
  microscope.log
```

The folder path is printed at startup (and again on failure). `output_tango_devices_logs/`
is git-ignored, so logs are never committed. Alternate configs as `.yaml` files
are supported — see [Configs](#configs---yaml) above.

## What it does under the hood (manual fallback)

The script automates the database-mode startup you would otherwise do by hand,
one terminal per server. Once the database is up and devices are registered
(stages 2–3, which have no standalone script — they live inside
`run_servers.py`), you can start or restart a **single** server in its own
terminal for debugging:

```bash
# Tango database (if not already running)
TANGO_HOST=localhost:9094 uv run python -m tango.databaseds.database 2

# One device server against the running DB (another terminal)
export TANGO_HOST=localhost:9094
uv run python -m asyncroscopy.hardware.SCAN scan_instance

# The microscope (another terminal)
export TANGO_HOST=localhost:9094
uv run python -m asyncroscopy.ThermoMicroscope microscope_instance

# Client side
export TANGO_HOST=localhost:9094
python -c "import tango; tango.DeviceProxy('asyncroscopy/scan/default')"
```

Running a server by hand requires its device to already be registered in the DB;
let `run_servers.py` do the registration once, then you can stop and relaunch any
individual server above. The conceptual workflow is the same in both cases:

```
Start Tango DB → Register devices → Start device servers → Connect via DeviceProxy
```

## Why database mode?

Running through the **Tango database** (rather than no-DB mode) buys us:

1. **Centralized device registry** — clients need only the *device name*; Tango
   resolves where the server runs.
2. **No manual port management** — clients don't track host/port per device.
3. **Deterministic startup** — DB → register → start servers → connect, exactly
   what `run_servers.py` automates.
4. **Device discovery** — query the DB for available devices, classes, servers:

   ```python
   import tango
   db = tango.Database()
   for d in db.get_device_name("*", "*"):   # all devices
       print(d)
   db.get_device_name("SCAN", "*")          # devices of one class
   db.get_class_list("*")                   # all classes
   db.get_server_list("*")                  # all servers
   ```

5. **Configuration via DB properties** — dependencies live in the database, not
   hardcoded (this is how the microscope learns its detector addresses):

   ```python
   db.put_device_property(MICRO_DEVICE, {"scan_device_address": [SCAN_DEVICE]})
   ```

6. **Distributed instruments** — servers can run on different machines; clients
   still connect by name.
7. **Scalable architecture** — higher-level devices orchestrate lower-level ones
   (microscope → detectors → acquisition).

✔ In practice the whole system is initialized by `run_servers.py` and then driven
from tools like **Jupyter notebooks** using simple `DeviceProxy` calls.
