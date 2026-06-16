from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from typing import Callable

import yaml


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_DIR / 'configs'
GENERATED_CONFIG_DIR = PROJECT_DIR / 'outputs' / 'startup_configs'
BODY_FONT = ('TkDefaultFont', 15)
TITLE_FONT = ('TkDefaultFont', 24, 'bold')
SECTION_FONT = ('TkDefaultFont', 18, 'bold')
TEXT_FONT = ('Menlo', 16)
ACTION_FONT = ('TkDefaultFont', 18, 'bold')

OutputCallback = Callable[[str], None]
DoneCallback = Callable[[int | None], None]
ANSI_PATTERN = re.compile(r'\x1b\[[0-9;]*m')


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding='utf-8')) or {}


def yaml_text(config: dict) -> str:
    return yaml.safe_dump(config, sort_keys=False)


def write_yaml(path: Path, config: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml_text(config), encoding='utf-8')
    return path


def action_button(parent, text: str, command, color: str, active_color: str) -> tk.Label:
    button = tk.Label(
        parent,
        text=text,
        bg=color,
        fg='white',
        font=ACTION_FONT,
        relief=tk.SOLID,
        bd=2,
        padx=18,
        pady=12,
        cursor='hand2',
    )
    button.bind('<ButtonPress-1>', lambda _event: button.configure(bg=active_color))
    button.bind('<ButtonRelease-1>', lambda _event: (button.configure(bg=color), command()))
    button.bind('<Leave>', lambda _event: button.configure(bg=color))
    return button


def configure_terminal(widget: tk.Text) -> None:
    widget.configure(font=TEXT_FONT, bg='#0d1117', fg='#c9d1d9', insertbackground='#c9d1d9')
    widget.tag_configure('command', foreground='#79c0ff')
    widget.tag_configure('ok', foreground='#3fb950')
    widget.tag_configure('run', foreground='#39c5cf')
    widget.tag_configure('wait', foreground='#d29922')
    widget.tag_configure('fail', foreground='#ff7b72')
    widget.tag_configure('skip', foreground='#8b949e')
    widget.tag_configure('plain', foreground='#c9d1d9')


def append_terminal_text(widget: tk.Text, text: str) -> None:
    widget.configure(state=tk.NORMAL)
    for line in text.splitlines(keepends=True):
        clean = ANSI_PATTERN.sub('', line)
        upper = clean.upper()
        if clean.startswith('$ '):
            tag = 'command'
        elif 'FAIL' in upper or 'ERROR' in upper or 'TRACEBACK' in upper or 'FAILED' in upper:
            tag = 'fail'
        elif ' OK ' in upper or upper.strip().startswith('OK') or ' READY ' in upper:
            tag = 'ok'
        elif 'RUN' in upper:
            tag = 'run'
        elif 'WAIT' in upper:
            tag = 'wait'
        elif 'SKIP' in upper:
            tag = 'skip'
        else:
            tag = 'plain'
        widget.insert(tk.END, clean, tag)
    widget.configure(state=tk.DISABLED)
    widget.see(tk.END)


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
        env = {**os.environ, 'PYTHONUNBUFFERED': '1'}
        popen_kwargs = {'cwd': PROJECT_DIR, 'env': env, 'stdout': subprocess.PIPE, 'stderr': subprocess.STDOUT, 'text': True, 'bufsize': 1}
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
            while True:
                line = self.process.stdout.readline()
                if line:
                    self.output(line)
                    continue
                if self.process.poll() is not None:
                    rest = self.process.stdout.read()
                    if rest:
                        self.output(rest)
                    break
                threading.Event().wait(0.05)
        self.done(self.process.wait())
