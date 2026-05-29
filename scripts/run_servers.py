#!/usr/bin/env python
"""Start the Tango database and asyncroscopy device servers."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import urlopen

import tango


DEFAULT_TANGO_HOST = "10.46.217.241"
DEFAULT_TANGO_PORT = 9094
DEFAULT_TILED_HOST = "10.46.217.241"
DEFAULT_TILED_PORT = 9091
DEFAULT_ACQUISITION_DIR = "outputs/tiled_acquisitions"
TILED_API_KEY = "secret"
DATABASE_TIMEOUT_SECONDS = 120
DEVICE_TIMEOUT_SECONDS = 120
TILED_TIMEOUT_SECONDS = 30

PROJECT_DIR = Path(__file__).resolve().parents[1]

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


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

# TODO: Break out alternate configs into .yaml files or somthing
# TODO: ex. UTKSpectra300.yaml, DigitatlTwin.yaml, WDTwin.yaml
# TODO: --debug flag where all the terminal outputs of the servers show in this termainl (or are saved to file)

MICROSCOPE_MODES = {
    "real": ("ThermoMicroscope", "asyncroscopy.ThermoMicroscope"),
    "dt": ("DigitalTwin", "asyncroscopy.DigitalTwin"),
}

SUPPORT_DEVICES = [
    DeviceConfig(
        key="camera",
        class_name="CAMERA",
        module_name="asyncroscopy.detectors.CAMERA",
    ),
    DeviceConfig(
        key="corrector",
        class_name="CORRECTOR",
        module_name="asyncroscopy.hardware.CORRECTOR",
    ),
    DeviceConfig(
        key="data",
        class_name="DATA",
        module_name="asyncroscopy.software.DATA",
    ),
    DeviceConfig(
        key="eds",
        class_name="EDS",
        module_name="asyncroscopy.detectors.EDS",
    ),
    DeviceConfig(
        key="flucam",
        class_name="FLUCAM",
        module_name="asyncroscopy.detectors.FLUCAM",
    ),
    DeviceConfig(
        key="scan",
        class_name="SCAN",
        module_name="asyncroscopy.hardware.SCAN",
    ),
    DeviceConfig(
        key="stage",
        class_name="STAGE",
        module_name="asyncroscopy.hardware.STAGE",
    ),
]


def build_devices(microscope_mode: str) -> list[DeviceConfig]:
    microscope_class, microscope_module = MICROSCOPE_MODES[microscope_mode]
    return [
        *SUPPORT_DEVICES,
        DeviceConfig(
            key="microscope",
            class_name=microscope_class,
            module_name=microscope_module,
            start_after_dependencies=True,
        ),
    ]


DEVICES = build_devices("real")

MICROSCOPE_DEVICE_KEYS = ("scan", "camera", "flucam", "eds", "stage", "corrector", "data")
MICROSCOPE_PROPERTIES = {
    f"{device_key}_device_address": [f"asyncroscopy/{device_key}/default"]
    for device_key in MICROSCOPE_DEVICE_KEYS
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--microscope",
        choices=sorted(MICROSCOPE_MODES),
        default="real",
        help="Microscope backend to start. Defaults to real.",
    )
    parser.add_argument(
        "--tiled-host",
        default=None,
        help=f"Tiled HTTP server host configured on the DATA device. Defaults to {DEFAULT_TILED_HOST}.",
    )
    parser.add_argument(
        "--tiled-port",
        type=int,
        default=None,
        help=f"Tiled HTTP server port configured on the DATA device. Defaults to {DEFAULT_TILED_PORT}.",
    )
    parser.add_argument(
        "--save-path",
        default=None,
        help=f"Acquisition directory served by Tiled. Defaults to {DEFAULT_ACQUISITION_DIR}.",
    )
    parser.add_argument(
        "--start-tiled",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Start the Tiled HTTP server as a tracked process. Defaults to yes.",
    )
    return parser.parse_args(argv)


def all_microscope_cleanup_patterns() -> set[str]:
    return {f"{class_name} microscope_instance" for class_name, _ in MICROSCOPE_MODES.values()}


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
    colors = {"OK": Style.green, "RUN": Style.cyan, "WAIT": Style.yellow, "FAIL": Style.red, "SKIP": Style.dim}
    tag = color(f"{status:>4}", colors.get(status, ""))
    if detail:
        print(f"  {tag}  {message:<32} {color(detail, Style.dim)}")
    else:
        print(f"  {tag}  {message}")


def make_environment(host: str, port: int, tiled_host: str, tiled_port: int, save_path: str) -> dict[str, str]:
    tango_host = f"{host}:{port}"
    tiled_uri = f"http://{tiled_host}:{tiled_port}"
    os.environ["TANGO_HOST"] = tango_host
    os.environ["ASYNCROSCOPY_TILED_URI"] = tiled_uri
    os.environ["ASYNCROSCOPY_ACQUISITION_DIR"] = save_path
    return {
        **os.environ,
        "TANGO_HOST": tango_host,
        "ASYNCROSCOPY_TILED_URI": tiled_uri,
        "ASYNCROSCOPY_ACQUISITION_DIR": save_path,
        "PYTHONUNBUFFERED": "1",
    }


def start_process(key: str, label: str, command: list[str], environment: dict[str, str]) -> ManagedProcess:
    process = subprocess.Popen(
        command,
        env=environment,
        cwd=PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
    if not process.running:
        return
    process.process.terminate()
    try:
        process.process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
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


def clear_old_processes(database_port: int, tiled_port: int, devices: list[DeviceConfig], clear_tiled: bool) -> None:
    stopped_databases = stop_processes_on_port(database_port)
    status_line(
        "OK" if stopped_databases else "SKIP",
        f"database port {database_port}",
        f"{stopped_databases} process(es) signaled",
    )

    if clear_tiled:
        stopped_tiled = stop_processes_on_port(tiled_port)
        status_line(
            "OK" if stopped_tiled else "SKIP",
            f"Tiled port {tiled_port}",
            f"{stopped_tiled} process(es) signaled",
        )

    stopped_servers = 0
    cleanup_patterns = {f"{device.class_name} {device.instance_name}" for device in devices}
    cleanup_patterns.update(all_microscope_cleanup_patterns())
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


def tiled_alive(uri: str) -> bool:
    try:
        with urlopen(uri, timeout=0.3):
            return True
    except (OSError, URLError):
        return False


def wait_for_tiled(uri: str, process: ManagedProcess, timeout: int) -> float:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if tiled_alive(uri):
            return time.monotonic() - start
        if not process.running:
            raise RuntimeError(f"Tiled server exited early with code {process.process.poll()}")
        print(color(".", Style.dim), end="", flush=True)
        time.sleep(0.5)
    raise TimeoutError(f"Tiled server did not become ready at {uri} after {timeout}s")


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


def register_devices(devices: list[DeviceConfig]) -> None:
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
    for property_name, property_value in MICROSCOPE_PROPERTIES.items():
        database.put_device_property(microscope.device_name, {property_name: property_value})
        status_line("OK", f"property: {property_name} = {property_value[0]}")


def configure_data_device(
    host: str,
    port: int,
    tiled_host: str,
    tiled_port: int,
    save_path: str,
) -> dict[str, object]:
    data = tango.DeviceProxy(f"tango://{host}:{port}/asyncroscopy/data/default")
    config = {
        "host": tiled_host,
        "port": tiled_port,
        "save_path": save_path,
    }
    return json.loads(data.configure(json.dumps(config)))


def refresh_data_config(host: str, port: int) -> dict[str, object]:
    data = tango.DeviceProxy(f"tango://{host}:{port}/asyncroscopy/data/default")
    _ = data.tiled_server
    return json.loads(data.get_config())


def tiled_executable() -> str:
    candidate = Path(sys.executable).with_name("tiled")
    return str(candidate) if candidate.exists() else "tiled"


def is_windows_drive_path(path: str | Path) -> bool:
    text = str(path)
    return len(text) >= 3 and text[1] == ":" and text[0].isalpha() and text[2] in {"\\", "/"}


def path_text(path: Path) -> str:
    return str(path).replace("\\", "/") if is_windows_drive_path(path) else str(path)


def tiled_catalog_path(save_path: str) -> str:
    return path_text(Path(save_path).expanduser() / ".asyncroscopy_tiled_catalog.db")


def init_tiled_catalog(save_path: str) -> str:
    catalog = tiled_catalog_path(save_path)
    if not (is_windows_drive_path(save_path) and os.name != "nt"):
        Path(save_path).expanduser().mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [tiled_executable(), "catalog", "init", "--if-not-exists", catalog],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return catalog


def start_tracked_tiled_server(
    tiled_host: str,
    tiled_port: int,
    save_path: str,
    environment: dict[str, str],
) -> ManagedProcess | None:
    uri = f"http://{tiled_host}:{tiled_port}"
    if tiled_alive(uri):
        status_line("OK", "Tiled server", f"already reachable at {uri}")
        return None

    catalog = init_tiled_catalog(save_path)
    server = start_process(
        "tiled",
        "Tiled HTTP server",
        [
            tiled_executable(),
            "serve",
            "catalog",
            catalog,
            "--read",
            save_path,
            "--public",
            "--api-key",
            TILED_API_KEY,
            "--host",
            tiled_host,
            "--port",
            str(tiled_port),
        ],
        environment,
    )
    print("  WAIT  Tiled HTTP server", end="", flush=True)
    elapsed = wait_for_tiled(uri, server, TILED_TIMEOUT_SECONDS)
    print(f" {color('OK', Style.green)} pid={server.pid} ready in {elapsed:.1f}s")
    return server


def print_debug_output(processes: Iterable[ManagedProcess]) -> None:
    print()
    print(color("Debug output", Style.bold + Style.yellow))
    print(color("-" * 78, Style.dim))
    for process in processes:
        stdout = read_process_output(process.process.stdout)
        stderr = read_process_output(process.process.stderr)
        print(f"{color(process.label, Style.bold)}  pid={process.pid}  running={process.running}  returncode={process.process.poll()}")
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


def print_summary(host: str, port: int, tiled_config: dict[str, object], processes: list[ManagedProcess], ready_times: dict[str, float]) -> None:
    print_section(7, 7, "Startup summary")
    print(f"  {color('TANGO_HOST', Style.bold):<18} {host}:{port}")
    print(f"  {color('TILED_URI', Style.bold):<18} {tiled_config.get('uri', '-')}")
    print(f"  {color('SAVE_PATH', Style.bold):<18} {tiled_config.get('save_path', '-')}")
    print(f"  {color('PROJECT', Style.bold):<18} {PROJECT_DIR}")
    print()
    print(f"  {'SERVER':<14} {'PID':>8} {'READY':>10}  COMMAND")
    print(color("  " + "-" * 74, Style.dim))
    for process in processes:
        ready = ready_times.get(process.key)
        ready_text = f"{ready:.1f}s" if ready is not None else "-"
        print(f"  {process.key:<14} {process.pid:>8} {ready_text:>10}  {' '.join(process.command)}")
    print()
    print(color("All asyncroscopy servers are ready.", Style.bold + Style.green))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    devices = build_devices(args.microscope)
    microscope = selected_microscope(devices)
    regular_devices = [device for device in devices if not device.start_after_dependencies]
    dependency_devices = [device for device in devices if device.start_after_dependencies]

    print_banner("ASYNCROSCOPY SERVER STARTUP")
    print("Press Enter at any prompt to use the value shown in brackets.")
    print()

    host = prompt_str("Tango database host", DEFAULT_TANGO_HOST)
    port = prompt_int("Tango database port", DEFAULT_TANGO_PORT)
    clear_first = prompt_bool("Clear old processes first", True)
    start_database = prompt_bool("Start Tango database", True)
    should_register_devices = prompt_bool("Register devices", True)
    device_timeout = prompt_int("Device startup timeout seconds", DEVICE_TIMEOUT_SECONDS)
    tiled_host = args.tiled_host or prompt_str("Tiled server host", DEFAULT_TILED_HOST)
    tiled_port = args.tiled_port if args.tiled_port is not None else prompt_int("Tiled server port", DEFAULT_TILED_PORT)
    save_path = args.save_path or prompt_str("Acquisition save path", DEFAULT_ACQUISITION_DIR)
    start_tiled = args.start_tiled if args.start_tiled is not None else prompt_bool("Start tracked Tiled server", True)

    environment = make_environment(host, port, tiled_host, tiled_port, save_path)
    processes: list[ManagedProcess] = []
    ready_times: dict[str, float] = {}
    tiled_config: dict[str, object] = {}

    print()
    print(f"  {color('TANGO_HOST', Style.bold):<18} {host}:{port}")
    print(f"  {color('TILED_URI', Style.bold):<18} http://{tiled_host}:{tiled_port}")
    print(f"  {color('SAVE_PATH', Style.bold):<18} {save_path}")
    print(f"  {color('PROJECT', Style.bold):<18} {PROJECT_DIR}")
    print(f"  {color('MICROSCOPE', Style.bold):<18} {args.microscope} ({microscope.class_name})")
    print_inventory(devices)

    try:
        print_section(1, 7, "Clearing old processes")
        if clear_first:
            clear_old_processes(port, tiled_port, devices, start_tiled)
        else:
            status_line("SKIP", "old process cleanup")

        print_section(2, 7, "Starting Tango database")
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
            print(f" {color('OK', Style.green)} pid={database.pid} ready in {elapsed:.1f}s")
        else:
            print("  WAIT  existing database readiness", end="", flush=True)
            elapsed = wait_for_database(host, port, DATABASE_TIMEOUT_SECONDS)
            ready_times["database"] = elapsed
            print(f" {color('OK', Style.green)} ready in {elapsed:.1f}s")

        print_section(3, 7, "Registering devices")
        if should_register_devices:
            register_devices(devices)
        else:
            status_line("SKIP", "device registration")

        print_section(4, 7, "Starting support device servers")
        for device in regular_devices:
            process = start_process(device.key, device.class_name, device.command, environment)
            processes.append(process)
            status_line("RUN", device.key, f"{device.module_name}  pid={process.pid}")

        for device in regular_devices:
            print(f"  WAIT  {device.device_name:<34}", end="", flush=True)
            elapsed = wait_for_device(device.device_name, device_timeout)
            ready_times[device.key] = elapsed
            print(f" {color('OK', Style.green)} ready in {elapsed:.1f}s")

        print_section(5, 7, "Configuring DATA/Tiled")
        tiled_config = configure_data_device(host, port, tiled_host, tiled_port, save_path)
        if start_tiled:
            tiled_process = start_tracked_tiled_server(tiled_host, tiled_port, save_path, environment)
            if tiled_process is not None:
                processes.append(tiled_process)
            tiled_config = refresh_data_config(host, port)
            status = str(tiled_config.get("tiled_server", "")).lower()
            status_line("OK" if status == "yes" else "FAIL", "DATA sees Tiled", str(tiled_config.get("uri", "")))
        else:
            status_line("SKIP", "Tiled server startup", "DATA device configured only")
        status_line("OK", "DATA save path", str(tiled_config.get("save_path", save_path)))

        print_section(6, 7, "Starting dependency device servers")
        for device in dependency_devices:
            print()
            status_line("RUN", device.key, f"{device.module_name}  starting after dependencies")
            process = start_process(device.key, device.class_name, device.command, environment)
            processes.append(process)
            print(f"  WAIT  {device.device_name:<34}", end="", flush=True)
            elapsed = wait_for_device(device.device_name, device_timeout)
            ready_times[device.key] = elapsed
            print(f" {color('OK', Style.green)} ready in {elapsed:.1f}s")

        print_summary(host, port, tiled_config, processes, ready_times)
        print()
        print(color("Leave this terminal open while you use the servers. Press Ctrl+C to stop them.", Style.dim))
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print()
        print(color("Shutdown requested. Stopping managed processes...", Style.yellow))
        stop_all(processes)
        status_line("OK", "shutdown complete")
        return 0
    except Exception as exc:
        print()
        print(color(f"Startup failed: {exc}", Style.bold + Style.red))
        print_debug_output(processes)
        stop_all(processes)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
