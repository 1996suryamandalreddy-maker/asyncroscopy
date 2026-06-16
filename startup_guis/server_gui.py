#!/usr/bin/env python
from __future__ import annotations

import queue
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from startup_guis.shared import BODY_FONT, CONFIG_DIR, GENERATED_CONFIG_DIR, SECTION_FONT, TEXT_FONT, TITLE_FONT, ManagedCommand, action_button, append_terminal_text, configure_terminal, load_yaml, write_yaml, yaml_text  # noqa: E402


DEFAULT_CONFIG_PATH = CONFIG_DIR / 'Spectra300.yaml'
GENERATED_CONFIG_PATH = GENERATED_CONFIG_DIR / 'server_gui.yaml'
DEVICE_MODULES = {
    'camera': 'asyncroscopy.instruments.electron_microscope.detectors.camera',
    'corrector': 'asyncroscopy.instruments.electron_microscope.hardware.corrector',
    'data': 'asyncroscopy.data.data',
    'eds': 'asyncroscopy.instruments.electron_microscope.detectors.eds',
    'flucam': 'asyncroscopy.instruments.electron_microscope.detectors.flucam',
    'scan': 'asyncroscopy.instruments.electron_microscope.hardware.scan',
    'stage': 'asyncroscopy.instruments.electron_microscope.hardware.stage',
}


