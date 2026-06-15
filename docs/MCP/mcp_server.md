# Asyncroscopy MCP Server

The MCP server is a FastMCP HTTP bridge over the live Tango database. It starts
after the Tango DB, support devices, Tiled, and microscope/digital twin are
ready.

## Start With The Stack

Use the MCP-enabled YAML:

```bash
uv run scripts/run_servers.py --yaml configs/Spectra300_MCP.yaml
uv run scripts/run_servers.py --yaml configs/Spectra300_MCP.yaml --microscope dt
```

The MCP endpoint defaults to:

```text
http://127.0.0.1:8000/mcp
```

Local model clients can connect to that endpoint with a FastMCP client while the
server terminal stays open.

## YAML Contract

```yaml
mcp:
  autostart: true
  name: Spectra300_MCP
  transport: streamable-http
  http_host: 127.0.0.1
  http_port: 8000
  data_device_address: asyncroscopy/data/default
  search_packages:
    - asyncroscopy
  blocked_classes:
    - DataBase
    - DServer
  blocked_functions:
    "*":
      - Init
```

`run_servers.py` starts this process last:

```bash
uv run python -m asyncroscopy.mcp.mcp_server ...
```

## Discovery

`MCPServer` connects to the Tango database, calls `get_device_exported("*")`,
opens each exported device with `DeviceProxy`, queries `command_list_query()`,
and registers every non-blocked Tango command as a FastMCP tool.

Tool signatures are built from Tango command types and, when available, source
method signatures in `search_packages`. NumPy values and Tango `DevEncoded`
payloads are normalized into JSON-safe results.

## Adding Commands

For device commands, add a Tango `@command` to the relevant device class. If the
device is registered and exported, MCP discovers it automatically.

For MCP-only helpers, add methods directly to `MCPServer` and decorate them:

```python
@tool()
def my_helper(self, value: str) -> str:
    return value
```

The base server includes `list_devices` and `get_data_from_key`. The latter reads
an acquired HDF5 DATA/Tiled key and returns dataset metadata plus a small preview.

## Blacklisting

Use `blocked_classes` to hide whole Tango classes and `blocked_functions` to hide
commands. `blocked_functions` accepts global command names, fully qualified
`Class.command` entries, or class-specific lists:

```yaml
blocked_functions:
  "*":
    - Init
    - DATA.stop_tiled_server
  ThermoMicroscope:
    - Disconnect
```

## Manual MCP Only

If the Tango stack is already running:

```bash
uv run python -m asyncroscopy.mcp.mcp_server \
  --name Spectra300_MCP \
  --tango-host localhost \
  --tango-port 9094 \
  --transport streamable-http \
  --http-host 127.0.0.1 \
  --http-port 8000 \
  --data-device-address asyncroscopy/data/default \
  --blocked-classes-json '["DataBase", "DServer"]' \
  --blocked-functions-json '{"*": ["Init", "Kill", "RestartServer"]}' \
  --search-packages-json '["asyncroscopy"]'
```
