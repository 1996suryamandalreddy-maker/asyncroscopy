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

## Notebook setup

Connect to the DATA Tango device once at the beginning of a workflow. The
`save_path` directory should be visible to the Tiled HTTP server, and the
microscope device should have `data_device_address` set to this Tango device.

```python
import json
import tango

data = tango.DeviceProxy("asyncroscopy/data/default")
data.host = "10.46.217.241"
data.port = 9091
data.save_path = "/path/served/by/tiled"
```

Acquire as usual, and treat the return value as the Tiled key:

```python
tiled_key = mic.acquire_scanned_image()
```

## Server Roles

There are two data-related servers:

- `asyncroscopy/data/default` is the DATA Tango device server. It belongs to asyncroscopy and bridges notebooks or microscope devices to Tiled.
- `http://10.46.217.241:9091` is the Tiled HTTP data server. It indexes and serves files.

The DATA device is started with the other Tango devices. The Tiled HTTP server
is started separately and must already be reachable.

## Direct Tiled access

We currently access the server in the notebook like this:

from tiled.client import from_uri

client = from_uri("http://10.46.217.241:9091")

list(client) # should print out some folders and files