def server_config_from_values(values: dict) -> dict:
    devices = {key: spec for key, spec in values['devices'].items() if values['enabled_devices'][key]}
    microscope = dict(values['microscope'])
    if values['autoscript_host']:
        microscope['host'] = values['autoscript_host']
    if values['autoscript_port']:
        microscope['port'] = int(values['autoscript_port'])
    config = {
        'microscope': microscope,
        'digital_twin': dict(values['digital_twin']),
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
        self.device_config = self.default_config.get('devices', {})
        self.vars = self.create_vars()
        self.build()
        self.refresh_yaml()
        self.after(100, self.flush_output)

    def create_vars(self) -> dict[str, tk.Variable]:
        microscope = self.default_config['microscope']
        tango = self.default_config['tango']
        tiled = self.default_config['tiled']
        vars = {
            'microscope_mode': tk.StringVar(value='real'),
            'autoscript_host': tk.StringVar(value=str(microscope.get('host', ''))),
            'autoscript_port': tk.StringVar(value=str(microscope.get('port', 9095))),
            'tango_host': tk.StringVar(value=str(tango.get('host', 'localhost'))),
            'tango_port': tk.StringVar(value=str(tango.get('port', 9094))),
            'tiled_host': tk.StringVar(value=str(tiled.get('host', 'localhost'))),
            'tiled_port': tk.StringVar(value=str(tiled.get('port', 9091))),
            'acquisition_dir': tk.StringVar(value=tiled.get('acquisition_dir', 'outputs/tiled_acquisitions')),
            'tiled_autostart': tk.BooleanVar(value=bool(tiled.get('autostart', True))),
            'device_timeout_seconds': tk.StringVar(value=str(self.default_config.get('device_timeout_seconds', 120))),
        }
        for key in DEVICE_MODULES:
            vars[f'device_{key}'] = tk.BooleanVar(value=key in self.device_config)
        for var in vars.values():
            var.trace_add('write', lambda *_: self.refresh_yaml())
        return vars

    def build(self) -> None:
        self.option_add('*Font', BODY_FONT)
        style = ttk.Style(self)
        style.configure('TButton', font=BODY_FONT, padding=8)
        style.configure('TCheckbutton', font=BODY_FONT)
        style.configure('TCombobox', font=BODY_FONT)
        style.configure('TEntry', font=BODY_FONT)
        style.configure('TLabel', font=BODY_FONT)
        style.configure('Title.TLabel', font=TITLE_FONT)
        style.configure('Section.TLabelframe.Label', font=SECTION_FONT)
        style.configure('Preview.TLabel', font=SECTION_FONT)
        root = ttk.PanedWindow(self, orient=tk.VERTICAL)
        root.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        top = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        controls = ttk.Frame(top, padding=8)
        preview = ttk.Frame(top, padding=8)
        terminal = ttk.Frame(root, padding=8)
        root.add(top, weight=1)
        root.add(terminal, weight=1)
        top.add(controls, weight=1)
        top.add(preview, weight=1)
        self.build_controls(controls)
        tk.Label(preview, text='Configuration (.yaml)', font=SECTION_FONT).pack(anchor='w', pady=(0, 6))
        self.yaml_preview = ScrolledText(preview, height=18, wrap=tk.NONE, font=TEXT_FONT)
        self.yaml_preview.pack(fill=tk.BOTH, expand=True)
        tk.Label(terminal, text='Terminal output', font=SECTION_FONT).pack(anchor='w', pady=(0, 6))
        self.output = ScrolledText(terminal, height=12, wrap=tk.WORD)
        configure_terminal(self.output)
        self.output.pack(fill=tk.BOTH, expand=True)

    def build_controls(self, parent: ttk.Frame) -> None:
        tk.Label(parent, text='Asyncroscopy Server Startup', font=TITLE_FONT).pack(anchor='w', pady=(0, 10))

        database = self.section(parent, 'Database')
        self.add_row(database, 0, 'Tango host', ttk.Entry(database, textvariable=self.vars['tango_host'], width=34))
        self.add_row(database, 1, 'Tango port', ttk.Entry(database, textvariable=self.vars['tango_port'], width=34))

        microscope = self.section(parent, 'Microscope')
        self.add_row(microscope, 0, 'Mode', ttk.Combobox(microscope, textvariable=self.vars['microscope_mode'], values=('real', 'dt'), state='readonly', width=31))
        self.add_row(microscope, 1, 'AutoScript host', ttk.Entry(microscope, textvariable=self.vars['autoscript_host'], width=34))
        self.add_row(microscope, 2, 'AutoScript port', ttk.Entry(microscope, textvariable=self.vars['autoscript_port'], width=34))
        self.add_row(microscope, 3, 'Device timeout', ttk.Entry(microscope, textvariable=self.vars['device_timeout_seconds'], width=34))

        data_server = self.section(parent, 'Data server')
        self.add_row(data_server, 0, 'Tiled host', ttk.Entry(data_server, textvariable=self.vars['tiled_host'], width=34))
        self.add_row(data_server, 1, 'Tiled port', ttk.Entry(data_server, textvariable=self.vars['tiled_port'], width=34))
        self.add_row(data_server, 2, 'Acquisition dir', ttk.Entry(data_server, textvariable=self.vars['acquisition_dir'], width=34))
        ttk.Checkbutton(data_server, text='Start Tiled HTTP server', variable=self.vars['tiled_autostart']).grid(row=3, column=0, columnspan=2, sticky='w', pady=(6, 0))

        devices = self.section(parent, 'Devices')
        for index, key in enumerate(DEVICE_MODULES):
            ttk.Checkbutton(devices, text=key, variable=self.vars[f'device_{key}']).grid(row=index // 2, column=index % 2, sticky='w', padx=(0, 28), pady=3)

        actions = ttk.Frame(parent)
        actions.pack(fill=tk.X, pady=(12, 0))
        action_button(actions, 'Start', self.start, '#1f7a35', '#2ea043').pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        action_button(actions, 'Stop', self.command.stop, '#b42318', '#dc2626').pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(actions, text='Load config file', command=self.read_config).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(actions, text='Save current config', command=self.save_config).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

    def section(self, parent: ttk.Frame, title: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=title, padding=10, style='Section.TLabelframe')
        frame.pack(fill=tk.X, pady=(0, 10))
        frame.columnconfigure(1, weight=1)
        return frame

    def add_row(self, parent: ttk.Frame, row: int, label: str, widget: tk.Widget) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=4)
        widget.grid(row=row, column=1, sticky='ew', pady=4)

    def current_config(self) -> dict:
        device_keys = {f'device_{key}' for key in DEVICE_MODULES}
        values = {key: var.get() for key, var in self.vars.items() if key not in device_keys}
        values['enabled_devices'] = {key: self.vars[f'device_{key}'].get() for key in DEVICE_MODULES}
        values['devices'] = {key: self.device_config.get(key, {'module_name': DEVICE_MODULES[key]}) for key in DEVICE_MODULES}
        values['microscope'] = self.default_config['microscope']
        values['digital_twin'] = self.default_config.get('digital_twin', {})
        return server_config_from_values(values)

    def refresh_yaml(self) -> None:
        if not hasattr(self, 'yaml_preview'):
            return
        self.yaml_preview.configure(state=tk.NORMAL)
        self.yaml_preview.delete('1.0', tk.END)
        self.yaml_preview.insert(tk.END, yaml_text(self.current_config()))
        self.yaml_preview.configure(state=tk.DISABLED)

    def save_config(self) -> None:
        path = filedialog.asksaveasfilename(initialdir=CONFIG_DIR, initialfile='server_config.yaml', defaultextension='.yaml', filetypes=[('YAML', '*.yaml'), ('All files', '*.*')])
        if path:
            write_yaml(Path(path), self.current_config())
            self.enqueue_output(f'Saved {path}\n')

    def read_config(self) -> None:
        path = filedialog.askopenfilename(initialdir=CONFIG_DIR, filetypes=[('YAML', '*.yaml *.yml'), ('All files', '*.*')])
        if not path:
            return
        config = load_yaml(Path(path))
        self.default_config = config
        self.device_config = config.get('devices', {})
        microscope = config.get('microscope', {})
        tango = config.get('tango', {})
        tiled = config.get('tiled', {})
        self.vars['autoscript_host'].set(str(microscope.get('host', '')))
        self.vars['autoscript_port'].set(str(microscope.get('port', '')))
        self.vars['tango_host'].set(str(tango.get('host', 'localhost')))
        self.vars['tango_port'].set(str(tango.get('port', 9094)))
        self.vars['tiled_host'].set(str(tiled.get('host', 'localhost')))
        self.vars['tiled_port'].set(str(tiled.get('port', 9091)))
        self.vars['acquisition_dir'].set(tiled.get('acquisition_dir', 'outputs/tiled_acquisitions'))
        self.vars['tiled_autostart'].set(bool(tiled.get('autostart', True)))
        self.vars['device_timeout_seconds'].set(str(config.get('device_timeout_seconds', 120)))
        for key in DEVICE_MODULES:
            self.vars[f'device_{key}'].set(key in self.device_config)
        self.refresh_yaml()
        self.enqueue_output(f'Loaded {path}\n')

    def start(self) -> None:
        config_path = write_yaml(GENERATED_CONFIG_PATH, self.current_config())
        self.command.start(['uv', 'run', 'python', '-u', 'startup_scripts/run_servers.py', '--yaml', str(config_path), '--microscope', self.vars['microscope_mode'].get()])

    def enqueue_output(self, text: str) -> None:
        self.output_queue.put(text)

    def process_done(self, returncode: int | None) -> None:
        self.enqueue_output(f'\nProcess exited with return code {returncode}.\n')

    def flush_output(self) -> None:
        while not self.output_queue.empty():
            append_terminal_text(self.output, self.output_queue.get())
        self.after(100, self.flush_output)


if __name__ == '__main__':
    ServerGui().mainloop()
