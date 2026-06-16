# Asyncroscopy Method Paper Outline for Microscopists

This outline translates the design philosophy notes into a logical flow for a scientific method-development paper. The intended reader is a microscopist who cares about reliable microscope operation, reproducible experiments, flexible hardware setups, and practical automation, but may not want the software architecture presented as its own end.

## Working Thesis

Asyncroscopy is a method for turning a scanning transmission electron microscope into a modular, self-describing, and automation-ready experimental platform. The central idea is to separate microscope functions into discoverable devices, isolate vendor-specific APIs behind stable interfaces, register acquired data as durable products, and expose the same control surface to notebooks, scripts, simulation, and agentic automation.

## 1. Why STEM Automation Needs an Instrument Architecture

Start with the experimental problem rather than the software problem.

- Modern STEM experiments increasingly involve coordinated motion, imaging, spectroscopy, aberration tuning, drift correction, segmentation, dose control, and real-time decision making.
- A single monolithic control script becomes brittle when detectors, microscope vendors, data systems, and analysis routines change.
- A useful automation method must support both hands-on notebook workflows and higher-level autonomous workflows.
- The goal is not only to automate one acquisition, but to make the microscope system composable, inspectable, and reproducible.

Possible paper language:

> We designed Asyncroscopy around the observation that automated STEM is a distributed experimental-control problem: microscope state, detector settings, acquisition routines, analysis, and data storage must be coordinated without hiding critical state inside a single script.

## 2. Model the Microscope as a Distributed Experimental System

Introduce the main architectural abstraction in microscope terms.

- Asyncroscopy treats the STEM as a set of addressable experimental subsystems: microscope, scan settings, stage, detectors, camera, corrector, data service, and digital twin.
- PyTango provides the device model: each subsystem exposes attributes, commands, and configuration properties.
- The Tango database acts like a live registry of the instrument configuration, so clients can discover what devices are running and how they are connected.
- This is analogous to describing the experimental setup as a connected instrument graph rather than as a single opaque API.

Paper purpose:

- Explain why the device-based view matters for microscope operation.
- Emphasize practical benefits: discovery, modular startup, remote control, device replacement, and clearer troubleshooting.

## 3. Make the Microscope Device an Orchestrator

Describe how acquisition is coordinated without centralizing all state.

- The top-level microscope device coordinates acquisition and vendor communication.
- Detector, scan, stage, and data settings live in their own devices.
- Acquisition commands read the current settings from these devices at the time of acquisition.
- This keeps the microscope command surface simple while preventing detector-specific state from becoming buried inside the microscope class.

Paper purpose:

- Present this as an experimental-control principle: the microscope coordinates subsystems, but subsystem state remains independently visible and adjustable.
- This helps microscopists reason about what settings were active during an acquisition.

## 4. Isolate Vendor APIs to Preserve Hardware Flexibility

Connect directly to the user's flexible microscope setup goal.

- Vendor-specific calls, such as Thermo Fisher AutoScript, are localized inside narrow adapter classes such as `ThermoMicroscope`.
- The rest of the system communicates through stable Asyncroscopy/Tango commands.
- Earlier architecture included separate AutoScript, Gatan, CEOS, simulated AutoScript, and digital twin backends, reinforcing the same principle.
- A new vendor or instrument configuration should require changing a small adapter layer, not rewriting notebooks, agents, data registration, or analysis workflows.

Paper purpose:

- Frame Asyncroscopy as a portable automation method rather than a one-microscope script.
- Emphasize that vendor isolation is what makes flexible microscope setups scientifically sustainable.

## 5. Preserve Asynchronous and Parallel Capabilities

Explain async behavior in terms of experimental needs.

- Automated STEM often requires multiple operations to be coordinated: move the stage, update scan parameters, acquire images, trigger detectors, register data, and run analysis.
- The project began with asynchronous central-server coordination and parallel notebook commands.
- The later PyTango design preserves the same distributed-control idea using independent device servers.
- Asynchronous design prevents the whole experiment from being limited by a single blocking command path.

Paper purpose:

- Present asynchronous operation as a requirement for real microscope automation, not a software embellishment.
- Tie it to real use cases: real-time experiments, multimodal acquisition, drift-aware control, and data registration during acquisition.

## 6. Treat Acquired Data as a Durable Experimental Product

Move from control to data reproducibility.

- Acquisition commands return registered data identifiers or file keys, not transient in-memory arrays.
- Real and simulated acquisitions write files with metadata and register them through the DATA/Tiled service.
- This makes data products addressable by notebooks, scripts, analysis routines, and agents after the acquisition completes.
- The method separates "perform acquisition" from "retrieve and analyze data", which is important for reproducibility and distributed workflows.

Paper purpose:

