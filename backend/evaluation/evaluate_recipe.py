from __future__ import annotations

import argparse
import base64
import csv
import html as html_lib
import io
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
from PIL import Image

from app.color_recipe import analyze_images, load_image_bytes, rgb_to_lab, to_uint8


PARAMETER_PATHS = [
    ("basic.exposureEv", 0.05),
    ("basic.contrast", 1.0),
    ("basic.highlights", 1.0),
    ("basic.shadows", 1.0),
    ("basic.whites", 1.0),
    ("basic.blacks", 1.0),
    ("color.temperature", 1.0),
    ("color.tint", 1.0),
    ("color.vibrance", 1.0),
    ("color.saturation", 1.0),
]
CORE_PARAMETER_PATHS = {
    "basic.exposureEv",
    "color.temperature",
    "color.tint",
    "color.saturation",
}


def main() -> None:
    args = parse_args()
    summary = evaluate_dataset(
        dataset_dir=args.dataset,
        output_dir=args.output,
        lut_size=args.lut_size,
        save_previews=args.save_previews,
    )
    print("Evaluated %d samples" % summary["sampleCount"])
    print("Mean RGB MAE: %.5f" % summary["imageMetrics"]["rgbMae"]["mean"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Color Recipe parameter recovery.")
    parser.add_argument("--dataset", required=True, type=Path, help="Synthetic dataset directory.")
    parser.add_argument("--output", required=True, type=Path, help="Evaluation report directory.")
    parser.add_argument("--lut-size", default=4, type=int, help="LUT size used by analyze_images.")
    parser.add_argument("--save-previews", action="store_true", help="Save source/target/predicted preview strips.")
    return parser.parse_args()


def evaluate_dataset(
    dataset_dir: Path,
    output_dir: Path,
    lut_size: int = 4,
    save_previews: bool = False,
) -> Dict[str, Any]:
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)
    manifest_path = dataset_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("Missing manifest.json in %s" % dataset_dir)

    manifest = read_json(manifest_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_dir = output_dir / "previews"
    if save_previews:
        preview_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    report_samples: List[Dict[str, Any]] = []
    image_metric_rows: List[Dict[str, float]] = []
    parameter_errors: Dict[str, List[float]] = {path: [] for path, _ in PARAMETER_PATHS}
    parameter_squared_errors: Dict[str, List[float]] = {path: [] for path, _ in PARAMETER_PATHS}
    direction_hits: Dict[str, List[int]] = {path: [] for path, _ in PARAMETER_PATHS}

    for sample in manifest["samples"]:
        sample_dir = dataset_dir / sample["id"]
        source_path = sample_dir / "source.png"
        target_path = sample_dir / "target.png"
        ground_truth_path = sample_dir / "ground_truth.json"

        source_bytes = source_path.read_bytes()
        target_bytes = target_path.read_bytes()
        ground_truth = read_json(ground_truth_path)
        analysis = analyze_images(source_bytes, target_bytes, strength=1.0, lut_size=lut_size)
        prediction = analysis["recipe"]

        row: Dict[str, Any] = {"id": sample["id"]}
        parameter_rows: List[Dict[str, Any]] = []
        for path, direction_epsilon in PARAMETER_PATHS:
            actual = float(get_nested(ground_truth, path, 0.0))
            predicted = float(get_nested(prediction, path, 0.0))
            error = predicted - actual
            parameter_errors[path].append(abs(error))
            parameter_squared_errors[path].append(error * error)
            if abs(actual) >= direction_epsilon:
                direction_hits[path].append(int(math.copysign(1.0, actual) == math.copysign(1.0, predicted)))

            row[path + ".actual"] = round(actual, 4)
            row[path + ".predicted"] = round(predicted, 4)
            row[path + ".error"] = round(error, 4)
            parameter_rows.append(
                {
                    "path": path,
                    "role": "core" if path in CORE_PARAMETER_PATHS else "auxiliary",
                    "actual": round(actual, 4),
                    "predicted": round(predicted, 4),
                    "error": round(error, 4),
                }
            )

        source_rgb = load_image_bytes(source_bytes)
        target_rgb = load_image_bytes(target_bytes)
        predicted_rgb = decode_preview_data_url(analysis["previewDataUrl"])
        metrics = image_metrics(target_rgb, predicted_rgb)
        image_metric_rows.append(metrics)
        row.update({key: round(value, 6) for key, value in metrics.items()})
        rows.append(row)
        report_samples.append(
            {
                "id": sample["id"],
                "sourceDataUrl": thumbnail_data_url(source_rgb),
                "targetDataUrl": thumbnail_data_url(target_rgb),
                "predictedDataUrl": thumbnail_data_url(predicted_rgb),
                "metrics": {key: round(value, 6) for key, value in metrics.items()},
                "parameters": parameter_rows,
            }
        )

        if save_previews:
            save_preview_strip(preview_dir / ("%s.png" % sample["id"]), source_rgb, target_rgb, predicted_rgb)

    write_samples_csv(output_dir / "samples.csv", rows)
    summary = build_summary(manifest, parameter_errors, parameter_squared_errors, direction_hits, image_metric_rows)
    write_json(output_dir / "summary.json", summary)
    write_html_report(output_dir / "report.html", summary, report_samples)
    return summary


def build_summary(
    manifest: Dict[str, Any],
    parameter_errors: Dict[str, List[float]],
    parameter_squared_errors: Dict[str, List[float]],
    direction_hits: Dict[str, List[int]],
    image_metric_rows: List[Dict[str, float]],
) -> Dict[str, Any]:
    parameter_metrics = {}
    for path, _ in PARAMETER_PATHS:
        errors = parameter_errors[path]
        squared_errors = parameter_squared_errors[path]
        hits = direction_hits[path]
        parameter_metrics[path] = {
            "mae": mean(errors),
            "rmse": math.sqrt(mean(squared_errors)),
            "directionAccuracy": mean(hits) if hits else None,
            "directionCount": len(hits),
        }

    image_metrics_summary = {}
    for key in ["rgbMae", "labDeltaMean"]:
        values = [row[key] for row in image_metric_rows]
        image_metrics_summary[key] = {
            "mean": mean(values),
            "max": max(values) if values else 0.0,
        }

    return {
        "version": 1,
        "sampleCount": len(manifest["samples"]),
        "parameterMetrics": parameter_metrics,
        "imageMetrics": image_metrics_summary,
    }


def image_metrics(target_rgb: np.ndarray, predicted_rgb: np.ndarray) -> Dict[str, float]:
    target, predicted = align_images(target_rgb, predicted_rgb)
    rgb_mae = float(np.mean(np.abs(target - predicted)))
    target_lab = rgb_to_lab(target)
    predicted_lab = rgb_to_lab(predicted)
    lab_delta = np.sqrt(np.sum((target_lab - predicted_lab) ** 2, axis=-1))
    return {
        "rgbMae": rgb_mae,
        "labDeltaMean": float(np.mean(lab_delta)),
    }


def align_images(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    height = min(a.shape[0], b.shape[0])
    width = min(a.shape[1], b.shape[1])
    return a[:height, :width], b[:height, :width]


def decode_preview_data_url(data_url: str) -> np.ndarray:
    _, encoded = data_url.split(",", 1)
    image = Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGB")
    return np.asarray(image).astype(np.float32) / 255.0


def thumbnail_data_url(rgb: np.ndarray, max_width: int = 320) -> str:
    image = Image.fromarray(to_uint8(rgb), mode="RGB")
    image.thumbnail((max_width, max_width), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def save_preview_strip(path: Path, source: np.ndarray, target: np.ndarray, predicted: np.ndarray) -> None:
    source, target = align_images(source, target)
    target, predicted = align_images(target, predicted)
    source, predicted = align_images(source, predicted)
    strip = np.concatenate([source, target, predicted], axis=1)
    Image.fromarray(to_uint8(strip), mode="RGB").save(path, format="PNG", optimize=True)


def write_html_report(path: Path, summary: Dict[str, Any], samples: List[Dict[str, Any]]) -> None:
    css = """
body{font-family:Inter,Segoe UI,Arial,sans-serif;margin:0;background:#f5f6f2;color:#1f2423}
header{padding:24px 28px;background:#202624;color:#fff}
h1{margin:0 0 8px;font-size:30px} h2{font-size:20px;margin:0 0 12px} h3{font-size:16px;margin:0 0 10px}
main{padding:24px 28px}.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-bottom:24px}
.metric,.sample{background:#fff;border:1px solid #d8ddd5;border-radius:8px}.metric{padding:14px}.metric span{display:block;color:#66706a;font-size:13px;margin-bottom:4px}.metric strong{font-size:24px}
.sample{margin-bottom:18px;padding:16px}.images{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:14px}.image-block{background:#eef1ec;border-radius:8px;overflow:hidden}.image-block img{width:100%;aspect-ratio:4/3;object-fit:cover;display:block}.image-block span{display:block;padding:8px 10px;font-size:13px;color:#59625d}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #e3e7e0;padding:8px;text-align:right}th:first-child,td:first-child{text-align:left}.core td:first-child{font-weight:700}.auxiliary{color:#68716b}
@media(max-width:760px){.images{grid-template-columns:1fr}main{padding:16px}header{padding:18px}}
"""
    parts = [
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
        "<title>Color Recipe Evaluation Report</title><style>%s</style></head><body>" % css,
        "<header><h1>Color Recipe Evaluation Report</h1><div>%d samples</div></header>" % summary["sampleCount"],
        "<main>",
        "<section class=\"summary\">",
    ]
    for key, value in summary["imageMetrics"].items():
        parts.append(
            "<div class=\"metric\"><span>%s mean</span><strong>%.5f</strong></div>"
            % (html_lib.escape(key), value["mean"])
        )
    for key in ["basic.exposureEv", "color.temperature", "color.tint", "color.saturation"]:
        metric = summary["parameterMetrics"][key]
        direction = metric["directionAccuracy"]
        direction_text = "n/a" if direction is None else "%.0f%%" % (direction * 100.0)
        parts.append(
            "<div class=\"metric\"><span>%s MAE / dir</span><strong>%.2f / %s</strong></div>"
            % (html_lib.escape(key), metric["mae"], direction_text)
        )
    parts.append("</section>")

    for sample in samples:
        parts.extend(
            [
                "<section class=\"sample\">",
                "<h2>%s</h2>" % html_lib.escape(sample["id"]),
                "<div class=\"images\">",
                image_block("Source", sample["sourceDataUrl"]),
                image_block("Target", sample["targetDataUrl"]),
                image_block("Predicted", sample["predictedDataUrl"]),
                "</div>",
                "<h3>Metrics: RGB MAE %.5f, LAB ΔE %.5f</h3>"
                % (sample["metrics"]["rgbMae"], sample["metrics"]["labDeltaMean"]),
                "<table><thead><tr><th>Parameter</th><th>Actual</th><th>Predicted</th><th>Error</th><th>Role</th></tr></thead><tbody>",
            ]
        )
        for row in sample["parameters"]:
            parts.append(
                "<tr class=\"%s\"><td>%s</td><td>%.4g</td><td>%.4g</td><td>%.4g</td><td>%s</td></tr>"
                % (
                    row["role"],
                    html_lib.escape(row["path"]),
                    row["actual"],
                    row["predicted"],
                    row["error"],
                    row["role"],
                )
            )
        parts.append("</tbody></table></section>")

    parts.append("</main></body></html>")
    path.write_text("\n".join(parts), encoding="utf-8")


def image_block(label: str, data_url: str) -> str:
    return (
        "<div class=\"image-block\"><img alt=\"%s\" src=\"%s\"><span>%s</span></div>"
        % (html_lib.escape(label), data_url, html_lib.escape(label))
    )


def write_samples_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def get_nested(payload: Dict[str, Any], dotted_path: str, default: Any = None) -> Any:
    value: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return float(sum(values) / len(values))


if __name__ == "__main__":
    main()
