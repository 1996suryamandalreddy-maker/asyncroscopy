# AS_server_SimAtomRes.py
# Digital Twin made by Austin Houston
# for simulating atomic resolution images

"""
designed to work ith Ceos digital twin
to get real probes and simulate images
mirrors the real thing.
"""
import ast
import sys
import time
import numpy as np

from asyncroscopy.clients.notebook_client import NotebookClient
from asyncroscopy.servers.protocols.execution_protocol import ExecutionProtocol
from asyncroscopy.servers.protocols.utils import package_message, unpackage_message

from pathlib import Path
from ase.io import read
from scipy.spatial import Voronoi
from ase import Atoms
from ase.build import bulk



try:
    from ase.io import read
except ImportError:
    print("ASE not installed; some functionality may be limited.")
try:
    from asyncroscopy.cloned_repos.pystemsim import data_generator as dg
except ImportError:
    print("pystemsim not installed; some functionality may be limited.")

import pyTEMlib.probe_tools as pt
import pyTEMlib.image_tools as it

from twisted.internet import reactor, protocol
from twisted.internet.defer import Deferred, inlineCallbacks, returnValue

# sys.path.insert(0, "C:\\AE_future\\autoscript_1_14\\")
sys.path.insert(0, "/Users/austin/Desktop/Projects/autoscript_tem_microscope_client")
import autoscript_tem_microscope_client as auto_script


# FACTORY — holds shared state (persistent across all connections)
class ASFactory(protocol.Factory):
    def __init__(self):
        # persistent states for all protocol instances
        self.microscope = None
        self.detectors = {}
        self.status = "Offline"
        self.sample = None

    def buildProtocol(self, addr):
        """Create a new protocol instance and attach the factory (shared state)."""
        proto = ASProtocol()
        proto.factory = self
        return proto