- Emphasize traceability: each acquisition produces a durable object with metadata.
- This is especially valuable when automated workflows generate many intermediate images, spectra, or scans.

## 7. Use a Digital Twin as the Simulation-to-Hardware Development Loop

This combines the original themes 8 and 10.

- The digital twin shares the same base microscope command surface as the real microscope.
- It provides persistent sample state, stage-coupled navigation, tilt, field of view, beam-position-dependent spectra, configurable noise, deterministic seeds, metadata, and file-backed output.
- Workflows can be developed, tested, and demonstrated in simulation before being transferred to the real instrument.
- Because simulation and hardware use the same commands, moving from twin to microscope changes the backend, not the scientific workflow.

Paper purpose:

- Present the digital twin as part of the scientific method, not just a software test mock.
- It reduces microscope time, supports safer agent development, and provides a controlled environment for workflow validation.

## 8. Expose the Live Instrument to Agentic Control Through Introspection

This combines the original themes 5 and 6.

- MCP provides an agent-facing layer over the Tango control system.
- Instead of manually writing a static tool list, the MCP server discovers running Tango devices, queries their commands, maps their input/output types, and exposes the non-blocked results as tools.
- The agent-facing interface is therefore tied to the actual running instrument configuration stored in the Tango database.
- This reduces mismatch between what an agent can request and what the microscope system can currently do.
- The same typed control surface can be used by notebooks, scripts, and LLM agents.

Paper purpose:

- Avoid over-centering the paper on LLMs; present agentic control as one consumer of the same robust instrument interface.
- The key method contribution is runtime introspection: the instrument can describe its available actions to higher-level automation systems.

## 9. Use Explicit Contracts for Safe Scientific Automation

Explain reliability in laboratory terms.

- Public commands and attributes should have typed, deterministic behavior.
- Binary or complex data must include explicit metadata and JSON-safe transport when exposed to agents or remote clients.
- Errors should be visible and diagnostic rather than silent.
- Tests and simulation protect against regressions before microscope time is used.
- These contracts matter because the same device commands may be called by humans, notebooks, scripts, GUIs, and agents.

Paper purpose:

- Frame software reliability as experimental reliability.
- Make the case that explicit interfaces are required for auditable autonomous microscopy.

## 10. Automate System Bring-Up as Part of the Method

Close the architecture loop with operations.

- A microscope automation method must reliably start the database, register devices, launch device servers, wait for readiness, configure host/port values, and start the MCP layer.
- Asyncroscopy includes startup scripts that encode this operational sequence.
- This makes the software state of the instrument reproducible, not just the microscope command sequence.

Paper purpose:

- Include deployment/startup as part of method development.
- Reproducible automation requires a reproducible control stack.

## Suggested Paper Flow

1. Motivation: automated STEM requires coordinated, reproducible control of many microscope subsystems.
2. Architecture: represent the microscope as distributed, discoverable Tango devices.
3. Orchestration: use the top-level microscope device to coordinate subsystem state and acquisition.
4. Vendor flexibility: isolate proprietary APIs behind narrow adapters.
5. Asynchronous operation: support parallel and nonblocking experimental workflows.
6. Data handling: return durable registered data objects with metadata.
7. Digital twin: develop and validate workflows on a shared simulation/hardware interface.
8. Agentic interface: expose the live device graph to LLM agents through MCP and runtime introspection.
9. Reliability: enforce typed contracts, explicit metadata, clear errors, and tests.
10. Deployment: automate startup and device registration so the method is reproducible in the lab.

## One-Paragraph Methods Summary

Asyncroscopy implements STEM automation as a distributed experimental-control architecture. Microscope subsystems are represented as discoverable Tango devices with explicit attributes and commands, while the top-level microscope device orchestrates acquisition by reading state from scan, detector, stage, and data devices. Vendor-specific APIs are isolated behind narrow adapters, allowing the same high-level workflow to target real hardware or a digital twin. Acquisitions produce durable DATA/Tiled references with metadata rather than transient arrays. The same live device graph can be used from notebooks, scripts, or LLM agents through an MCP server that introspects the running Tango database and exposes typed tools. This design supports asynchronous workflows, flexible microscope configurations, simulation-to-hardware transfer, and reproducible system bring-up.

## Short Figure Concept

Figure title: "Asyncroscopy as a layered automation method for STEM"

- Bottom layer: real microscope hardware, detectors, stage, corrector, vendor APIs.
- Control layer: Tango devices for microscope, scan, stage, detectors, DATA, and digital twin.
- Data layer: file-backed acquisitions registered with DATA/Tiled.
- Automation layer: notebooks, scripts, GUI, and MCP/LLM agents all using the same device contracts.
- Feedback arrows: analysis and agent decisions update device commands for the next acquisition.
