import io
import unittest

import numpy as np
from PIL import Image

from app.color_recipe import (
    analyze_images,
    apply_recipe,
    build_model,
    apply_transfer,
    generate_cube_lut,
    list_example_cases,
    rgb_to_hsl,
)


def png_bytes(rgb):
    image = Image.fromarray(np.clip(rgb * 255, 0, 255).astype(np.uint8), mode="RGB")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class ColorRecipeTests(unittest.TestCase):
    def test_strength_zero_preserves_source(self):
        source = np.full((8, 8, 3), [0.25, 0.35, 0.45], dtype=np.float32)
        reference = np.full((8, 8, 3), [0.75, 0.65, 0.45], dtype=np.float32)
        model = build_model(source, reference, 0.0)
        result = apply_transfer(source, model)
        self.assertTrue(np.allclose(source, result, atol=1e-5))

    def test_analysis_returns_preview_recipe_and_lut(self):
        source = np.zeros((16, 16, 3), dtype=np.float32)
        source[..., 0] = 0.25
        source[..., 1] = 0.35
        source[..., 2] = 0.45

        reference = np.zeros((16, 16, 3), dtype=np.float32)
        reference[..., 0] = 0.7
        reference[..., 1] = 0.55
        reference[..., 2] = 0.35

        result = analyze_images(png_bytes(source), png_bytes(reference), strength=0.7, lut_size=4)
        self.assertTrue(result["previewDataUrl"].startswith("data:image/png;base64,"))
        self.assertIn("basic", result["recipe"])
        self.assertIn("deconstruction", result)
        self.assertIn("stepPreviews", result)
        self.assertIn("xmpPreset", result)
        self.assertIn("strengthRecommendation", result)
        self.assertIn("moduleContributions", result)
        self.assertIn("metrics", result)
        self.assertIn("exportRecipe", result)
        self.assertIn("crs:Exposure2012", result["xmpPreset"])
        self.assertEqual(len(result["stepPreviews"]), 4)
        self.assertIn("luminance", result["metrics"]["histograms"])
        self.assertIn("reference", result["metrics"]["hueDistribution"])
        self.assertIn("LUT_3D_SIZE 4", result["lutCube"])

    def test_cube_lut_uses_recipe_renderer(self):
        recipe = {
            "basic": {"exposureEv": 0.0, "contrast": 0, "highlights": 0, "shadows": 0, "whites": 0, "blacks": 0},
            "color": {"temperature": 0, "tint": 0, "vibrance": 0, "saturation": 0},
        }
        lut = generate_cube_lut(recipe, size=2)
        first_rgb = [float(value) for value in lut.splitlines()[4].split()]
        expected = apply_recipe(np.array([[0.0, 0.0, 0.0]], dtype=np.float32), recipe)[0]
        self.assertTrue(np.allclose(first_rgb, expected, atol=1e-6))

    def test_tone_curve_changes_luminance(self):
        source = np.full((8, 8, 3), 0.4, dtype=np.float32)
        recipe = {
            "basic": {},
            "color": {},
            "toneCurve": {"input": [0.0, 0.5, 1.0], "output": [0.0, 0.7, 1.0]},
        }
        result = apply_recipe(source, recipe)
        self.assertGreater(float(result.mean()), float(source.mean()))

    def test_hsl_recipe_changes_targeted_bucket(self):
        source = np.zeros((8, 8, 3), dtype=np.float32)
        source[..., 2] = 0.8
        source[..., 1] = 0.3
        recipe = {
            "basic": {},
            "color": {},
            "hsl": {"blue": {"hue": 0, "saturation": -30, "luminance": 0}},
        }
        result = apply_recipe(source, recipe)
        self.assertLess(float(rgb_to_hsl(result)[..., 1].mean()), float(rgb_to_hsl(source)[..., 1].mean()))

    def test_recipe_strength_zero_preserves_source(self):
        source = np.full((8, 8, 3), [0.2, 0.4, 0.6], dtype=np.float32)
        recipe = {
            "basic": {"exposureEv": 1.0, "contrast": 50, "highlights": 20, "shadows": 20, "whites": 20, "blacks": -20},
            "color": {"temperature": 30, "tint": 20, "vibrance": 20, "saturation": 20},
            "hsl": {"blue": {"hue": 20, "saturation": 20, "luminance": 20}},
        }
        result = apply_recipe(source, recipe, strength=0.0)
        self.assertTrue(np.allclose(source, result, atol=1e-6))

    def test_example_cases_include_images_and_lesson_metadata(self):
        cases = list_example_cases()
        self.assertGreaterEqual(len(cases), 8)
        self.assertTrue(cases[0]["sourceDataUrl"].startswith("data:image/png;base64,"))
        self.assertTrue(cases[0]["referenceDataUrl"].startswith("data:image/png;base64,"))
        self.assertIn("learningGoal", cases[0])


if __name__ == "__main__":
    unittest.main()
