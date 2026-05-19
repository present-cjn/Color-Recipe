import { Download, ImagePlus, Loader2, SlidersHorizontal, Wand2 } from "lucide-react";
import { useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
const HSL_LABELS = {
  red: "红",
  orange: "橙",
  yellow: "黄",
  green: "绿",
  aqua: "青",
  blue: "蓝",
  purple: "紫",
  magenta: "洋红",
};

function App() {
  const [source, setSource] = useState(null);
  const [reference, setReference] = useState(null);
  const [sourceUrl, setSourceUrl] = useState("");
  const [referenceUrl, setReferenceUrl] = useState("");
  const [strength, setStrength] = useState(70);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const canAnalyze = source && reference && !loading;
  const recipe = result?.recipe;

  const basicRows = useMemo(() => {
    if (!recipe) return [];
    return [
      ["曝光", `${recipe.basic.exposureEv} EV`],
      ["对比", recipe.basic.contrast],
      ["高光", recipe.basic.highlights],
      ["阴影", recipe.basic.shadows],
      ["白色", recipe.basic.whites],
      ["黑色", recipe.basic.blacks],
      ["色温", recipe.color.temperature],
      ["色调", recipe.color.tint],
      ["自然饱和度", recipe.color.vibrance],
      ["饱和度", recipe.color.saturation],
    ];
  }, [recipe]);

  function handleFile(kind, file) {
    if (!file) return;
    const url = URL.createObjectURL(file);
    if (kind === "source") {
      if (sourceUrl) URL.revokeObjectURL(sourceUrl);
      setSource(file);
      setSourceUrl(url);
    } else {
      if (referenceUrl) URL.revokeObjectURL(referenceUrl);
      setReference(file);
      setReferenceUrl(url);
    }
    setResult(null);
    setError("");
  }

  async function analyze() {
    if (!source || !reference) return;
    setLoading(true);
    setError("");
    const formData = new FormData();
    formData.append("source", source);
    formData.append("reference", reference);
    formData.append("strength", String(strength / 100));
    formData.append("lut_size", "17");

    try {
      const response = await fetch(`${API_BASE}/api/analyze`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail ?? `HTTP ${response.status}`);
      }
      setResult(await response.json());
    } catch (err) {
      setError(err.message || "分析失败");
    } finally {
      setLoading(false);
    }
  }

  function downloadText(filename, text) {
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  function downloadPreview() {
    const link = document.createElement("a");
    link.href = result.previewDataUrl;
    link.download = "color-recipe-preview.png";
    link.click();
  }

  return (
    <main className="app-shell">
      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>Color Recipe</h1>
            <p>上传原图和参考图，生成调色预览、参数建议和 LUT。</p>
          </div>
          <button className="primary-action" disabled={!canAnalyze} onClick={analyze}>
            {loading ? <Loader2 className="spin" size={18} /> : <Wand2 size={18} />}
            生成配方
          </button>
        </header>

        <section className="image-grid" aria-label="图片工作区">
          <ImageDrop
            title="原图 A"
            imageUrl={sourceUrl}
            onFile={(file) => handleFile("source", file)}
          />
          <ImageDrop
            title="参考图 B"
            imageUrl={referenceUrl}
            onFile={(file) => handleFile("reference", file)}
          />
          <Preview imageUrl={result?.previewDataUrl} loading={loading} />
        </section>

        <section className="control-strip">
          <label htmlFor="strength">
            <SlidersHorizontal size={18} />
            风格强度
          </label>
          <input
            id="strength"
            type="range"
            min="0"
            max="100"
            value={strength}
            onChange={(event) => setStrength(Number(event.target.value))}
          />
          <output>{strength}%</output>
        </section>

        {error && <div className="error-panel">{error}</div>}
      </section>

      <aside className="recipe-panel">
        <div className="panel-heading">
          <h2>参数建议</h2>
          {result && (
            <div className="download-actions">
              <button title="下载预览图" onClick={downloadPreview}>
                <Download size={16} />
                PNG
              </button>
              <button title="下载 LUT" onClick={() => downloadText("color-recipe.cube", result.lutCube)}>
                <Download size={16} />
                LUT
              </button>
              <button title="下载 JSON" onClick={() => downloadText("color-recipe.json", result.recipeJson)}>
                <Download size={16} />
                JSON
              </button>
            </div>
          )}
        </div>

        {!recipe ? (
          <div className="empty-state">等待生成调色配方</div>
        ) : (
          <>
            <div className="parameter-grid">
              {basicRows.map(([label, value]) => (
                <div className="parameter" key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>

            <section className="curve-block">
              <h3>亮度曲线</h3>
              <div className="curve-list">
                {recipe.toneCurve.input.map((point, index) => (
                  <span key={`${point}-${index}`}>
                    {Math.round(point * 100)} → {Math.round(recipe.toneCurve.output[index] * 100)}
                  </span>
                ))}
              </div>
            </section>

            <section className="hsl-block">
              <h3>HSL 分色</h3>
              <div className="hsl-table">
                <span>颜色</span>
                <span>色相</span>
                <span>饱和</span>
                <span>明度</span>
                {Object.entries(recipe.hsl).map(([name, row]) => (
                  <HslRow key={name} name={name} row={row} />
                ))}
              </div>
            </section>
          </>
        )}
      </aside>
    </main>
  );
}

function ImageDrop({ title, imageUrl, onFile }) {
  return (
    <label className="image-slot">
      <input
        type="file"
        accept="image/*"
        onChange={(event) => onFile(event.target.files?.[0])}
      />
      {imageUrl ? (
        <img src={imageUrl} alt={title} />
      ) : (
        <div className="placeholder">
          <ImagePlus size={30} />
          <span>{title}</span>
        </div>
      )}
      <span className="slot-label">{title}</span>
    </label>
  );
}

function Preview({ imageUrl, loading }) {
  return (
    <div className="image-slot preview-slot">
      {loading ? (
        <div className="placeholder">
          <Loader2 className="spin" size={30} />
          <span>计算中</span>
        </div>
      ) : imageUrl ? (
        <img src={imageUrl} alt="调色预览" />
      ) : (
        <div className="placeholder">
          <Wand2 size={30} />
          <span>调色预览</span>
        </div>
      )}
      <span className="slot-label">结果 C</span>
    </div>
  );
}

function HslRow({ name, row }) {
  return (
    <>
      <strong>{HSL_LABELS[name] ?? name}</strong>
      <span>{row.hue}</span>
      <span>{row.saturation}</span>
      <span>{row.luminance}</span>
    </>
  );
}

export default App;
