# Asyncroscopy Broad Sweep Notes

First-pass notes from a broad read of the `main` branch documentation, representative source modules, and commit history. These notes intentionally abstract one level above implementation detail so they can support a scientific method-development paper on automated STEM control.

## Scope Read

- Documentation reviewed: `README.md`, `docs/index.md`, `docs/dev_guide.md`, `docs/asyncroscopy_block_diagram.md`, `docs/digital_twin.md`, `docs/MCP/*`, `docs/Operation/tango_db_mode.md`, `docs/Microscopy/*`, and `docs/Adding_New_Hardware/add_detector.md`.
- Source architecture sampled: `electron_microscope.py`, `auto_script.py`, `digital_twin.py`, `mcp/mcp_server.py`, `data/data.py`, device modules under `instruments/electron_microscope/hardware/` and `instruments/electron_microscope/detectors/`, legacy `servers/protocols/*`, and `clients/notebook_client.py`.
- Git history sampled from first commit through `main` tip. The project history clusters into: early asynchronous server architecture, smart proxy/digital twin/vendor backends, scientific workflow notebooks, PyTango migration, MCP integration, persistent digital twin, Tiled/DATA integration, and operational startup tooling.

## Historical Arc

### 1. Early async server orchestration

- Earliest commits emphasize notebook-callable microscope control, microscope-facing servers, a common transport protocol, and an asynchronous coordinating server.
- The first architecture separated a central server from execution backends, routing commands by prefixes such as `AS`, `Gatan`, and `Ceos`.
- Legacy Twisted code shows a central routing table, framed messages, command dispatch, backend forwarding, and client-side parallel command submission.
- The initial design problem was not just "call the microscope API"; it was coordinating several independently addressable control endpoints while allowing notebook workflows to remain simple.

### 2. Common language across heterogeneous instruments

- The phrase "transport protocol - common language" appears very early in history and remains structurally important.
- Vendor-specific servers emerged for AutoScript/Thermo Fisher, Gatan, CEOS, simulated AutoScript, and digital twin backends.
- The architecture moved toward a stable outer contract that can survive changing vendor APIs.
- A recurring pattern is: isolate vendor-specific API calls inside a narrow adapter, then expose stable commands upward to notebooks, agents, and orchestration logic.

### 3. Digital twins as development infrastructure

- Digital twin work begins early and later becomes a central part of the PyTango architecture.
- The current `DigitalTwin` is not merely a mock. It maintains a persistent simulated sample, stage-coupled viewport, tilt, field of view, beam-position-dependent spectrum, configurable noise, deterministic seeds, file-backed acquisitions, and metadata.
- This makes the twin useful for testing, demos, workflow development, and agent safety exercises without requiring microscope time.
- The twin mirrors the real microscope interface, which allows software workflows to be developed once and later run against real or simulated hardware.

### 4. Scientific workflows as drivers of architecture

- Notebook history includes aberration optimization, atom fabrication, hole/target blasting, drift correction, segmentation, fluence calibration, image acquisition, EDS point spectra, digital twin EDS, tilt, MCP server tutorials, and speed metrics.
- These notebooks appear to be more than examples: they function as pressure tests for whether the control architecture can support real experimental loops.
- Many later refactors simplify acquisition, data writing, scan settings, and startup in response to these workflows.
- The project repeatedly moves functionality from one-off notebooks toward reusable device commands and server infrastructure.

### 5. Migration from Twisted to PyTango

- `README.md` states that `main` now contains the PyTango-based architecture, with the previous Twisted implementation preserved in `twisted-legacy`.
- The PyTango migration reframes the project as distributed instrument infrastructure: each microscope subsystem becomes a discoverable device with attributes, commands, and database properties.
- Tango database mode gives centralized registration, location transparency, deterministic startup, device discovery, configurable inter-device dependencies, distributed deployment, and scalable orchestration.
- This is a major design maturation: the framework moves from a custom async messaging system toward an established controls-system substrate.

### 6. Microscope as orchestrator, not owner of all state

- `electron_microscope.py` and `auto_script.py` repeatedly state that detector settings are read from detector `DeviceProxy` objects; detector devices are the single source of truth for their own parameters.
- The top-level microscope owns high-level acquisition commands and vendor connection logic, while support devices own scan, detector, stage, camera, flucam, corrector, and data state.
- The architecture encourages adding new detector modules rather than growing a monolithic microscope object.
- Current docs direct contributors to add device properties, register proxy addresses, and implement vendor-specific acquisition logic only where appropriate.

### 7. Data as an addressable product of acquisition

