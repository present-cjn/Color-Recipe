# Color Recipe

Color Recipe 是一个“参考图驱动”的调色配方 MVP。上传原图 A 和参考图 B 后，后端会计算调色预览、可解释参数建议，以及可导入剪辑/调色软件的 `.cube` LUT。

## 功能

- 双图上传：原图和参考图。
- 调色预览：基于曝光、对比、LAB 色彩迁移和饱和度修正生成。
- 参数建议：曝光、对比、高光、阴影、白色、黑色、色温、色调、自然饱和度、饱和度、亮度曲线和 HSL 分色。
- 导出：PNG 预览图、JSON 配方、`.cube` LUT。

## 技术栈

- 后端：FastAPI、Pillow、NumPy。
- 前端：Vite、React、lucide-react。
- 算法：sRGB/ICC 归一化、LAB 均值/方差迁移、亮度分位曲线、HSL 分桶分析、3D LUT 采样。

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

打开 `http://localhost:5173`。如果后端不在 `http://localhost:8000`，启动前端时设置：

```bash
VITE_API_BASE=http://your-api-host:8000 npm run dev
```

## 测试

```bash
cd backend
PYTHONPATH=. python3 -m unittest discover -s tests
```

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

当前预览图、LUT 和合成数据集都使用同一套 recipe 应用逻辑。这样导出的参数和预览效果保持一致，评测报告也能直接反映参数反推质量。

## 当前边界

这是第一版可落地 MVP，目标是给出接近参考图整体风格的调色建议。它不会复刻参考图的构图、布光、局部修图、材质变化或 AI 重绘效果。
