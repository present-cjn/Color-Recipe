from __future__ import annotations

import base64
import io
import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np
from PIL import Image, ImageCms, ImageOps


D65 = np.array([0.95047, 1.0, 1.08883], dtype=np.float32)
HUE_BUCKETS = [
    ("red", 345, 15),
    ("orange", 15, 45),
    ("yellow", 45, 75),
    ("green", 75, 165),
    ("aqua", 165, 195),
    ("blue", 195, 255),
    ("purple", 255, 285),
    ("magenta", 285, 345),
]


@dataclass
class ImageProfile:
    rgb_mean: np.ndarray
    rgb_std: np.ndarray
    lab_mean: np.ndarray
    lab_std: np.ndarray
    luminance_mean: float
    luminance_std: float
    luminance_percentiles: Dict[str, float]
    channel_curves: Dict[str, List[float]]
    chroma_mean: float
    saturation_mean: float
    hsl_buckets: Dict[str, Dict[str, float]]


@dataclass
class TransferModel:
    source: ImageProfile
    reference: ImageProfile
    strength: float


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def load_image_bytes(data: bytes, max_size: int = 1800) -> np.ndarray:
    with Image.open(io.BytesIO(data)) as image:
        image = ImageOps.exif_transpose(image)
        image = convert_to_srgb(image)
        image = image.convert("RGB")
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        return np.asarray(image).astype(np.float32) / 255.0


def convert_to_srgb(image: Image.Image) -> Image.Image:
    icc = image.info.get("icc_profile")
    if not icc:
        return image

    try:
        source_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        target_profile = ImageCms.createProfile("sRGB")
        return ImageCms.profileToProfile(image, source_profile, target_profile, outputMode="RGB")
    except Exception:
        return image


def encode_png_data_url(rgb: np.ndarray) -> str:
    image = Image.fromarray(to_uint8(rgb), mode="RGB")
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    payload = base64.b64encode(output.getvalue()).decode("ascii")
    return "data:image/png;base64," + payload


def to_uint8(rgb: np.ndarray) -> np.ndarray:
    return np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8)


def srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
    rgb = np.maximum(rgb, 0.0)
    return np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * (rgb ** (1.0 / 2.4)) - 0.055)


def rgb_to_xyz(rgb: np.ndarray) -> np.ndarray:
    linear = srgb_to_linear(np.clip(rgb, 0.0, 1.0))
    matrix = np.array(
        [
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ],
        dtype=np.float32,
    )
    return np.tensordot(linear, matrix.T, axes=1)


def xyz_to_rgb(xyz: np.ndarray) -> np.ndarray:
    matrix = np.array(
        [
            [3.2404542, -1.5371385, -0.4985314],
            [-0.9692660, 1.8760108, 0.0415560],
            [0.0556434, -0.2040259, 1.0572252],
        ],
        dtype=np.float32,
    )
    linear = np.tensordot(xyz, matrix.T, axes=1)
    return np.clip(linear_to_srgb(linear), 0.0, 1.0)


def xyz_to_lab(xyz: np.ndarray) -> np.ndarray:
    scaled = xyz / D65
    epsilon = 216.0 / 24389.0
    kappa = 24389.0 / 27.0
    f = np.where(scaled > epsilon, np.cbrt(scaled), (kappa * scaled + 16.0) / 116.0)
    l = 116.0 * f[..., 1] - 16.0
    a = 500.0 * (f[..., 0] - f[..., 1])
    b = 200.0 * (f[..., 1] - f[..., 2])
    return np.stack([l, a, b], axis=-1)


def lab_to_xyz(lab: np.ndarray) -> np.ndarray:
    l = lab[..., 0]
    a = lab[..., 1]
    b = lab[..., 2]
    fy = (l + 16.0) / 116.0
    fx = fy + a / 500.0
    fz = fy - b / 200.0
    f = np.stack([fx, fy, fz], axis=-1)
    epsilon = 216.0 / 24389.0
    kappa = 24389.0 / 27.0
    cubed = f ** 3
    xyz = np.where(cubed > epsilon, cubed, (116.0 * f - 16.0) / kappa)
    return xyz * D65


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    return xyz_to_lab(rgb_to_xyz(rgb))


def lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    return xyz_to_rgb(lab_to_xyz(lab))


def rgb_to_hsl(rgb: np.ndarray) -> np.ndarray:
    r = rgb[..., 0]
    g = rgb[..., 1]
    b = rgb[..., 2]
    maxc = np.max(rgb, axis=-1)
    minc = np.min(rgb, axis=-1)
    delta = maxc - minc
    lightness = (maxc + minc) / 2.0

    saturation = np.zeros_like(lightness)
    valid = delta > 1e-6
    saturation[valid] = delta[valid] / (1.0 - np.abs(2.0 * lightness[valid] - 1.0) + 1e-6)

    hue = np.zeros_like(lightness)
    red_max = valid & (maxc == r)
    green_max = valid & (maxc == g)
    blue_max = valid & (maxc == b)
    hue[red_max] = ((g[red_max] - b[red_max]) / delta[red_max]) % 6.0
    hue[green_max] = ((b[green_max] - r[green_max]) / delta[green_max]) + 2.0
    hue[blue_max] = ((r[blue_max] - g[blue_max]) / delta[blue_max]) + 4.0
    hue = hue / 6.0

    return np.stack([hue, np.clip(saturation, 0.0, 1.0), lightness], axis=-1)


def compute_profile(rgb: np.ndarray) -> ImageProfile:
    flat_rgb = rgb.reshape((-1, 3))
    lab = rgb_to_lab(rgb)
    flat_lab = lab.reshape((-1, 3))
    luminance = np.dot(flat_rgb, np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))
    hsl = rgb_to_hsl(rgb).reshape((-1, 3))
    chroma = np.sqrt(flat_lab[:, 1] ** 2 + flat_lab[:, 2] ** 2)

    percentile_values = np.percentile(luminance, [1, 5, 25, 50, 75, 95, 99])
    percentile_keys = ["p01", "p05", "p25", "p50", "p75", "p95", "p99"]
    luminance_percentiles = {
        key: float(value) for key, value in zip(percentile_keys, percentile_values)
    }

    channel_curves = {}
    for index, name in enumerate(["r", "g", "b"]):
        channel_curves[name] = [
            float(value) for value in np.percentile(flat_rgb[:, index], [0, 25, 50, 75, 100])
        ]

    return ImageProfile(
        rgb_mean=flat_rgb.mean(axis=0),
        rgb_std=flat_rgb.std(axis=0) + 1e-6,
        lab_mean=flat_lab.mean(axis=0),
        lab_std=flat_lab.std(axis=0) + 1e-6,
        luminance_mean=float(luminance.mean()),
        luminance_std=float(luminance.std() + 1e-6),
        luminance_percentiles=luminance_percentiles,
        channel_curves=channel_curves,
        chroma_mean=float(chroma.mean()),
        saturation_mean=float(hsl[:, 1].mean()),
        hsl_buckets=compute_hsl_buckets(hsl),
    )


def compute_hsl_buckets(hsl: np.ndarray) -> Dict[str, Dict[str, float]]:
    hue_degrees = hsl[:, 0] * 360.0
    result = {}
    for name, start, end in HUE_BUCKETS:
        if start > end:
            mask = (hue_degrees >= start) | (hue_degrees < end)
        else:
            mask = (hue_degrees >= start) & (hue_degrees < end)

        mask = mask & (hsl[:, 1] > 0.05)
        if np.any(mask):
            result[name] = {
                "hue": float(circular_mean_degrees(hue_degrees[mask])),
                "saturation": float(np.mean(hsl[mask, 1])),
                "luminance": float(np.mean(hsl[mask, 2])),
                "coverage": float(np.mean(mask)),
            }
        else:
            center = (start + end) / 2.0 if start <= end else 0.0
            result[name] = {
                "hue": float(center),
                "saturation": 0.0,
                "luminance": 0.0,
                "coverage": 0.0,
            }
    return result


def circular_mean_degrees(values: np.ndarray) -> float:
    radians = np.deg2rad(values)
    mean = math.degrees(math.atan2(float(np.sin(radians).mean()), float(np.cos(radians).mean())))
    return mean % 360.0


