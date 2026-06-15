# Asyncroscopy Design Philosophy Themes

Second-pass synthesis from `asyncroscopy_broad_sweep_notes.md`. These are the design philosophies emphasized strongly enough to mention in a scientific method-development paper.

## 1. Design the microscope as a distributed, discoverable system

Asyncroscopy treats the STEM not as one opaque API endpoint, but as a network of addressable devices: microscope, scan settings, stage, detectors, corrector, camera, flucam, data server, and digital twin. PyTango database mode provides the registry, location transparency, startup order, device discovery, and configuration properties that make this practical.

Paper angle: automation becomes more robust when the instrument is modeled as a set of discoverable services with explicit contracts, rather than a single monolithic control script.

## 2. Keep the top-level microscope as an orchestrator

The `Microscope`/`ThermoMicroscope` layer coordinates acquisitions and vendor communication, but detector and support-device state lives in dedicated Tango devices. Scan dwell time, image size, scan region, detector settings, stage pose, and data paths are not hidden inside the microscope class.

Paper angle: separation of orchestration from subsystem state improves extensibility, testing, and cross-vendor adaptation.

## 3. Isolate vendor APIs behind narrow adapters

Thermo AutoScript calls live in `ThermoMicroscope`; earlier history includes separate AS, Gatan, CEOS, simulated AS, and twin servers. The surrounding system talks through stable Asyncroscopy/Tango commands, not directly to each vendor library.

Paper angle: flexible microscope setups require vendor-specific code to be localized. The rest of the automation stack should not change when the hardware backend changes.

## 4. Preserve asynchronous and parallel operation as a first principle

The project began with asynchronous central-server coordination, backend routing, and notebook clients capable of sending parallel commands. Later PyTango adoption changes the substrate but preserves the distributed-control premise.

Paper angle: STEM automation often requires coordinating acquisition, motion, detectors, analysis, and data registration without blocking the whole workflow on one operation. Asynchronous design is therefore a scientific capability, not just a software preference.

## 5. Design with LLM agents in mind

The MCP server is not a thin manually written command list. It discovers Tango devices, queries commands, maps Tango types to Python types, normalizes binary data, recovers source-level parameter names/docstrings, and exposes tools, resources, and prompts to LLM agents.

Paper angle: LLM compatibility is strongest when the instrument runtime is self-describing. MCP plus Tango introspection lets agents operate through the same typed, documented control surface used by notebooks and scripts.

## 6. Couple agent control to runtime introspection and database state

The Tango database stores which devices exist and how they relate; MCP reads that live system state to generate tools. This creates an agent-facing interface coupled to the actual running instrument configuration rather than to a stale hand-authored schema.

Paper angle: agentic microscope control should be grounded in live device discovery and current configuration, reducing mismatch between what an agent thinks exists and what the laboratory system is actually running.

## 7. Treat data products as registered, durable objects

Acquisition commands increasingly return DATA/Tiled keys or filenames, not raw arrays. Real and simulated acquisitions save files with metadata, register them through the DATA/Tiled device, and return a reference for later access.

Paper angle: automated microscopy needs traceable data products. Returning durable data references supports reproducibility, remote access, downstream analysis, and agent workflows.

## 8. Make digital twins part of the method, not an afterthought

The digital twin mirrors the microscope command surface while providing persistent sample state, stage-coupled navigation, tilt, deterministic seeds, configurable noise, image rendering, spectrum simulation, metadata, and file-backed output.

Paper angle: a digital twin lowers the cost and risk of developing autonomous workflows. It supports testing, demonstration, and algorithm development before microscope time is used.

## 9. Prefer explicit, typed, testable contracts

The developer guide repeatedly emphasizes typing, explicit return formats, deterministic metadata, clear errors, logging/state reporting, and tests. MCP type conversion and DevEncoded normalization are concrete examples.

Paper angle: automated instrument control requires infrastructure-grade reliability. Strong public contracts are especially important when humans, notebooks, scripts, and LLM agents all share the same control surface.

## 10. Keep simulation and hardware on the same interface

AutoScript can be unavailable on development machines, and the framework can still import, test, and run simulated workflows. The real microscope and digital twin share the base microscope commands.

Paper angle: the same acquisition workflow can be exercised in simulation and then transferred to hardware with minimal code changes, which accelerates method development and reduces hardware risk.

## 11. Let scientific workflows drive infrastructure

The git history shows repeated movement from notebooks and experiments into reusable architecture: aberration optimization, segmentation, atom fabrication, drift correction, EDS, tilt, real-time experiments, advanced scanning, and data registration.

Paper angle: Asyncroscopy is workflow-led infrastructure. The architecture emerged from real STEM automation tasks, then abstracted the repeated needs into devices, servers, data contracts, and agent interfaces.

## 12. Automate system bring-up, not just microscope actions

Startup scripts register devices, launch Tango DB, start subdevice servers, wait for readiness, clean stale servers, configure host/port values, and start MCP. This operational layer receives substantial historical attention.

Paper angle: autonomous microscopy depends on reproducible software deployment. A method paper should include system initialization as part of the automation method.

## Condensed Thesis

Asyncroscopy's design philosophy is to make STEM automation a self-describing distributed control problem. Vendor APIs are isolated behind microscope adapters; subsystem state is separated into Tango devices; data products are registered through a data service; digital twins share the hardware-facing command surface; and MCP exposes the live, typed, introspected runtime to LLM agents. This makes automation flexible across microscope setups, robust under asynchronous workflows, and suitable for both human notebook users and agentic control.

## Phrases Worth Reusing in the Paper

- "self-describing distributed instrument control"
- "the microscope as an orchestrator of typed device contracts"
- "vendor isolation through narrow hardware adapters"
- "LLM-facing tools generated from live runtime introspection"
- "simulation and hardware share the same command surface"
- "acquisition returns durable data references rather than transient arrays"
- "automation of the microscope includes automation of system bring-up"
- "workflow-led infrastructure for autonomous STEM"

## Mapping to User-Identified Philosophies

- Design with LLM in mind: MCP server, Tango database discovery, source introspection, tool/resource/prompt registration, type mapping, and JSON-safe data normalization.
- Design with asynchronous capabilities: early central/back-end server architecture, parallel notebook client calls, distributed Tango devices, independent server processes, and non-monolithic acquisition/data registration.
- Flexible vendor communication: AutoScript/Thermo code localized to `ThermoMicroscope`, legacy AS/Gatan/CEOS backends, digital twin alternatives, and stable high-level Asyncroscopy/Tango commands above the vendor layer.
