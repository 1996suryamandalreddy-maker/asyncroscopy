# Modifying `ThermoMicroscope`

`ThermoMicroscope` (asyncroscopy/ThermoMicroscope.py) is the AutoScript vendor
subclass of [`Microscope`](modify_base_microscope.md). It owns the AutoScript
connection and implements the `_helper` methods the base declares abstract.

**Every `_acquire_*` helper ends the same way:** call the AutoScript API, then
hand the result to `save_acquisition(self, data_server, ...)`
(asyncroscopy/software/DataWriter.py). That writes one HDF5 file per acquisition,
registers it via the `data` proxy (asyncroscopy/software/DATA.py), and returns
the **Tiled key string** the command sends back to the client. `data_server`
comes from `self._detector_proxies.get("data")`. See
[data_integration.md](../Tiled_server/data_integration.md).

If you're editing this class, you're usually doing one of these:

1. **Adding or modifying an attribute**
   (Expose new device state clients can read.)

2. **Updating an attribute read/write method**
   (Control how a value is validated, stored, or synced with AutoScript.)

3. **Implementing or changing a `_helper`**
   Implement the base's abstract `_helper` (or override an optional one).
   Acquisition helpers must finish via `save_acquisition` so the command
   returns a Tiled key. Examples already present: `_acquire_scanned_image`,
   `_acquire_camera_image`, `_acquire_scanned_data_advanced`,
   `_acquire_spectrum`.

4. **Adding a new detector**
   Add a device property for its address (on the base), register it in
   `_connect_detector_proxies`, and read it in the relevant helper.
   ```python
   "newdet": self.newdet_device_address,
   ```

5. **Adding or changing acquisition settings**
   Extend what is read from the detector devices — dwell time, resolution,
   scan region, exposure — and pass it into the AutoScript `*Settings` object
   inside the helper. Pick the right `dataset_name` for `save_acquisition`
   (e.g. `"image"`, `"spectrum"`, `"stem_data"`); multi-detector results are
   stored under `image/<DETECTOR>`.
