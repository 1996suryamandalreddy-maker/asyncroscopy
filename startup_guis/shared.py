from __future__ import annotations

import os
import signal
import subprocess
import threading
from pathlib import Path
from typing import Callable

import yaml


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_DIR / 'configs'
GENERATED_CONFIG_DIR = PROJECT_DIR / 'outputs' / 'startup_configs'

OutputCallback = Callable[[str], None]
DoneCallback = Callable[[int | None], None]


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding='utf-8')) or {}


def yaml_text(config: dict) -> str:
    return yaml.safe_dump(config, sort_keys=False)


def write_yaml(path: Path, config: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml_text(config), encoding='utf-8')
    return path


class ManagedCommand:
    def __init__(self, output: OutputCallback, done: DoneCallback):
        self.output = output
        self.done = done
        self.process: subprocess.Popen[str] | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, command: list[str]) -> None:
        if self.running:
            self.output('A process is already running.\n')
            return
        popen_kwargs = {'cwd': PROJECT_DIR, 'stdout': subprocess.PIPE, 'stderr': subprocess.STDOUT, 'text': True, 'bufsize': 1}
        if os.name == 'nt':
            popen_kwargs['creationflags'] = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
        else:
            popen_kwargs['start_new_session'] = True
        self.output(f'$ {" ".join(command)}\n')
        self.process = subprocess.Popen(command, **popen_kwargs)
        threading.Thread(target=self._read_output, daemon=True).start()

    def stop(self) -> None:
        if not self.running:
            self.output('No process is running.\n')
            return
        assert self.process is not None
        if os.name == 'nt':
            self.process.terminate()
        else:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            except OSError:
                self.process.terminate()
        self.output('Stop requested.\n')

    def _read_output(self) -> None:
        assert self.process is not None
        if self.process.stdout is not None:
            for line in self.process.stdout:
                self.output(line)
        self.done(self.process.wait())
