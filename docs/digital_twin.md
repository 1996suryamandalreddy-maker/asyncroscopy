# DigitalTwin

`DigitalTwin` is the simulated version of the `ThermoMicroscope`.  
It provides realistic-enough image and spectrum behavior for development, testing, and demos without requiring AutoScript or hardware.

## How it works

1. On startup, the twin generates a **persistent synthetic sample** (deterministic from seed).
2. Stage pose (`x, y, z, alpha, beta`) defines the current viewport into that sample.
3. `acquire_scanned_image()` calls the inherited microscope command, which delegates to `_acquire_stem_image()`.
4. `_acquire_stem_image()` renders the current pose/FoV, writes a TIFF with metadata, and returns the DATA/Tiled key when a DATA device is configured.
5. `acquire_spectrum("eds")` delegates to `_acquire_spectrum()`, which estimates composition at the current beam position and saves a `.npy` spectrum for now.

This means moving the stage navigates the sample, and revisiting the same pose can reproduce the same view when stage noise is disabled.

## Available features

- Persistent sample per device session
- Deterministic sample generation via seed
- Stage-coupled navigation in **XY + Z + alpha/beta tilt**
- Beam-position-dependent spectrum simulation
- File-backed acquisition output instead of in-memory image caches
- Configurable stage move noise
- Viewport metadata reporting
- Manual sample regeneration with a new seed

Spectrum files are currently saved as `.npy` with a JSON metadata sidecar. This is a temporary format; simulated spectra should migrate to `.emd` to match microscope EDS output.

## Key properties

- `sample_seed`: controls deterministic sample generation
- `sample_particle_count`: controls synthetic particle count
- `sample_extent_scale`: controls sample XY size relative to FoV
- `stage_move_noise_std`: adds Gaussian perturbation to stage moves

## Key commands

- `move_stage([x, y, z, alpha, beta])`
- `get_stage()`
- `set_fov(fov)`
- `acquire_scanned_image()`
- `place_beam([x, y])`
- `acquire_spectrum("eds")`
- `get_viewport_metadata()`
- `regenerate_sample(seed)`
