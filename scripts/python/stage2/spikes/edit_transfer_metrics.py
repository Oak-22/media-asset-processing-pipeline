"""Render-comparison metrics for the JPEG-to-RAW edit transfer spike.

Pure numpy: sRGB -> CIELAB (D65), CIEDE2000, similarity alignment by phase
correlation on gradient magnitude, clip masks, a flat-region noise estimate,
and white-balance response fits. File I/O lives in the calling scripts,
except `load_tiff_srgb01`, which imports tifffile lazily.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

# IEC 61966-2-1 sRGB -> XYZ (D65). The white is derived from the same matrix
# so that sRGB white maps to a* = b* = 0 exactly.
SRGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ]
)
WHITE_D65 = SRGB_TO_XYZ @ np.ones(3)
CLIP_THRESHOLD = 250 / 255
BORDER_TRIM_FRACTION = 0.04


def load_tiff_srgb01(path: str | Path) -> np.ndarray:
    """Read an 8- or 16-bit RGB TIFF as float64 sRGB values in [0, 1]."""
    import tifffile

    data = tifffile.imread(str(path))
    if data.ndim != 3 or data.shape[-1] < 3:
        raise ValueError(f"{path}: expected an RGB image, got shape {data.shape}")
    scale = float(np.iinfo(data.dtype).max) if data.dtype.kind == "u" else 1.0
    return data[..., :3].astype(np.float64) / scale


def srgb_to_lab(srgb01: np.ndarray) -> np.ndarray:
    """Convert sRGB values in [0, 1] to CIELAB (D65)."""
    v = np.asarray(srgb01, dtype=np.float64)
    linear = np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)
    t = (linear @ SRGB_TO_XYZ.T) / WHITE_D65
    eps, kappa = 216 / 24389, 24389 / 27
    f = np.where(t > eps, np.cbrt(t), (kappa * t + 16) / 116)
    return np.stack(
        [116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])],
        axis=-1,
    )


def delta_e_2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """CIEDE2000 colour difference (kL = kC = kH = 1), per Sharma et al. 2005."""
    L1, a1, b1 = np.moveaxis(np.asarray(lab1, dtype=np.float64), -1, 0)
    L2, a2, b2 = np.moveaxis(np.asarray(lab2, dtype=np.float64), -1, 0)
    c_bar = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    g = 0.5 * (1 - np.sqrt(c_bar**7 / (c_bar**7 + 25.0**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.where((a1p == 0) & (b1 == 0), 0, np.degrees(np.arctan2(b1, a1p)) % 360)
    h2p = np.where((a2p == 0) & (b2 == 0), 0, np.degrees(np.arctan2(b2, a2p)) % 360)

    zero_chroma = (c1p * c2p) == 0
    dh = h2p - h1p
    dhp = np.where(zero_chroma, 0, np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh)))
    dLp, dCp = L2 - L1, c2p - c1p
    dHp = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dhp / 2))

    l_bar, c_bar_p = (L1 + L2) / 2, (c1p + c2p) / 2
    h_sum = h1p + h2p
    h_bar = np.where(
        zero_chroma,
        h_sum,
        np.where(np.abs(h1p - h2p) <= 180, h_sum / 2, np.where(h_sum < 360, (h_sum + 360) / 2, (h_sum - 360) / 2)),
    )
    t = (
        1
        - 0.17 * np.cos(np.radians(h_bar - 30))
        + 0.24 * np.cos(np.radians(2 * h_bar))
        + 0.32 * np.cos(np.radians(3 * h_bar + 6))
        - 0.20 * np.cos(np.radians(4 * h_bar - 63))
    )
    d_theta = 30 * np.exp(-(((h_bar - 275) / 25) ** 2))
    r_c = 2 * np.sqrt(c_bar_p**7 / (c_bar_p**7 + 25.0**7))
    s_l = 1 + 0.015 * (l_bar - 50) ** 2 / np.sqrt(20 + (l_bar - 50) ** 2)
    s_c = 1 + 0.045 * c_bar_p
    s_h = 1 + 0.015 * c_bar_p * t
    r_t = -np.sin(np.radians(2 * d_theta)) * r_c
    return np.sqrt(
        (dLp / s_l) ** 2 + (dCp / s_c) ** 2 + (dHp / s_h) ** 2 + r_t * (dCp / s_c) * (dHp / s_h)
    )


def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    """Binary dilation with a (2r+1) square, by shifted ORs."""
    out = mask.copy()
    h, w = mask.shape
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            shifted = np.zeros_like(mask)
            shifted[max(dy, 0) : h + min(dy, 0), max(dx, 0) : w + min(dx, 0)] = mask[
                max(-dy, 0) : h + min(-dy, 0), max(-dx, 0) : w + min(-dx, 0)
            ]
            out |= shifted
    return out


def clip_mask(srgb01: np.ndarray, threshold: float = CLIP_THRESHOLD, radius: int = 2) -> np.ndarray:
    """Pixels where any channel is at or above the clip threshold, dilated."""
    return dilate(np.any(srgb01 >= threshold, axis=-1), radius)


def match_shape(image: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Crop or edge-pad an image to `shape` (renders can differ by a pixel)."""
    h, w = shape
    image = image[:h, :w]
    pad = [(0, h - image.shape[0]), (0, w - image.shape[1])] + [(0, 0)] * (image.ndim - 2)
    return np.pad(image, pad, mode="edge")