- Acquisition commands return DATA/Tiled unique ids or file keys rather than raw in-memory arrays.
- `DATA.py` bridges Tango to a Tiled HTTP data server, storing host, port, save path, server status, and path registration.
- Real and simulated acquisitions save files first, then register those files with Tiled and return a stable key.
- This shifts acquisition semantics from "command returns bytes" to "command produces a registered data object", which is better aligned with reproducibility, downstream analysis, and remote agents.

### 8. MCP as an LLM-facing control layer

- MCP documentation explicitly frames `MCPServer` as a bridge between Tango and LLM agents.
- The server discovers exported Tango devices, filters infrastructure classes, queries device commands, maps Tango types to Python types, creates wrappers, and registers them as MCP tools.
- Source-level introspection recovers real parameter names and docstrings from Tango device classes, improving LLM usability.
- The MCP layer also supports native tools, resources, and prompts, allowing hardware commands and domain guidance to coexist in one agent-facing server.
- Design direction: do not hand-write every LLM tool. Instead, make the runtime self-describing enough that tools can be generated from the control system.

### 9. Explicit contracts at system boundaries

- The developer guide emphasizes type annotations, deterministic return contracts, explicit communication formats, metadata, tests, clear error semantics, and deterministic logging/state reporting.
- MCP type mapping and DevEncoded normalization show this in practice: binary payloads must become JSON-safe objects with metadata and base64 payloads.
- Tango device attributes and commands become formal contracts between UI/notebook/agent layers and instrument subsystems.
- The emphasis is on auditable, deterministic interfaces suitable for hardware-facing science.

### 10. Startup and deployment became first-class concerns

- History includes repeated work on Tango database mode, server runners, configuration, stale server cleanup, cross-platform startup, GUI server launchers, and host/port configurability.
- `startup_scripts/run_servers.py` starts the Tango/device stack, while `startup_scripts/run_mcp.py` starts MCP separately from explicit YAML.
- This suggests the team learned that method development needs reproducible system bring-up, not only individual device APIs.
- Automation of the microscope includes automation of the software stack itself.

## Commit-History Signals

- 2025-10 to 2025-11: asynchronous coordination, backend server routing, digital twin servers, CEOS support, smart proxy, dynamic servers.
- 2025-12: pystemsim integration, aberration optimization, segmentation, dose mapping, physical damage models, atom fabrication workflows, real STEM server compatibility.
- 2026-02: documentation and hardware extension guides begin to formalize architecture.
- 2026-03: base electron microscope abstraction, digital twin, database mode, tests, PyTango workflows, stage/scan/device modules, HAADF/EDS twin, MCP server implementation, command discovery, type mapping, DevEncoded serialization, transport flexibility, and MCP docs.
- 2026-04: persistent digital twin sample, tilt/autofocus/screen current/image shift controls, deployment docs, Tango DB startup, and split server/MCP startup scripts.
- 2026-05: real-time experiments, Tango-Tiled/DATA integration, scan/acquisition refactors, new devices, block diagram, Tiled registration, server initialization simplification, speed improvements.

## Recurrent Design Motifs

- Build stable control abstractions around unstable, proprietary, or vendor-specific APIs.
- Treat hardware modules as independently addressable services.
- Make discovery and introspection part of the runtime.
- Preserve asynchronous and distributed execution as a core capability.
- Keep user workflows notebook-friendly while making the underlying system agent- and automation-ready.
- Use digital twins to collapse the gap between development, testing, demonstration, and real operation.
- Return durable data references and metadata instead of transient process-local objects.
- Prefer explicit device contracts, typed interfaces, and testable behavior over clever internal coupling.
- Keep hardware-specific dependencies optional or isolated so development can proceed off-instrument.
- Let scientific workflow needs drive refactoring from scripts/notebooks into infrastructure.

## Notes for Paper Framing

- Asyncroscopy can be presented as a layered method for automated STEM: vendor APIs at the bottom; Tango devices as the control substrate; DATA/Tiled as the data substrate; MCP as the LLM/agent substrate; notebooks/scripts as human-facing workflow clients.
- The method-development contribution is not only a new automation script. It is an architectural pattern for making advanced microscopy systems discoverable, composable, inspectable, and safe to automate.
- The paper can contrast early custom async routing with the later PyTango/MCP design as an evolution from "message passing among servers" to "self-describing distributed instrument control".
- The design philosophy is pragmatic: preserve compatibility with real microscope constraints, isolate vendor details, keep simulation in lockstep with real command surfaces, and make automation layers consume the same device contracts as human workflows.
