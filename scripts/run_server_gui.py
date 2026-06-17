import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QCheckBox, QTextEdit, QLineEdit, QGroupBox, QFormLayout
)
from PyQt6.QtCore import QProcess, pyqtSignal

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR.parent))

from scripts.run_servers import load_config
PROJECT_DIR = CURRENT_DIR.parent

class EmittingProcess(QProcess):    
    output_ready = pyqtSignal(str)

    def __init__(self, parent=None):        
        super().__init__(parent)        
        self.readyReadStandardOutput.connect(self.handle_stdout)        
        self.readyReadStandardError.connect(self.handle_stderr)

    def handle_stdout(self):        
        self.output_ready.emit(self.readAllStandardOutput().data().decode())

    def handle_stderr(self):        
        self.output_ready.emit(self.readAllStandardError().data().decode())

class ServerManagerGUI(QMainWindow):    
    def __init__(self):        
        super().__init__()        
        self.setWindowTitle("Asyncroscopy Server Manager")        
        self.resize(1100, 650)        
        self.processes = []        
        self.mcp_process = None        
        self.tiled_process = None        
        self.init_ui()
        self.scan_configs()

    def init_ui(self):        
        central_widget = QWidget()        
        main_layout = QHBoxLayout(central_widget)
        left_panel = QVBoxLayout()        
        
        top_config_layout = QFormLayout()
        self.config_combo = QComboBox()
        self.config_combo.currentIndexChanged.connect(self.load_selected_config)
        
        top_config_layout.addRow("Config File:", self.config_combo)
        left_panel.addLayout(top_config_layout)

        self.settings_btn = QPushButton("▶ Expand Settings")
        self.settings_btn.setCheckable(True)
        self.settings_btn.toggled.connect(self.toggle_settings)
        left_panel.addWidget(self.settings_btn)

        self.settings_widget = QWidget()
        self.settings_widget.setVisible(False)
        settings_layout = QFormLayout(self.settings_widget)
        settings_layout.setContentsMargins(0, 5, 0, 5)

        self.tango_host_input = QLineEdit("127.0.0.1")        
        self.tango_port_input = QLineEdit("9094")
        self.tiled_host_input = QLineEdit("127.0.0.1")
        self.tiled_port_input = QLineEdit("9091")
        self.tiled_dir_input = QLineEdit("outputs/tiled_acquisitions")
        self.autoscript_host_input = QLineEdit("127.0.0.1")
        self.autoscript_port_input = QLineEdit("9095")
        self.timeout_input = QLineEdit("120")
        
        self.tiled_cb = QCheckBox("Autostart Tiled Server", checked=True)
        self.clear_old_cb = QCheckBox("Clear old processes first", checked=True)        
        self.start_db_cb = QCheckBox("Start Tango database", checked=True)        
        self.register_dev_cb = QCheckBox("Register devices", checked=True)        

        settings_layout.addRow("Tango Host:", self.tango_host_input)        
        settings_layout.addRow("Tango Port:", self.tango_port_input)        
        settings_layout.addRow("Tiled Host:", self.tiled_host_input)        
        settings_layout.addRow("Tiled Port:", self.tiled_port_input)        
        settings_layout.addRow("Tiled Dir:", self.tiled_dir_input)        
        settings_layout.addRow("AutoScript Host:", self.autoscript_host_input)        
        settings_layout.addRow("AutoScript Port:", self.autoscript_port_input)        
        settings_layout.addRow("Startup Timeout (s):", self.timeout_input)        
        settings_layout.addRow(self.tiled_cb)
        settings_layout.addRow(self.clear_old_cb)        
        settings_layout.addRow(self.start_db_cb)        
        settings_layout.addRow(self.register_dev_cb)
        left_panel.addWidget(self.settings_widget)

        server_group = QGroupBox("Execution Controls")        
        server_layout = QVBoxLayout()        
        
        self.start_all_btn = QPushButton("Run Selected Servers")        
        self.start_all_btn.clicked.connect(self.start_servers)        
        self.start_all_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")        
        server_layout.addWidget(self.start_all_btn)

        self.stop_all_btn = QPushButton("Stop All Servers")        
        self.stop_all_btn.clicked.connect(self.stop_servers)        
        self.stop_all_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")        
        server_layout.addWidget(self.stop_all_btn)
        server_group.setLayout(server_layout)        
        left_panel.addWidget(server_group)

        extra_group = QGroupBox("Extra Services")        
        extra_layout = QVBoxLayout()
        self.start_db_btn = QPushButton("Start Database Separately")        
        self.start_db_btn.clicked.connect(self.start_db)        
        extra_layout.addWidget(self.start_db_btn)

        self.start_mcp_btn = QPushButton("Start MCP Server")        
        self.start_mcp_btn.clicked.connect(self.start_mcp)        
        extra_layout.addWidget(self.start_mcp_btn)

        tiled_standalone_layout = QHBoxLayout()        
        self.tiled_standalone_path = QLineEdit("data.db")        
        self.start_tiled_btn = QPushButton("Start Standalone Data Server")        
        self.start_tiled_btn.clicked.connect(self.start_tiled)
        tiled_standalone_layout.addWidget(self.tiled_standalone_path)
        tiled_standalone_layout.addWidget(self.start_tiled_btn)
        extra_layout.addLayout(tiled_standalone_layout)
        
        extra_group.setLayout(extra_layout)        
        left_panel.addWidget(extra_group)        
        left_panel.addStretch()

        right_panel = QVBoxLayout()        
        right_panel.addWidget(QLabel("Terminal Log Output"))        
        self.log_widget = QTextEdit(readOnly=True)        
        right_panel.addWidget(self.log_widget)

        main_layout.addLayout(left_panel, 1)        
        main_layout.addLayout(right_panel, 2)
        self.setCentralWidget(central_widget)

    def toggle_settings(self, checked):
        self.settings_widget.setVisible(checked)
        self.settings_btn.setText("▼ Collapse Settings" if checked else "▶ Expand Settings")

    def scan_configs(self):
        self.config_combo.clear()
        config_dir = PROJECT_DIR / "configs"
        if config_dir.exists():
            for path in sorted(config_dir.glob("*.yaml")):
                self.config_combo.addItem(path.name, str(path))

    def load_selected_config(self):
        path_str = self.config_combo.currentData()
        if not path_str:
            return
        try:
            cfg = load_config(Path(path_str))
            self.tango_host_input.setText(str(cfg.tango_host))
            self.tango_port_input.setText(str(cfg.tango_port))
            self.tiled_host_input.setText(str(cfg.tiled.host))
            self.tiled_port_input.setText(str(cfg.tiled.port))
            self.tiled_dir_input.setText(str(cfg.tiled.acquisition_dir))
            self.tiled_cb.setChecked(bool(cfg.tiled.autostart))
            self.timeout_input.setText(str(cfg.device_timeout_seconds))
            if cfg.microscope and cfg.microscope.host:
                self.autoscript_host_input.setText(str(cfg.microscope.host))
                self.autoscript_port_input.setText(str(cfg.microscope.port))
        except Exception as e:
            self.log(f"Error loading configuration: {str(e)}\n")

    def log(self, text):        
        self.log_widget.insertPlainText(text)        
        self.log_widget.ensureCursorVisible()

    def start_servers(self):        
        path_str = self.config_combo.currentData()
        if not path_str:
            return
        
        filename = Path(path_str).name.lower()
        mode = "dt" if ("dt" in filename or "twin" in filename) else "real"
        
        self.log(f"Starting servers using {Path(path_str).name} ({mode} mode)...\n")
        cmd = ["uv", "run", "python", "-u", str(PROJECT_DIR / "scripts" / "run_servers.py"), "--yaml", path_str, "--microscope", mode]
        
        process = EmittingProcess(self)        
        process.output_ready.connect(self.log)        
        process.start(cmd[0], cmd[1:])
        self.processes.append(process)

    def stop_servers(self):        
        self.log("Stopping all servers...\n")        
        for p in self.processes:            
            p.kill()        
        self.processes.clear()        
        if self.mcp_process:            
            self.mcp_process.kill()            
        if self.tiled_process:            
            self.tiled_process.kill()            

    def start_db(self):        
        self.log("Database Server not yet implemented\n")      

    def start_mcp(self):        
        self.log("Starting MCP Server...\n")        
        self.mcp_process = EmittingProcess(self)        
        self.mcp_process.output_ready.connect(self.log)        
        self.mcp_process.start("uv", ["run", "python", "-u", str(PROJECT_DIR / "scripts" / "start_mcp_server_cli.py")])
        gui_host = self.tango_host_input.text().strip() or "127.0.0.1"
        gui_port = self.tango_port_input.text().strip() or "9094"
        input_data = f"{gui_host}\n{gui_port}\n"
        self.mcp_process.write(input_data.encode()) #starting solely the mcp server fails to connect most likely due to a lack of a delay 


    def start_tiled(self):        
        self.log(f"Starting Data Server with {self.tiled_standalone_path.text()}...\n")        
        try:            
            self.tiled_process = EmittingProcess(self)            
            self.tiled_process.output_ready.connect(self.log)            
            self.tiled_process.start("tiled", ["serve", "config", self.tiled_standalone_path.text()])        
        except Exception as e:            
            self.log(f"Error starting Data Server: {e}\n")

    def closeEvent(self, event):
        self.stop_servers()
        event.accept()

if __name__ == "__main__":    
    app = QApplication(sys.argv)    
    window = ServerManagerGUI()    
    window.show()    
    sys.exit(app.exec())