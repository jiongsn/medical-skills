---
name: medical-guideline-ocr-mermaid
description: 当任务是把医学指南 PDF 转成最终 Markdown，并需要先调用 PaddleOCR-VL 做 OCR/版面解析，再用 VLM 把指南中的图片、图表、算法图或流程图转换为 Mermaid，最后回填输出一个保留正文和表格的 Markdown 文件时使用。也适用于已有 PaddleOCR Markdown 但仍需抽取图片并转 Mermaid 的情况。
---

# 医学指南 PDF 到 Mermaid Markdown

## 概览

默认从 PDF 开始处理：先调用 PaddleOCR-VL 解析 PDF，得到 OCR Markdown 和图片；再由 agent 使用可用的 VLM/图片理解能力逐张解析图片；最后把 Mermaid 回填到原图片位置，输出一个最终 Markdown 文件。

核心约定是“保留 OCR 正文和表格”：PaddleOCR 生成的 Markdown 是正文来源，VLM 只负责图片中的可见结构和文字，不改写正文、表格、标题、图注和周围段落。

## 主流程：PDF 到最终 Markdown

### 1. 从 PDF 运行 PaddleOCR 并准备工作区

用户给 PDF 时，必须优先使用 `from-pdf`，不要让用户先手工跑 OCR。

```bash
python3 <skill-dir>/scripts/guideline_ocr_mermaid.py from-pdf \
  --input guideline.pdf \
  --work-dir guideline_ocr_mermaid_work \
  --api-url "$PADDLEOCR_API_URL" \
  --token "$PADDLEOCR_TOKEN" \
  --output guideline.with-mermaid.md
```

这一步会完成：

- 调用 PaddleOCR-VL 版面解析 API。
- 保存 `paddleocr/combined.md` 作为 OCR 正文和表格来源。
- 保存 PaddleOCR 返回的图片。
- 抽取 Markdown 中的图片块。
- 生成 `figures/image_manifest.json`、`figures/prompts/`、`figures/mermaid_map.json` 和 `workflow_state.json`。

第 1 步完成标准：`from-pdf` 返回 `PASS`，并提示发现的图片块数量。

### 2. 用 VLM 转换图片

逐一查看 `figures/image_manifest.json` 中的图片。每张图片使用 `figures/prompts/image_XXX.md` 作为 VLM 提示词。

把 VLM 输出写入 `figures/mermaid_map.json`，键名保持图片 id，例如：

```json
{
  "image_001": "flowchart LR\n    A[\"Start\"] --> B[\"Action\"]"
}
```

JSON 值里不要写 Markdown 代码围栏；回填脚本会自动加上 Mermaid 代码块。

第 2 步完成标准：`image_manifest.json` 里的每个图片 id 都有对应 Mermaid 源码。如果图片确实无法可靠识别，最终报告中列出图片 id；不要猜测补全。

### 3. 回填并输出最终 Markdown

VLM 映射完成后运行：

```bash
python3 <skill-dir>/scripts/guideline_ocr_mermaid.py finalize \
  --work-dir guideline_ocr_mermaid_work
```

`finalize` 会读取 `workflow_state.json`，把 Mermaid 回填到 OCR Markdown 的原图片位置，并输出最终 Markdown。

第 3 步完成标准：脚本返回 `PASS`，最终 Markdown 中图片引用为 0，Mermaid 数量等于原图片数量。

## 已有 PaddleOCR Markdown 的快捷流程

如果用户已经提供 PaddleOCR Markdown，不需要再调用 API，可以从抽取图片开始：

```bash
python3 <skill-dir>/scripts/guideline_ocr_mermaid.py extract \
  --markdown paddleocr_output/combined.md \
  --out-dir guideline_figures
```

然后用 VLM 填写 `guideline_figures/mermaid_map.json`，再运行：

```bash
python3 <skill-dir>/scripts/guideline_ocr_mermaid.py apply \
  --markdown paddleocr_output/combined.md \
  --manifest guideline_figures/image_manifest.json \
  --mermaid-map guideline_figures/mermaid_map.json \
  --output guideline.with-mermaid.md
```

## PaddleOCR API 获取与填写

需要直接调用 API 时，先阅读 [PaddleOCR-VL API 说明](references/paddleocr-vl-api.md)。固定入口是 `https://aistudio.baidu.com/paddleocr/task`。

不要把完整 `API_URL` 猜成固定值。官方示例使用 `API_URL = "<your url>"`，并说明 `API_URL` 和 `TOKEN` 都要到 PaddleOCR 官网任务页的 API 调用示例里获取；官方文档只固定了主要操作路径 `POST /layout-parsing`。

如果用户没有提供 API 凭据，明确告诉用户或同事：

1. 打开 `https://aistudio.baidu.com/paddleocr/task`。
2. 登录百度/AI Studio 账号，并按页面要求开通服务或完成认证。
3. 进入 PaddleOCR API 或 PaddleOCR-VL 的 API 调用示例。
4. 复制 `API_URL` 和 `TOKEN`。
5. 在运行 Agent 的终端中设置：

```bash
export PADDLEOCR_API_URL="复制来的 API_URL"
export PADDLEOCR_TOKEN="复制来的 TOKEN"
```

如果团队已经统一预置 `PADDLEOCR_API_URL`，同事只需要填 `PADDLEOCR_TOKEN`。不要把 `TOKEN` 写进最终 Markdown、README 或共享材料。

默认建议使用稳定 OCR 参数：`temperature=0.0`、`repetitionPenalty=1.0`、开启版面检测和图表识别、开启跨页表格合并和标题层级恢复。

如果 PaddleOCR API URL 或 token 缺失，不要伪造 OCR 结果；先要求用户提供凭据或设置环境变量。

## VLM 规则

使用 [图片转 Mermaid 提示词](references/figure-to-mermaid.md) 约束 VLM。必须遵守：

- Mermaid 只来自图片中的可见文字和可见结构。
- 保留原图中的英文术语、阈值、符号、脚注标记和药物名称。
- 不添加医学解释、翻译、指南解读或推荐意见。
- 垂直算法、风险分层和决策树优先使用 `flowchart TB`；左右路径图优先使用 `flowchart LR`。
- 如果局部文字无法辨认，只标记 `[unreadable]`，不要猜测。

## 汇报标准

最终汇报必须包含：最终 Markdown 路径、PaddleOCR 是否成功、原始图片数量、Mermaid 代码块数量、剩余图片引用数量、无法识别的图片 id。除非实际运行过 Mermaid 渲染检查，否则不要声称“渲染已验证”。

## 资源

- `scripts/guideline_ocr_mermaid.py`：从 PDF 调 PaddleOCR、抽取图片、生成 VLM 工作区、回填 Mermaid 和验证最终 Markdown。
- `references/paddleocr-vl-api.md`：本流程用到的 PaddleOCR-VL 请求和响应字段说明。
- `references/figure-to-mermaid.md`：VLM 图片转 Mermaid 的提示词约束。
