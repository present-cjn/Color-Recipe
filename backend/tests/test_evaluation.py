import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from app.color_recipe import rgb_to_hsl
from evaluation.evaluate_recipe import evaluate_dataset
from evaluation.make_synthetic_dataset import make_synthetic_dataset
from evaluation.recipe_apply import apply_recipe


def gradient_image(width=24, height=18):
    x = np.linspace(0.1, 0.9, width, dtype=np.float32)
    y = np.linspace(0.15, 0.85, height, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    return np.stack([xx, yy, 1.0 - xx * 0.6], axis=-1)


def save_png(path, rgb):
    image = Image.fromarray(np.clip(rgb * 255, 0, 255).astype(np.uint8), mode="RGB")
    image.save(path, format="PNG")


class EvaluationTests(unittest.TestCase):
    def test_empty_recipe_preserves_image(self):
        source = gradient_image()
        result = apply_recipe(source, {"basic": {}, "color": {}})
        self.assertTrue(np.allclose(source, result, atol=1e-5))

    def test_exposure_and_saturation_move_expected_direction(self):
        source = gradient_image()
        brighter = apply_recipe(source, {"basic": {"exposureEv": 0.5}, "color": {}})
        self.assertGreater(float(brighter.mean()), float(source.mean()))

        saturated = apply_recipe(source, {"basic": {}, "color": {"saturation": 40}})
        source_sat = float(rgb_to_hsl(source)[..., 1].mean())
        result_sat = float(rgb_to_hsl(saturated)[..., 1].mean())
        self.assertGreater(result_sat, source_sat)

    def test_synthetic_dataset_generation_is_seeded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            input_dir.mkdir()
            save_png(input_dir / "one.png", gradient_image())

            first = make_synthetic_dataset(input_dir, root / "dataset_a", variants_per_image=2, seed=7, max_size=64)
            second = make_synthetic_dataset(input_dir, root / "dataset_b", variants_per_image=2, seed=7, max_size=64)

            first_recipe = json.loads((root / "dataset_a" / "sample_000000" / "ground_truth.json").read_text())
            second_recipe = json.loads((root / "dataset_b" / "sample_000000" / "ground_truth.json").read_text())
            self.assertEqual(len(first["samples"]), 2)
            self.assertEqual(first_recipe, second_recipe)

    def test_evaluate_dataset_writes_summary_and_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            input_dir.mkdir()
            save_png(input_dir / "one.png", gradient_image())
            save_png(input_dir / "two.png", np.flipud(gradient_image()))

            dataset_dir = root / "dataset"
            report_dir = root / "report"
            make_synthetic_dataset(input_dir, dataset_dir, variants_per_image=1, seed=11, max_size=64)
            summary = evaluate_dataset(dataset_dir, report_dir, lut_size=3, save_previews=True)

            self.assertEqual(summary["sampleCount"], 2)
            self.assertTrue((report_dir / "summary.json").exists())
            self.assertTrue((report_dir / "samples.csv").exists())
            self.assertTrue((report_dir / "report.html").exists())
            self.assertTrue((report_dir / "previews" / "sample_000000.png").exists())
            self.assertIn("basic.exposureEv", summary["parameterMetrics"])
            self.assertIn("rgbMae", summary["imageMetrics"])
            self.assertIn("Color Recipe Evaluation Report", (report_dir / "report.html").read_text())


if __name__ == "__main__":
    unittest.main()