# PROTOCOL — handles per-connection command execution
class ASProtocol(ExecutionProtocol):
    def __init__(self):
        super().__init__()
        allowed = []
        for name, value in ExecutionProtocol.__dict__.items():
            if callable(value) and not name.startswith("_"):
                allowed.append(name)
        self.allowed_commands = set(allowed)

    def connect_AS(self, args: dict):
        """Connect to the microscope via AutoScript"""
        host = args.get('host')
        port = args.get('port')
        
        self.log.info(f"[AS] Connecting to microscope at {host}:{port}...")
        self.factory.microscope = 'Debugging'
        self.factory.status = "Ready"
        msg = "Connected to Digital Twin microscope."
        self.sendString(package_message(msg))

    def set_current(self, args: dict):
        """Set the beam current (pA)"""
        beam_current = args.get('beam_current')
        self.factory.beam_current = float(beam_current)
        self.log.info(f"[AS] Beam current set to {beam_current} pA")
        msg = f"Beam current set to {beam_current} pA"
        self.sendString(package_message(msg))

    def get_scanned_image(self, args: dict):
        """Return a scanned image using the indicated detector"""
        scanning_detector = args.get('scanning_detector')

        size = args.get('size')
        size = int(size)

        dwell_time = args.get('dwell_time')
        dwell_time = float(dwell_time)

        fov = args.get('fov') # Angstrom
        fov = float(fov) # Angstrom (100 is good)
        pixel_size = fov / size
        edge_crop = 20

        blur_noise_level = args.get('blur_noise', 0.5)
        blur_noise_level = float(blur_noise_level)

        if dwell_time * size * size > 600: # frame time > 10 minutes
            self.log.info(f"[AS] Error: Acquisition too long: {dwell_time*size*size} seconds")
            return None
        else:
            self.log.info(f"[AS] Acquiring image with detector '{scanning_detector}', size={size}, dwell_time={dwell_time}s")
            self.factory.status = "Busy"

            # get probe
            # connect to central through the client
            tem = NotebookClient.connect(host='localhost',port=9000)
            ab = tem.send_command(destination = 'Ceos', command = 'getAberrations', args = {})
            ab = ast.literal_eval(ab)
            ab['acceleration_voltage'] = 60e3 # eV
            ab['FOV'] = fov /10 # nm
            ab['convergence_angle'] = 30 # mrad
            ab['wavelength'] = it.get_wavelength(ab['acceleration_voltage'])

            if self.factory.sample == None:
                # create sample
                # oversized so we can induce drift
                sample_fov = (fov*1.5, fov*1.5, fov*0.5)  # angstroms
                grain_size = 15  # average, used to get n_grains
                empty_grains = 0.10  # 10% empty grains
                lattice_constant = 4.08
                desired_angles = [(0, 0, 0), (60, 0, 0), (45,45,45)]

                # Create gold supercell
                gold_bulk = bulk('Au', 'fcc', a=lattice_constant)
                repeat_bounds = np.max(sample_fov)
                repeat_factors = (int(repeat_bounds/lattice_constant), int(repeat_bounds/lattice_constant), int(repeat_bounds/lattice_constant))
                supercell = gold_bulk.repeat(repeat_factors)

                # Generate grain centers
                n_grains = sample_fov[0] * sample_fov[1] // (4/3 * np.pi * grain_size**2)
                n_grains = np.max([1, int(n_grains)])
                grain_centers = np.random.rand(n_grains, 3) * np.array(sample_fov)
                vor = Voronoi(grain_centers[:, :2])

                # Determine which grains are empty
                n_empty = int(n_grains * empty_grains)
                empty_grain_indices = set(np.random.choice(n_grains, n_empty, replace=False))

                # Generate rotation angles for each grain
                grain_angles = []
                for i in range(n_grains):
                    if i < len(desired_angles):
                        grain_angles.append(desired_angles[i])
                    else:
                        grain_angles.append(tuple(np.random.rand(3) * 360))

                def rotation_matrix(alpha, beta, gamma):
                    """Create rotation matrix from Euler angles (degrees)"""
                    a, b, g = np.radians([alpha, beta, gamma])
                    Rz = np.array([[np.cos(a), -np.sin(a), 0],[np.sin(a), np.cos(a), 0],[0, 0, 1]])
                    Ry = np.array([[np.cos(b), 0, np.sin(b)],[0, 1, 0],[-np.sin(b), 0, np.cos(b)]])
                    Rx = np.array([[1, 0, 0],[0, np.cos(g), -np.sin(g)],[0, np.sin(g), np.cos(g)]])
                    return Rz @ Ry @ Rx

                # Process each grain
                all_positions = []
                all_grain_labels = []
                for grain_idx in range(n_grains):
                    if grain_idx in empty_grain_indices:
                        continue
                    
                    # Get rotation for this grain
                    angles = grain_angles[grain_idx]
                    R = rotation_matrix(*angles)
                    positions = supercell.get_positions().copy()
                    positions -= positions.mean(axis=0)
                    positions = positions @ R.T
                    positions += grain_centers[grain_idx]
                    mask_fov = ((positions[:, 0] >= 0) & (positions[:, 0] < sample_fov[0]) &
                                (positions[:, 1] >= 0) & (positions[:, 1] < sample_fov[1]) &
                                (positions[:, 2] >= 0) & (positions[:, 2] < sample_fov[2]))
                    positions = positions[mask_fov]
                    
                    # Assign to nearest grain center (Voronoi)
                    distances = np.linalg.norm(positions[:, np.newaxis, :] - grain_centers[np.newaxis, :, :], axis=2)
                    closest_grain = np.argmin(distances, axis=1)
                    mask_voronoi = (closest_grain == grain_idx)
                    grain_positions = positions[mask_voronoi]
                    all_positions.append(grain_positions)
                    all_grain_labels.extend([grain_idx] * len(grain_positions))

                # Combine all atoms
                all_positions = np.vstack(all_positions)
                all_grain_labels = np.array(all_grain_labels)
                xtal = Atoms('Au' * len(all_positions), positions=all_positions)
                self.factory.sample = xtal # atoms object
                # move_stage sets sample back to None

            # create image
            edge = 2 * edge_crop * pixel_size
            frame = (0,fov+edge,0,fov+edge) # limits of the image in angstroms
            potential = dg.create_pseudo_potential(self.factory.sample, pixel_size, sigma=1, bounds=frame, atom_frame=11)
            # will ba problem here. right now, it crops from bottom left, not middle.
            # to do drift correction, must change the frame.  should work then?
            # first attempt at drift: just do drift = np.random, then shift frame by that much
            probe = dg.get_probe(ab, potential)
            image = dg.convolve_kernel(potential, probe)
            image = image[edge_crop:-edge_crop, edge_crop:-edge_crop]

            # add shot noise
            scan_time = dwell_time * size * size
            counts = scan_time * (self.factory.beam_current * 1e-12) / (1.602e-19) / 100
            noisy_image = dg.poisson_noise(image, counts=counts)

            # add gaussian blob-like noise
            blur_noise = dg.lowfreq_noise(noisy_image, noise_level=0.1, freq_scale=.5)
            noisy_image += blur_noise * blur_noise_level

            # time.sleep(1)
            sim_im = np.array(noisy_image, dtype=np.float32)
            self.factory.status = "Ready"
            self.sendString(package_message(sim_im))


    def get_stage(self, args=None):
        """Return current stage position (placeholder)"""
        positions = [np.random.uniform(-10, 10) for _ in range(5)]
        positions = np.array(positions, dtype=np.float32)
        self.sendString(package_message(positions))

    def move_stage(self, args: dict):
        """Move the stage by specified amounts (x, y, z, alpha, beta)"""
        move_type = args.get('move_type', 'relative')  # 'relative' or 'absolute'
        x = args.get('x', None)
        y = args.get('y', None)
        z = args.get('z', None)
        alpha = args.get('alpha', None)
        beta = args.get('beta', None)

        if move_type == 'relative':
            self.log.info(f"[AS] Moving stage by deltas")
        elif move_type == 'absolute':
            self.log.info(f"[AS] Moving stage to absolutes")
        else:
            self.log.info(f"[AS] No movement parameters provided.")

        self.factory.sample = None
        msg = "stage move finished"
        self.sendString(package_message(msg))


    def get_status(self, args=None):
        """Return the server status"""
        msg = f"Microscope is {self.factory.status}"
        self.sendString(package_message(msg))


if __name__ == "__main__":
    port = 9001
    print(f"[AS] Server running on port {port}...")
    reactor.listenTCP(port, ASFactory())
    reactor.run()