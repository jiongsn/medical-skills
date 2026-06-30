# medical-skills

这是一个医学场景的 Agent Skill 仓库。

简单说，Skill 就是一套给 AI 助手看的“操作说明书”。安装后，Claude、Codex 等 Agent 在处理医学资料时，会按这里写好的流程工作，而不是每次都从头理解任务。

## 现在包含的 Skill

### `medical-guideline-ocr-mermaid`

用于从医学指南 PDF 生成最终 Markdown：先调用 PaddleOCR-VL 做 OCR 和版面解析，再让 Agent 用 VLM 把图片流程图转换成 Mermaid，最后把 Mermaid 回填到原图片位置。

适合这类场景：

- 手里是 PDF 指南，希望最终得到一个正文、表格和 Mermaid 图都在同一个文件里的 Markdown。
- PaddleOCR 可以解析文字和表格，但指南里的流程图、算法图仍然需要 VLM 读取。
- 希望医学同事后续审阅的是可复制、可编辑的 Mermaid 流程图。
- 同一份指南有多个 OCR 版本，需要保留文字/表格更好的版本，只替换图片位置。

推荐流程：

```text
PDF 指南 → PaddleOCR-VL 解析正文/表格/图片 → VLM 把图片转 Mermaid → 回填并输出最终 Markdown
```

这个 Skill 不负责判断指南医学内容是否正确，也不应该改写正文或表格。它只把 PDF 变成更适合审阅和后续结构化处理的 Markdown。

### `medical-guideline-parser-v2`

用于把一份 Markdown 格式的医学指南整理成两类结构化结果：

1. **完整诊疗逻辑**
   - 例如：诊断条件、分期/分型、风险分层、治疗选择、疗效评估、随访。
   - 重点是整理成“如果满足什么条件，就应该做什么”的诊疗决策路径。

2. **临床实体清单**
   - 例如：症状、体征、检验指标、影像检查、评分量表、分期字段、药物、治疗方案、不良反应、随访项目。
   - 重点是尽量完整列出指南里出现过的医学字段，方便后续做病历抽取或疾病配置。

这个 Skill 不是用来直接判断某个患者该怎么治疗，也不是替代医生决策。它的作用是帮助 Agent 从指南中提炼结构化信息。

## 适合什么时候用

适合这些场景：

- 想把 PDF 指南先转成可审阅的 Markdown。
- 想把指南里的图片流程图转换成可复制、可编辑的 Mermaid。
- 想把某个病种指南整理成结构化诊疗逻辑。
- 想知道一个病种病历抽取时应该关注哪些字段。
- 想为后续生成疾病配置、病历抽取 schema 或临床数据库字段做准备。
- 想检查指南里哪些章节已经覆盖，哪些地方还有缺口。

不适合这些场景：

- 直接给真实患者做诊疗建议。
- 简单总结 PDF。
- 只想摘录几条推荐意见。

## 如何安装

仓库名：

```text
medical-skills
```

最简单的方式：把这个 GitHub 地址发给支持安装 Skill 的 Agent：

```text
https://github.com/jiongsn/medical-skills
```

可以直接对 Agent 说：

```text
请帮我安装这个 GitHub 仓库里的 Skill：https://github.com/jiongsn/medical-skills
```

如果对方的 Agent 支持安装 Skill，通常会自动识别仓库并完成安装；如果 Agent 只能聊天、不能操作本机环境，就需要改用下面的命令。

备用命令：

```bash
npx skills@latest add jiongsn/medical-skills
```

如果这个仓库以后放在组织账号下，把 `jiongsn` 换成组织名即可：

```bash
npx skills@latest add <组织名>/medical-skills
```

安装过程中，选择要安装的 Skill 和目标 Agent 即可。

## 输入文件要求

`medical-guideline-ocr-mermaid` 默认输入是 **PDF**。运行它需要：

- PaddleOCR-VL API 地址和 token，或已经配置好的 `PADDLEOCR_API_URL`、`PADDLEOCR_TOKEN` 环境变量。
- Agent 具备查看图片并调用 VLM/图片理解能力的环境。

### PaddleOCR API 怎么获取

同事只需要记住这个固定入口：`https://aistudio.baidu.com/paddleocr/task`。

需要说明清楚的是：官方文档没有给一个所有人通用、可以永久写死的完整 `API_URL`；官方示例写的是 `API_URL = "<your url>"`，并说明 `API_URL` 和 `TOKEN` 都要从 PaddleOCR 官网任务页的 **API 调用示例** 中获取。文档固定的是接口操作路径 `POST /layout-parsing`，完整调用 URL 仍以任务页生成的示例为准。

给同事的操作步骤：

1. 打开 PaddleOCR 官网任务页：`https://aistudio.baidu.com/paddleocr/task`。
2. 登录百度/AI Studio 账号；如果页面要求实名认证或开通服务，按页面提示完成。
3. 进入 PaddleOCR API 或 PaddleOCR-VL 的 **API 调用示例**。
4. 复制调用示例中的 `API_URL` 和 `TOKEN`。
5. 不要把 `TOKEN` 写进共享文档，也不要发到多人群里；只在本机环境变量、私密凭据管理器或私密对话里提供。

推荐填法：在运行 Agent 的终端里设置环境变量：

```bash
export PADDLEOCR_API_URL="从 PaddleOCR API 调用示例复制的 API_URL"
export PADDLEOCR_TOKEN="从 PaddleOCR API 调用示例复制的 TOKEN"
```

