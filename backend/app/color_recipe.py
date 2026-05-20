from __future__ import annotations

import base64
import io
import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List
from xml.sax.saxutils import escape

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
STRENGTH_PRESETS = [
    {"id": "natural", "label": "自然", "strength": 0.4, "description": "保留原图质感，适合直接作为起点。"},
    {"id": "standard", "label": "标准", "strength": 0.55, "description": "明显靠近参考图，同时控制过度风险。"},
    {"id": "strong", "label": "强匹配", "strength": 0.78, "description": "用于观察风格方向，不建议默认套用。"},
]
EXAMPLE_CASES = [
    {
        "id": "clean-japanese",
        "title": "日系清透",
        "category": "清透",
        "difficulty": "基础",
        "learningGoal": "学习抬高中间调、降低反差并控制浅色饱和度。",
        "styleNotes": "画面更亮、更柔，绿色和蓝色趋于干净克制。",
        "commonMistakes": ["曝光提高后忘记压高光", "绿色饱和度过高导致画面发脏"],
    },
    {
        "id": "warm-film",
        "title": "胶片暖调",
        "category": "胶片",
        "difficulty": "进阶",
        "learningGoal": "学习暖色白平衡、柔高光和轻微暗部抬升。",
        "styleNotes": "整体偏暖，暗部不死黑，高光不过白。",
        "commonMistakes": ["只加色温导致肤色发橙", "对比过强破坏胶片柔和感"],
    },
    {
        "id": "commercial-portrait",
        "title": "商业人像",
        "category": "人像",
        "difficulty": "进阶",
        "learningGoal": "学习保护橙色肤色，同时提升画面明净度。",
        "styleNotes": "肤色稳定，高光干净，背景颜色不过度抢眼。",
        "commonMistakes": ["橙色 HSL 调整过度", "自然饱和度过高让肤色变脏"],
    },
    {
        "id": "city-cool",
        "title": "城市冷调",
        "category": "城市",
        "difficulty": "进阶",
        "learningGoal": "学习冷色氛围、蓝青色分离和高反差控制。",
        "styleNotes": "整体偏冷，阴影略青，亮部保留清晰结构。",
        "commonMistakes": ["整体降温过度导致主体失去血色", "暗部压得过死"],
    },
    {
        "id": "forest-green",
        "title": "森系绿色",
        "category": "自然",
        "difficulty": "进阶",
        "learningGoal": "学习单独控制绿色色相、饱和度和明度。",
        "styleNotes": "绿色更统一，饱和度更克制，画面偏柔和。",
        "commonMistakes": ["绿色全部降饱和导致画面灰", "绿色色相偏移过大显假"],
    },
    {
        "id": "seaside-blue",
        "title": "海边蓝调",
        "category": "旅行",
        "difficulty": "基础",
        "learningGoal": "学习蓝色和青色的明度、饱和度分离。",
        "styleNotes": "水面和天空更通透，整体偏清爽。",
        "commonMistakes": ["蓝色饱和度过高", "高光没有保留细节"],
    },
    {
        "id": "neon-night",
        "title": "夜景霓虹",
        "category": "夜景",
        "difficulty": "高级",
        "learningGoal": "学习暗部控制、色彩浓度和高光保护。",
        "styleNotes": "暗部保留氛围，彩色光源更集中。",
        "commonMistakes": ["黑色压死", "饱和度全局提升导致噪点和色块明显"],
    },
    {
        "id": "low-sat-gray",
        "title": "低饱和高级灰",
        "category": "低饱和",
        "difficulty": "进阶",
        "learningGoal": "学习降低色彩浓度但保留影调层次。",
        "styleNotes": "颜色克制，反差有层次，不是简单变灰。",
        "commonMistakes": ["只降饱和度导致画面没精神", "中间调缺乏层次"],
    },
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


def hsl_to_rgb(hsl: np.ndarray) -> np.ndarray:
    hue = np.mod(hsl[..., 0], 1.0)
    saturation = np.clip(hsl[..., 1], 0.0, 1.0)
    lightness = np.clip(hsl[..., 2], 0.0, 1.0)

    chroma = (1.0 - np.abs(2.0 * lightness - 1.0)) * saturation
    h = hue * 6.0
    x = chroma * (1.0 - np.abs((h % 2.0) - 1.0))
    zeros = np.zeros_like(hue)

    rgb_prime = np.zeros(hsl.shape, dtype=np.float32)
    masks = [
        (0.0 <= h) & (h < 1.0),
        (1.0 <= h) & (h < 2.0),
        (2.0 <= h) & (h < 3.0),
        (3.0 <= h) & (h < 4.0),
        (4.0 <= h) & (h < 5.0),
        (5.0 <= h) & (h < 6.0),
    ]
    values = [
        (chroma, x, zeros),
        (x, chroma, zeros),
        (zeros, chroma, x),
        (zeros, x, chroma),
        (x, zeros, chroma),
        (chroma, zeros, x),
    ]
    for mask, channels in zip(masks, values):
        if np.any(mask):
            rgb_prime[..., 0][mask] = channels[0][mask]
            rgb_prime[..., 1][mask] = channels[1][mask]
            rgb_prime[..., 2][mask] = channels[2][mask]

    match = (lightness - chroma / 2.0)[..., None]
    return np.clip(rgb_prime + match, 0.0, 1.0)


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
    """Apply a full recipe, then blend the final visual result by strength."""
    strength = float(np.clip(strength, 0.0, 1.0))
    source = np.clip(rgb.astype(np.float32, copy=True), 0.0, 1.0)
    if strength <= 0:
        return source

    result = source.copy()
    basic = recipe.get("basic", {})
    color = recipe.get("color", {})

    exposure_ev = float(basic.get("exposureEv", 0.0))
    result = np.clip(result * (2.0 ** exposure_ev), 0.0, 1.0)

    result = apply_luminance_controls(
        result,
        contrast=float(basic.get("contrast", 0.0)),
        highlights=float(basic.get("highlights", 0.0)),
        shadows=float(basic.get("shadows", 0.0)),
        whites=float(basic.get("whites", 0.0)),
        blacks=float(basic.get("blacks", 0.0)),
    )
    result = apply_tone_curve(result, recipe.get("toneCurve", {}), 0.45)

    result = apply_lab_color_shift(
        result,
        temperature=float(color.get("temperature", 0.0)) * 0.85,
        tint=float(color.get("tint", 0.0)) * 0.85,
    )

    saturation = float(color.get("saturation", 0.0)) * 0.65
    vibrance = float(color.get("vibrance", 0.0)) * 0.75
    result = adjust_saturation(result, 1.0 + saturation / 100.0)
    result = adjust_vibrance(result, vibrance)
    result = apply_hsl_recipe(result, recipe.get("hsl", {}), 0.6)
    return np.clip(source * (1.0 - strength) + result * strength, 0.0, 1.0)


def apply_tone_curve(rgb: np.ndarray, tone: Dict[str, Any], strength: float = 1.0) -> np.ndarray:
    inputs = tone.get("input")
    outputs = tone.get("output")
    if not inputs or not outputs or len(inputs) != len(outputs):
        return rgb

    result = np.clip(rgb.copy(), 0.0, 1.0)
    input_points = np.asarray(inputs, dtype=np.float32)
    output_points = np.asarray(outputs, dtype=np.float32)
    order = np.argsort(input_points)
    input_points = input_points[order]
    output_points = output_points[order]

    current_luma = luma(result)
    mapped_luma = np.interp(current_luma, input_points, output_points).astype(np.float32)
    target_luma = current_luma + (mapped_luma - current_luma) * float(np.clip(strength, 0.0, 1.0))
    result = result + (target_luma - current_luma)[..., None]

    channels = tone.get("channels", {})
    for index, name in enumerate(["r", "g", "b"]):
        channel = channels.get(name, {})
        channel_input = channel.get("input")
        channel_output = channel.get("output")
        if not channel_input or not channel_output or len(channel_input) != len(channel_output):
            continue
        x = np.asarray(channel_input, dtype=np.float32)
        y = np.asarray(channel_output, dtype=np.float32)
        order = np.argsort(x)
        mapped = np.interp(result[..., index], x[order], y[order]).astype(np.float32)
        result[..., index] = result[..., index] + (mapped - result[..., index]) * 0.35 * strength
    return np.clip(result, 0.0, 1.0)


def apply_hsl_recipe(rgb: np.ndarray, hsl_recipe_values: Dict[str, Any], strength: float = 1.0) -> np.ndarray:
    if not hsl_recipe_values:
        return rgb

    hsl = rgb_to_hsl(rgb)
    hue_degrees = hsl[..., 0] * 360.0
    for name, start, end in HUE_BUCKETS:
        row = hsl_recipe_values.get(name)
        if not row:
            continue
        if start > end:
            mask = (hue_degrees >= start) | (hue_degrees < end)
        else:
            mask = (hue_degrees >= start) & (hue_degrees < end)
        mask = mask & (hsl[..., 1] > 0.05)
        if not np.any(mask):
            continue

        hsl[..., 0][mask] = np.mod(
            hsl[..., 0][mask] + float(row.get("hue", 0.0)) * strength / 360.0,
            1.0,
        )
        hsl[..., 1][mask] = np.clip(
            hsl[..., 1][mask] + float(row.get("saturation", 0.0)) * strength / 100.0,
            0.0,
            1.0,
        )
        hsl[..., 2][mask] = np.clip(
            hsl[..., 2][mask] + float(row.get("luminance", 0.0)) * strength / 100.0,
            0.0,
            1.0,
        )
    return hsl_to_rgb(hsl)


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


def generate_cube_lut(recipe: Dict[str, Any], size: int = 17, strength: float = 1.0) -> str:
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
            rows.append(apply_recipe(grid, recipe, strength=strength))

    transformed = np.concatenate(rows, axis=0)
    for rgb in transformed:
        lines.append("%.6f %.6f %.6f" % (rgb[0], rgb[1], rgb[2]))
    return "\n".join(lines) + "\n"


def scale_recipe(recipe: Dict[str, Any], strength: float) -> Dict[str, Any]:
    strength = float(np.clip(strength, 0.0, 1.0))
    scaled = json.loads(json.dumps(recipe))
    scaled["strength"] = round(strength, 3)
    for section in ["basic", "color"]:
        for key, value in scaled.get(section, {}).items():
            if isinstance(value, (int, float)):
                scaled[section][key] = round(float(value) * strength, 2 if key == "exposureEv" else 0)

    tone = scaled.get("toneCurve", {})
    inputs = tone.get("input", [])
    outputs = tone.get("output", [])
    if len(inputs) == len(outputs):
        tone["output"] = [
            round(float(inputs[index]) + (float(outputs[index]) - float(inputs[index])) * strength, 4)
            for index in range(len(inputs))
        ]
    for channel in tone.get("channels", {}).values():
        channel_input = channel.get("input", [])
        channel_output = channel.get("output", [])
        if len(channel_input) == len(channel_output):
            channel["output"] = [
                round(float(channel_input[index]) + (float(channel_output[index]) - float(channel_input[index])) * strength, 4)
                for index in range(len(channel_input))
            ]

    for row in scaled.get("hsl", {}).values():
        for key in ["hue", "saturation", "luminance"]:
            row[key] = round(float(row.get(key, 0.0)) * strength, 0)
    return scaled


def build_deconstruction(source: ImageProfile, reference: ImageProfile, recipe: Dict[str, Any]) -> Dict[str, Any]:
    basic = recipe["basic"]
    color = recipe["color"]
    hsl = recipe["hsl"]
    tone = recipe["toneCurve"]

    dominant_hsl = sorted(
        [
            (name, row)
            for name, row in hsl.items()
            if float(row.get("coverage", 0.0)) >= 0.01
            and (
                abs(float(row.get("hue", 0.0))) >= 4
                or abs(float(row.get("saturation", 0.0))) >= 4
                or abs(float(row.get("luminance", 0.0))) >= 4
            )
        ],
        key=lambda item: float(item[1].get("coverage", 0.0)),
        reverse=True,
    )[:3]

    summary_parts = [
        describe_exposure(float(basic["exposureEv"])),
        describe_contrast(float(basic["contrast"])),
        describe_temperature(float(color["temperature"]), float(color["tint"])),
        describe_saturation(float(color["saturation"]), float(color["vibrance"])),
    ]
    summary = "；".join([part for part in summary_parts if part]) or "参考图与原图整体调性接近，建议以小幅微调为主。"

    key_differences = [
        {
            "label": "曝光",
            "value": "%+.2f EV" % float(basic["exposureEv"]),
            "explanation": "根据两张图的平均亮度差计算，先决定整体明暗基准。",
        },
        {
            "label": "反差",
            "value": "%+d" % int(round(float(basic["contrast"]))),
            "explanation": "来自亮度标准差和分位点差异，用于判断画面是更硬还是更柔。",
        },
        {
            "label": "白平衡",
            "value": "色温 %+d / 色调 %+d"
            % (int(round(float(color["temperature"]))), int(round(float(color["tint"])))),
            "explanation": "由 LAB 色彩均值差推导，是参考图整体冷暖和绿洋红偏移的近似。",
        },
        {
            "label": "色彩浓度",
            "value": "自然饱和度 %+d / 饱和度 %+d"
            % (int(round(float(color["vibrance"]))), int(round(float(color["saturation"])))),
            "explanation": "综合 chroma 和 HSL 平均饱和度，决定颜色是否更克制或更浓烈。",
        },
    ]

    steps = [
        {
            "id": "basic",
            "title": "先定基础影调",
            "summary": "调整曝光、对比、高光、阴影、白色和黑色，让原图进入参考图的明暗范围。",
            "parameters": [
                parameter_note("曝光", basic["exposureEv"], "EV", "先定整体亮度，避免后续颜色判断被明暗误导。"),
                parameter_note("对比", basic["contrast"], "", "匹配参考图的明暗分离程度。"),
                parameter_note(
                    "高光/阴影",
                    "%+d / %+d"
                    % (int(round(float(basic["highlights"]))), int(round(float(basic["shadows"])))),
                    "",
                    "控制亮部和暗部的局部压缩或抬升。",
                ),
            ],
        },
        {
            "id": "curve",
            "title": "再塑造曲线",
            "summary": "用亮度曲线和 RGB 通道曲线微调黑白场、中间调和通道偏色。",
            "parameters": [
                parameter_note("亮度曲线", curve_note(tone), "", "曲线负责参考图最明显的明暗层次和通透感。"),
            ],
        },
        {
            "id": "color",
            "title": "校准整体色彩",
            "summary": "用色温、色调、自然饱和度和饱和度对齐参考图的整体色彩基调。",
            "parameters": [
                parameter_note("色温", color["temperature"], "", "控制画面冷暖倾向。"),
                parameter_note("色调", color["tint"], "", "控制绿和洋红方向的整体偏移。"),
                parameter_note(
                    "自然饱和度/饱和度",
                    "%+d / %+d"
                    % (int(round(float(color["vibrance"]))), int(round(float(color["saturation"])))),
                    "",
                    "先保守提升低饱和颜色，再调整整体浓度。",
                ),
            ],
        },
        {
            "id": "hsl",
            "title": "最后做 HSL 分色",
            "summary": hsl_step_summary(dominant_hsl),
            "parameters": [
                parameter_note(
                    hsl_label(name),
                    "%+d / %+d / %+d"
                    % (
                        int(round(float(row["hue"]))),
                        int(round(float(row["saturation"]))),
                        int(round(float(row["luminance"]))),
                    ),
                    "",
                    "分别对应色相、饱和度、明度。",
                )
                for name, row in dominant_hsl
            ]
            or [parameter_note("HSL", "0", "", "主要颜色桶差异较小，当前不需要强分色。")],
        },
    ]

    return {
        "summary": summary,
        "keyDifferences": key_differences,
        "steps": steps,
        "diagnostics": diagnostics(source, reference, recipe),
        "lightroomNote": "Lightroom/ACR 参数为近似映射，用于教学和起点预设，不等同于 Adobe 内部算法。",
    }


def parameter_note(label: str, value: Any, unit: str, reason: str) -> Dict[str, Any]:
    return {
        "label": label,
        "value": str(value) + ((" " + unit) if unit else ""),
        "reason": reason,
    }


def describe_exposure(value: float) -> str:
    if value > 0.12:
        return "参考图整体更亮"
    if value < -0.12:
        return "参考图整体更暗"
    return "整体曝光接近"


def describe_contrast(value: float) -> str:
    if value > 8:
        return "反差更强"
    if value < -8:
        return "反差更柔"
    return "反差变化不大"


def describe_temperature(temperature: float, tint: float) -> str:
    parts = []
    if temperature > 6:
        parts.append("色彩偏暖")
    elif temperature < -6:
        parts.append("色彩偏冷")
    if tint > 6:
        parts.append("略偏洋红")
    elif tint < -6:
        parts.append("略偏绿色")
    return "、".join(parts)


def describe_saturation(saturation: float, vibrance: float) -> str:
    amount = saturation + vibrance * 0.5
    if amount > 8:
        return "颜色更浓"
    if amount < -8:
        return "颜色更克制"
    return "饱和度接近"


def curve_note(tone: Dict[str, Any]) -> str:
    inputs = tone.get("input", [])
    outputs = tone.get("output", [])
    if len(inputs) < 5 or len(outputs) < 5:
        return "无明显曲线变化"
    shadow = (outputs[1] - inputs[1]) * 100.0
    mid = (outputs[2] - inputs[2]) * 100.0
    highlight = (outputs[3] - inputs[3]) * 100.0
    return "阴影 %+d / 中间调 %+d / 高光 %+d" % (round(shadow), round(mid), round(highlight))


def hsl_step_summary(rows: List[Any]) -> str:
    if not rows:
        return "参考图没有明显需要单独处理的主色桶，HSL 只做轻微校准。"
    parts = []
    for name, row in rows:
        shifts = []
        if abs(float(row["hue"])) >= 4:
            shifts.append("色相%+d" % int(row["hue"]))
        if abs(float(row["saturation"])) >= 4:
            shifts.append("饱和%+d" % int(row["saturation"]))
        if abs(float(row["luminance"])) >= 4:
            shifts.append("明度%+d" % int(row["luminance"]))
        parts.append("%s%s" % (hsl_label(name), "、".join(shifts)))
    return "重点处理：" + "；".join(parts)


def hsl_label(name: str) -> str:
    labels = {
        "red": "红色",
        "orange": "橙色",
        "yellow": "黄色",
        "green": "绿色",
        "aqua": "青色",
        "blue": "蓝色",
        "purple": "紫色",
        "magenta": "洋红",
    }
    return labels.get(name, name)


def diagnostics(source: ImageProfile, reference: ImageProfile, recipe: Dict[str, Any]) -> List[Dict[str, str]]:
    notes: List[Dict[str, str]] = []
    reference_hsl = reference.hsl_buckets
    if reference_hsl["orange"]["coverage"] > 0.08:
        notes.append({"label": "肤色/暖色覆盖", "message": "参考图橙色覆盖较高，HSL 调整时应避免过度移动橙色明度和色相。"})
    if reference_hsl["blue"]["coverage"] > 0.08 or reference_hsl["aqua"]["coverage"] > 0.08:
        notes.append({"label": "天空/冷色覆盖", "message": "蓝色或青色覆盖较高，建议重点检查天空、阴影或背景冷色是否自然。"})
    if reference_hsl["green"]["coverage"] > 0.08:
        notes.append({"label": "绿色覆盖", "message": "绿色占比较高，适合用 HSL 单独控制植被的饱和度和明度。"})
    if abs(float(recipe["basic"]["contrast"])) > 45:
        notes.append({"label": "高反差调整", "message": "对比度变化较大，建议回看暗部是否丢失层次。"})
    if not notes:
        notes.append({"label": "整体风险", "message": "没有检测到需要特别保护的高覆盖颜色，当前配方适合做全局风格起点。"})
    return notes


def strength_recommendation(source: ImageProfile, reference: ImageProfile, requested: float) -> Dict[str, Any]:
    contrast_gap = abs(reference.luminance_std / source.luminance_std - 1.0)
    exposure_gap = abs(exposure_delta_ev(source, reference))
    saturation_gap = abs(reference.saturation_mean / max(source.saturation_mean, 1e-4) - 1.0)
    risk = contrast_gap * 0.45 + exposure_gap * 0.25 + saturation_gap * 0.35
    recommended = 0.55
    if risk > 0.55:
        recommended = 0.4
    elif risk < 0.22:
        recommended = 0.62

    mode = min(STRENGTH_PRESETS, key=lambda item: abs(float(item["strength"]) - recommended))
    reasons = []
    if exposure_gap > 0.5:
        reasons.append("原图和参考图曝光差较大，降低强度可避免亮度过冲。")
    if contrast_gap > 0.35:
        reasons.append("反差差异较大，曲线和基础面板容易叠加。")
    if saturation_gap > 0.35:
        reasons.append("饱和度差异较大，建议让 HSL 只做局部微调。")
    if not reasons:
        reasons.append("两张图整体差异适中，标准强度适合观察参考图风格。")

    return {
        "requestedStrength": round(float(np.clip(requested, 0.0, 1.0)), 3),
        "recommendedStrength": round(recommended, 3),
        "mode": mode["id"],
        "label": mode["label"],
        "reason": " ".join(reasons),
        "presets": STRENGTH_PRESETS,
    }


def module_contributions(recipe: Dict[str, Any]) -> List[Dict[str, str]]:
    basic = recipe.get("basic", {})
    color = recipe.get("color", {})
    hsl = recipe.get("hsl", {})
    tone = recipe.get("toneCurve", {})
    curve_amount = mean_abs_delta(tone.get("input", []), tone.get("output", [])) * 100.0
    hsl_amount = max(
        [
            abs(float(row.get("hue", 0.0))) * 0.4
            + abs(float(row.get("saturation", 0.0)))
            + abs(float(row.get("luminance", 0.0)))
            for row in hsl.values()
        ]
        or [0.0]
    )
    return [
        {
            "id": "basic",
            "label": "基础影调",
            "role": "主调整",
            "impact": impact_label(abs(float(basic.get("exposureEv", 0.0))) * 40.0 + abs(float(basic.get("contrast", 0.0)))),
            "message": "先建立曝光、对比和黑白场，是当前配方的主要骨架。",
        },
        {
            "id": "curve",
            "label": "曲线",
            "role": "微调",
            "impact": impact_label(curve_amount),
            "message": "曲线只补充层次和通道细节，避免重复替代基础影调。",
        },
        {
            "id": "color",
            "label": "整体色彩",
            "role": "主调整",
            "impact": impact_label(abs(float(color.get("temperature", 0.0))) + abs(float(color.get("tint", 0.0))) + abs(float(color.get("saturation", 0.0)))),
            "message": "负责白平衡和整体颜色浓度，是参考图色彩基调的主要来源。",
        },
        {
            "id": "hsl",
            "label": "HSL 分色",
            "role": "局部微调",
            "impact": impact_label(hsl_amount),
            "message": "只处理高覆盖或差异明显的颜色，避免全局饱和度和 HSL 重复用力。",
        },
    ]


def impact_label(value: float) -> str:
    if value >= 45:
        return "强"
    if value >= 18:
        return "中"
    return "轻"


def mean_abs_delta(a: List[float], b: List[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    return float(sum(abs(float(y) - float(x)) for x, y in zip(a, b)) / len(a))


def analysis_metrics(source_rgb: np.ndarray, reference_rgb: np.ndarray, preview_rgb: np.ndarray) -> Dict[str, Any]:
    return {
        "histograms": {
            "luminance": {
                "source": histogram_values(luma(source_rgb)),
                "reference": histogram_values(luma(reference_rgb)),
                "result": histogram_values(luma(preview_rgb)),
            },
            "rgb": {
                name: {
                    "source": histogram_values(source_rgb[..., index]),
                    "reference": histogram_values(reference_rgb[..., index]),
                    "result": histogram_values(preview_rgb[..., index]),
                }
                for index, name in enumerate(["r", "g", "b"])
            },
            "saturation": {
                "source": histogram_values(rgb_to_hsl(source_rgb)[..., 1]),
                "reference": histogram_values(rgb_to_hsl(reference_rgb)[..., 1]),
                "result": histogram_values(rgb_to_hsl(preview_rgb)[..., 1]),
            },
        },
        "hueDistribution": {
            "source": hue_distribution(source_rgb),
            "reference": hue_distribution(reference_rgb),
            "result": hue_distribution(preview_rgb),
        },
        "toneZones": tone_zones(source_rgb, reference_rgb, preview_rgb),
        "colorCast": color_cast(source_rgb, reference_rgb, preview_rgb),
    }


def histogram_values(values: np.ndarray, bins: int = 16) -> List[float]:
    hist, _ = np.histogram(np.clip(values, 0.0, 1.0), bins=bins, range=(0.0, 1.0))
    total = max(int(hist.sum()), 1)
    return [round(float(value) / total, 4) for value in hist]


def hue_distribution(rgb: np.ndarray) -> Dict[str, float]:
    hsl = rgb_to_hsl(rgb).reshape((-1, 3))
    buckets = compute_hsl_buckets(hsl)
    return {name: round(float(row["coverage"]), 4) for name, row in buckets.items()}


def tone_zones(source_rgb: np.ndarray, reference_rgb: np.ndarray, preview_rgb: np.ndarray) -> Dict[str, Dict[str, float]]:
    return {
        "shadows": zone_values(source_rgb, reference_rgb, preview_rgb, 0.0, 0.33),
        "midtones": zone_values(source_rgb, reference_rgb, preview_rgb, 0.33, 0.66),
        "highlights": zone_values(source_rgb, reference_rgb, preview_rgb, 0.66, 1.0),
    }


def zone_values(source_rgb: np.ndarray, reference_rgb: np.ndarray, preview_rgb: np.ndarray, low: float, high: float) -> Dict[str, float]:
    result = {}
    for label, rgb in [("source", source_rgb), ("reference", reference_rgb), ("result", preview_rgb)]:
        values = luma(rgb)
        mask = (values >= low) & (values < high)
        result[label] = round(float(values[mask].mean()) if np.any(mask) else 0.0, 4)
    return result


def color_cast(source_rgb: np.ndarray, reference_rgb: np.ndarray, preview_rgb: np.ndarray) -> Dict[str, Any]:
    casts = {}
    for label, rgb in [("source", source_rgb), ("reference", reference_rgb), ("result", preview_rgb)]:
        lab_mean = rgb_to_lab(rgb).reshape((-1, 3)).mean(axis=0)
        casts[label] = {
            "a": round(float(lab_mean[1]), 3),
            "b": round(float(lab_mean[2]), 3),
            "direction": cast_direction(float(lab_mean[1]), float(lab_mean[2])),
        }
    return casts


def cast_direction(a: float, b: float) -> str:
    horizontal = "偏洋红" if a > 2 else "偏绿" if a < -2 else ""
    vertical = "偏暖" if b > 3 else "偏冷" if b < -3 else ""
    return "、".join([part for part in [vertical, horizontal] if part]) or "接近中性"


def build_step_previews(source_rgb: np.ndarray, recipe: Dict[str, Any], strength: float = 1.0) -> List[Dict[str, str]]:
    stages = [
        ("basic", "基础影调", {"basic": recipe.get("basic", {})}),
        ("curve", "加入曲线", {"basic": recipe.get("basic", {}), "toneCurve": recipe.get("toneCurve", {})}),
        (
            "color",
            "加入整体色彩",
            {
                "basic": recipe.get("basic", {}),
                "toneCurve": recipe.get("toneCurve", {}),
                "color": recipe.get("color", {}),
            },
        ),
        ("hsl", "加入 HSL 分色", recipe),
    ]
    return [
        {
            "id": stage_id,
            "label": label,
            "previewDataUrl": encode_png_data_url(apply_recipe(source_rgb, partial_recipe, strength=strength)),
        }
        for stage_id, label, partial_recipe in stages
    ]


def lightroom_settings(recipe: Dict[str, Any]) -> Dict[str, int | float | str]:
    basic = recipe.get("basic", {})
    color = recipe.get("color", {})
    hsl = recipe.get("hsl", {})
    settings: Dict[str, int | float | str] = {
        "WhiteBalance": "Custom",
        "Exposure2012": round(float(basic.get("exposureEv", 0.0)), 2),
        "Contrast2012": int(clamp(float(basic.get("contrast", 0.0)), -100, 100)),
        "Highlights2012": int(clamp(float(basic.get("highlights", 0.0)), -100, 100)),
        "Shadows2012": int(clamp(float(basic.get("shadows", 0.0)), -100, 100)),
        "Whites2012": int(clamp(float(basic.get("whites", 0.0)), -100, 100)),
        "Blacks2012": int(clamp(float(basic.get("blacks", 0.0)), -100, 100)),
        "Temperature": int(clamp(5500 + float(color.get("temperature", 0.0)) * 35, 2000, 50000)),
        "Tint": int(clamp(float(color.get("tint", 0.0)), -150, 150)),
        "Vibrance": int(clamp(float(color.get("vibrance", 0.0)), -100, 100)),
        "Saturation": int(clamp(float(color.get("saturation", 0.0)), -100, 100)),
    }
    for name, prefix in [
        ("red", "Red"),
        ("orange", "Orange"),
        ("yellow", "Yellow"),
        ("green", "Green"),
        ("aqua", "Aqua"),
        ("blue", "Blue"),
        ("purple", "Purple"),
        ("magenta", "Magenta"),
    ]:
        row = hsl.get(name, {})
        settings["HueAdjustment" + prefix] = int(clamp(float(row.get("hue", 0.0)), -100, 100))
        settings["SaturationAdjustment" + prefix] = int(clamp(float(row.get("saturation", 0.0)), -100, 100))
        settings["LuminanceAdjustment" + prefix] = int(clamp(float(row.get("luminance", 0.0)), -100, 100))
    return settings


def generate_xmp_preset(recipe: Dict[str, Any], name: str = "Color Recipe") -> str:
    settings = lightroom_settings(recipe)
    attributes = [
        'crs:PresetType="Normal"',
        'crs:Cluster="Color Recipe"',
        'crs:UUID="color-recipe-generated"',
        'crs:SupportsAmount="False"',
        'crs:SupportsColor="True"',
        'crs:SupportsMonochrome="True"',
        'crs:SupportsHighDynamicRange="True"',
        'crs:SupportsNormalDynamicRange="True"',
        'crs:RequiresRGBTables="False"',
        'crs:Name="%s"' % escape(name),
    ]
    attributes.extend(['crs:%s="%s"' % (key, escape(str(value))) for key, value in settings.items()])
    joined = "\n   ".join(attributes)
    return """<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
   %s/>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
""" % joined


def list_example_cases() -> List[Dict[str, Any]]:
    return [
        {
            **case,
            "sourceDataUrl": encode_png_data_url(example_image(case["id"], target=False)),
            "referenceDataUrl": encode_png_data_url(example_image(case["id"], target=True)),
        }
        for case in EXAMPLE_CASES
    ]


def example_image(case_id: str, target: bool = False, size: int = 360) -> np.ndarray:
    x = np.linspace(0.0, 1.0, size, dtype=np.float32)
    y = np.linspace(0.0, 1.0, int(size * 0.72), dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    base = np.stack(
        [
            0.28 + 0.55 * xx,
            0.24 + 0.52 * yy,
            0.32 + 0.38 * (1.0 - xx * 0.45),
        ],
        axis=-1,
    )
    base += 0.08 * np.sin((xx * 6.0 + yy * 3.0))[..., None]
    base = np.clip(base, 0.0, 1.0)
    if not target:
        return base

    recipes = {
        "clean-japanese": {"basic": {"exposureEv": 0.35, "contrast": -18, "highlights": -18, "shadows": 22, "whites": 8, "blacks": 12}, "color": {"temperature": -4, "tint": 3, "vibrance": -8, "saturation": -6}, "hsl": {"green": {"hue": -8, "saturation": -18, "luminance": 12}, "blue": {"hue": -6, "saturation": -12, "luminance": 8}}},
        "warm-film": {"basic": {"exposureEv": 0.08, "contrast": -10, "highlights": -28, "shadows": 18, "whites": -8, "blacks": 10}, "color": {"temperature": 28, "tint": 8, "vibrance": 6, "saturation": -8}, "hsl": {"orange": {"hue": -4, "saturation": -6, "luminance": 6}, "green": {"hue": 12, "saturation": -22, "luminance": -4}}},
        "commercial-portrait": {"basic": {"exposureEv": 0.22, "contrast": 14, "highlights": -10, "shadows": 10, "whites": 14, "blacks": -8}, "color": {"temperature": 8, "tint": 6, "vibrance": 10, "saturation": -4}, "hsl": {"orange": {"hue": -2, "saturation": -4, "luminance": 10}, "red": {"hue": 0, "saturation": -8, "luminance": 5}}},
        "city-cool": {"basic": {"exposureEv": -0.05, "contrast": 26, "highlights": -8, "shadows": -18, "whites": 10, "blacks": -18}, "color": {"temperature": -26, "tint": -4, "vibrance": 4, "saturation": -6}, "hsl": {"aqua": {"hue": -8, "saturation": 10, "luminance": -4}, "blue": {"hue": -10, "saturation": 12, "luminance": -8}}},
        "forest-green": {"basic": {"exposureEv": 0.05, "contrast": -6, "highlights": -14, "shadows": 14, "whites": 0, "blacks": 6}, "color": {"temperature": 10, "tint": -8, "vibrance": -6, "saturation": -10}, "hsl": {"green": {"hue": -18, "saturation": -24, "luminance": 10}, "yellow": {"hue": -10, "saturation": -14, "luminance": 4}}},
        "seaside-blue": {"basic": {"exposureEv": 0.18, "contrast": 8, "highlights": -12, "shadows": 8, "whites": 12, "blacks": 0}, "color": {"temperature": -10, "tint": 0, "vibrance": 12, "saturation": 2}, "hsl": {"aqua": {"hue": -8, "saturation": 12, "luminance": 12}, "blue": {"hue": -6, "saturation": 10, "luminance": 8}}},
        "neon-night": {"basic": {"exposureEv": -0.45, "contrast": 36, "highlights": -34, "shadows": -20, "whites": 18, "blacks": -22}, "color": {"temperature": -12, "tint": 18, "vibrance": 24, "saturation": 10}, "hsl": {"magenta": {"hue": 8, "saturation": 28, "luminance": 4}, "blue": {"hue": -12, "saturation": 22, "luminance": -10}}},
        "low-sat-gray": {"basic": {"exposureEv": -0.08, "contrast": 10, "highlights": -16, "shadows": 12, "whites": -6, "blacks": -4}, "color": {"temperature": -4, "tint": 2, "vibrance": -28, "saturation": -26}, "hsl": {"green": {"hue": 8, "saturation": -32, "luminance": 4}, "blue": {"hue": 0, "saturation": -24, "luminance": -2}}},
    }
    recipe = recipes.get(case_id, recipes["clean-japanese"])
    return apply_recipe(base, recipe, strength=0.82)


def analyze_images(
    source_bytes: bytes,
    reference_bytes: bytes,
    strength: float = 0.55,
    lut_size: int = 17,
) -> Dict[str, Any]:
    source_rgb = load_image_bytes(source_bytes)
    reference_rgb = load_image_bytes(reference_bytes)
    visual_strength = float(np.clip(strength, 0.0, 1.0))
    model = build_model(source_rgb, reference_rgb, visual_strength)
    recipe = generate_recipe(model.source, model.reference, 1.0)
    recipe["strength"] = round(visual_strength, 3)
    preview_rgb = apply_recipe(source_rgb, recipe, strength=visual_strength)
    export_recipe = scale_recipe(recipe, visual_strength)
    lut = generate_cube_lut(recipe, lut_size, strength=visual_strength)
    deconstruction = build_deconstruction(model.source, model.reference, recipe)
    xmp = generate_xmp_preset(export_recipe)

    return {
        "previewDataUrl": encode_png_data_url(preview_rgb),
        "stepPreviews": build_step_previews(source_rgb, recipe, strength=visual_strength),
        "recipe": recipe,
        "exportRecipe": export_recipe,
        "deconstruction": deconstruction,
        "strengthRecommendation": strength_recommendation(model.source, model.reference, visual_strength),
        "moduleContributions": module_contributions(recipe),
        "metrics": analysis_metrics(source_rgb, reference_rgb, preview_rgb),
        "lightroomSettings": lightroom_settings(recipe),
        "lutCube": lut,
        "xmpPreset": xmp,
        "recipeJson": json.dumps(export_recipe, ensure_ascii=False, indent=2),
    }
