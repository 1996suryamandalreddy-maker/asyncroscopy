"""
An MCPServer with specific resources for the Thermo Spectra 300 TEM.
"""

from asyncroscopy.mcp.mcp_server import MCPServer
from fastmcp.resources import resource

class ThermoMCP(MCPServer):
    """
    An MCP Server customized for the Thermo Spectra 300 TEM.
    """
    SUPPORTED_HARDWARE = ["ThermoMicroscope"]
    DIGITAL_TWIN = "DigitalTwin"

    def __init__(
        self,
        name: str = "ThermoSpectra300_MCP",
        tango_host: str = "localhost",
        tango_port: int = 9094,
        **kwargs
    ):
        """
        Initialize the ThermoMCP server.
        """
        super().__init__(
            name=name,
            tango_host=tango_host,
            tango_port=tango_port,
            **kwargs
        )

    @resource("spectra300://microscope_specs")
    def get_spectra_specs(self) -> str:
        """Get the hardware specifications for the Thermo Spectra 300 TEM."""
        return (
            "Thermo Spectra 300 TEM Specifications:\n"
            "- Acceleration Voltage: 30-300 kV\n"
            "- Modes: TEM, STEM\n"
            "- Detectors: Panther STEM, EDS (Dual-X / Super-X), EELS (Continuum/Quantum), Ceta Camera\n"
            "- Resolution: High-resolution capabilities down to sub-Angstrom limits\n"
            "- Application: Atomic-resolution characterization, analytical chemistry, and in-situ experiments."
        )

    @resource("spectra300://detector_config")
    def get_detector_config(self) -> str:
        """Get the typical detector configurations for the Thermo Spectra 300."""
        return (
            "Thermo Spectra 300 Common Detectors:\n"
            "HAADF (High-Angle Annular Dark-Field): Used for Z-contrast imaging in STEM mode.\n"
            "DF/BF (Dark/Bright Field): Additional STEM detectors.\n"
            "CETA: High-speed CMOS camera for TEM imaging and diffraction.\n"
            "EDS (Energy-Dispersive X-Ray Spectroscopy): Compositional analysis.\n"
            "EELS (Electron Energy Loss Spectroscopy): Elemental mapping and chemical state analysis."
        )
