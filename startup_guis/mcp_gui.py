#!/usr/bin/env python
from __future__ import annotations

import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

import yaml

from startup_guis.shared import CONFIG_DIR, GENERATED_CONFIG_DIR, ManagedCommand, load_yaml, write_yaml, yaml_text


DEFAULT_CONFIG_PATH = CONFIG_DIR / 'mcp.yaml'
GENERATED_CONFIG_PATH = GENERATED_CONFIG_DIR / 'mcp_gui.yaml'


def mcp_config_from_values(values: dict) -> dict:
    blocked_functions = yaml.safe_load(values['blocked_functions']) if values['blocked_functions'].strip() else {}
    return {
        'tango': {'host': values['tango_host'], 'port': int(values['tango_port'])},
        'mcp': {
            'name': values['name'],
            'transport': values['transport'],
            'http_host': values['http_host'],
            'http_port': int(values['http_port']),
            'data_device_address': values['data_device_address'],
            'quiet': values['quiet'],
            'blocked_classes': [item.strip() for item in values['blocked_classes'].split(',') if item.strip()],
            'blocked_functions': blocked_functions or {},
        },
    }


class McpGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Asyncroscopy MCP Startup')
        self.geometry('1080x720')
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.command = ManagedCommand(self.enqueue_output, self.process_done)
        self.default_config = load_yaml(DEFAULT_CONFIG_PATH)
        self.vars = self.create_vars()
        self.build()
        self.refresh_yaml()
        self.after(100, self.flush_output)

    def create_vars(self) -> dict[str, tk.Variable]:
        tango = self.default_config['tango']
        mcp = self.default_config['mcp']
        vars = {
            'tango_host': tk.StringVar(value=str(tango.get('host', 'localhost'))),
            'tango_port': tk.StringVar(value=str(tango.get('port', 9094))),
            'name': tk.StringVar(value=mcp.get('name', 'Spectra300_MCP')),
            'transport': tk.StringVar(value=mcp.get('transport', 'streamable-http')),
            'http_host': tk.StringVar(value=mcp.get('http_host', '127.0.0.1')),
            'http_port': tk.StringVar(value=str(mcp.get('http_port', 8000))),
            'data_device_address': tk.StringVar(value=mcp.get('data_device_address', 'asyncroscopy/data/default')),
            'quiet': tk.BooleanVar(value=bool(mcp.get('quiet', True))),
            'blocked_classes': tk.StringVar(value=', '.join(mcp.get('blocked_classes', []))),
        }
        for var in vars.values():
            var.trace_add('write', lambda *_: self.refresh_yaml())
        return vars

    def build(self) -> None:
        root = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        root.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        controls = ttk.Frame(root, padding=8)
        preview = ttk.Frame(root, padding=8)
        root.add(controls, weight=1)
        root.add(preview, weight=1)
        self.build_controls(controls)
        ttk.Label(preview, text='Generated YAML').pack(anchor='w')
        self.yaml_preview = ScrolledText(preview, height=16, wrap=tk.NONE)
        self.yaml_preview.pack(fill=tk.BOTH, expand=True)
        ttk.Label(preview, text='Terminal output').pack(anchor='w', pady=(10, 0))
        self.output = ScrolledText(preview, height=12, wrap=tk.WORD)
        self.output.pack(fill=tk.BOTH, expand=True)

    def build_controls(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text='MCP startup').grid(row=0, column=0, columnspan=2, sticky='w')
        rows = [
            ('Tango host', 'tango_host'), ('Tango port', 'tango_port'), ('Name', 'name'), ('Transport', 'transport'),
            ('HTTP host', 'http_host'), ('HTTP port', 'http_port'), ('DATA device', 'data_device_address'), ('Blocked classes', 'blocked_classes'),
        ]
        for index, (label, key) in enumerate(rows, start=1):
            widget = ttk.Combobox(parent, textvariable=self.vars[key], values=('streamable-http',), state='readonly') if key == 'transport' else ttk.Entry(parent, textvariable=self.vars[key], width=42)
            ttk.Label(parent, text=label).grid(row=index, column=0, sticky='w', pady=2)
            widget.grid(row=index, column=1, sticky='ew', pady=2)
        ttk.Checkbutton(parent, text='Quiet mode', variable=self.vars['quiet']).grid(row=9, column=0, columnspan=2, sticky='w', pady=4)
        ttk.Label(parent, text='Blocked functions YAML').grid(row=10, column=0, columnspan=2, sticky='w', pady=(10, 0))
        self.blocked_functions = ScrolledText(parent, height=8, width=42, wrap=tk.NONE)
        self.blocked_functions.insert(tk.END, yaml.safe_dump(self.default_config['mcp'].get('blocked_functions', {}), sort_keys=False))
        self.blocked_functions.grid(row=11, column=0, columnspan=2, sticky='nsew')
        self.blocked_functions.bind('<KeyRelease>', lambda _event: self.refresh_yaml())
        ttk.Button(parent, text='Start', command=self.start).grid(row=12, column=0, sticky='ew', pady=(12, 0))
        ttk.Button(parent, text='Stop', command=self.command.stop).grid(row=12, column=1, sticky='ew', pady=(12, 0))
        ttk.Button(parent, text='Save current config', command=self.save_config).grid(row=13, column=0, columnspan=2, sticky='ew', pady=(6, 0))
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(11, weight=1)

    def current_config(self) -> dict:
        values = {key: var.get() for key, var in self.vars.items()}
        values['blocked_functions'] = self.blocked_functions.get('1.0', tk.END) if hasattr(self, 'blocked_functions') else ''
        return mcp_config_from_values(values)

    def refresh_yaml(self) -> None:
        if not hasattr(self, 'yaml_preview'):
            return
        self.yaml_preview.delete('1.0', tk.END)
        try:
            self.yaml_preview.insert(tk.END, yaml_text(self.current_config()))
        except yaml.YAMLError as exc:
            self.yaml_preview.insert(tk.END, f'Invalid blocked_functions YAML: {exc}')

    def save_config(self) -> None:
        path = filedialog.asksaveasfilename(initialdir=CONFIG_DIR, initialfile='mcp_config.yaml', defaultextension='.yaml', filetypes=[('YAML', '*.yaml'), ('All files', '*.*')])
        if path:
            write_yaml(Path(path), self.current_config())
            self.enqueue_output(f'Saved {path}\n')

    def start(self) -> None:
        config_path = write_yaml(GENERATED_CONFIG_PATH, self.current_config())
        self.command.start(['uv', 'run', 'python', 'startup_scripts/run_mcp.py', '--yaml', str(config_path)])

    def enqueue_output(self, text: str) -> None:
        self.output_queue.put(text)

    def process_done(self, returncode: int | None) -> None:
        self.enqueue_output(f'\nProcess exited with return code {returncode}.\n')

    def flush_output(self) -> None:
        while not self.output_queue.empty():
            self.output.insert(tk.END, self.output_queue.get())
            self.output.see(tk.END)
        self.after(100, self.flush_output)


if __name__ == '__main__':
    McpGui().mainloop()
