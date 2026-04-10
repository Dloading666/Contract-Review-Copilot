# 统一云端 OCR 链路设计

## 目标

将当前项目中“本地 PaddleOCR + 云端模型校对”的双轨 OCR 方案，收敛为单一的云端 OCR 方案。

升级后的规则如下：

- `txt/docx`：继续直接提取文本，不走 OCR
- `jpg/jpeg/png/webp`：统一走 `PaddlePaddle/PaddleOCR-VL-1.5`
- `pdf`：无论是否可直接抽文本，都统一逐页转图片，再走 `PaddlePaddle/PaddleOCR-VL-1.5`

这样做的目标是让产品行为一致，避免“有时走本地 OCR、有时走视觉模型 OCR”的混用状态。

## 范围

本次改动覆盖：

- 后端 `/api/ocr/ingest` 的 OCR 实现
- 图片和 PDF 的识别链路
- Docker 运行时依赖
- 前端 OCR 处理中提示文案
- OCR 结果返回结构中的 `used_ocr_model`

本次不包含：

- `txt/docx` 的读取逻辑改造
- 合同分析模型的切换
- 上传区交互大改
- OCR 之后的“用户确认再分析”流程调整

## 核心决策

### 1. 统一单一 OCR 模型

项目中的图片 OCR 和 PDF OCR 统一使用配置项 `ocr_model`，当前值为：

- `PaddlePaddle/PaddleOCR-VL-1.5`

后端不再在主流程中调用本地 `PaddleOCR`。

### 2. PDF 全量走 OCR

所有 PDF 都先转成图片，再按页调用 OCR 模型。

不再保留“先直提 PDF 文本，再判断是否回退 OCR”的分支。

代价：

- 普通文字型 PDF 会变慢
- OCR 成本会上升

收益：

- 用户心智统一
- 后端逻辑更简单
- 识别来源更稳定、可观测

### 3. 文本文件继续直读

`txt/docx` 不做图片化，不送 OCR 模型。

原因：

- 本身已经是结构化文本输入
- 强行转图只会增加延迟和出错面

### 4. 先确认再分析流程保持不变

OCR 完成后仍然先回填右侧文档区，用户确认或手改后，再进入合同分析。

## 目标架构

### 上传分流

1. `txt`
   - 直接解码文本
2. `docx`
   - 直接提取段落与表格文本
3. `jpg/jpeg/png/webp`
   - 直接调用云端 OCR 模型
4. `pdf`
   - 先逐页转图片
   - 再逐页调用云端 OCR 模型

### 识别流程

图片页级处理统一为：

1. 读取文件内容
2. 规范化 MIME 类型
3. 转成 `data:image/...;base64,...`
4. 调用 `PaddlePaddle/PaddleOCR-VL-1.5`
5. 提取页级文本
6. 按用户上传顺序拼接为 `merged_text`

## 后端改动

### `backend/src/llm_client.py`

- 保留并使用现有 `extract_text_from_image()`
- 让它成为图片 OCR 的唯一主入口
- `ocr_model` 固定来自配置项
- 返回实际使用的 OCR 模型名称

### `backend/src/ocr/ingest_service.py`

- 移除对本地 `paddle_service.py` 的主流程依赖
- 图片文件直接调用 `extract_text_from_image()`
- PDF 统一走“转图片 -> OCR”
- 删除“PDF 直接抽文本优先”的逻辑
- 删除“本地 OCR 后再模型校对”的组合流程

### `backend/src/ocr/paddle_service.py`

- 不再参与生产主流程
- 本轮保留文件仅作历史参考或回滚备用
- `/api/ocr/ingest` 不再调用其中任何能力

### `backend/src/main.py`

- `/api/ocr/ingest` 接口保持不变
- 继续返回统一的 `ContractIngestResult`

## 前端改动

### 上传交互

- 继续调用 `/api/ocr/ingest`
- 前端不需要感知本地 OCR 是否存在
- `txt/docx` 仍然是“导入文本”
- 图片与 PDF 统一视为“OCR 导入”

### 提示文案

上传处理中提示统一为中性表达，例如：

- “正在识别合同图片并提取文字...”
- “正在逐页识别 PDF 内容...”

不再出现“本地 OCR”“模型校对”混合表达。

## 返回结构

保持现有返回结构：

```json
{
  "source_type": "pdf_ocr",
  "display_name": "lease.pdf",
  "used_ocr_model": "PaddlePaddle/PaddleOCR-VL-1.5",
  "merged_text": "完整合同文本",
  "pages": [
    {
      "page_index": 1,
      "filename": "lease-page-1.png",
      "text": "第一页文本",
      "average_confidence": null,
      "warnings": []
    }
  ],
  "warnings": []
}
```

约定：

- `used_ocr_model`：固定返回当前云端 OCR 模型
- `pages[]`：保留页级文本，便于排错和后续扩展
- `average_confidence`：如果模型不直接提供可靠分数，可以先返回 `null`

## 失败处理

### 单页失败

- 不直接整单报废
- 保留成功页
- 在 `warnings[]` 中标出失败页

### 全部失败

- 返回明确错误
- 提示重新上传或检查图片/PDF 清晰度

### 模型调用失败

- 直接透传清晰的错误信息
- 不再回退本地 PaddleOCR

## Docker 与依赖

### 依赖调整

后端镜像移除以下本地 OCR 依赖：

- `paddlepaddle`
- `paddleocr`
- 本地 OCR 所需的额外系统依赖

### 保留依赖

- `pypdfium2`：继续用于 PDF 转图片
- OpenAI 兼容客户端：继续用于调用 SiliconFlow 接口

## 测试策略

### 后端

- 图片 OCR 走 `extract_text_from_image()`
- PDF 始终走“转图 -> OCR”
- `txt/docx` 保持直读
- `used_ocr_model` 返回 `PaddlePaddle/PaddleOCR-VL-1.5`
- 模型异常时返回清晰错误，不回退本地 OCR

### 前端

- 上传图片仍调用 `/api/ocr/ingest`
- 上传 PDF 时等待 OCR 结果并进入 `ocr_ready`
- OCR 结果仍能回填右侧文档区

## 风险与权衡

1. 普通文字型 PDF 会比当前实现更慢，因为不再直提文本。
2. OCR 成本会上升，因为所有 PDF 都要走视觉模型。
3. 彻底去掉本地 OCR 后，云端模型不可用时没有本地兜底。
4. 由于模型可能不返回稳定置信度，页级 `average_confidence` 可能需要先降级为 `null`。

## 实施顺序

1. 将 `ingest_service.py` 收敛为单一云端 OCR 链路
2. 让 PDF 始终走“转图片 -> OCR”
3. 移除生产主流程对 `paddle_service.py` 的依赖
4. 更新前端上传提示文案
5. 调整测试断言
6. 调整 Docker 依赖并重新部署
