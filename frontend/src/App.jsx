import {
  BarChart3,
  BookOpen,
  Download,
  Eye,
  ImagePlus,
  Layers,
  Loader2,
  SlidersHorizontal,
  Wand2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";
const DEFAULT_PRESETS = [
  { id: "natural", label: "自然", strength: 0.4 },
  { id: "standard", label: "标准", strength: 0.55 },
  { id: "strong", label: "强匹配", strength: 0.78 },
];
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
  const [mode, setMode] = useState("reference");
  const [source, setSource] = useState(null);
  const [reference, setReference] = useState(null);
  const [sourceUrl, setSourceUrl] = useState("");
  const [referenceUrl, setReferenceUrl] = useState("");
  const [selectedStyleId, setSelectedStyleId] = useState("");
  const [strength, setStrength] = useState(55);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activePreview, setActivePreview] = useState("final");
  const [compare, setCompare] = useState(55);
  const [examples, setExamples] = useState([]);

  const selectedStyle = examples.find((item) => item.id === selectedStyleId);
  const referenceReady = mode === "reference" ? Boolean(reference) : Boolean(selectedStyle);
  const canAnalyze = source && referenceReady && !loading;
  const recipe = result?.recipe;
  const deconstruction = result?.deconstruction;
  const presets = result?.strengthRecommendation?.presets ?? DEFAULT_PRESETS;
  const stepPreview = result?.stepPreviews?.find((item) => item.id === activePreview);
  const previewUrl = activePreview === "final" ? result?.previewDataUrl : stepPreview?.previewDataUrl;

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

  useEffect(() => {
    fetch(`${API_BASE}/api/examples`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`))))
      .then((payload) => {
        const cases = payload.cases ?? [];
        setExamples(cases);
        if (cases[0]) setSelectedStyleId(cases[0].id);
      })
      .catch(() => setExamples([]));
  }, []);

  function switchMode(nextMode) {
    setMode(nextMode);
    setResult(null);
    setActivePreview("final");
    setError("");
    if (nextMode === "style") {
      clearReference();
    }
  }

  function clearReference() {
    if (referenceUrl) URL.revokeObjectURL(referenceUrl);
    setReference(null);
    setReferenceUrl("");
  }

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
    setActivePreview("final");
    setError("");
  }

  function selectStyle(styleId) {
    setSelectedStyleId(styleId);
    setResult(null);
    setActivePreview("final");
    setError("");
  }

  function applyPreset(preset) {
    setStrength(Math.round(Number(preset.strength) * 100));
  }

  async function analyze() {
    if (!source || !referenceReady) return;
    setLoading(true);
    setError("");
    const formData = new FormData();
    formData.append("source", source);
    if (mode === "style") {
      formData.append("reference", await dataUrlToFile(selectedStyle.referenceDataUrl, `${selectedStyle.id}-reference.png`));
    } else {
      formData.append("reference", reference);
    }
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
      const payload = await response.json();
      setResult(payload);
      setActivePreview("final");
    } catch (err) {
      const message = err.message || "分析失败";
      if (message === "Failed to fetch") {
        setError(`无法连接后端服务。请确认 ${API_BASE}/api/health 可以访问，并检查前端端口是否被后端 CORS 允许。`);
      } else {
        setError(message);
      }
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
            <p>{mode === "reference" ? "用一张目标图拆解调色思路。" : "选择一种风格，把它应用到你的照片。"}</p>
          </div>
          <button className="primary-action" disabled={!canAnalyze} onClick={analyze}>
            {loading ? <Loader2 className="spin" size={18} /> : <Wand2 size={18} />}
            生成配方
          </button>
        </header>

        <ModeSwitcher mode={mode} onChange={switchMode} />

        {mode === "style" && (
          <StylePicker examples={examples} selectedStyleId={selectedStyleId} onSelect={selectStyle} />
        )}

        {mode === "style" && selectedStyle && (
          <CaseLesson example={selectedStyle} />
        )}

        <section className={mode === "reference" ? "image-grid reference-grid" : "image-grid style-grid"} aria-label="图片工作区">
          <ImageDrop
            title="原图"
            hint="选择要调色的照片"
            imageUrl={sourceUrl}
            onFile={(file) => handleFile("source", file)}
          />
          {mode === "reference" ? (
            <ImageDrop
              title="目标图"
              hint="上传想学习的参考风格"
              imageUrl={referenceUrl}
              onFile={(file) => handleFile("reference", file)}
            />
          ) : (
            <StyleReference style={selectedStyle} />
          )}
          <Preview
            sourceUrl={sourceUrl}
            imageUrl={previewUrl}
            loading={loading}
            compare={compare}
            onCompare={setCompare}
          />
        </section>

        <StrengthControl
          presets={presets}
          strength={strength}
          onPreset={applyPreset}
          onStrength={setStrength}
        />

        {result?.strengthRecommendation && (
          <section className="recommendation">
            <strong>推荐强度：{Math.round(result.strengthRecommendation.recommendedStrength * 100)}% · {result.strengthRecommendation.label}</strong>
            <p>{result.strengthRecommendation.reason}</p>
          </section>
        )}

        {result && (
          <StepPreviewStrip
            steps={result.stepPreviews ?? []}
            activePreview={activePreview}
            onChange={setActivePreview}
          />
        )}

        {error && <div className="error-panel">{error}</div>}
      </section>

      <ResultPanel
        result={result}
        recipe={recipe}
        deconstruction={deconstruction}
        basicRows={basicRows}
        downloadPreview={downloadPreview}
        downloadText={downloadText}
      />
    </main>
  );
}

function ModeSwitcher({ mode, onChange }) {
  return (
    <section className="mode-switcher" aria-label="调色模式">
      <button className={mode === "reference" ? "active" : ""} onClick={() => onChange("reference")}>
        <BookOpen size={18} />
        <span>参考图分析</span>
      </button>
      <button className={mode === "style" ? "active" : ""} onClick={() => onChange("style")}>
        <Layers size={18} />
        <span>风格套用</span>
      </button>
    </section>
  );
}

function StylePicker({ examples, selectedStyleId, onSelect }) {
  if (!examples.length) return null;
  return (
    <section className="style-picker" aria-label="风格类型">
      <div className="section-kicker">
        <BookOpen size={18} />
        <span>选择风格类型</span>
      </div>
      <div className="style-list">
        {examples.map((example) => (
          <button
            className={selectedStyleId === example.id ? "active" : ""}
            key={example.id}
            onClick={() => onSelect(example.id)}
          >
            <img src={example.referenceDataUrl} alt={example.title} />
            <span>{example.title}</span>
            <small>{example.category} · {example.difficulty}</small>
          </button>
        ))}
      </div>
    </section>
  );
}

function StrengthControl({ presets, strength, onPreset, onStrength }) {
  return (
    <section className="control-strip">
      <label htmlFor="strength">
        <SlidersHorizontal size={18} />
        风格强度
      </label>
      <div className="strength-controls">
        <div className="preset-buttons">
          {presets.map((preset) => (
            <button
              key={preset.id}
              className={Math.abs(strength - Math.round(Number(preset.strength) * 100)) <= 2 ? "active" : ""}
              onClick={() => onPreset(preset)}
            >
              {preset.label}
            </button>
          ))}
        </div>
        <input
          id="strength"
          type="range"
          min="0"
          max="100"
          value={strength}
          onChange={(event) => onStrength(Number(event.target.value))}
        />
      </div>
      <output>{strength}%</output>
    </section>
  );
}

function StepPreviewStrip({ steps, activePreview, onChange }) {
  return (
    <section className="step-strip" aria-label="分步骤预览">
      <div className="section-kicker">
        <Layers size={18} />
        <span>步骤预览</span>
      </div>
      <div className="step-buttons">
        {steps.map((step) => (
          <button
            key={step.id}
            className={activePreview === step.id ? "active" : ""}
            onClick={() => onChange(step.id)}
          >
            {step.label}
          </button>
        ))}
        <button className={activePreview === "final" ? "active" : ""} onClick={() => onChange("final")}>
          完整配方
        </button>
      </div>
    </section>
  );
}

function ImageDrop({ title, hint, imageUrl, onFile }) {
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
          <small>{hint}</small>
        </div>
      )}
      <span className="slot-label">{title}</span>
    </label>
  );
}

function StyleReference({ style }) {
  return (
    <div className="image-slot style-reference">
      {style ? (
        <>
          <img src={style.referenceDataUrl} alt={style.title} />
          <div className="style-caption">
            <strong>{style.title}</strong>
            <span>{style.category} · {style.difficulty}</span>
          </div>
        </>
      ) : (
        <div className="placeholder">
          <BookOpen size={30} />
          <span>风格来源</span>
        </div>
      )}
      <span className="slot-label">风格</span>
    </div>
  );
}

function Preview({ sourceUrl, imageUrl, loading, compare, onCompare }) {
  return (
    <div className="image-slot preview-slot">
      {loading ? (
        <div className="placeholder">
          <Loader2 className="spin" size={30} />
          <span>计算中</span>
        </div>
      ) : imageUrl ? (
        <div className="compare-view">
          {sourceUrl && <img className="compare-source" src={sourceUrl} alt="原图对比" />}
          <img
            className="compare-result"
            src={imageUrl}
            alt="调色预览"
            style={{ clipPath: `inset(0 ${100 - compare}% 0 0)` }}
          />
          <div className="compare-line" style={{ left: `${compare}%` }} />
          <input
            aria-label="原图和结果对比"
            className="compare-slider"
            type="range"
            min="0"
            max="100"
            value={compare}
            onChange={(event) => onCompare(Number(event.target.value))}
          />
        </div>
      ) : (
        <div className="placeholder">
          <Wand2 size={30} />
          <span>调色预览</span>
        </div>
      )}
      <span className="slot-label">结果</span>
    </div>
  );
}

function ResultPanel({ result, recipe, deconstruction, basicRows, downloadPreview, downloadText }) {
  return (
    <aside className="recipe-panel">
      <div className="panel-heading">
        <h2>{result ? "分析结果" : "等待分析"}</h2>
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
            <button title="下载 Lightroom/ACR 预设" onClick={() => downloadText("color-recipe.xmp", result.xmpPreset)}>
              <Download size={16} />
              XMP
            </button>
          </div>
        )}
      </div>

      {!recipe ? (
        <div className="empty-state">
          <Wand2 size={24} />
          <span>选择模式并生成配方后，这里会显示拆解、指标和导出。</span>
        </div>
      ) : (
        <>
          <section className="deconstruction">
            <div className="section-title">
              <BookOpen size={18} />
              <h3>风格拆解</h3>
            </div>
            <p className="summary-text">{deconstruction?.summary}</p>
            <div className="difference-list">
              {deconstruction?.keyDifferences?.map((item) => (
                <div className="difference" key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                  <p>{item.explanation}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="steps-panel">
            <div className="section-title">
              <Layers size={18} />
              <h3>调色步骤</h3>
            </div>
            {deconstruction?.steps?.map((step) => (
              <article className="step-card" key={step.id}>
                <h4>{step.title}</h4>
                <p>{step.summary}</p>
                <div className="step-params">
                  {step.parameters.map((parameter) => (
                    <div key={`${step.id}-${parameter.label}`}>
                      <span>{parameter.label}</span>
                      <strong>{parameter.value}</strong>
                      <p>{parameter.reason}</p>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </section>

          {result?.moduleContributions && (
            <section className="contribution-panel">
              <div className="section-title">
                <Layers size={18} />
                <h3>模块贡献</h3>
              </div>
              <div className="contribution-list">
                {result.moduleContributions.map((item) => (
                  <div className="contribution" key={item.id}>
                    <span>{item.label}</span>
                    <strong>{item.role} · {item.impact}</strong>
                    <p>{item.message}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {result?.metrics && <MetricsPanel metrics={result.metrics} />}

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

          <section className="diagnostics">
            <div className="section-title">
              <Eye size={18} />
              <h3>检查重点</h3>
            </div>
            {deconstruction?.diagnostics?.map((item) => (
              <div className="diagnostic" key={item.label}>
                <strong>{item.label}</strong>
                <p>{item.message}</p>
              </div>
            ))}
            <p className="lightroom-note">{deconstruction?.lightroomNote}</p>
          </section>
        </>
      )}
    </aside>
  );
}

function CaseLesson({ example }) {
  if (!example) return null;
  return (
    <div className="case-lesson">
      <strong>{example.learningGoal}</strong>
      <p>{example.styleNotes}</p>
      <div>
        {example.commonMistakes?.map((item) => (
          <span key={item}>{item}</span>
        ))}
      </div>
    </div>
  );
}

function MetricsPanel({ metrics }) {
  const hueRows = Object.entries(metrics.hueDistribution?.reference ?? {});
  return (
    <section className="metrics-panel">
      <div className="section-title">
        <BarChart3 size={18} />
        <h3>分析依据</h3>
      </div>
      <MetricChart title="亮度分布" series={metrics.histograms?.luminance} />
      <MetricChart title="饱和度分布" series={metrics.histograms?.saturation} />
      <div className="hue-bars">
        <h4>参考图色相覆盖</h4>
        {hueRows.map(([name, value]) => (
          <div className="hue-bar" key={name}>
            <span>{HSL_LABELS[name] ?? name}</span>
            <div><i style={{ width: `${Math.min(Number(value) * 360, 100)}%` }} /></div>
            <strong>{Math.round(Number(value) * 100)}%</strong>
          </div>
        ))}
      </div>
      <div className="cast-card">
        <span>色偏方向</span>
        <strong>参考图：{metrics.colorCast?.reference?.direction}</strong>
        <p>结果图：{metrics.colorCast?.result?.direction}</p>
      </div>
    </section>
  );
}

function MetricChart({ title, series }) {
  if (!series) return null;
  return (
    <div className="metric-chart">
      <h4>{title}</h4>
      <div className="chart-grid">
        {["source", "reference", "result"].map((key) => (
          <div className={`chart-row ${key}`} key={key}>
            <span>{key === "source" ? "原图" : key === "reference" ? "参考" : "结果"}</span>
            <div className="bars">
              {series[key]?.map((value, index) => (
                <i key={`${key}-${index}`} style={{ height: `${Math.max(Number(value) * 120, 2)}px` }} />
              ))}
            </div>
          </div>
        ))}
      </div>
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

async function dataUrlToFile(dataUrl, filename) {
  const response = await fetch(dataUrl);
  const blob = await response.blob();
  return new File([blob], filename, { type: blob.type || "image/png" });
}

export default App;
