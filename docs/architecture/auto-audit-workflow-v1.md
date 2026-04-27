# 合规智审 Copilot 六维自动审计工作流 v1

## 目标

- 围绕并发性能、异步解耦、内容安全、存储架构、大文件处理、防机器注册六个维度自动扫描项目风险。
- 输出可落地的评分、问题清单、影响说明、优化建议和验收标准。
- 为每次上线前的质量门禁、迭代复盘和后续架构优化提供稳定基线。

## 代码入口

- 扫描器：`backend/src/audit/scanner.py`
- 命令行入口：`backend/src/audit/cli.py`
- 数据模型：`backend/src/audit/models.py`
- Golden eval：`backend/src/evals/golden_runner.py`
- Golden 样本：`backend/evals/golden_contracts.json`
- 自动化测试：`backend/tests/test_project_audit.py`
- CI 门禁：`.github/workflows/ci.yml`
- 持久化草案：`docs/architecture/auto-audit-schema-v1.sql`

## 工作流程

1. 收集
   - 读取后端、前端、配置、文档中的关键源码信号。
   - 提取 FastAPI 路由、队列、worker、限流、上传和存储相关能力。
   - 生成项目快照，避免扫描过程依赖运行时状态。
2. 识别
   - 按六个维度匹配高风险模式，例如同步 OCR、缺少重试、浏览器本地保存合同全文。
3. 评分
   - 根据发现的问题严重级别扣分，生成每个维度的独立得分。
4. 汇总
   - 计算综合评分和发布建议：`block`、`warning` 或 `pass`。
5. 输出
   - 生成 JSON 和 Markdown 报告，便于机器读取和人工审阅。
6. 验收
   - 每个发现项都包含影响、建议、验收标准和建议负责人。
7. 评测
   - 使用 golden 合同样本集验证核心风险识别不回退。
   - 当前 eval 默认走确定性规则审查，不依赖外部模型，适合 CI 稳定执行。
8. 迭代
   - 修复后重新运行审计，对比评分和 finding 数量变化。

## 审计维度

### 并发性能

- 检查长耗时任务是否仍在同步请求链路执行。
- 关注 OCR、PDF 解析、报告导出和模型调用的阻塞风险。
- 评估队列化和快速返回 task_id 的覆盖程度。

### 异步解耦

- 检查 review / deepen / queue 是否拥有统一任务模型。
- 检查 worker 是否具备重试、退避、失败落库和死信能力。
- 关注前端轮询、SSE 与任务状态之间的一致性。

### 内容安全

- 检查接口是否向前端暴露原始异常、供应商错误或系统路径。
- 检查模型输出是否经过思考过程、参考来源和空内容清洗。
- 检查敏感提示是否使用稳定错误码和用户友好文案。

### 存储架构

- 检查合同原文、审查报告和聊天历史是否长期保存在浏览器本地。
- 评估是否具备后端持久化、账号隔离、加密摘要和清理策略。

### 大文件处理

- 检查 PDF 页数、图片像素、批量图片数量、文件大小的前后端双重限制。
- 检查超限文件是否能快速失败并给出明确提示。

### 防机器注册

- 检查注册、发送验证码、登录和审查入口的限流能力。
- 检查是否接入 CAPTCHA/Turnstile、设备指纹和风险分策略。

## 评分规则

- 基础分：100
- P0：扣 25 分
- P1：扣 15 分
- P2：扣 8 分
- P3：扣 3 分

维度权重：
- 并发性能：20
- 异步解耦：20
- 内容安全：20
- 存储架构：15
- 大文件处理：15
- 防机器注册：10

发布建议：
- 任一维度低于 60 分或综合评分低于 75 分：`block`
- 综合评分 75–84 分：`warning`
- 综合评分不低于 85 分：`pass`

## 当前重点优化方向

1. 将大文件 OCR、报告导出和深度审查统一纳入后台任务体系。
2. 为队列任务补齐 retry_count、last_error、dead_letter 和可观测日志。
3. 将合同历史从浏览器本地存储迁移到后端账号级安全存储。
4. 在上传链路补齐文件大小、页数、像素数和批量图片数量的双端校验。
5. 在注册链路接入 CAPTCHA/Turnstile，并结合设备指纹和风险分。
6. 对所有用户可见错误执行稳定文案映射，不直接暴露 `str(exc)`。

## 运行方式

本地生成报告：

```bash
cd backend
python -m src.audit.cli --repo-root .. --output-dir ..\docs\audits --base-name current-baseline
```

输出文件：
- `docs/audits/current-baseline.json`
- `docs/audits/current-baseline.md`

运行 golden eval：

```bash
cd backend
python -m src.evals.golden_runner --samples evals/golden_contracts.json
```

CI 会自动执行：
- 后端 pytest
- Golden eval
- 六维工程审计
- 前端 Vitest
- 前端生产构建

## 后续计划

- 接入 CI，在合并前自动生成审计报告。
- 将审计结果持久化到数据库，支持趋势对比。
- 为每个 finding 生成修复任务和验证记录。
- 在管理后台展示维度评分、风险趋势和待办清单。
