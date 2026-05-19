# Color Recipe 项目进度报告

报告日期：2026-05-19  
报告范围：基于当前本地工作区文件状态整理，包含已实现但尚未提交到 Git 的 `backend/`、`frontend/`、`.gitignore` 与 README 更新。

## 一、项目概述

Color Recipe 是一个“参考图驱动”的调色配方 MVP。用户上传原图 A 与参考图 B 后，系统会分析两张图片的整体亮度、色彩、饱和度与 HSL 分布，生成调色预览图、可解释参数建议，以及可导入剪辑/调色软件的 `.cube` LUT。

当前版本的目标不是复刻参考图的构图、局部光影或 AI 重绘效果，而是输出接近参考图整体视觉风格的调色建议，并提供可验证、可导出的调色结果。

## 二、截止目前已完成内容

### 1. 后端 API 服务

已完成 FastAPI 后端基础服务，核心文件位于 `backend/app/`。

已实现内容：

- `GET /api/health` 健康检查接口，返回服务可用状态。
- `POST /api/analyze` 图片分析接口，接收 `source`、`reference`、`strength`、`lut_size`。
- 接口侧完成图片类型校验、空文件校验与异常包装。
- 配置 CORS，允许本地 Vite 前端 `localhost:5173` 与 `127.0.0.1:5173` 访问。
- 分析接口返回：
  - `previewDataUrl`：PNG 调色预览图的 base64 data URL。
  - `recipe`：结构化调色配方对象。
  - `lutCube`：`.cube` 3D LUT 文本。
  - `recipeJson`：可下载的 JSON 配方文本。

### 2. 图像分析与调色算法

已完成第一版调色配方生成逻辑，核心文件为 `backend/app/color_recipe.py`。

已实现能力：

- 图片读取与预处理：
  - EXIF 方向修正。
  - ICC 色彩配置转换到 sRGB。
  - RGB 归一化。
  - 长边缩放，控制分析计算量。
- 色彩空间转换：
  - sRGB 与 Linear RGB 转换。
  - RGB 与 XYZ 转换。
  - XYZ 与 LAB 转换。
  - RGB 与 HSL 转换。
- 图像特征提取：
  - RGB 均值、标准差。
  - LAB 均值、标准差。
  - 亮度均值、标准差。
  - 亮度分位数：p01、p05、p25、p50、p75、p95、p99。
  - RGB 通道曲线分位点。
  - 平均 chroma、平均 saturation。
  - HSL 八个颜色桶：红、橙、黄、绿、青、蓝、紫、洋红。
- 调色模型：
  - 基于曝光差计算整体曝光修正。
  - 基于亮度标准差计算对比修正。
  - 基于 LAB 均值和方差迁移进行整体色彩迁移。
  - 基于饱和度比例进行饱和度修正。
- 公开配方应用逻辑：
  - 支持曝光、对比、高光、阴影、白色、黑色。
  - 支持色温、色调、自然饱和度、饱和度。
  - 当前预览图、LUT 生成和合成评测共用同一套 `apply_recipe`，保证输出链路一致。
- 调色配方生成：
  - `basic`：曝光、对比、高光、阴影、白色、黑色。
  - `color`：色温、色调、自然饱和度、饱和度。
  - `toneCurve`：亮度曲线与 RGB 通道曲线。
  - `hsl`：八个色相桶的色相、饱和度、明度建议。
  - `analysis`：原图与参考图的关键统计摘要。
- LUT 导出：
  - 支持生成 `.cube` 格式 3D LUT。
  - LUT 尺寸限制在 2 到 33，默认接口侧使用 17。

### 3. 前端 MVP 界面

已完成 React + Vite 前端，核心文件位于 `frontend/src/`。

已实现内容：

- 三栏图像工作区：
  - 原图 A 上传。
  - 参考图 B 上传。
  - 结果 C 预览。
- 风格强度滑杆：
  - 范围 0% 到 100%。
  - 请求接口时转换为 0 到 1 的 `strength`。
- 生成配方交互：
  - 调用后端 `/api/analyze`。
  - 加载中状态展示。
  - 错误信息展示。
- 参数建议面板：
  - 展示曝光、对比、高光、阴影、白色、黑色、色温、色调、自然饱和度、饱和度。
  - 展示亮度曲线点位。
  - 展示 HSL 分色表。
- 导出能力：
  - 下载 PNG 预览图。
  - 下载 `.cube` LUT。
  - 下载 JSON 配方。
- 响应式样式：
  - 桌面端为主工作区 + 右侧参数面板。
  - 窄屏下自动切换为单列布局。

### 4. 合成数据集与评测体系

已完成第一阶段不依赖 Lightroom/XMP 数据集的评测链路，核心文件位于 `backend/evaluation/`。

已实现内容：

- 合成数据集生成脚本：`make_synthetic_dataset.py`
  - 从输入图片目录批量生成样本。
  - 每张图片可生成多个参数变体。
  - 输出 `source.png`、`target.png`、`ground_truth.json`。
  - 支持随机种子，保证数据集可复现。
  - 输出 `manifest.json`。
- 评测脚本：`evaluate_recipe.py`
  - 对合成数据集逐样本运行当前算法。
  - 比较 ground truth 与预测配方。
  - 统计 MAE、RMSE、方向准确率。
  - 统计 RGB MAE 与 LAB 平均色差。
  - 输出 `summary.json`、`samples.csv`、`report.html`。
  - 可选输出 `previews/`，生成 source/target/predicted 三图对比。
