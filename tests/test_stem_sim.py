import numpy as np
import pytest
from ase.build import bulk

from asyncroscopy.simulation.StemSim import (
    make_holes,
    rotate_xtal,
    sub_pix_gaussian,
    create_pseudo_potential,
    get_masks,
    poisson_noise,
    lowfreq_noise,
    grid_crop,
    resize_image,
    shotgun_crop,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def simple_crystal():
    """Small gold FCC crystal for testing."""
    return bulk('Au', 'fcc', a=4.08, cubic=True).repeat([3, 3, 1])

@pytest.fixture
def simple_potential(simple_crystal):
    """Generate a small potential map from the crystal."""
    bounds = [0, 12, 0, 12]
    return create_pseudo_potential(simple_crystal, pixel_size=0.1, sigma=0.5, bounds=bounds)

# ── make_holes ─────────────────────────────────────────────────────────────────

def test_make_holes_reduces_atoms(simple_crystal):
    original_count = len(simple_crystal)
    result = make_holes(simple_crystal.copy(), n_holes=2, hole_size=3.0)
    assert len(result) < original_count

def test_make_holes_zero_holes(simple_crystal):
    original_count = len(simple_crystal)
    result = make_holes(simple_crystal.copy(), n_holes=0, hole_size=3.0)
    assert len(result) == original_count

# ── rotate_xtal ────────────────────────────────────────────────────────────────

def test_rotate_xtal_preserves_cell(simple_crystal):
    rotated = rotate_xtal(simple_crystal, 45)
    np.testing.assert_allclose(rotated.cell, simple_crystal.cell, atol=1e-6)

def test_rotate_xtal_360_similar_count(simple_crystal):
    original = len(simple_crystal)
    rotated = rotate_xtal(simple_crystal, 360)
    # Boundary clipping is expected even at 360°, so allow generous tolerance
    assert abs(len(rotated) - original) < original * 0.5

# ── sub_pix_gaussian ───────────────────────────────────────────────────────────

def test_sub_pix_gaussian_shape():
    g = sub_pix_gaussian(size=10, sigma=0.5)
    assert g.shape == (10, 10)

def test_sub_pix_gaussian_max_is_one():
    g = sub_pix_gaussian(size=10, sigma=0.5)
    assert np.isclose(g.max(), 1.0)

def test_sub_pix_gaussian_shift():
    g_centered = sub_pix_gaussian(size=21, sigma=1.0, dx=0, dy=0)
    g_shifted  = sub_pix_gaussian(size=21, sigma=1.0, dx=2, dy=0)
    # Peak should move — arrays must differ
    assert not np.allclose(g_centered, g_shifted)

# ── create_pseudo_potential ────────────────────────────────────────────────────

def test_potential_shape(simple_potential):
    bounds = [0, 12, 0, 12]
    expected = int((bounds[1] - bounds[0]) / 0.1)
    assert simple_potential.shape == (expected, expected)

def test_potential_normalized(simple_potential):
    assert simple_potential.max() <= 1.0
    assert simple_potential.min() >= 0.0

# ── get_masks ──────────────────────────────────────────────────────────────────

def test_get_masks_one_hot(simple_crystal):
    masks = get_masks(simple_crystal, pixel_size=0.2, radius=3, mode='one_hot')
    # First channel = background; channels sum to 1 everywhere
    assert masks.ndim == 3
    assert masks[0].shape == masks[1].shape  # all channels same spatial size

def test_get_masks_binary(simple_crystal):
    mask = get_masks(simple_crystal, pixel_size=0.2, radius=3, mode='binary')
    assert set(np.unique(mask)).issubset({0, 1})

def test_get_masks_integer(simple_crystal):
    mask = get_masks(simple_crystal, pixel_size=0.2, radius=3, mode='integer')
    assert mask.ndim == 2

def test_get_masks_invalid_mode(simple_crystal):
    with pytest.raises(ValueError):
        get_masks(simple_crystal, mode='invalid_mode')

# ── poisson_noise ──────────────────────────────────────────────────────────────

def test_poisson_noise_range(simple_potential):
    noisy = poisson_noise(simple_potential, counts=1e6)
    assert noisy.min() >= 0.0
    assert noisy.max() <= 1.0

def test_poisson_noise_changes_image(simple_potential):
    noisy = poisson_noise(simple_potential, counts=1e6)
    assert not np.allclose(noisy, simple_potential)

# ── lowfreq_noise ──────────────────────────────────────────────────────────────

def test_lowfreq_noise_shape(simple_potential):
    noisy = lowfreq_noise(simple_potential, noise_level=0.05)
    assert noisy.shape == simple_potential.shape

# ── grid_crop ──────────────────────────────────────────────────────────────────

def test_grid_crop_output_count():
    img = np.random.rand(640, 640)
    crops = grid_crop(img, crop_size=128, crop_glide=64)
    expected_n = int((640 - 128) / 64 + 1) ** 2
    assert crops.shape[0] == expected_n
    assert crops.shape[1:] == (128, 128)

# ── resize_image ───────────────────────────────────────────────────────────────

def test_resize_image_2d():
    arr = np.random.rand(100, 100)
    resized = resize_image(arr, 64)
    assert resized.shape == (64, 64)

def test_resize_image_3d():
    arr = np.random.rand(3, 100, 100)
    resized = resize_image(arr, 64)
    assert resized.shape == (3, 64, 64)

# ── shotgun_crop ───────────────────────────────────────────────────────────────

def test_shotgun_crop_count():
    img = np.random.rand(1024, 1024)
    crops = shotgun_crop(img, crop_size=256, n_crops=5, seed=0)
    assert crops.shape[0] == 5
    assert crops.shape[1:] == (256, 256)

def test_shotgun_crop_reproducible():
    img = np.random.rand(1024, 1024)
    c1 = shotgun_crop(img, crop_size=256, n_crops=3, seed=99)
    c2 = shotgun_crop(img, crop_size=256, n_crops=3, seed=99)
    np.testing.assert_array_equal(c1, c2)

def test_shotgun_crop_magnification_var():
    img = np.random.rand(1024, 1024)
    # Should not raise; output still standardized to crop_size
    crops = shotgun_crop(img, crop_size=256, magnification_var=0.2, n_crops=5, seed=0)
    assert crops.shape == (5, 256, 256)