"""Small, dependency-light color math used by the palette generator."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

Array = np.ndarray


def hex_to_srgb(value: str) -> Array:
    raw = value.lstrip("#")
    if len(raw) != 6:
        raise ValueError(f"expected #RRGGBB, got {value!r}")
    return np.array([int(raw[i : i + 2], 16) for i in (0, 2, 4)], dtype=float) / 255.0


def srgb_to_hex(rgb: Iterable[float]) -> str:
    values = np.clip(np.asarray(tuple(rgb), dtype=float), 0.0, 1.0)
    return "#" + "".join(f"{round(channel * 255):02X}" for channel in values)


def srgb_to_linear(rgb: Array) -> Array:
    rgb = np.asarray(rgb, dtype=float)
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(rgb: Array) -> Array:
    rgb = np.asarray(rgb, dtype=float)
    return np.where(
        rgb <= 0.0031308,
        12.92 * rgb,
        1.055 * np.maximum(rgb, 0.0) ** (1.0 / 2.4) - 0.055,
    )


def srgb_to_oklab(rgb: Array) -> Array:
    linear = srgb_to_linear(np.asarray(rgb, dtype=float))
    matrix_1 = np.array(
        [
            [0.4122214708, 0.5363325363, 0.0514459929],
            [0.2119034982, 0.6806995451, 0.1073969566],
            [0.0883024619, 0.2817188376, 0.6299787005],
        ]
    )
    matrix_2 = np.array(
        [
            [0.2104542553, 0.7936177850, -0.0040720468],
            [1.9779984951, -2.4285922050, 0.4505937099],
            [0.0259040371, 0.7827717662, -0.8086757660],
        ]
    )
    lms = np.tensordot(linear, matrix_1.T, axes=1)
    return np.tensordot(np.cbrt(lms), matrix_2.T, axes=1)


def oklab_to_srgb(lab: Array) -> Array:
    lab = np.asarray(lab, dtype=float)
    matrix_1_inv = np.array(
        [
            [1.0, 0.3963377774, 0.2158037573],
            [1.0, -0.1055613458, -0.0638541728],
            [1.0, -0.0894841775, -1.2914855480],
        ]
    )
    matrix_2_inv = np.array(
        [
            [4.0767416621, -3.3077115913, 0.2309699292],
            [-1.2684380046, 2.6097574011, -0.3413193965],
            [-0.0041960863, -0.7034186147, 1.7076147010],
        ]
    )
    lms_root = np.tensordot(lab, matrix_1_inv.T, axes=1)
    linear = np.tensordot(lms_root**3, matrix_2_inv.T, axes=1)
    return linear_to_srgb(linear)


def warm_transform(rgb: Array, gains: Iterable[float]) -> Array:
    """Apply an explicit RGB gamma-ramp surrogate to commanded sRGB values."""
    return np.clip(np.asarray(rgb, dtype=float) * np.asarray(tuple(gains), dtype=float), 0, 1)


def perceived_lab(rgb: Array, gains: Iterable[float]) -> Array:
    """Convert commanded sRGB to Oklab after an explicit warm-display transform."""
    return srgb_to_oklab(warm_transform(rgb, gains))


def wcag_luminance(rgb: Array) -> Array:
    linear = srgb_to_linear(np.asarray(rgb, dtype=float))
    return np.tensordot(linear, np.array([0.2126, 0.7152, 0.0722]), axes=1)


def contrast_ratio(left: Array, right: Array) -> float:
    a = float(wcag_luminance(np.asarray(left, dtype=float)))
    b = float(wcag_luminance(np.asarray(right, dtype=float)))
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def delta_e_ok(left: Array, right: Array) -> float:
    return float(np.linalg.norm(np.asarray(left) - np.asarray(right)) * 100.0)


def pairwise_distances(lab: Array) -> Array:
    lab = np.asarray(lab, dtype=float)
    delta = lab[:, None, :] - lab[None, :, :]
    distance = np.linalg.norm(delta, axis=-1) * 100.0
    return distance[np.triu_indices(len(lab), k=1)]
