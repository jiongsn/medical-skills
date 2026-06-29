# PaddleOCR-VL API 说明

来源：https://ai.baidu.com/ai-doc/AISTUDIO/Cmkz2m0ma，核对日期：2026-06-29。

仅当用户希望这个 skill 直接调用 PaddleOCR 时阅读本文件。如果用户已经有 PaddleOCR 生成的 Markdown，跳过 API 调用，直接从图片抽取开始。

## API_URL 和 TOKEN 在哪里获取

固定入口：`https://aistudio.baidu.com/paddleocr/task`。

PaddleOCR 官方文档的 Python 调用示例中写明：`API_URL` 和 `TOKEN` 请访问 PaddleOCR 官网任务页，在 API 调用示例中获取。官方示例没有提供一个所有账号通用的完整 `API_URL`；它写的是 `API_URL = "<your url>"`。接口说明只固定了主要操作路径：`POST /layout-parsing`。

给同事的操作说明：

1. 打开 `https://aistudio.baidu.com/paddleocr/task`。
2. 登录百度/AI Studio 账号；如页面要求实名认证、开通服务或选择计费方式，按页面提示完成。
3. 找到 PaddleOCR API 或 PaddleOCR-VL 的 API 调用示例。
4. 复制示例中的 `API_URL` 和 `TOKEN`。
5. 在运行 Agent 的机器上设置环境变量：

```bash
export PADDLEOCR_API_URL="复制来的 API_URL"
export PADDLEOCR_TOKEN="复制来的 TOKEN"
```

如果团队已经统一预置 `PADDLEOCR_API_URL`，同事只需要设置：

```bash
export PADDLEOCR_TOKEN="复制来的 TOKEN"
```

或者在脚本命令中直接传入：

```bash
python3 skills/medical-guideline-ocr-mermaid/scripts/guideline_ocr_mermaid.py from-pdf \
  --input guideline.pdf \
  --work-dir guideline_ocr_mermaid_work \
  --api-url "复制来的 API_URL" \
  --token "复制来的 TOKEN"
```

安全要求：`TOKEN` 是凭据，不要写入最终 Markdown、公开 README、邮件正文或群聊。只应存在于本机环境变量、私密凭据管理器或私密对话中。

## 接口

官方文档中的主要操作是版面解析：

```text
POST /layout-parsing
```

完整 base URL 取决于用户在 PaddleOCR 控制台或部署环境中的配置。脚本要求显式提供 `--api-url` 或环境变量 `PADDLEOCR_API_URL`，不要猜测接口地址。

请求头：

```text
Authorization: token <TOKEN>
Content-Type: application/json
```

## 本流程用到的请求字段

必填或常用字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `file` | string | 服务端可访问的文件 URL，或 PDF/图片字节的 Base64 字符串。 |
| `fileType` | integer/null | `0` 表示 PDF，`1` 表示图片；如果缺省，服务可能会根据 URL 推断。 |

适合医学指南 OCR 的常用选项：

| 字段 | 含义 |
|---|---|
| `useDocOrientationClassify` | 是否进行 0/90/180/270 度方向矫正。 |
| `useDocUnwarping` | 是否进行弯曲或倾斜文本图像矫正。 |
| `useLayoutDetection` | 是否识别和排序版面区域；医学指南 PDF 通常建议开启。 |
| `useChartRecognition` | 是否尽量把图表解析为可编辑数据。 |
| `layoutShapeMode` | 版面检测形状，可选 `rect`、`quad`、`poly` 或 `auto`；截图中的流程使用 `auto`。 |
| `repetitionPenalty` | 输出重复时可提高；截图中的流程使用 `1.00`。 |
| `temperature` | 越低越保守稳定；截图中的流程使用 `0.00`。 |
| `restructurePages` | 是否重构多页输出，适合跨页结构。 |
| `mergeTables` | 是否在支持的解析路径中合并跨页表格。 |
| `relevelTitles` | 是否恢复段落和标题层级。 |
| `prettifyMarkdown` | 是否请求更整洁的 Markdown 输出。 |
| `visualize` | 是否返回可视化或中间图；纯文本流程可关闭以减少输出体积。 |

## 本流程用到的响应字段

成功响应包含 `result`。

`result.layoutParsingResults` 是数组。图片输入通常长度为 1；PDF 输入通常按页或解析结果返回多个元素。

每个解析结果可能包含：

| 字段 | 含义 |
|---|---|
| `markdown.text` | 需要保留为目标 OCR 正文的 Markdown 文本。 |
| `markdown.images` | Markdown 图片相对路径到 Base64 图片字符串或图片 URL 的映射。 |
| `outputImages` | 可选的可视化或中间 JPEG 图片。 |
| `inputImage` | 可选的输入图片 JPEG Base64。 |

辅助脚本支持 `markdown.images` 中的 Base64 图片和 URL 图片。

## 医学指南 PDF 推荐起始参数

建议从下面这组参数开始：

```json
{
  "fileType": 0,
  "useDocOrientationClassify": false,
  "useDocUnwarping": false,
  "useLayoutDetection": true,
  "useChartRecognition": true,
  "layoutShapeMode": "auto",
  "repetitionPenalty": 1.0,
  "temperature": 0.0,
  "restructurePages": true,
  "mergeTables": true,
  "relevelTitles": true,
  "prettifyMarkdown": true,
  "visualize": false
}
```

如果这组参数让表格变差，保留质量更好的 OCR Markdown，只用本 skill 做图片替换。
