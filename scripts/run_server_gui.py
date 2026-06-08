import sys
import os
import yaml
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QCheckBox,
    QTextEdit, QLineEdit, QGroupBox, QFormLayout
)
from PyQt6.QtCore import QProcess, pyqtSignal
from scripts.run_servers import SUPPORT_DEVICES

PROJECT_DIR = Path(__file__).resolve().parents[1]

class EmittingProcess(QProcess):
    output_ready = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.readyReadStandardOutput.connect(self.handle_stdout)
        self.readyReadStandardError.connect(self.handle_stderr)

    def handle_stdout(self):
        data = self.readAllStandardOutput().data().decode()
        self.output_ready.emit(data)

    def handle_stderr(self):
        data = self.readAllStandardError().data().decode()
        self.output_ready.emit(data)


class ServerManagerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Asyncroscopy Server Manager")
        self.resize(1000, 600)
        self.processes = []
        self.mcp_process = None
        self.tiled_process = None
        self.yaml_config = self.load_yaml_config()
        self.init_ui()

    def load_yaml_config(self):
        config_path = PROJECT_DIR / "tools" / "servers_config.yaml"
        if config_path.exists():
            with open(config_path, "r") as f:
                return yaml.safe_load(f)
        return {}

    def init_ui(self):
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)

        left_panel = QVBoxLayout()

        config_group = QGroupBox("Configuration")
        config_layout = QFormLayout()

        self.tango_host_input = QLineEdit("127.0.0.1")
        self.tango_port_input = QLineEdit("9094")
        
        self.clear_old_cb = QCheckBox("Clear old processes first")
        self.clear_old_cb.setChecked(True)
        self.start_db_cb = QCheckBox("Start Tango database")
        self.start_db_cb.setChecked(True)
        self.register_dev_cb = QCheckBox("Register devices")
        self.register_dev_cb.setChecked(True)
        self.timeout_input = QLineEdit("120")

        config_layout.addRow("Tango Host:", self.tango_host_input)
        config_layout.addRow("Tango Port:", self.tango_port_input)
        config_layout.addRow("Startup Timeout (s):", self.timeout_input)
        config_layout.addRow(self.clear_old_cb)
        config_layout.addRow(self.start_db_cb)
        config_layout.addRow(self.register_dev_cb)

        self.microscope_combo = QComboBox()
        if self.yaml_config:
            for key in self.yaml_config.keys():
                self.microscope_combo.addItem(key.replace("_", " ").title(), key)
        else:
            self.microscope_combo.addItem("Thermo Microscope", "thermo_microscope")

        self.microscope_combo.currentIndexChanged.connect(self.update_mode_combo)

        self.mode_combo = QComboBox()
        self.update_mode_combo()

        config_layout.addRow("Microscope Type:", self.microscope_combo)
        config_layout.addRow("Startup Mode:", self.mode_combo)
        
        self.load_yaml_btn = QPushButton("Load from YAML")
        self.load_yaml_btn.clicked.connect(self.update_mode_combo)
        config_layout.addWidget(self.load_yaml_btn)

        config_group.setLayout(config_layout)
        left_panel.addWidget(config_group)

        server_group = QGroupBox("Servers to Start")
        server_layout = QVBoxLayout()
        self.server_checkboxes = {}
        
        try:
            for dev in SUPPORT_DEVICES:
                cb = QCheckBox(f"{dev.key.title()} ({dev.class_name})")
                cb.setChecked(True)
                self.server_checkboxes[dev.key] = cb
                server_layout.addWidget(cb)
        except ImportError:
            pass

        self.start_all_btn = QPushButton("Run Selected Servers")
        self.start_all_btn.clicked.connect(self.start_servers)
        self.start_all_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        server_layout.addWidget(self.start_all_btn)

        self.stop_all_btn = QPushButton("Stop All Servers")
        self.stop_all_btn.clicked.connect(self.stop_servers)
        self.stop_all_btn.setStyleSheet("background-color: #f44336; color: white;")
        server_layout.addWidget(self.stop_all_btn)

        server_group.setLayout(server_layout)
        left_panel.addWidget(server_group)

        extra_group = QGroupBox("Extra Services")
        extra_layout = QVBoxLayout()

        self.start_db_btn = QPushButton("Start Database")
        self.start_db_btn.clicked.connect(self.start_db)
        extra_layout.addWidget(self.start_db_btn)

        self.start_mcp_btn = QPushButton("Start MCP Server")
        self.start_mcp_btn.clicked.connect(self.start_mcp)
        extra_layout.addWidget(self.start_mcp_btn)

        tiled_layout = QHBoxLayout()
        self.tiled_cb = QCheckBox("Data Server")
        self.tiled_path = QLineEdit("data.db")
        tiled_layout.addWidget(self.tiled_cb)
        tiled_layout.addWidget(self.tiled_path)
        
        self.start_tiled_btn = QPushButton("Start Data Server")
        self.start_tiled_btn.clicked.connect(self.start_tiled)
        
        extra_layout.addLayout(tiled_layout)
        extra_layout.addWidget(self.start_tiled_btn)

        extra_group.setLayout(extra_layout)
        left_panel.addWidget(extra_group)
        left_panel.addStretch()

        right_panel = QVBoxLayout()
        right_panel.addWidget(QLabel("Terminal Log Output"))
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        right_panel.addWidget(self.log_widget)

        main_layout.addLayout(left_panel, 1)
        main_layout.addLayout(right_panel, 2)

        self.setCentralWidget(central_widget)

    def update_mode_combo(self):
        self.mode_combo.clear()
        if not self.yaml_config:
            self.mode_combo.addItem("Real Microscope", "real")
            self.mode_combo.addItem("Digital Twin", "dt")
            return

        key = self.microscope_combo.currentData()
        config_list = self.yaml_config.get(key, [])
        for item in config_list:
            self.mode_combo.addItem(item["name"], item["value"])

    def log(self, text):
        self.log_widget.insertPlainText(text)
        self.log_widget.ensureCursorVisible()

    def start_servers(self):
        mode = self.mode_combo.currentData()
        self.log(f"Starting servers in {mode} mode...\n")
        
        cmd = ["uv", "run", "python", "-u", str(PROJECT_DIR / "scripts" / "run_servers.py"), "--microscope", mode]
        
        process = EmittingProcess(self)
        process.output_ready.connect(self.log)
        process.start(cmd[0], cmd[1:])
        
        host = self.tango_host_input.text()
        port = self.tango_port_input.text()
        clear_old = 'Y' if self.clear_old_cb.isChecked() else 'N'
        start_db = 'Y' if self.start_db_cb.isChecked() else 'N'
        register_dev = 'Y' if self.register_dev_cb.isChecked() else 'N'
        timeout = self.timeout_input.text()
        
        process.write(f"{host}\n{port}\n{clear_old}\n{start_db}\n{register_dev}\n{timeout}\n\n".encode())
        
        self.processes.append(process)

    def stop_servers(self):
        self.log("Stopping all servers...\n")
        for p in self.processes:
            p.kill()
        self.processes.clear()
        if self.mcp_process:
            self.mcp_process.kill()
            self.mcp_process = None
        if self.tiled_process:
            self.tiled_process.kill()
            self.tiled_process = None

    def start_db(self):
        self.log("Starting Database...\n")
        cmd = ["sh", str(PROJECT_DIR / "scripts" / "1_start_db.sh")]
        try:
            db_process = EmittingProcess(self)
            db_process.output_ready.connect(self.log)
            db_process.start(cmd[0], cmd[1:])
            self.processes.append(db_process)
        except Exception as e:
            self.log(f"Error starting database: {e}\n")

    def start_mcp(self):
        self.log("Starting MCP Server...\n")
        cmd = ["uv", "run", "python", "-u", str(PROJECT_DIR / "scripts" / "start_mcp_server_cli.py")]
        self.mcp_process = EmittingProcess(self)
        self.mcp_process.output_ready.connect(self.log)
        self.mcp_process.start(cmd[0], cmd[1:])

    def start_tiled(self):
        if not self.tiled_cb.isChecked():
            self.log("Data Server checkbox is not checked.\n")
            return
            
        data_path = self.tiled_path.text()
        self.log(f"Starting Data Server with {data_path}...\n")
        cmd = ["tiled", "serve", "sqlite", data_path]
        try:
            self.tiled_process = EmittingProcess(self)
            self.tiled_process.output_ready.connect(self.log)
            self.tiled_process.start(cmd[0], cmd[1:])
        except Exception as e:
            self.log(f"Error starting Data Server: {e}\n")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ServerManagerGUI()
    window.show()
    sys.exit(app.exec())
