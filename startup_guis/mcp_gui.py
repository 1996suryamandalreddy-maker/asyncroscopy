#!/usr/bin/env python
from __future__ import annotations

import queue
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

import yaml

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from startup_guis.shared import BODY_FONT, CONFIG_DIR, GENERATED_CONFIG_DIR, SECTION_FONT, TEXT_FONT, TITLE_FONT, ManagedCommand, action_button, append_terminal_text, configure_terminal, load_yaml, write_yaml, yaml_text  # noqa: E402


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
        self.yaml_preview = ScrolledText(preview, height=16, wrap=tk.NONE, font=TEXT_FONT)
        self.yaml_preview.pack(fill=tk.BOTH, expand=True)
        tk.Label(terminal, text='Terminal output', font=SECTION_FONT).pack(anchor='w', pady=(0, 6))
        self.output = ScrolledText(terminal, height=12, wrap=tk.WORD)
        configure_terminal(self.output)
        self.output.pack(fill=tk.BOTH, expand=True)

    def build_controls(self, parent: ttk.Frame) -> None:
        tk.Label(parent, text='Asyncroscopy MCP Startup', font=TITLE_FONT).pack(anchor='w', pady=(0, 10))

        database = self.section(parent, 'Database')
        self.add_row(database, 0, 'Tango host', ttk.Entry(database, textvariable=self.vars['tango_host'], width=34))
        self.add_row(database, 1, 'Tango port', ttk.Entry(database, textvariable=self.vars['tango_port'], width=34))

        mcp_server = self.section(parent, 'MCP server')
        self.add_row(mcp_server, 0, 'Name', ttk.Entry(mcp_server, textvariable=self.vars['name'], width=34))
        self.add_row(mcp_server, 1, 'Transport', ttk.Combobox(mcp_server, textvariable=self.vars['transport'], values=('streamable-http',), state='readonly', width=31))
        self.add_row(mcp_server, 2, 'HTTP host', ttk.Entry(mcp_server, textvariable=self.vars['http_host'], width=34))
        self.add_row(mcp_server, 3, 'HTTP port', ttk.Entry(mcp_server, textvariable=self.vars['http_port'], width=34))
        ttk.Checkbutton(mcp_server, text='Quiet mode', variable=self.vars['quiet']).grid(row=4, column=0, columnspan=2, sticky='w', pady=(6, 0))

        data_access = self.section(parent, 'Data access')
        self.add_row(data_access, 0, 'DATA device', ttk.Entry(data_access, textvariable=self.vars['data_device_address'], width=34))

        access_control = self.section(parent, 'Access control')
        self.add_row(access_control, 0, 'Blocked classes', ttk.Entry(access_control, textvariable=self.vars['blocked_classes'], width=34))
        ttk.Label(access_control, text='Blocked functions YAML').grid(row=1, column=0, columnspan=2, sticky='w', pady=(8, 4))
        self.blocked_functions = ScrolledText(access_control, height=8, width=42, wrap=tk.NONE)
        self.blocked_functions.insert(tk.END, yaml.safe_dump(self.default_config['mcp'].get('blocked_functions', {}), sort_keys=False))
        self.blocked_functions.grid(row=2, column=0, columnspan=2, sticky='nsew')
        self.blocked_functions.bind('<KeyRelease>', lambda _event: self.refresh_yaml())
        access_control.rowconfigure(2, weight=1)

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
        values = {key: var.get() for key, var in self.vars.items()}
        values['blocked_functions'] = self.blocked_functions.get('1.0', tk.END) if hasattr(self, 'blocked_functions') else ''
        return mcp_config_from_values(values)

    def refresh_yaml(self) -> None:
        if not hasattr(self, 'yaml_preview'):
            return
        self.yaml_preview.configure(state=tk.NORMAL)
        self.yaml_preview.delete('1.0', tk.END)
        try:
            self.yaml_preview.insert(tk.END, yaml_text(self.current_config()))
        except yaml.YAMLError as exc:
            self.yaml_preview.insert(tk.END, f'Invalid blocked_functions YAML: {exc}')
        self.yaml_preview.configure(state=tk.DISABLED)

    def save_config(self) -> None:
        path = filedialog.asksaveasfilename(initialdir=CONFIG_DIR, initialfile='mcp_config.yaml', defaultextension='.yaml', filetypes=[('YAML', '*.yaml'), ('All files', '*.*')])
        if path:
            write_yaml(Path(path), self.current_config())
            self.enqueue_output(f'Saved {path}\n')

    def read_config(self) -> None:
        path = filedialog.askopenfilename(initialdir=CONFIG_DIR, filetypes=[('YAML', '*.yaml *.yml'), ('All files', '*.*')])
        if not path:
            return
        config = load_yaml(Path(path))
        tango = config.get('tango', {})
        mcp = config.get('mcp', {})
        self.vars['tango_host'].set(str(tango.get('host', 'localhost')))
        self.vars['tango_port'].set(str(tango.get('port', 9094)))
        self.vars['name'].set(mcp.get('name', 'Spectra300_MCP'))
        self.vars['transport'].set(mcp.get('transport', 'streamable-http'))
        self.vars['http_host'].set(mcp.get('http_host', '127.0.0.1'))
        self.vars['http_port'].set(str(mcp.get('http_port', 8000)))
        self.vars['data_device_address'].set(mcp.get('data_device_address', 'asyncroscopy/data/default'))
        self.vars['quiet'].set(bool(mcp.get('quiet', True)))
        self.vars['blocked_classes'].set(', '.join(mcp.get('blocked_classes', [])))
        self.blocked_functions.delete('1.0', tk.END)
        self.blocked_functions.insert(tk.END, yaml.safe_dump(mcp.get('blocked_functions', {}), sort_keys=False))
        self.refresh_yaml()
        self.enqueue_output(f'Loaded {path}\n')

    def start(self) -> None:
        config_path = write_yaml(GENERATED_CONFIG_PATH, self.current_config())
        self.command.start(['uv', 'run', 'python', '-u', 'startup_scripts/run_mcp.py', '--yaml', str(config_path)])

    def enqueue_output(self, text: str) -> None:
        self.output_queue.put(text)

    def process_done(self, returncode: int | None) -> None:
        self.enqueue_output(f'\nProcess exited with return code {returncode}.\n')

    def flush_output(self) -> None:
        while not self.output_queue.empty():
            append_terminal_text(self.output, self.output_queue.get())
        self.after(100, self.flush_output)


if __name__ == '__main__':
    McpGui().mainloop()
