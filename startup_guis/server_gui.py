#!/usr/bin/env python
from __future__ import annotations

import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

from startup_guis.shared import CONFIG_DIR, GENERATED_CONFIG_DIR, ManagedCommand, load_yaml, write_yaml, yaml_text


DEFAULT_CONFIG_PATH = CONFIG_DIR / 'Spectra300.yaml'
GENERATED_CONFIG_PATH = GENERATED_CONFIG_DIR / 'server_gui.yaml'
DEVICE_MODULES = {
    'camera': 'asyncroscopy.detectors.CAMERA',
    'corrector': 'asyncroscopy.hardware.CORRECTOR',
    'data': 'asyncroscopy.software.DATA',
    'eds': 'asyncroscopy.detectors.EDS',
    'flucam': 'asyncroscopy.detectors.FLUCAM',
    'scan': 'asyncroscopy.hardware.SCAN',
    'stage': 'asyncroscopy.hardware.STAGE',
}


def server_config_from_values(values: dict) -> dict:
    devices = {key: {'module_name': module} for key, module in values['devices'].items() if values['enabled_devices'][key]}
    microscope = {
        'class_name': values['microscope_class'],
        'module_name': values['microscope_module'],
        'description': values['microscope_description'],
    }
    if values['autoscript_host']:
        microscope['host'] = values['autoscript_host']
    if values['autoscript_port']:
        microscope['port'] = int(values['autoscript_port'])
    config = {
        'microscope': microscope,
        'digital_twin': {
            'class_name': values['digital_twin_class'],
            'module_name': values['digital_twin_module'],
            'description': values['digital_twin_description'],
        },
        'devices': devices,
        'tango': {'host': values['tango_host'], 'port': int(values['tango_port'])},
        'tiled': {
            'host': values['tiled_host'],
            'port': int(values['tiled_port']),
            'acquisition_dir': values['acquisition_dir'],
            'autostart': values['tiled_autostart'],
        },
        'device_timeout_seconds': int(values['device_timeout_seconds']),
    }
    return config


class ServerGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Asyncroscopy Server Startup')
        self.geometry('1180x760')
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.command = ManagedCommand(self.enqueue_output, self.process_done)
        self.default_config = load_yaml(DEFAULT_CONFIG_PATH)
        self.vars = self.create_vars()
        self.build()
        self.refresh_yaml()
        self.after(100, self.flush_output)

    def create_vars(self) -> dict[str, tk.Variable]:
        microscope = self.default_config['microscope']
        digital_twin = self.default_config.get('digital_twin', {})
        tango = self.default_config['tango']
        tiled = self.default_config['tiled']
        devices = self.default_config.get('devices', {})
        vars = {
            'microscope_mode': tk.StringVar(value='real'),
            'microscope_class': tk.StringVar(value=microscope.get('class_name', 'ThermoMicroscope')),
            'microscope_module': tk.StringVar(value=microscope.get('module_name', 'asyncroscopy.ThermoMicroscope')),
            'microscope_description': tk.StringVar(value=microscope.get('description', '')),
            'autoscript_host': tk.StringVar(value=str(microscope.get('host', ''))),
            'autoscript_port': tk.StringVar(value=str(microscope.get('port', 9095))),
            'digital_twin_class': tk.StringVar(value=digital_twin.get('class_name', 'DigitalTwin')),
            'digital_twin_module': tk.StringVar(value=digital_twin.get('module_name', 'asyncroscopy.DigitalTwin')),
            'digital_twin_description': tk.StringVar(value=digital_twin.get('description', 'Software digital twin')),
            'tango_host': tk.StringVar(value=str(tango.get('host', 'localhost'))),
            'tango_port': tk.StringVar(value=str(tango.get('port', 9094))),
            'tiled_host': tk.StringVar(value=str(tiled.get('host', 'localhost'))),
            'tiled_port': tk.StringVar(value=str(tiled.get('port', 9091))),
            'acquisition_dir': tk.StringVar(value=tiled.get('acquisition_dir', 'outputs/tiled_acquisitions')),
            'tiled_autostart': tk.BooleanVar(value=bool(tiled.get('autostart', True))),
            'device_timeout_seconds': tk.StringVar(value=str(self.default_config.get('device_timeout_seconds', 120))),
        }
        for key in DEVICE_MODULES:
            vars[f'device_{key}'] = tk.BooleanVar(value=key in devices)
            vars[f'device_module_{key}'] = tk.StringVar(value=(devices.get(key) or {}).get('module_name', DEVICE_MODULES[key]))
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
        self.yaml_preview = ScrolledText(preview, height=18, wrap=tk.NONE)
        self.yaml_preview.pack(fill=tk.BOTH, expand=True)
        ttk.Label(preview, text='Terminal output').pack(anchor='w', pady=(10, 0))
        self.output = ScrolledText(preview, height=12, wrap=tk.WORD)
        self.output.pack(fill=tk.BOTH, expand=True)

    def build_controls(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text='Server startup').grid(row=0, column=0, columnspan=3, sticky='w')
        self.add_row(parent, 1, 'Microscope mode', ttk.Combobox(parent, textvariable=self.vars['microscope_mode'], values=('real', 'dt'), state='readonly'))
        rows = [
            ('Tango host', 'tango_host'), ('Tango port', 'tango_port'), ('Tiled host', 'tiled_host'), ('Tiled port', 'tiled_port'),
            ('Acquisition dir', 'acquisition_dir'), ('Device timeout', 'device_timeout_seconds'), ('Microscope class', 'microscope_class'),
            ('Microscope module', 'microscope_module'), ('Description', 'microscope_description'), ('AutoScript host', 'autoscript_host'),
            ('AutoScript port', 'autoscript_port'), ('Digital twin class', 'digital_twin_class'), ('Digital twin module', 'digital_twin_module'),
            ('Digital twin description', 'digital_twin_description'),
        ]
        for index, (label, key) in enumerate(rows, start=2):
            self.add_row(parent, index, label, ttk.Entry(parent, textvariable=self.vars[key], width=42))
        ttk.Checkbutton(parent, text='Start Tiled HTTP server', variable=self.vars['tiled_autostart']).grid(row=16, column=0, columnspan=3, sticky='w', pady=4)
        ttk.Label(parent, text='Devices').grid(row=17, column=0, sticky='w', pady=(10, 0))
        for offset, key in enumerate(DEVICE_MODULES, start=18):
            ttk.Checkbutton(parent, text=key, variable=self.vars[f'device_{key}']).grid(row=offset, column=0, sticky='w')
            ttk.Entry(parent, textvariable=self.vars[f'device_module_{key}'], width=42).grid(row=offset, column=1, columnspan=2, sticky='ew')
        button_row = 18 + len(DEVICE_MODULES)
        ttk.Button(parent, text='Start', command=self.start).grid(row=button_row, column=0, sticky='ew', pady=(12, 0))
        ttk.Button(parent, text='Stop', command=self.command.stop).grid(row=button_row, column=1, sticky='ew', pady=(12, 0))
        ttk.Button(parent, text='Save current config', command=self.save_config).grid(row=button_row, column=2, sticky='ew', pady=(12, 0))
        parent.columnconfigure(1, weight=1)

    def add_row(self, parent: ttk.Frame, row: int, label: str, widget: tk.Widget) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', pady=2)
        widget.grid(row=row, column=1, columnspan=2, sticky='ew', pady=2)

    def current_config(self) -> dict:
        values = {key: var.get() for key, var in self.vars.items() if not key.startswith('device_')}
        values['enabled_devices'] = {key: self.vars[f'device_{key}'].get() for key in DEVICE_MODULES}
        values['devices'] = {key: self.vars[f'device_module_{key}'].get() for key in DEVICE_MODULES}
        return server_config_from_values(values)

    def refresh_yaml(self) -> None:
        if not hasattr(self, 'yaml_preview'):
            return
        self.yaml_preview.delete('1.0', tk.END)
        self.yaml_preview.insert(tk.END, yaml_text(self.current_config()))

    def save_config(self) -> None:
        path = filedialog.asksaveasfilename(initialdir=CONFIG_DIR, initialfile='server_config.yaml', defaultextension='.yaml', filetypes=[('YAML', '*.yaml'), ('All files', '*.*')])
        if path:
            write_yaml(Path(path), self.current_config())
            self.enqueue_output(f'Saved {path}\n')

    def start(self) -> None:
        config_path = write_yaml(GENERATED_CONFIG_PATH, self.current_config())
        self.command.start(['uv', 'run', 'python', 'startup_scripts/run_servers.py', '--yaml', str(config_path), '--microscope', self.vars['microscope_mode'].get()])

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
    ServerGui().mainloop()
