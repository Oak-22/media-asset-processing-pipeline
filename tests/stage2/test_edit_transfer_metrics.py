"""Tests for the edit-transfer render metrics and hash manifests, on synthetic data."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np

    from scripts.python.stage2.spikes import edit_transfer_metrics as m
except ImportError:  # numpy lives in .venv; the stdlib-only suites still run without it
    np = None

from scripts.python.stage2.spikes.build_edit_transfer_hash_manifest import build_manifest, compare_manifests

SHARMA_DATA = Path(__file__).parent / "data" / "ciede2000testdata.txt"


def textured_image(height: int = 340, width: int = 512, seed: int = 0) -> "np.ndarray":
    """1/f-like texture scaled to 0..100, so alignment has structure at all scales."""
    rng = np.random.default_rng(seed)
    spectrum = np.fft.fft2(rng.standard_normal((height, width)))
    fy, fx = np.fft.fftfreq(height)[:, None], np.fft.fftfreq(width)[None, :]
    image = np.fft.ifft2(spectrum / (np.hypot(fx, fy) + 0.01) ** 1.2).real
    return (image - image.min()) / (image.max() - image.min()) * 100


@unittest.skipIf(np is None, "numpy not installed")
class ColourMetricTests(unittest.TestCase):
    def test_ciede2000_matches_sharma_published_pairs(self) -> None:
        data = np.loadtxt(SHARMA_DATA)
        got = m.delta_e_2000(data[:, 0:3], data[:, 3:6])
        self.assertEqual(len(data), 34)
        self.assertLess(np.abs(got - data[:, 6]).max(), 1e-4)
        np.testing.assert_allclose(got, m.delta_e_2000(data[:, 3:6], data[:, 0:3]), atol=1e-12)

    def test_srgb_white_and_black_map_to_lab_endpoints(self) -> None:
        lab = m.srgb_to_lab(np.array([[1.0, 1.0, 1.0], [0.0, 0.0, 0.0]]))
        np.testing.assert_allclose(lab, [[100, 0, 0], [0, 0, 0]], atol=1e-9)

    def test_compare_lab_reports_offsets_and_scores_clipped_pixels_apart(self) -> None:
        ref = np.zeros((20, 20, 3))
        ref[..., 0] = 50
        mov = ref.copy()
        mov[..., 0] += 2
        mov[..., 2] += 1
        valid = np.ones((20, 20), dtype=bool)
        clipped = np.zeros((20, 20), dtype=bool)
        clipped[:5] = True
        mov[:5, :, 0] = 40
        result = m.compare_lab(ref, mov, valid, clipped)
        self.assertAlmostEqual(result["dL_mean"], 2.0)
        self.assertAlmostEqual(result["db_mean"], 1.0)
        self.assertAlmostEqual(result["clip_dL_mean"], -10.0)
        self.assertAlmostEqual(result["scored_fraction"], 0.75)
        self.assertLess(result["de_median_exposure_matched"], result["de_median"])

    def test_clip_mask_dilates_by_radius(self) -> None:
        rgb = np.zeros((9, 9, 3))
        rgb[4, 4, 1] = 1.0
        mask = m.clip_mask(rgb, radius=2)
        self.assertEqual(int(mask.sum()), 25)
        self.assertTrue(mask[2, 2] and mask[6, 6] and not mask[1, 4])


@unittest.skipIf(np is None, "numpy not installed")
class AlignmentTests(unittest.TestCase):
    def test_recovers_known_similarity(self) -> None:
        reference = textured_image()
        truth = m.Similarity(scale=1.008, rotation_degrees=0.12, shift_x=3.4, shift_y=-2.1)
        moving = np.nan_to_num(m.warp_similarity(reference, truth), nan=50.0)
        estimate = m.estimate_similarity(reference, moving, downsample_levels=0)
        aligned = m.apply_alignment(moving, estimate)
        # Two bilinear resamplings blur fine texture, so compare with the exact inverse.
        exact = m.apply_alignment(
            moving,
            m.Similarity(1 / truth.scale, -truth.rotation_degrees, -truth.shift_x / truth.scale, -truth.shift_y / truth.scale),
        )
        valid = m.border_mask(reference.shape) & ~np.isnan(aligned) & ~np.isnan(exact)
        self.assertAlmostEqual(estimate.scale, 1 / truth.scale, delta=0.002)
        self.assertAlmostEqual(estimate.rotation_degrees, -truth.rotation_degrees, delta=0.05)
        exact_residual = np.abs(exact[valid] - reference[valid]).mean()
        self.assertLess(np.abs(aligned[valid] - reference[valid]).mean(), 1.5 * exact_residual + 0.1)
        self.assertGreater(
            m.gradient_correlation(reference, aligned, valid),
            m.gradient_correlation(reference, exact, valid) - 0.05,
        )

    def test_match_shape_crops_and_pads(self) -> None:
        image = np.arange(12.0).reshape(3, 4)
        self.assertEqual(m.match_shape(image, (2, 5)).shape, (2, 5))
        self.assertEqual(m.match_shape(image, (2, 5))[0, 4], 3.0)


@unittest.skipIf(np is None, "numpy not installed")
class WhiteBalanceTests(unittest.TestCase):
    def test_conversion_recovers_synthetic_linear_map(self) -> None:
        per_mired, per_tint = np.array([-0.3, -1.2]), np.array([0.9, -0.1])
        true_map = np.array([[4.0, 0.3], [-0.5, 2.0]])
        per_temp_inc = per_mired * true_map[0, 0] + per_tint * true_map[1, 0]
        per_tint_inc = per_mired * true_map[0, 1] + per_tint * true_map[1, 1]
        steps = np.array([-12.0, -6.0, 6.0, 12.0])
        responses = []
        for vector in (per_mired, per_tint, per_temp_inc, per_tint_inc):
            response, r2 = m.wb_response(steps, np.outer(steps, vector))
            np.testing.assert_allclose(response, vector)
            self.assertAlmostEqual(r2, 1.0)
            responses.append(response)
        np.testing.assert_allclose(m.wb_conversion(*responses), true_map, atol=1e-12)

    def test_wb_shift_uses_midtones_only(self) -> None:
        center = np.zeros((4, 4, 3))
        center[..., 0] = 50
        center[0, :, 0] = 95  # highlights excluded
        shifted = center.copy()
        shifted[..., 1] += 1.5
        shifted[0, :, 1] += 10
        da, db = m.wb_shift(center, shifted, np.ones((4, 4), dtype=bool))
        self.assertAlmostEqual(da, 1.5)
        self.assertAlmostEqual(db, 0.0)


@unittest.skipIf(np is None, "numpy not installed")
class NoiseTests(unittest.TestCase):
    def test_flat_region_noise_tracks_injected_sigma(self) -> None:
        rng = np.random.default_rng(1)
        base = np.full((256, 256), 50.0)
        sigmas = [m.flat_region_noise(base + rng.normal(0, s, base.shape)) for s in (0.5, 1.0, 2.0)]
        self.assertTrue(sigmas[0] < sigmas[1] < sigmas[2])
        self.assertAlmostEqual(sigmas[2] / sigmas[1], 2.0, delta=0.15)

    def test_match_noise_level_interpolates(self) -> None:
        self.assertAlmostEqual(m.match_noise_level([0, 10, 20], [3.0, 2.0, 1.0], 1.5), 15.0)
        self.assertEqual(m.match_noise_level([0, 10, 20], [3.0, 2.0, 1.0], 0.2), 20.0)


class HashManifestTests(unittest.TestCase):
    def test_compare_flags_content_changes_and_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "A.ARW").write_bytes(b"raw")
            (root / "A.xmp").write_bytes(b"<x/>")
            (root / "B.JPG").write_bytes(b"jpg")
            (root / "other.txt").write_bytes(b"ignored")
            pre = build_manifest(root, "[AB].*")
            self.assertEqual(pre["file_count"], 3)
            self.assertTrue(compare_manifests(pre, build_manifest(root, "[AB].*"))["identical"])

            (root / "A.xmp").write_bytes(b"<y/>")
            (root / "B.JPG").unlink()
            result = compare_manifests(pre, build_manifest(root, "[AB].*"))
            self.assertFalse(result["identical"])
            self.assertEqual(result["content_changed"], ["A.xmp"])
            self.assertEqual(result["missing"], ["B.JPG"])


if __name__ == "__main__":
    unittest.main()