如果团队里确认所有同事使用同一个 `API_URL`，可以由管理员或你先在每台机器上预置 `PADDLEOCR_API_URL`。这样同事日常只需要提供 `PADDLEOCR_TOKEN`：

```bash
export PADDLEOCR_TOKEN="从 PaddleOCR API 调用示例复制的 TOKEN"
```

也可以在命令里直接传入：

```bash
python3 skills/medical-guideline-ocr-mermaid/scripts/guideline_ocr_mermaid.py from-pdf \
  --input guideline.pdf \
  --work-dir guideline_ocr_mermaid_work \
  --api-url "从 PaddleOCR API 调用示例复制的 API_URL" \
  --token "从 PaddleOCR API 调用示例复制的 TOKEN"
```

如果同事不会设置环境变量，可以直接告诉 Agent：

```text
我已经打开 https://aistudio.baidu.com/paddleocr/task，并从 API 调用示例里拿到了 API_URL 和 TOKEN。请使用 medical-guideline-ocr-mermaid 处理这个 PDF；如果你需要，我会在私密对话里提供 API_URL 和 TOKEN。
```

`medical-guideline-parser-v2` 默认输入是 **Markdown（.md）格式** 的指南文本。如果原始资料是 PDF，建议先用 `medical-guideline-ocr-mermaid` 生成最终 Markdown，再交给 `medical-guideline-parser-v2`。

推荐流程：

```text
PDF 指南 → medical-guideline-ocr-mermaid → 带 Mermaid 的最终 Markdown → medical-guideline-parser-v2
```

这样做的原因是：医学指南里的章节、表格、分级、推荐语、图注和流程图都很重要。先转成结构清楚的 Markdown，Agent 更容易看到完整文本结构，也更容易做章节覆盖和实体穷尽检查。

## 如何使用

在 Agent 里可以这样说：

```text
使用 medical-guideline-ocr-mermaid，帮我处理这份 PDF：先调用 PaddleOCR 做 OCR，再用 VLM 把图片流程图转成 Mermaid，最后输出一个 Markdown 文件。
```

如果已经有 PaddleOCR Markdown，也可以说：

```text
使用 medical-guideline-ocr-mermaid，帮我把这份 PaddleOCR Markdown 里的图片流程图转成 Mermaid，并保留原正文和表格。
```

继续结构化指南时可以说：

```text
使用 medical-guideline-parser-v2，帮我把这份指南整理成完整诊疗逻辑和临床实体清单。
```

## 输出会包含什么

如果使用 `medical-guideline-ocr-mermaid`，通常会包含：

- PaddleOCR 解析得到的 OCR Markdown
- 从 OCR Markdown 抽取出的原始图片清单 `image_manifest.json`
- 每张图片对应的 VLM 提示词
- Mermaid 映射文件 `mermaid_map.json`
- 回填 Mermaid 后的最终 Markdown 文件
- 图片数量、Mermaid 数量和剩余图片引用数量的验证结果

如果使用 `medical-guideline-parser-v2`，通常会包含：

- 诊疗逻辑树
- 临床实体清单
- 术语标准化映射
- 药物类别与通用名表
- 指南章节覆盖表
- 自检结果

Skill 运行到最后，会询问是否继续交给下游 Skill 生成疾病配置。

## 质量检查

仓库里带了检查脚本。正常使用时，Agent 应该在输出最终结果前自动运行，不需要医学同事手动执行。

如果使用 `medical-guideline-ocr-mermaid`，最后应检查图片是否已经被 Mermaid 替换：

```bash
python3 skills/medical-guideline-ocr-mermaid/scripts/guideline_ocr_mermaid.py validate --markdown path/to/final.md --expected-mermaid-count <图片数量>
```

这个脚本会检查最终 Markdown 里剩余的图片引用、Mermaid 数量、Markdown 代码块是否闭合，以及常见 Mermaid 不可渲染语法，例如未转义的 `<`/`>`、错误边标签、无 id 的 `[unreadable]`、样式语法和 subgraph。

如果使用 `medical-guideline-parser-v2`，可以运行：

```bash
python3 skills/medical-guideline-parser-v2/scripts/validate_output.py path/to/output.md
```

这个脚本会检查结构化输出有没有明显问题，例如：

- 缺少诊疗逻辑
- 缺少实体清单
- 缺少章节覆盖表
- 出现“节选”“等”“...”这类不完整写法

这些脚本只能检查格式、数量和常见遗漏，不能判断医学内容是否完全正确。医学准确性仍然需要人工复核。

## 仓库结构

```text
medical-skills/
├── skills/
│   ├── medical-guideline-ocr-mermaid/
│   │   ├── SKILL.md
│   │   ├── references/
│   │   └── scripts/
│   │       └── guideline_ocr_mermaid.py
│   └── medical-guideline-parser-v2/
│       ├── SKILL.md
│       └── scripts/
│           └── validate_output.py
├── .claude-plugin/
│   └── plugin.json
├── .codex-plugin/
│   └── plugin.json
├── README.md
└── LICENSE
```

## 后续可以继续添加

这个仓库以后可以继续放其他医学 Skill，例如：

- 药物说明书解析
- 临床试验方案解析
- 医学证据等级整理
- 病种配置生成
- 医学内容质控

新增 Skill 时，放到 `skills/` 目录下即可。
