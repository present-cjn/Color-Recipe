# Color Recipe

Color Recipe 是一个调色分析工作台，支持“参考图分析”和“风格套用”两种模式。系统会计算调色预览、可解释参数建议、风格拆解，以及可导入 Lightroom/ACR 或剪辑/调色软件的预设文件。

## 功能

- 双模式工作流：
  - 参考图分析：上传原图和目标图，拆解目标图的调色逻辑。
  - 风格套用：先选择风格类型，再上传原图，用内置风格参考生成配方。
- 调色预览：基于曝光、对比、亮度曲线、RGB 通道曲线、LAB 色彩迁移、饱和度修正和 HSL 分色生成。
- 风格拆解：解释参考图在曝光、反差、白平衡、饱和度、曲线和 HSL 上的核心差异。
- 分步骤预览：按基础影调、曲线、整体色彩、HSL 分色逐步查看每一步对结果的贡献。
- 强度模式：提供自然、标准、强匹配三档，并返回推荐强度和推荐理由。
- 分析依据：展示亮度、RGB、饱和度、色相覆盖、色偏方向等指标，帮助理解系统判断。
- 风格案例库：内置日系清透、胶片暖调、商业人像、城市冷调、森系绿色、海边蓝调、夜景霓虹、低饱和高级灰等练习案例。
- 参数建议：曝光、对比、高光、阴影、白色、黑色、色温、色调、自然饱和度、饱和度、亮度曲线和 HSL 分色。
- 导出：PNG 预览图、JSON 配方、`.cube` LUT、Lightroom/ACR 近似 `.xmp` 预设。

## 技术栈

- 后端：FastAPI、Pillow、NumPy。
- 前端：Vite、React、lucide-react。
- 算法：sRGB/ICC 归一化、LAB 均值/方差迁移、亮度分位曲线、RGB 通道曲线、HSL 分桶分析、最终视觉强度混合、3D LUT 采样、Lightroom/ACR 参数近似映射。

## 运行

后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

打开 Vite 输出的本地地址，通常是 `http://localhost:5173`。如果 5173 被占用，Vite 会自动切换到 5174 等其他端口。

前端默认请求 `http://127.0.0.1:8000`。如果后端不在这个地址，启动前端时设置：

```bash
VITE_API_BASE=http://your-api-host:8000 npm run dev
```

本地排错：

- 后端健康检查：打开 `http://127.0.0.1:8000/api/health`，应返回 `{"status":"ok"}`。
- 如果点击“生成配方”出现 `Failed to fetch`，通常是后端未启动、`VITE_API_BASE` 地址不对，或前端端口不在后端 CORS 允许范围内。
- 当前后端允许 `localhost` / `127.0.0.1` 的 `5170` 到 `5179` 端口，覆盖 Vite 常见自动换端口场景。

## 测试

```bash
cd backend
PYTHONPATH=. python3 -m unittest discover -s tests
```

## 教学工作流

参考图分析：

1. 选择“参考图分析”。
2. 上传原图和目标图。
3. 点击“生成配方”，观察原图、目标图和结果图。
4. 查看风格拆解、步骤预览、分析依据和导出参数。

风格套用：

1. 选择“风格套用”。
2. 从风格类型中选择一个练习方向，先阅读学习目标和常见错误。
3. 上传自己的原图。
4. 点击“生成配方”，系统会使用内置风格参考图作为目标图进行分析。
5. 在“风格强度”中切换自然、标准、强匹配三档，理解强度变化。

通用学习顺序：

1. 先观察原图、目标图/风格参考和结果图。
2. 在“风格强度”中切换自然、标准、强匹配三档，理解强度变化。
3. 查看“步骤预览”，依次观察基础影调、曲线、整体色彩和 HSL 的贡献。
4. 查看“分析依据”，用亮度、饱和度、色相覆盖和色偏方向验证判断。
5. 下载 XMP、LUT 或 JSON，作为 Lightroom/ACR 或其他软件中的练习起点。

## 合成参数评测

第一阶段评测不依赖 Lightroom/XMP 数据集，而是用我们自己的参数体系生成 ground truth。流程是：从一批普通图片生成 `source.png`、`target.png`、`ground_truth.json`，再用当前算法根据 source/target 反推参数并统计误差。

生成合成数据集：

```bash
cd backend
PYTHONPATH=. python3 -m evaluation.make_synthetic_dataset \
  --input /path/to/images \
  --output /tmp/color-recipe-synthetic \
  --variants-per-image 3 \
  --seed 42
```

运行评测：

```bash
cd backend
PYTHONPATH=. python3 -m evaluation.evaluate_recipe \
  --dataset /tmp/color-recipe-synthetic \
  --output /tmp/color-recipe-report \
  --save-previews
```

评测输出：

- `summary.json`：整体 MAE、RMSE、方向准确率，以及 RGB/LAB 图像误差。
- `samples.csv`：逐样本 ground truth、预测值和误差。
- `report.html`：可视化报告，展示 source / target / predicted 三图、核心参数误差和图像误差。
- `previews/`：可选的 source/target/predicted 三图横向对比。

当前预览图、分步骤预览、LUT 和合成数据集都使用同一套 recipe 应用逻辑。这样导出的参数和预览效果保持一致，评测报告也能直接反映参数反推质量。

## 当前边界

这是第一版可落地的进阶调色分析工具，目标是给出接近参考图整体风格的调色建议，并解释每一步为什么这样调。它不会复刻参考图的构图、布光、局部修图、材质变化或 AI 重绘效果。

Lightroom/ACR `.xmp` 导出是基于当前内部参数体系的近似映射，用于教学、拆解和起点预设，不等同于 Adobe 内部算法的精确复刻。
