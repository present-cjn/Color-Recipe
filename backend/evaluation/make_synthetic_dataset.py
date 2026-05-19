from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

import numpy as np
from PIL import Image, ImageOps

from app.color_recipe import convert_to_srgb, to_uint8
from evaluation.recipe_apply import apply_recipe


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def main() -> None:
    args = parse_args()
    manifest = make_synthetic_dataset(
        input_dir=args.input,
        output_dir=args.output,
        variants_per_image=args.variants_per_image,
        seed=args.seed,
        max_size=args.max_size,
    )
    print("Generated %d samples at %s" % (len(manifest["samples"]), args.output))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a synthetic Color Recipe evaluation dataset.")
    parser.add_argument("--input", required=True, type=Path, help="Directory containing source images.")
    parser.add_argument("--output", required=True, type=Path, help="Output dataset directory.")
    parser.add_argument("--variants-per-image", default=3, type=int, help="Number of recipes per input image.")
    parser.add_argument("--seed", default=42, type=int, help="Random seed.")
    parser.add_argument("--max-size", default=1200, type=int, help="Maximum long edge for generated images.")
    return parser.parse_args()


def make_synthetic_dataset(
    input_dir: Path,
    output_dir: Path,
    variants_per_image: int = 3,
    seed: int = 42,
    max_size: int = 1200,
) -> Dict[str, Any]:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    image_paths = list(iter_image_paths(input_dir))
    if not image_paths:
        raise ValueError("No images found in %s" % input_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    samples: List[Dict[str, Any]] = []
    sample_index = 0

    for image_path in image_paths:
        source_rgb = load_image_path(image_path, max_size=max_size)
        for variant_index in range(max(1, variants_per_image)):
            recipe = sample_recipe(rng)
            target_rgb = apply_recipe(source_rgb, recipe, strength=1.0)
            sample_id = "sample_%06d" % sample_index
            sample_dir = output_dir / sample_id
            sample_dir.mkdir(parents=True, exist_ok=True)

            save_rgb(sample_dir / "source.png", source_rgb)
            save_rgb(sample_dir / "target.png", target_rgb)
            write_json(sample_dir / "ground_truth.json", recipe)

            samples.append(
                {
                    "id": sample_id,
                    "source_image": str(image_path),
                    "variant": variant_index,
                    "source": "%s/source.png" % sample_id,
                    "target": "%s/target.png" % sample_id,
                    "ground_truth": "%s/ground_truth.json" % sample_id,
                }
            )
            sample_index += 1

    manifest = {
        "version": 1,
        "seed": seed,
        "variantsPerImage": variants_per_image,
        "maxSize": max_size,
        "samples": samples,
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def iter_image_paths(input_dir: Path) -> Iterable[Path]:
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            yield path


def load_image_path(path: Path, max_size: int) -> np.ndarray:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image = convert_to_srgb(image)
        image = image.convert("RGB")
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        return np.asarray(image).astype(np.float32) / 255.0


def save_rgb(path: Path, rgb: np.ndarray) -> None:
    image = Image.fromarray(to_uint8(rgb), mode="RGB")
    image.save(path, format="PNG", optimize=True)


def sample_recipe(rng: np.random.Generator) -> Dict[str, Any]:
    return {
        "version": 1,
        "strength": 1.0,
        "basic": {
            "exposureEv": round(float(rng.uniform(-1.0, 1.0)), 2),
            "contrast": int(rng.integers(-60, 61)),
            "highlights": int(rng.integers(-60, 61)),
            "shadows": int(rng.integers(-60, 61)),
            "whites": int(rng.integers(-60, 61)),
            "blacks": int(rng.integers(-60, 61)),
        },
        "color": {
            "temperature": int(rng.integers(-60, 61)),
            "tint": int(rng.integers(-60, 61)),
            "vibrance": int(rng.integers(-60, 61)),
            "saturation": int(rng.integers(-60, 61)),
        },
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
