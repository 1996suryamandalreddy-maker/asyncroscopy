import os
import sys
import signal
import json
import subprocess
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from collections import deque
from typing import Self

PROCESS_OUTPUT_LINES = 200
TANGO_DATABASE_FILES = ("tango_database.db", "Tango_database.db")

PROJECT_DIR = Path(__file__).resolve().parents[2]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


def process_output_buffer() -> deque[str]:
    return deque(maxlen=PROCESS_OUTPUT_LINES)

@dataclass
class ManagedProcess:
    key: str
    label: str
    command: list[str]
    process: subprocess.Popen[bytes] | None = None
    log_path: Path | None = None
    stdout_lines: deque[str] = field(default_factory=process_output_buffer)
    stderr_lines: deque[str] = field(default_factory=process_output_buffer)
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    saved_pid: int | None = None

    @property
    def pid(self) -> int | None:
        if self.process:
            return self.process.pid
        return self.saved_pid

    @property
    def running(self) -> bool:
        if self.process:
            return self.process.poll() is None
        return False

    def to_json(self) -> dict:
        return {
            "pid": self.pid,
            "key": self.key,
            "label": self.label,
            "command": self.command,
            "start_time": self.start_time
        }

    @classmethod
    def from_json(cls, data: dict) -> Self:
        return cls(
            key=data.get("key", ""),
            label=data.get("label", ""),
            command=data.get("command", []),
            saved_pid=data.get("pid"),
            start_time=data.get("start_time", datetime.now().isoformat())
        )


class ProcessManager:
    """Manages all running subprocesses."""

    def __init__(self, state_file: str = "data.json"):
        self.active_processes: list[ManagedProcess] = []
        self.state_file = Path(state_file)

    def __enter__(self):
        self._load_from_file()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown_all()

    def _load_from_file(self):
        if not self.state_file.exists():
            return
        try:
            with open(self.state_file, "r", encoding="utf-8") as file:
                data = json.load(file)
                if isinstance(data, list):
                    for item in data:
                        proc = ManagedProcess.from_json(item)
                        self.active_processes.append(proc)
        except json.JSONDecodeError:
            print(f"Warning: {self.state_file} is corrupted. Starting fresh.")

    def _write_to_file(self):
        with open(self.state_file, "w", encoding="utf-8") as file:
            data = [proc.to_json() for proc in self.active_processes]
            json.dump(data, file, indent=4)

    def scour_ports(self, ports: list[int]):
        """Find and kill any process squatting on critical ports."""
        for port in ports:
            count = self.stop_processes_on_port(port)
            if count > 0:
                print(f"Cleared {count} stale process(es) on port {port}")

    def wipe_databases(self):
        """Delete stale .db files to prevent startup corruption."""
        for filename in TANGO_DATABASE_FILES:
            path = PROJECT_DIR / filename
            if path.exists():
                try:
                    path.unlink()
                    print(f"Deleted stale database: {filename}")
                except OSError as e:
                    print(f"Failed to delete {filename}: {e}")

    def start_process(self, key: str, label: str, command: list[str], env: dict) -> ManagedProcess:
        """Starts a process and tracks it for global cleanup."""
        popen_kwargs = {"env": env, "cwd": PROJECT_DIR}
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
            
        proc = subprocess.Popen(command, **popen_kwargs)
        managed = ManagedProcess(key=key, label=label, command=command, process=proc)
        self.active_processes.append(managed)
        self._write_to_file()
        return managed

    def _terminate_process_tree(self, pid: int, timeout: float = 5.0):
        """Terminates a process tree."""
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            return

        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return

        try:
            subprocess.run(["timeout", str(timeout)], capture_output=True) 
        except Exception:
            pass 

        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def stop_process(self, process: ManagedProcess, timeout: float = 5.0):
        """Stops a single managed process safely."""
        if process.pid:
            self._terminate_process_tree(process.pid, timeout)
        if process in self.active_processes:
            self.active_processes.remove(process)
            self._write_to_file()

    def shutdown_all(self):
        """Performs a clean shutdown of every tracked process."""
        for managed in reversed(self.active_processes):
            self.stop_process(managed)
        self.active_processes.clear()
        if self.state_file.exists():
            self.state_file.unlink()

    def stop_processes_on_port(self, port: int) -> int:
        """Identifies and kills processes occupying a specific TCP port."""
        if os.name == "nt":
            try:
                result = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True)
            except FileNotFoundError:
                return 0

            pids = set()
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) < 5 or parts[0].upper() != "TCP":
                    continue
                if parts[3].upper() == "LISTENING" and parts[1].endswith(f":{port}") and parts[-1].isdigit():
                    pids.add(int(parts[-1]))

            stopped = 0
            for pid in pids:
                res = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
                if res.returncode == 0:
                    stopped += 1
            return stopped

        try:
            result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
        except FileNotFoundError:
            return 0

        stopped = 0
        # Check for PIDs on each line of the stdout
        for pid_str in result.stdout.splitlines():
            if pid_str.strip().isdigit():
                self._terminate_process_tree(int(pid_str.strip()))
                stopped += 1
        return stopped