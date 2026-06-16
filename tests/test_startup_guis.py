from startup_guis import mcp_gui, server_gui


def test_server_gui_builds_server_yaml():
    config = server_gui.server_config_from_values(
        {
            'microscope_class': 'ThermoMicroscope',
            'microscope_module': 'asyncroscopy.ThermoMicroscope',
            'microscope_description': 'Real microscope',
            'autoscript_host': '10.0.0.1',
            'autoscript_port': '9095',
            'digital_twin_class': 'DigitalTwin',
            'digital_twin_module': 'asyncroscopy.DigitalTwin',
            'digital_twin_description': 'Twin',
            'devices': {'data': 'asyncroscopy.software.DATA', 'scan': 'asyncroscopy.hardware.SCAN'},
            'enabled_devices': {'data': True, 'scan': False},
            'tango_host': 'localhost',
            'tango_port': '9094',
            'tiled_host': 'localhost',
            'tiled_port': '9091',
            'acquisition_dir': 'outputs/tiled_acquisitions',
            'tiled_autostart': True,
            'device_timeout_seconds': '120',
        }
    )

    assert config['microscope']['host'] == '10.0.0.1'
    assert config['microscope']['port'] == 9095
    assert config['devices'] == {'data': {'module_name': 'asyncroscopy.software.DATA'}}
    assert config['tango'] == {'host': 'localhost', 'port': 9094}


def test_mcp_gui_builds_mcp_yaml():
    config = mcp_gui.mcp_config_from_values(
        {
            'tango_host': '10.0.0.2',
            'tango_port': '9094',
            'name': 'Spectra300_MCP',
            'transport': 'streamable-http',
            'http_host': '0.0.0.0',
            'http_port': '8000',
            'data_device_address': 'asyncroscopy/data/default',
            'quiet': True,
            'blocked_classes': 'DataBase, DServer',
            'blocked_functions': '"*":\n  - Init\n  - Kill\n',
        }
    )

    assert config['tango'] == {'host': '10.0.0.2', 'port': 9094}
    assert config['mcp']['http_host'] == '0.0.0.0'
    assert config['mcp']['blocked_classes'] == ['DataBase', 'DServer']
    assert config['mcp']['blocked_functions'] == {'*': ['Init', 'Kill']}
