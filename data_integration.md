# DATA acquisition workflow

See more at https://github.com/bluesky/tiled.

`ThermoMicroscope` saves real AutoScript acquisitions on the microscope side
and returns the registered Tiled key through Tango. `asyncroscopy/software/DATA.py`
is the Tango data device for registering those files with the Tiled HTTP server.

The save format is one HDF5 file per acquisition event. Each correlated output
is stored as a dataset in that file, with parsed AutoScript XML leaf metadata
written as HDF5 dataset attributes.

Typical dataset names are:

- `image` for single image acquisitions
- `images/HAADF`, `images/BF`, etc. for multi-detector STEM acquisitions
- `spectrum` for spectra
- `stem_data` for STEM data acquisitions

## Server startup

`scripts/run_servers.py` can configure the DATA device and start the Tiled HTTP
server during normal server startup:

```bash
uv run scripts/run_servers.py \
  --tiled-host 10.46.217.241 \
  --tiled-port 9091 \
  --save-path D:/microscopedata/tiled/ahoust17/2026_05_29_test/
```

If these flags are omitted, the script prompts for the same values, including
the acquisition path. The DATA device receives the configuration through
`ASYNCROSCOPY_TILED_URI` and `ASYNCROSCOPY_ACQUISITION_DIR`. Once
`asyncroscopy/data/default` is reachable, `run_servers.py` starts the Tiled HTTP
server as a tracked process so it appears in the startup summary and stops with
the other managed servers.

## Notebook setup

Connect to the DATA Tango device once at the beginning of a workflow. The
`save_path` directory should be visible to the Tiled HTTP server, and the
microscope device should have `data_device_address` set to this Tango device.
When the server was started through `run_servers.py`, notebooks only need to
read the existing configuration.

```python
import json
import tango

data = tango.DeviceProxy("asyncroscopy/data/default")
config = json.loads(data.get_config())
```

Acquire as usual, and treat the return value as the Tiled key:

```python
tiled_key = mic.acquire_scanned_image()
```

Each acquisition is registered explicitly when the file is written; there is no
background Tiled watcher.

## Server Roles

There are two data-related servers:

- `asyncroscopy/data/default` is the DATA Tango device server. It belongs to asyncroscopy and bridges notebooks or microscope devices to Tiled.
- `http://10.46.217.241:9091` is the Tiled HTTP data server. It indexes and serves files.

The DATA device is started with the other Tango devices. The Tiled HTTP server
can be started and tracked by `run_servers.py`, or it can already be running at
the configured URI.

## Direct Tiled access

We currently access the server in the notebook like this:

from tiled.client import from_uri

client = from_uri("http://10.46.217.241:9091")

list(client) # should print out some folders and files