def build_model(source_rgb: np.ndarray, reference_rgb: np.ndarray, strength: float) -> TransferModel:
    return TransferModel(
        source=compute_profile(source_rgb),
        reference=compute_profile(reference_rgb),
        strength=clamp(strength, 0.0, 1.0),
    )


def apply_transfer(rgb: np.ndarray, model: TransferModel) -> np.ndarray:
    strength = model.strength
    if strength <= 0:
        return np.clip(rgb.copy(), 0.0, 1.0)

    source = model.source
    reference = model.reference

    exposure_ev = exposure_delta_ev(source, reference)
    adjusted = np.clip(rgb * (2.0 ** (exposure_ev * 0.65 * strength)), 0.0, 1.0)

    contrast_ratio = clamp(reference.luminance_std / source.luminance_std, 0.65, 1.55)
    contrast_factor = 1.0 + (contrast_ratio - 1.0) * strength
    adjusted = np.clip((adjusted - 0.5) * contrast_factor + 0.5, 0.0, 1.0)

    lab = rgb_to_lab(adjusted)
    src_mean = source.lab_mean
    ref_mean = source.lab_mean + (reference.lab_mean - source.lab_mean) * strength
    std_ratio = np.clip(reference.lab_std / source.lab_std, 0.55, 1.85)
    std_mix = 1.0 + (std_ratio - 1.0) * strength
    lab = (lab - src_mean) * std_mix + ref_mean

    result = lab_to_rgb(lab)
    saturation_ratio = clamp(reference.saturation_mean / max(source.saturation_mean, 1e-4), 0.65, 1.45)
    result = adjust_saturation(result, 1.0 + (saturation_ratio - 1.0) * 0.7 * strength)
    return np.clip(result, 0.0, 1.0)


def apply_recipe(rgb: np.ndarray, recipe: Dict[str, Any], strength: float = 1.0) -> np.ndarray:
    """Apply the public Color Recipe parameter subset to an RGB image."""
    strength = float(np.clip(strength, 0.0, 1.0))
    result = np.clip(rgb.astype(np.float32, copy=True), 0.0, 1.0)
    basic = recipe.get("basic", {})
    color = recipe.get("color", {})

    exposure_ev = float(basic.get("exposureEv", 0.0)) * strength
    result = np.clip(result * (2.0 ** exposure_ev), 0.0, 1.0)

    result = apply_luminance_controls(
        result,
        contrast=float(basic.get("contrast", 0.0)) * strength,
        highlights=float(basic.get("highlights", 0.0)) * strength,
        shadows=float(basic.get("shadows", 0.0)) * strength,
        whites=float(basic.get("whites", 0.0)) * strength,
        blacks=float(basic.get("blacks", 0.0)) * strength,
    )

    result = apply_lab_color_shift(
        result,
        temperature=float(color.get("temperature", 0.0)) * strength,
        tint=float(color.get("tint", 0.0)) * strength,
    )

    saturation = float(color.get("saturation", 0.0)) * strength
    vibrance = float(color.get("vibrance", 0.0)) * strength
    result = adjust_saturation(result, 1.0 + saturation / 100.0)
    result = adjust_vibrance(result, vibrance)
    return np.clip(result, 0.0, 1.0)


def apply_luminance_controls(
    rgb: np.ndarray,
    contrast: float = 0.0,
    highlights: float = 0.0,
    shadows: float = 0.0,
    whites: float = 0.0,
    blacks: float = 0.0,
) -> np.ndarray:
    result = np.clip(rgb.copy(), 0.0, 1.0)

    contrast_factor = 1.0 + np.clip(contrast, -100.0, 100.0) / 100.0
    result = np.clip((result - 0.5) * contrast_factor + 0.5, 0.0, 1.0)

    luminance = luma(result)
    result = shift_by_mask(result, smoothstep(0.55, 1.0, luminance), highlights / 180.0)
    result = shift_by_mask(result, 1.0 - smoothstep(0.0, 0.45, luminance), shadows / 180.0)
    result = shift_by_mask(result, smoothstep(0.82, 1.0, luminance), whites / 220.0)
    result = shift_by_mask(result, 1.0 - smoothstep(0.0, 0.18, luminance), blacks / 220.0)
    return np.clip(result, 0.0, 1.0)