- 公共 recipe 应用入口：`recipe_apply.py`
  - 将评测侧与主算法侧的 recipe 应用逻辑统一。

### 5. 测试覆盖

已完成后端与评测链路的 unittest 测试，位于 `backend/tests/`。

当前测试覆盖：

- strength 为 0 时，调色迁移应保持原图不变。
- 图片分析接口底层函数应返回预览图、recipe 和 LUT。
- `.cube` LUT 应使用统一的 recipe renderer。
- 空 recipe 应保持图像不变。
- 曝光和饱和度参数应推动图像向预期方向变化。
- 合成数据集生成应支持随机种子复现。
- 评测脚本应正确写出 summary、samples、HTML report 和 preview 文件。

已执行验证：

```bash
cd backend
PYTHONPATH=. python3 -m unittest discover -s tests
```

结果：7 个测试全部通过。

已执行前端构建验证：

```bash
cd frontend
npm run build
```

结果：Vite 生产构建成功，输出到 `frontend/dist/`。

## 三、当前技术栈

后端：

- FastAPI
- Uvicorn
- Pillow
- NumPy
- python-multipart

前端：

- Vite
- React
- lucide-react

工程与验证：

- Python unittest
- npm build
- 合成数据集评测脚本

## 四、项目文件结构概览

```text
Color-Recipe/
├── README.md
├── PROJECT_PROGRESS_REPORT.md
├── .gitignore
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py
│   │   └── color_recipe.py
│   ├── evaluation/
│   │   ├── recipe_apply.py
│   │   ├── make_synthetic_dataset.py
│   │   └── evaluate_recipe.py
│   └── tests/
│       ├── test_color_recipe.py
│       └── test_evaluation.py
└── frontend/
    ├── package.json
    ├── package-lock.json
    ├── index.html
    ├── vite.config.js
    └── src/
        ├── main.jsx
        ├── App.jsx
        └── styles.css
```

## 五、当前项目状态判断

当前项目已经达到可运行 MVP 状态：

- 后端接口可接收两张图片并输出完整分析结果。
- 前端可完成上传、分析、预览、参数查看和导出。
- LUT、JSON、PNG 三类核心产物已实现。
- 算法链路具备基础可解释性。
- 已建立不依赖外部专业调色数据集的第一阶段自动评测体系。
- 后端测试和前端构建均已通过。

同时，当前 Git 状态显示主要实现仍处于未提交状态。后续若进入协作或发布阶段，应先整理提交边界，并确认是否需要将本报告纳入版本控制。

## 六、当前边界与不足

当前版本仍属于整体风格迁移 MVP，存在以下边界：

- 调色算法主要依赖全局统计特征，暂不支持局部区域级调整。
- 不识别人像、天空、肤色、商品等语义对象。
- 不复刻参考图的构图、布光、景深、材质变化或局部修图。
- HSL 参数目前用于建议展示，核心预览与 LUT 尚未完整应用所有 HSL 分色调整。
- 色温、色调、自然饱和度等参数是内部 LAB/HSL 统计到通用调色术语的近似映射，还不是某个具体软件的精确参数模型。
- 评测数据集为合成数据，适合验证参数反推链路，但不能完全代表真实摄影调色场景。
- 前端目前是本地 MVP 界面，尚未加入鉴权、历史记录、批处理、任务队列或云端存储。

## 七、建议下一阶段工作

建议按以下顺序推进：

1. 固化当前 MVP
   - 将当前 README、后端、前端、评测与测试文件整理为一次明确提交。
   - 增加 API 响应 schema 或 Pydantic 模型，提升接口契约稳定性。
   - 增加更多异常路径测试，例如坏图、非图片、极小图片、透明图和超大图。

2. 提升调色一致性
   - 将 HSL 分色参数真正应用到 `apply_recipe` 和 LUT 中。
   - 将 tone curve 应用逻辑补齐，使曲线建议与预览结果更一致。
   - 为肤色、天空、绿色植被等常见摄影场景增加专项样本验证。

3. 扩展评测体系
   - 引入真实图片样本集，补充人工主观评分或参考软件输出对照。
   - 持续跟踪 RGB MAE、LAB 色差、核心参数方向准确率。
   - 将评测命令接入 CI，避免算法改动造成回归。

4. 改善产品体验
   - 支持拖拽上传与重新选择图片。
   - 增加原图/预览对比滑杆。
   - 增加导出文件名自定义。
   - 增加参数复制、预设保存和历史记录。

5. 面向真实使用场景增强
   - 支持批量图片套用同一 recipe。
   - 支持更高尺寸预览或原尺寸导出。
   - 支持常见调色软件参数模板映射。
   - 明确 `.cube` LUT 在不同软件中的兼容性测试清单。

## 八、结论

Color Recipe 当前已完成从“上传两张图”到“生成预览、参数建议、JSON 配方和 LUT”的主流程闭环，并补齐了第一阶段自动化评测与测试验证。项目已经具备本地演示、算法迭代和后续产品化扩展的基础。

下一阶段重点应放在调色结果一致性、真实样本评测、HSL/tone curve 应用闭环，以及更贴近摄影/视频工作流的导出与批处理能力上。
