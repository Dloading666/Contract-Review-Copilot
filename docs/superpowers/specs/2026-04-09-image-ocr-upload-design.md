# 图片 OCR 上传设计

## 目标

支持用户上传合同照片或截图，后端使用本地 PaddleOCR 提取文字，并在开始合同分析前先把识别结果展示给用户确认。确认后的文本再进入现有合同审查、问答、避坑指南和报告导出链路。

## 用户流程

1. 用户在现有上传区上传 `.jpg`、`.jpeg`、`.png` 或 `.webp`。
2. 前端调用受鉴权保护的 `/api/ocr/extract`。
3. FastAPI 后端调用 PaddleOCR 识别图片文字。
4. 前端将 OCR 文本填入右侧文档区，并进入 `ocr_ready` 状态。
5. 用户可以直接修改识别结果。
6. 用户点击“确认并开始分析”后，才进入现有 `/api/review` 流程。

## 前端改动

- 真实上传入口使用 `frontend/src/components/DocPanel.tsx`，不再使用旧的 `ContractInput` 作为主路径。
- 上传区新增图片格式支持：`.jpg`、`.jpeg`、`.png`、`.webp`。
- 图片上传成功后调用 `onOcrReady(text, filename)`，而不是直接调用 `onFileUpload(...)`。
- `App.tsx` 新增 `ocr_ready` 状态，用于承接“已识别、待确认”的中间态。
- `DocPanel` 在 `ocr_ready` 状态下显示可编辑文本框和“确认并开始分析”按钮。
- `ChatPanel` 在 `ocr_ready` 状态下显示引导提示，不展示分析阶段的思考步骤。

## 后端改动

- 新增 `backend/src/ocr/paddle_service.py`，封装本地 PaddleOCR 调用。
- 新增 `backend/src/ocr/__init__.py`，统一导出 OCR 服务。
- `backend/src/main.py` 新增 `/api/ocr` 与 `/api/ocr/extract` 两个入口，兼容旧调用并提供新命名。
- OCR 接口只负责图片转文本，不负责风险分析。
- 接口返回：
  - `text`
  - `lines`
  - `average_confidence`
  - `engine`
  - `filename`

## 技术约束

- PaddleOCR 集成在现有 FastAPI 后端内，不拆分独立服务。
- 图片 OCR 与 LLM 模型选择解耦：
  - 图片识别固定由本地 PaddleOCR 处理。
  - 用户在上传区选择的模型只用于后续合同分析、问答和报告生成。
- 为避免拍照件误识别，OCR 完成后不自动启动分析。

## 验证

- 前端测试覆盖：
  - 图片上传命中 `/api/ocr/extract`
  - OCR 成功后进入 `ocr_ready`
  - 用户确认后才开始审查流
- 后端测试覆盖：
  - OCR 接口鉴权
  - OCR 接口返回结构
  - PaddleOCR 服务的图片类型校验与文本提取