def apply_lab_color_shift(rgb: np.ndarray, temperature: float = 0.0, tint: float = 0.0) -> np.ndarray:
    if abs(temperature) < 1e-6 and abs(tint) < 1e-6:
        return rgb

    lab = rgb_to_lab(rgb)
    lab[..., 1] += np.clip(tint, -100.0, 100.0) / 7.0
    lab[..., 2] += np.clip(temperature, -100.0, 100.0) / 9.0
    return np.clip(lab_to_rgb(lab), 0.0, 1.0)


def adjust_saturation(rgb: np.ndarray, factor: float) -> np.ndarray:
    luminance = luma(rgb)[..., None]
    return np.clip(luminance + (rgb - luminance) * factor, 0.0, 1.0)


def adjust_vibrance(rgb: np.ndarray, amount: float) -> np.ndarray:
    hsl = rgb_to_hsl(rgb)
    saturation = hsl[..., 1]
    factor = 1.0 + (np.clip(amount, -100.0, 100.0) / 100.0) * (1.0 - saturation)
    return adjust_saturation(rgb, float(np.mean(factor)))


def luma(rgb: np.ndarray) -> np.ndarray:
    return np.dot(rgb, np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))


def shift_by_mask(rgb: np.ndarray, mask: np.ndarray, amount: float) -> np.ndarray:
    return rgb + mask[..., None] * amount


