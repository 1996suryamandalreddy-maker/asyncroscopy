#!/usr/bin/env python
"""Start the Tango database and asyncroscopy device servers."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

import tango
import yaml


DATABASE_TIMEOUT_SECONDS = 120
TILED_COMMAND_TIMEOUT_MILLIS = 120_000

PROJECT_DIR = Path(__file__).resolve().parents[1]

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

# Default config used in interactive mode (no --yaml). Passing --yaml <file>
# selects a different config AND runs headlessly (no prompts).
DEFAULT_CONFIG_PATH = PROJECT_DIR / "configs" / "Spectra300.yaml"


class Style:
    enabled = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
    reset = "\033[0m" if enabled else ""
    bold = "\033[1m" if enabled else ""
    dim = "\033[2m" if enabled else ""
    green = "\033[32m" if enabled else ""
    yellow = "\033[33m" if enabled else ""
    red = "\033[31m" if enabled else ""
    cyan = "\033[36m" if enabled else ""


@dataclass(frozen=True)
class DeviceConfig:
    key: str
    class_name: str
    module_name: str
    start_after_dependencies: bool = False

    @property
    def server_name(self) -> str:
        return f"{self.class_name}/{self.instance_name}"

    @property
    def device_name(self) -> str:
        return f"asyncroscopy/{self.key}/default"

    @property
    def command(self) -> list[str]:
        return ["uv", "run", "python", "-m", self.module_name, self.instance_name]

    @property
    def instance_name(self) -> str:
        return f"{self.key}_instance"


@dataclass
class ManagedProcess:
    key: str
    label: str
    command: list[str]
    process: subprocess.Popen[bytes]

    @property
    def pid(self) -> int:
        return self.process.pid

    @property
    def running(self) -> bool:
        return self.process.poll() is None


# TODO: --debug flag where all server output streams to this terminal / log files (next commit).


@dataclass(frozen=True)
class MicroscopeConfig:
    class_name: str
    module_name: str
    description: str = ""
    host: str | None = None
    port: int | None = None


@dataclass(frozen=True)
class TiledConfig:
    host: str
    port: int
    acquisition_dir: str
    autostart: bool = True


@dataclass(frozen=True)
class MCPConfig:
    autostart: bool
    name: str
    transport: str
    http_host: str
    http_port: int
    data_device_address: str
    search_packages: list[str]
    blocked_classes: list[str]
    blocked_functions: dict[str, list[str]]

    def command(self, tango_host: str, tango_port: int) -> list[str]:
        command = [
            "uv",
            "run",
            "python",
            "-m",
            "asyncroscopy.mcp.mcp_server",
            "--name",
            self.name,
            "--tango-host",
            tango_host,
            "--tango-port",
            str(tango_port),
            "--transport",
            self.transport,
            "--http-host",
            self.http_host,
            "--http-port",
            str(self.http_port),
            "--data-device-address",
            self.data_device_address,
            "--quiet",
            "--blocked-classes-json",
            json.dumps(self.blocked_classes),
            "--blocked-functions-json",
            json.dumps(self.blocked_functions),
            "--search-packages-json",
            json.dumps(self.search_packages),
        ]
        return command


@dataclass(frozen=True)
class Config:
    path: Path
    microscope: MicroscopeConfig
    digital_twin: MicroscopeConfig | None
    support_devices: list[DeviceConfig]
    tango_host: str
    tango_port: int
    tiled: TiledConfig
    mcp: MCPConfig
    device_timeout_seconds: int


def _require(mapping, key: str, where: str):
    if not isinstance(mapping, dict) or key not in mapping:
        raise KeyError(f"Config section '{where}' is missing required key '{key}'")
    return mapping[key]


def _microscope_config(raw: dict) -> MicroscopeConfig:
    return MicroscopeConfig(
        class_name=_require(raw, "class_name", "microscope"),
        module_name=_require(raw, "module_name", "microscope"),
        description=raw.get("description", ""),
        host=raw.get("host"),
        port=raw.get("port"),
    )


def load_config(path: Path) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    support_devices = [
        DeviceConfig(
            key=key,
            class_name=(spec or {}).get("class_name", key.upper()),
            module_name=_require(spec or {}, "module_name", f"devices.{key}"),
        )
        for key, spec in _require(raw, "devices", "(top level)").items()
    ]
    digital_twin = raw.get("digital_twin")
    tango_section = raw.get("tango", {})
    tiled = _require(raw, "tiled", "(top level)")
    mcp = _require(raw, "mcp", "(top level)")

    return Config(
        path=path,
        microscope=_microscope_config(_require(raw, "microscope", "(top level)")),
        digital_twin=_microscope_config(digital_twin) if digital_twin else None,
        support_devices=support_devices,
        tango_host=_require(tango_section, "host", "tango"),
        tango_port=int(_require(tango_section, "port", "tango")),
        tiled=TiledConfig(
            host=_require(tiled, "host", "tiled"),
            port=int(_require(tiled, "port", "tiled")),
            acquisition_dir=_require(tiled, "acquisition_dir", "tiled"),
            autostart=bool(tiled.get("autostart", True)),
        ),
        mcp=MCPConfig(
            autostart=bool(_require(mcp, "autostart", "mcp")),
            name=_require(mcp, "name", "mcp"),
            transport=_require(mcp, "transport", "mcp"),
            http_host=_require(mcp, "http_host", "mcp"),
            http_port=int(_require(mcp, "http_port", "mcp")),
            data_device_address=_require(mcp, "data_device_address", "mcp"),
            search_packages=list(_require(mcp, "search_packages", "mcp")),
            blocked_classes=list(_require(mcp, "blocked_classes", "mcp")),
            blocked_functions={key: list(value) for key, value in _require(mcp, "blocked_functions", "mcp").items()},
        ),
        device_timeout_seconds=int(raw.get("device_timeout_seconds", 120)),
    )


def selected_microscope_config(config: Config, mode: str) -> MicroscopeConfig:
    if mode == "dt":
        if config.digital_twin is None:
            raise ValueError(
                f"{config.path} has no 'digital_twin' block (needed for --microscope dt)"
            )
        return config.digital_twin
    return config.microscope


def build_devices(config: Config, mode: str) -> list[DeviceConfig]:
    micro = selected_microscope_config(config, mode)
    return [
        *config.support_devices,
        DeviceConfig(
            key="microscope",
            class_name=micro.class_name,
            module_name=micro.module_name,
            start_after_dependencies=True,
        ),
    ]


def device_address_properties(config: Config) -> dict[str, list[str]]:
    return {
        f"{device.key}_device_address": [device.device_name]
        for device in config.support_devices
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--microscope",
        choices=["real", "dt"],
        default="real",
        help="Which block to start: 'real' microscope or 'dt' digital twin. Defaults to real.",
    )
    parser.add_argument(
        "--yaml",
        type=Path,
        default=None,
        metavar="PATH",
        help="YAML config to start from. When given, runs headlessly (no prompts). "
        "When omitted, uses the bundled default config and prompts interactively.",
    )
    return parser.parse_args(argv)


def all_microscope_cleanup_patterns(config: Config) -> set[str]:
    classes = {config.microscope.class_name}
    if config.digital_twin is not None:
        classes.add(config.digital_twin.class_name)
    return {f"{class_name} microscope_instance" for class_name in classes}


def selected_microscope(devices: list[DeviceConfig]) -> DeviceConfig:
    return next(device for device in devices if device.key == "microscope")


def color(text: str, code: str) -> str:
    return f"{code}{text}{Style.reset}" if Style.enabled else text


def prompt_str(label: str, default: str) -> str:
    try:
        answer = input(f"{color(label, Style.bold)} [{default}]: ").strip()
    except EOFError:
        print(default)
        return default
    return answer or default


def prompt_int(label: str, default: int) -> int:
    while True:
        raw = prompt_str(label, str(default))
        try:
            return int(raw)
        except ValueError:
            print(f"  {color('Invalid number.', Style.red)} Please enter an integer or press Enter.")


def prompt_bool(label: str, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        try:
            answer = input(f"{color(label, Style.bold)} [{suffix}]: ").strip().lower()
        except EOFError:
            print("yes" if default else "no")
            return default
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print(f"  {color('Invalid choice.', Style.red)} Enter y, n, or press Enter.")


def print_banner(title: str) -> None:
    width = 78
    print()
    print(color("=" * width, Style.cyan))
    print(color(title.center(width), Style.bold + Style.cyan))
    print(color("=" * width, Style.cyan))


def print_section(step: int, total: int, title: str) -> None:
    print()
    print(color(f"[{step}/{total}] {title}", Style.bold))
    print(color("-" * 78, Style.dim))


def status_line(status: str, message: str, detail: str = "") -> None:
    colors = {
        "OK": Style.green,
        "RUN": Style.cyan,
        "WAIT": Style.yellow,
        "FAIL": Style.red,
        "SKIP": Style.dim,
    }
    tag = color(f"{status:>4}", colors.get(status, ""))
    if detail:
        print(f"  {tag}  {message:<32} {color(detail, Style.dim)}")
    else:
        print(f"  {tag}  {message}")


def make_environment(
    host: str, port: int, tiled_host: str, tiled_port: int, acquisition_dir: str
) -> dict[str, str]:
    tango_host = f"{host}:{port}"
    os.environ["TANGO_HOST"] = tango_host
    return {
        **os.environ,
        "TANGO_HOST": tango_host,
        "ASYNCROSCOPY_TILED_URI": f"http://{tiled_host}:{tiled_port}",
        "ASYNCROSCOPY_ACQUISITION_DIR": acquisition_dir,
        "PYTHONUNBUFFERED": "1",
    }


def start_process(
    key: str, label: str, command: list[str], environment: dict[str, str]
) -> ManagedProcess:
    popen_kwargs = {
        "env": environment,
        "cwd": PROJECT_DIR,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(
        command,
        **popen_kwargs,
    )
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            try:
                os.set_blocking(stream.fileno(), False)
            except (AttributeError, OSError):
                pass
    return ManagedProcess(key=key, label=label, command=command, process=process)


def read_process_output(stream) -> str:
    if stream is None:
        return ""

    chunks: list[bytes] = []
    while True:
        try:
            chunk = stream.read(4096)
        except BlockingIOError:
            break
        except Exception:
            break
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks).decode(errors="replace").strip()


def stop_process(process: ManagedProcess, timeout: float = 5.0) -> None:
    if not process.running and os.name == "nt":
        return
    if os.name == "nt":
        process.process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            if not process.running:
                return
            process.process.terminate()
        except OSError:
            process.process.terminate()
    try:
        process.process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError:
                process.process.kill()
        process.process.wait(timeout=timeout)


def stop_all(processes: Iterable[ManagedProcess]) -> None:
    for process in reversed(list(processes)):
        stop_process(process)


def stop_processes_on_port(port: int) -> int:
    if os.name == "nt":
        try:
            result = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True)
        except FileNotFoundError:
            status_line("SKIP", f"database port {port}", "netstat is not available")
            return 0

        pids: set[int] = set()
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 5 or parts[0].upper() != "TCP":
                continue
            local_address = parts[1]
            state = parts[3].upper()
            pid = parts[-1]
            if state == "LISTENING" and local_address.rsplit(":", 1)[-1] == str(port) and pid.isdigit():
                pids.add(int(pid))

        stopped = 0
        for pid in sorted(pids):
            try:
                result = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
            except FileNotFoundError:
                status_line("SKIP", f"PID {pid}", "taskkill is not available")
                continue
            if result.returncode == 0:
                stopped += 1
            else:
                status_line("FAIL", f"PID {pid}", (result.stderr or result.stdout).strip())
        return stopped

    try:
        result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
    except FileNotFoundError:
        status_line("SKIP", f"database port {port}", "lsof is not installed")
        return 0

    stopped = 0
    for line in result.stdout.splitlines():
        if not line.strip().isdigit():
            continue
        try:
            os.kill(int(line), signal.SIGTERM)
            stopped += 1
        except ProcessLookupError:
            pass
        except PermissionError:
            status_line("FAIL", f"PID {line}", "permission denied")
    return stopped


def stop_python_process_matching(pattern: str) -> bool:
    if os.name == "nt":
        script = (
            "$pattern = $args[0]; "
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -and $_.CommandLine.Contains($pattern) } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", script, pattern],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return False
        return result.returncode == 0 and bool(result.stdout.strip())

    try:
        result = subprocess.run(["pkill", "-f", pattern], capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return result.returncode == 0


def clear_old_processes(
    port: int,
    devices: list[DeviceConfig],
    config: Config,
    tiled_port: int | None = None,
    mcp_port: int | None = None,
) -> None:
    stopped_databases = stop_processes_on_port(port)
    status_line("OK" if stopped_databases else "SKIP", f"database port {port}", f"{stopped_databases} process(es) signaled")

    if tiled_port is not None and tiled_port != port:
        stopped_tiled = stop_processes_on_port(tiled_port)
        status_line("OK" if stopped_tiled else "SKIP", f"Tiled port {tiled_port}", f"{stopped_tiled} process(es) signaled")

    if mcp_port is not None and mcp_port not in {port, tiled_port}:
        stopped_mcp = stop_processes_on_port(mcp_port)
        status_line("OK" if stopped_mcp else "SKIP", f"MCP port {mcp_port}", f"{stopped_mcp} process(es) signaled")

    stopped_servers = 0
    cleanup_patterns = {f"{device.class_name} {device.instance_name}" for device in devices}
    cleanup_patterns.update(all_microscope_cleanup_patterns(config))
    for pattern in sorted(cleanup_patterns):
        if stop_python_process_matching(pattern):
            stopped_servers += 1

    status_line("OK" if stopped_servers else "SKIP", "old device servers", f"{stopped_servers} process group(s) signaled")
    time.sleep(2)


def wait_for_database(host: str, port: int, timeout: int) -> float:
    start = time.monotonic()
    last_error: Exception | None = None
    while time.monotonic() - start < timeout:
        try:
            db = tango.Database(host, port)
            db.get_db_host()
            return time.monotonic() - start
        except Exception as exc:
            last_error = exc
            print(color(".", Style.dim), end="", flush=True)
            time.sleep(1)
    raise TimeoutError(f"Tango database did not become ready after {timeout}s. Last error: {last_error}")


def wait_for_device(device_name: str, timeout: int) -> float:
    start = time.monotonic()
    last_error: Exception | None = None
    while time.monotonic() - start < timeout:
        try:
            proxy = tango.DeviceProxy(device_name)
            proxy.ping()
            return time.monotonic() - start
        except Exception as exc:
            last_error = exc
            print(color(".", Style.dim), end="", flush=True)
            time.sleep(1)
    raise TimeoutError(f"{device_name} did not become ready after {timeout}s. Last error: {last_error}")


def wait_for_tcp_port(host: str, port: int, timeout: int, process: ManagedProcess | None = None) -> float:
    connect_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    start = time.monotonic()
    last_error: Exception | None = None
    while time.monotonic() - start < timeout:
        if process is not None and not process.running:
            stdout = read_process_output(process.process.stdout)
            stderr = read_process_output(process.process.stderr)
            detail = f"stdout: {stdout or '(empty)'}\nstderr: {stderr or '(empty)'}"
            raise RuntimeError(f"{process.label} exited before {host}:{port} accepted connections.\n{detail}")
        try:
            with socket.create_connection((connect_host, port), timeout=1.0):
                return time.monotonic() - start
        except OSError as exc:
            last_error = exc
            print(color(".", Style.dim), end="", flush=True)
            time.sleep(1)
    raise TimeoutError(f"{host}:{port} did not accept TCP connections after {timeout}s. Last error: {last_error}")


def register_devices(
    devices: list[DeviceConfig], microscope_properties: dict[str, list[str]]
) -> None:
    database = tango.Database()
    status_line("OK", "database", f"{database.get_db_host()}:{database.get_db_port()}")

    for device in devices:
        device_info = tango.DbDevInfo()
        device_info.server = device.server_name
        device_info._class = device.class_name
        device_info.name = device.device_name
        database.add_device(device_info)
        status_line("OK", device.device_name)

    microscope = selected_microscope(devices)
    for property_name, property_value in microscope_properties.items():
        database.put_device_property(microscope.device_name, {property_name: property_value})
        status_line("OK", f"property: {property_name} = {property_value[0]}")


def get_data_proxy() -> tango.DeviceProxy:
    data = tango.DeviceProxy("asyncroscopy/data/default")
    data.set_timeout_millis(TILED_COMMAND_TIMEOUT_MILLIS)
    return data


def stop_tiled_server() -> None:
    try:
        get_data_proxy().stop_tiled_server()
    except Exception:
        pass


def print_debug_output(processes: Iterable[ManagedProcess]) -> None:
    print()
    print(color("Debug output", Style.bold + Style.yellow))
    print(color("-" * 78, Style.dim))
    for process in processes:
        stdout = read_process_output(process.process.stdout)
        stderr = read_process_output(process.process.stderr)
        print(
            f"{color(process.label, Style.bold)}  pid={process.pid}  running={process.running}  returncode={process.process.poll()}"
        )
        print(f"  command: {' '.join(process.command)}")
        print(f"  stdout: {stdout or '(empty)'}")
        print(f"  stderr: {stderr or '(empty)'}")
        print()


def print_inventory(devices: list[DeviceConfig]) -> None:
    status_line("OK", "device inventory", f"{len(devices)} declaration(s) built into this script")
    key_width = max(len(device.key) for device in devices)
    class_width = max(len(device.class_name) for device in devices)
    for device in devices:
        status_line("RUN", device.key.ljust(key_width), f"{device.class_name.ljust(class_width)}  {device.device_name}")


def print_summary(
    host: str,
    port: int,
    processes: list[ManagedProcess],
    ready_times: dict[str, float],
    tiled_config: dict | None = None,
    mcp_config: MCPConfig | None = None,
    step: int = 5,
    total: int = 5,
) -> None:
    print_section(step, total, "Startup summary")
    print(f"  {color('TANGO_HOST', Style.bold):<18} {host}:{port}")
    print(f"  {color('PROJECT', Style.bold):<18} {PROJECT_DIR}")
    print()
    print(f"  {'SERVER':<14} {'PID':>8} {'READY':>10}  COMMAND")
    print(color("  " + "-" * 74, Style.dim))
    for process in processes:
        ready = ready_times.get(process.key)
        ready_text = f"{ready:.1f}s" if ready is not None else "-"
        print(
            f"  {process.key:<14} {process.pid:>8} {ready_text:>10}  {' '.join(process.command)}"
        )
    if tiled_config is not None:
        print()
        print(f"  {color('TILED_URI', Style.bold):<18} {tiled_config['uri']}")
        print(f"  {color('TILED_SERVING', Style.bold):<18} {tiled_config['tiled_server_serving']}")
    if mcp_config is not None and mcp_config.autostart:
        print()
        print(f"  {color('MCP_HTTP', Style.bold):<18} http://{mcp_config.http_host}:{mcp_config.http_port}/mcp")
        print(f"  {color('MCP_NAME', Style.bold):<18} {mcp_config.name}")
    print()
    print(color("All asyncroscopy servers are ready.", Style.bold + Style.green))


def main(argv: list[str] | None = None) -> int:
    def request_shutdown(_signum, _frame) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, request_shutdown)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, request_shutdown)

    args = parse_args(argv)
    config_path = args.yaml or DEFAULT_CONFIG_PATH
    try:
        config = load_config(config_path)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(color(f"Config error: {exc}", Style.bold + Style.red))
        return 1

    headless = args.yaml is not None
    devices = build_devices(config, args.microscope)
    microscope = selected_microscope(devices)
    micro_config = selected_microscope_config(config, args.microscope)
    regular_devices = [device for device in devices if not device.start_after_dependencies]
    dependency_devices = [device for device in devices if device.start_after_dependencies]

    print_banner("ASYNCROSCOPY SERVER STARTUP")

    microscope_properties = device_address_properties(config)
    if headless:
        print(f"Headless start from {config_path}")
        print()
        host, port = config.tango_host, config.tango_port
        tiled_host, tiled_port = config.tiled.host, config.tiled.port
        acquisition_dir = config.tiled.acquisition_dir
        should_start_tiled = config.tiled.autostart
        should_start_mcp = config.mcp.autostart
        clear_first = start_database = should_register_devices = True
        device_timeout = config.device_timeout_seconds
        if micro_config.host is not None and micro_config.port is not None:
            microscope_properties["autoscript_host_ip"] = [str(micro_config.host)]
            microscope_properties["autoscript_host_port"] = [str(micro_config.port)]
    else:
        print("Press Enter at any prompt to use the value shown in brackets.")
        print()
        host = prompt_str("Tango database host", config.tango_host)
        port = prompt_int("Tango database port", config.tango_port)
        default_tiled = urlsplit(os.environ.get("ASYNCROSCOPY_TILED_URI", f"http://{config.tiled.host}:{config.tiled.port}"))
        tiled_host = prompt_str("Tiled HTTP host", default_tiled.hostname or config.tiled.host)
        tiled_port = prompt_int("Tiled HTTP port", default_tiled.port or config.tiled.port)
        acquisition_dir = prompt_str(
            "Acquisition save path",
            os.environ.get("ASYNCROSCOPY_ACQUISITION_DIR", config.tiled.acquisition_dir),
        )
        should_start_tiled = prompt_bool("Start Tiled HTTP server", config.tiled.autostart)
        should_start_mcp = prompt_bool("Start MCP HTTP server", config.mcp.autostart)
        clear_first = prompt_bool("Clear old processes first", True)
        start_database = prompt_bool("Start Tango database", True)
        should_register_devices = prompt_bool("Register devices", True)
        device_timeout = prompt_int("Device startup timeout seconds", config.device_timeout_seconds)
        if should_start_mcp:
            config = replace(
                config,
                mcp=replace(
                    config.mcp,
                    autostart=True,
                    http_host=prompt_str("MCP HTTP host", config.mcp.http_host),
                    http_port=prompt_int("MCP HTTP port", config.mcp.http_port),
                ),
            )
        if micro_config.host is not None and micro_config.port is not None:
            autoscript_host = prompt_str("AutoScript host IP", str(micro_config.host))
            autoscript_port = prompt_int("AutoScript host port", int(micro_config.port))
            microscope_properties["autoscript_host_ip"] = [autoscript_host]
            microscope_properties["autoscript_host_port"] = [str(autoscript_port)]

    total_steps = 6 if should_start_mcp else 5

    environment = make_environment(host, port, tiled_host, tiled_port, acquisition_dir)
    processes: list[ManagedProcess] = []
    ready_times: dict[str, float] = {}
    tiled_config = None

    print()
    print(f"  {color('TANGO_HOST', Style.bold):<18} {host}:{port}")
    print(f"  {color('PROJECT', Style.bold):<18} {PROJECT_DIR}")
    print(f"  {color('CONFIG', Style.bold):<18} {config_path}")
    print(f"  {color('MICROSCOPE', Style.bold):<18} {args.microscope} ({microscope.class_name})")
    if should_start_mcp:
        print(f"  {color('MCP', Style.bold):<18} {config.mcp.name} ({config.mcp.http_host}:{config.mcp.http_port})")
    print_inventory(devices)

    try:
        print_section(1, total_steps, "Clearing old processes")
        if clear_first:
            clear_old_processes(
                port,
                devices,
                config,
                tiled_port if should_start_tiled else None,
                config.mcp.http_port if should_start_mcp else None,
            )
        else:
            status_line("SKIP", "old process cleanup")

        print_section(2, total_steps, "Starting Tango database")
        if start_database:
            database = start_process(
                "database",
                "Tango database",
                ["uv", "run", "python", "-m", "tango.databaseds.database", "2"],
                environment,
            )
            processes.append(database)
            print("  WAIT  database readiness", end="", flush=True)
            elapsed = wait_for_database(host, port, DATABASE_TIMEOUT_SECONDS)
            ready_times["database"] = elapsed
            print(
                f" {color('OK', Style.green)} pid={database.pid} ready in {elapsed:.1f}s"
            )
        else:
            print("  WAIT  existing database readiness", end="", flush=True)
            elapsed = wait_for_database(host, port, DATABASE_TIMEOUT_SECONDS)
            ready_times["database"] = elapsed
            print(f" {color('OK', Style.green)} ready in {elapsed:.1f}s")

        print_section(3, total_steps, "Registering devices")
        if should_register_devices:
            register_devices(devices, microscope_properties)
        else:
            status_line("SKIP", "device registration")

        print_section(4, total_steps, "Starting device servers")
        for device in regular_devices:
            process = start_process(device.key, device.class_name, device.command, environment)
            processes.append(process)
            status_line("RUN", device.key, f"{device.module_name}  pid={process.pid}")

        for device in regular_devices:
            print(f"  WAIT  {device.device_name:<34}", end="", flush=True)
            elapsed = wait_for_device(device.device_name, device_timeout)
            ready_times[device.key] = elapsed
            print(f" {color('OK', Style.green)} ready in {elapsed:.1f}s")

        if should_start_tiled:
            tiled_config = json.loads(get_data_proxy().start_tiled_server())
            if tiled_config["tiled_server"] != "yes":
                raise RuntimeError(
                    f"Tiled HTTP server failed to start: {tiled_config['tiled_server_status']}"
                )
            status_line("OK", "Tiled HTTP server", f"{tiled_config['uri']} serving {tiled_config['tiled_server_serving']}")
        else:
            status_line("SKIP", "Tiled HTTP server")

        for device in dependency_devices:
            print()
            status_line("RUN", device.key, f"{device.module_name}  starting after dependencies")
            process = start_process(device.key, device.class_name, device.command, environment)
            processes.append(process)
            print(f"  WAIT  {device.device_name:<34}", end="", flush=True)
            elapsed = wait_for_device(device.device_name, device_timeout)
            ready_times[device.key] = elapsed
            print(f" {color('OK', Style.green)} ready in {elapsed:.1f}s")

        if should_start_mcp:
            print_section(5, total_steps, "Starting MCP server")
            mcp_process = start_process(
                "mcp",
                config.mcp.name,
                config.mcp.command(host, port),
                environment,
            )
            processes.append(mcp_process)
            status_line("RUN", "mcp", f"{config.mcp.name}  pid={mcp_process.pid}")
            print(
                f"  WAIT  MCP HTTP {config.mcp.http_host}:{config.mcp.http_port:<21}",
                end="",
                flush=True,
            )
            elapsed = wait_for_tcp_port(config.mcp.http_host, config.mcp.http_port, device_timeout, mcp_process)
            ready_times["mcp"] = elapsed
            print(f" {color('OK', Style.green)} ready in {elapsed:.1f}s")
        else:
            status_line("SKIP", "MCP HTTP server")

        print_summary(
            host,
            port,
            processes,
            ready_times,
            tiled_config,
            config.mcp if should_start_mcp else None,
            step=total_steps,
            total=total_steps,
        )
        print()
        print(
            color(
                "Leave this terminal open while you use the servers. Press Ctrl+C to stop them.",
                Style.dim,
            )
        )
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print()
        print(color("Shutdown requested. Stopping managed processes...", Style.yellow))
        stop_tiled_server()
        stop_all(processes)
        status_line("OK", "shutdown complete")
        return 0
    except Exception as exc:
        print()
        print(color(f"Startup failed: {exc}", Style.bold + Style.red))
        print_debug_output(processes)
        stop_tiled_server()
        stop_all(processes)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