# --- alignment ------------------------------------------------------------


@dataclass(frozen=True)
class Similarity:
    """Maps moving-image coordinates onto the reference, about the centre."""

    scale: float = 1.0
    rotation_degrees: float = 0.0
    shift_x: float = 0.0
    shift_y: float = 0.0
    peak: float = 0.0


def warp_similarity(image: np.ndarray, transform: Similarity) -> np.ndarray:
    """Resample `image` under `transform`; bilinear, NaN outside the source."""
    h, w = image.shape[:2]
    cy, cx = (h - 1) / 2, (w - 1) / 2
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    theta = np.radians(transform.rotation_degrees)
    c, s = np.cos(theta), np.sin(theta)
    xo, yo = xx - cx - transform.shift_x, yy - cy - transform.shift_y
    xs = (c * xo + s * yo) / transform.scale + cx
    ys = (-s * xo + c * yo) / transform.scale + cy
    x0, y0 = np.floor(xs).astype(int), np.floor(ys).astype(int)
    fx, fy = xs - x0, ys - y0
    valid = (x0 >= 0) & (y0 >= 0) & (x0 < w - 1) & (y0 < h - 1)
    x0, y0 = np.clip(x0, 0, w - 2), np.clip(y0, 0, h - 2)
    if image.ndim == 3:
        fx, fy, valid = fx[..., None], fy[..., None], valid[..., None]
    out = (
        image[y0, x0] * (1 - fx) * (1 - fy)
        + image[y0, x0 + 1] * fx * (1 - fy)
        + image[y0 + 1, x0] * (1 - fx) * fy
        + image[y0 + 1, x0 + 1] * fx * fy
    )
    return np.where(valid, out, np.nan)