def smoothstep(edge0: float, edge1: float, value: np.ndarray) -> np.ndarray:
    width = max(edge1 - edge0, 1e-6)
    t = np.clip((value - edge0) / width, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def exposure_delta_ev(source: ImageProfile, reference: ImageProfile) -> float:
    return clamp(
        math.log2(max(reference.luminance_mean, 1e-4) / max(source.luminance_mean, 1e-4)),
        -2.0,
        2.0,
    )


def generate_recipe(source: ImageProfile, reference: ImageProfile, strength: float) -> Dict[str, Any]:
    exposure = exposure_delta_ev(source, reference) * strength
    contrast = (reference.luminance_std / source.luminance_std - 1.0) * 100.0 * strength
    saturation = (reference.saturation_mean / max(source.saturation_mean, 1e-4) - 1.0) * 100.0 * strength
    chroma = (reference.chroma_mean / max(source.chroma_mean, 1e-4) - 1.0) * 100.0 * strength
    lab_delta = (reference.lab_mean - source.lab_mean) * strength
    p = source.luminance_percentiles
    q = reference.luminance_percentiles

    return {
        "version": 1,
        "strength": round(strength, 3),
        "basic": {
            "exposureEv": round(exposure, 2),
            "contrast": round(clamp(contrast, -100, 100), 0),
            "highlights": round(clamp((q["p95"] - p["p95"]) * 140.0 * strength, -100, 100), 0),
            "shadows": round(clamp((q["p25"] - p["p25"]) * 140.0 * strength, -100, 100), 0),
            "whites": round(clamp((q["p99"] - p["p99"]) * 120.0 * strength, -100, 100), 0),
            "blacks": round(clamp((q["p05"] - p["p05"]) * 120.0 * strength, -100, 100), 0),
        },
        "color": {
            "temperature": round(clamp(lab_delta[2] * 9.0, -100, 100), 0),
            "tint": round(clamp(lab_delta[1] * 7.0, -100, 100), 0),
            "vibrance": round(clamp(chroma * 0.75, -100, 100), 0),
            "saturation": round(clamp(saturation, -100, 100), 0),
        },
        "toneCurve": tone_curve(source, reference, strength),
        "hsl": hsl_recipe(source, reference, strength),
        "analysis": {
            "source": profile_summary(source),
            "reference": profile_summary(reference),
        },
    }


def tone_curve(source: ImageProfile, reference: ImageProfile, strength: float) -> Dict[str, Any]:
    source_points = [source.luminance_percentiles[key] for key in ["p05", "p25", "p50", "p75", "p95"]]
    reference_points = [
        source_points[index] + (reference.luminance_percentiles[key] - source_points[index]) * strength
        for index, key in enumerate(["p05", "p25", "p50", "p75", "p95"])
    ]
    return {
        "input": [round(x, 4) for x in source_points],
        "output": [round(clamp(x, 0.0, 1.0), 4) for x in reference_points],
        "channels": {
            name: {
                "input": [round(x, 4) for x in source.channel_curves[name]],
                "output": [
                    round(clamp(source.channel_curves[name][i] + (reference.channel_curves[name][i] - source.channel_curves[name][i]) * strength, 0.0, 1.0), 4)
                    for i in range(5)
                ],
            }
            for name in ["r", "g", "b"]
        },
    }


def hsl_recipe(source: ImageProfile, reference: ImageProfile, strength: float) -> Dict[str, Dict[str, float]]:
    result = {}
    for name, _, _ in HUE_BUCKETS:
        src = source.hsl_buckets[name]
        ref = reference.hsl_buckets[name]
        coverage = max(src["coverage"], ref["coverage"])
        weight = clamp(coverage * 8.0, 0.25, 1.0)
        hue_shift = shortest_hue_delta(src["hue"], ref["hue"]) * strength * weight
        saturation_shift = (ref["saturation"] - src["saturation"]) * 100.0 * strength * weight
        luminance_shift = (ref["luminance"] - src["luminance"]) * 100.0 * strength * weight
        result[name] = {
            "hue": round(clamp(hue_shift, -100, 100), 0),
            "saturation": round(clamp(saturation_shift, -100, 100), 0),
            "luminance": round(clamp(luminance_shift, -100, 100), 0),
            "coverage": round(coverage, 4),
        }
    return result


def shortest_hue_delta(source: float, reference: float) -> float:
    return ((reference - source + 180.0) % 360.0) - 180.0


def profile_summary(profile: ImageProfile) -> Dict[str, Any]:
    return {
        "luminanceMean": round(profile.luminance_mean, 4),
        "luminanceStd": round(profile.luminance_std, 4),
        "labMean": [round(float(x), 4) for x in profile.lab_mean],
        "chromaMean": round(profile.chroma_mean, 4),
        "saturationMean": round(profile.saturation_mean, 4),
    }


def generate_cube_lut(recipe: Dict[str, Any], size: int = 17) -> str:
    size = int(clamp(size, 2, 33))
    lines = [
        'TITLE "Color Recipe"',
        "LUT_3D_SIZE %d" % size,
        "DOMAIN_MIN 0.0 0.0 0.0",
        "DOMAIN_MAX 1.0 1.0 1.0",
    ]
    values = np.linspace(0.0, 1.0, size, dtype=np.float32)
    rows: List[np.ndarray] = []
    for blue in values:
        for green in values:
            grid = np.stack(
                [
                    values,
                    np.full_like(values, green),
                    np.full_like(values, blue),
                ],
                axis=-1,
            )
            rows.append(apply_recipe(grid, recipe))

    transformed = np.concatenate(rows, axis=0)
    for rgb in transformed:
        lines.append("%.6f %.6f %.6f" % (rgb[0], rgb[1], rgb[2]))
    return "\n".join(lines) + "\n"


def analyze_images(
    source_bytes: bytes,
    reference_bytes: bytes,
    strength: float = 0.7,
    lut_size: int = 17,
) -> Dict[str, Any]:
    source_rgb = load_image_bytes(source_bytes)
    reference_rgb = load_image_bytes(reference_bytes)
    model = build_model(source_rgb, reference_rgb, strength)
    recipe = generate_recipe(model.source, model.reference, model.strength)
    preview_rgb = apply_recipe(source_rgb, recipe)
    lut = generate_cube_lut(recipe, lut_size)

    return {
        "previewDataUrl": encode_png_data_url(preview_rgb),
        "recipe": recipe,
        "lutCube": lut,
        "recipeJson": json.dumps(recipe, ensure_ascii=False, indent=2),
    }
