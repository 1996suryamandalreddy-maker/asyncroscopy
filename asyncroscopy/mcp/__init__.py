__all__ = ["MCPServer", "ThermoMCP"]


def __getattr__(name):
    if name == "MCPServer":
        from .mcp_server import MCPServer

        return MCPServer
    if name == "ThermoMCP":
        from .ThermoMCP import ThermoMCP

        return ThermoMCP
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