def _phase_correlation(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    """Sub-pixel (dy, dx) that moves b onto a, plus the correlation peak."""
    window = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    fa = np.fft.fft2((a - a.mean()) * window)
    fb = np.fft.fft2((b - b.mean()) * window)
    cross = fa * np.conj(fb)
    cross /= np.abs(cross) + 1e-12
    surface = np.fft.ifft2(cross).real
    py, px = np.unravel_index(np.argmax(surface), surface.shape)
    h, w = surface.shape

    def refine(minus: float, centre: float, plus: float) -> float:
        denominator = minus - 2 * centre + plus
        return 0.0 if denominator == 0 else 0.5 * (minus - plus) / denominator

    dy = py + refine(surface[(py - 1) % h, px], surface[py, px], surface[(py + 1) % h, px])
    dx = px + refine(surface[py, (px - 1) % w], surface[py, px], surface[py, (px + 1) % w])
    if dy > h / 2:
        dy -= h
    if dx > w / 2:
        dx -= w
    return float(dy), float(dx), float(surface[py, px])


def _gradient_magnitude(luminance: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(luminance)
    return np.hypot(gx, gy)


def _half(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[0] // 2 * 2, image.shape[1] // 2 * 2
    image = image[:h, :w]
    return (image[0::2, 0::2] + image[1::2, 0::2] + image[0::2, 1::2] + image[1::2, 1::2]) / 4


def estimate_similarity(
    reference_l: np.ndarray,
    moving_l: np.ndarray,
    scales: np.ndarray | None = None,
    rotations: np.ndarray | None = None,
    downsample_levels: int = 1,
    refine_passes: int = 2,
) -> Similarity:
    """Grid search over scale and rotation; translation by phase correlation.

    Runs at 1/2**downsample_levels resolution, then `refine_passes` finer
    grids around the optimum, halving the step each time. The returned
    shift is in full-resolution pixels.
    """
    ref, mov = reference_l, moving_l
    for _ in range(downsample_levels):
        ref, mov = _half(ref), _half(mov)
    factor = 2**downsample_levels
    scales = np.linspace(0.98, 1.02, 9) if scales is None else scales
    rotations = np.linspace(-0.3, 0.3, 7) if rotations is None else rotations
    ref_grad = _gradient_magnitude(ref)
    fill = float(np.mean(mov))

    def search(scale_grid: np.ndarray, rotation_grid: np.ndarray) -> Similarity:
        best = Similarity(peak=-np.inf)
        for scale in scale_grid:
            for rotation in rotation_grid:
                warped = np.nan_to_num(warp_similarity(mov, Similarity(scale, rotation)), nan=fill)
                dy, dx, peak = _phase_correlation(ref_grad, _gradient_magnitude(warped))
                if peak > best.peak:
                    best = Similarity(float(scale), float(rotation), dx, dy, peak)
        return best

    best = search(scales, rotations)
    scale_step = float(np.ptp(scales)) / max(len(scales) - 1, 1)
    rotation_step = float(np.ptp(rotations)) / max(len(rotations) - 1, 1)
    for _ in range(refine_passes):
        best = search(
            best.scale + np.linspace(-scale_step, scale_step, 5),
            best.rotation_degrees + np.linspace(-rotation_step, rotation_step, 5),
        )
        scale_step, rotation_step = scale_step / 2, rotation_step / 2
    return Similarity(best.scale, best.rotation_degrees, best.shift_x * factor, best.shift_y * factor, best.peak)


def apply_alignment(image: np.ndarray, transform: Similarity) -> np.ndarray:
    """Scale/rotate then translate, in one resampling pass.

    warp_similarity applies the shift after the scale and rotation, which is
    the order estimate_similarity measures them in.
    """
    return warp_similarity(image, transform)


def border_mask(shape: tuple[int, int], fraction: float = BORDER_TRIM_FRACTION) -> np.ndarray:
    h, w = shape
    trim = int(round(fraction * max(h, w)))
    mask = np.zeros(shape, dtype=bool)
    mask[trim : h - trim, trim : w - trim] = True
    return mask


def gradient_correlation(reference_l: np.ndarray, moving_l: np.ndarray, valid: np.ndarray) -> float:
    a = _gradient_magnitude(np.nan_to_num(reference_l))[valid]
    b = _gradient_magnitude(np.nan_to_num(moving_l))[valid]
    if a.size < 2 or a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


# --- comparison -------------------------------------------------------------


def compare_lab(
    reference_lab: np.ndarray,
    moving_lab: np.ndarray,
    valid: np.ndarray,
    clipped: np.ndarray | None = None,
) -> dict[str, float]:
    """Colour-difference statistics over valid, unclipped pixels.

    Differences are moving minus reference. Clipped pixels are scored
    separately as `clip_dL_mean` (recovered highlights read negative).
    """
    clipped = np.zeros(valid.shape, dtype=bool) if clipped is None else clipped
    scored = valid & ~clipped
    if not scored.any():
        raise ValueError("No valid unclipped pixels to compare")
    ref, mov = reference_lab[scored], moving_lab[scored]
    de = delta_e_2000(ref, mov)
    dl = mov[:, 0] - ref[:, 0]
    # Same comparison with the mean brightness offset removed.
    shifted = mov.copy()
    shifted[:, 0] -= dl.mean()
    de_exposure_matched = delta_e_2000(ref, shifted)
    ref_l_pct = np.percentile(ref[:, 0], [5, 50, 95])
    mov_l_pct = np.percentile(mov[:, 0], [5, 50, 95])
    clip_region = valid & clipped
    return {
        "de_mean": float(de.mean()),
        "de_median": float(np.median(de)),
        "de_p95": float(np.percentile(de, 95)),
        "de_p99": float(np.percentile(de, 99)),
        "de_max": float(de.max()),
        "de_median_exposure_matched": float(np.median(de_exposure_matched)),
        "dL_mean": float(dl.mean()),
        "dL_p50": float(np.median(dl)),
        "da_mean": float((mov[:, 1] - ref[:, 1]).mean()),
        "db_mean": float((mov[:, 2] - ref[:, 2]).mean()),
        "L_p5_diff": float(mov_l_pct[0] - ref_l_pct[0]),
        "L_p50_diff": float(mov_l_pct[1] - ref_l_pct[1]),
        "L_p95_diff": float(mov_l_pct[2] - ref_l_pct[2]),
        "clip_dL_mean": (
            float((moving_lab[clip_region, 0] - reference_lab[clip_region, 0]).mean())
            if clip_region.any()
            else None
        ),
        "scored_fraction": float(scored.sum() / valid.size),
        "clipped_fraction": float(clipped.sum() / clipped.size),
    }


def wb_shift(center_lab: np.ndarray, shifted_lab: np.ndarray, valid: np.ndarray) -> tuple[float, float]:
    """Mean (Δa*, Δb*) between two renders of the same frame, on mid-tones."""
    midtone = valid & (center_lab[..., 0] > 15) & (center_lab[..., 0] < 85)
    if not midtone.any():
        raise ValueError("No mid-tone pixels for WB measurement")
    diff = shifted_lab[midtone] - center_lab[midtone]
    return float(diff[:, 1].mean()), float(diff[:, 2].mean())


@dataclass(frozen=True)
class LinearFit:
    slope: float
    intercept: float
    r2: float


def fit_line(x: np.ndarray, y: np.ndarray) -> LinearFit:
    x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    slope, intercept = np.polyfit(x, y, 1)
    residual = y - (slope * x + intercept)
    total = ((y - y.mean()) ** 2).sum()
    r2 = 1.0 - (residual**2).sum() / total if total > 0 else float("nan")
    return LinearFit(float(slope), float(intercept), float(r2))


def wb_response(steps: np.ndarray, shifts: np.ndarray) -> tuple[np.ndarray, float]:
    """Fit a Lab (Δa*, Δb*) response per unit step, through the origin.

    `shifts` has one (Δa*, Δb*) row per step. Returns the per-unit response
    vector and the R² of the response projected on its own direction.
    """
    steps = np.asarray(steps, dtype=np.float64)
    shifts = np.asarray(shifts, dtype=np.float64)
    response = (steps @ shifts) / (steps @ steps)
    norm = np.linalg.norm(response)
    if norm == 0:
        return response, float("nan")
    projected = shifts @ (response / norm)
    fit = fit_line(steps, projected)
    return response, fit.r2


def wb_conversion(raw_temp: np.ndarray, raw_tint: np.ndarray, jpeg_temp: np.ndarray, jpeg_tint: np.ndarray) -> np.ndarray:
    """2x2 map from JPEG increments to RAW (mired, tint) offsets.

    Columns of each Jacobian are the Lab responses per unit step. The result
    M satisfies J_raw @ M = J_jpeg, so M[0, 0] is mired per JPEG temperature
    increment and M[1, 1] is RAW tint per JPEG tint increment.
    """
    j_raw = np.column_stack([raw_temp, raw_tint])
    j_jpeg = np.column_stack([jpeg_temp, jpeg_tint])
    return np.linalg.solve(j_raw, j_jpeg)


# --- noise ------------------------------------------------------------------


def _box_blur(image: np.ndarray, radius: int) -> np.ndarray:
    size = 2 * radius + 1
    padded = np.pad(image, radius, mode="reflect")
    cumulative = padded.cumsum(axis=0).cumsum(axis=1)
    cumulative = np.pad(cumulative, ((1, 0), (1, 0)))
    total = (
        cumulative[size:, size:]
        - cumulative[:-size, size:]
        - cumulative[size:, :-size]
        + cumulative[:-size, :-size]
    )
    return total / size**2


def flat_region_noise(luminance: np.ndarray, tile: int = 32, flat_fraction: float = 0.25) -> float:
    """Noise sigma (in L* units) from the flattest tiles.

    High-pass residual = L* minus a 5x5 box blur. Tiles are ranked by the
    gradient energy of the blurred image; the median residual std of the
    flattest `flat_fraction` of tiles is returned.
    """
    smooth = _box_blur(luminance, 2)
    residual = luminance - smooth
    texture = _gradient_magnitude(smooth)
    h, w = luminance.shape
    stats = []
    for y in range(0, h - tile + 1, tile):
        for x in range(0, w - tile + 1, tile):
            stats.append(
                (
                    float(texture[y : y + tile, x : x + tile].mean()),
                    float(residual[y : y + tile, x : x + tile].std()),
                )
            )
    if not stats:
        raise ValueError("Image smaller than one noise tile")
    stats.sort()
    keep = stats[: max(1, int(len(stats) * flat_fraction))]
    return float(np.median([sigma for _, sigma in keep]))


def match_noise_level(amounts: list[float], sigmas: list[float], target: float) -> float:
    """NR amount whose noise sigma best matches `target`, linearly interpolated."""
    order = np.argsort(amounts)
    amounts_sorted = np.asarray(amounts, dtype=np.float64)[order]
    sigmas_sorted = np.asarray(sigmas, dtype=np.float64)[order]
    for i in range(len(amounts_sorted) - 1):
        s0, s1 = sigmas_sorted[i], sigmas_sorted[i + 1]
        if (s0 - target) * (s1 - target) <= 0 and s0 != s1:
            return float(amounts_sorted[i] + (target - s0) * (amounts_sorted[i + 1] - amounts_sorted[i]) / (s1 - s0))
    return float(amounts_sorted[np.argmin(np.abs(sigmas_sorted - target))])
