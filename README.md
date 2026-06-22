# medical-skills

这是一个医学场景的 Agent Skill 仓库。

简单说，Skill 就是一套给 AI 助手看的“操作说明书”。安装后，Claude、Codex 等 Agent 在处理医学资料时，会按这里写好的流程工作，而不是每次都从头理解任务。

## 现在包含的 Skill

### `medical-guideline-parser-v2`

用于把一份医学指南整理成两类结构化结果：

1. **完整诊疗逻辑**
   - 例如：诊断条件、分期/分型、风险分层、治疗选择、疗效评估、随访。
   - 重点是整理成“如果满足什么条件，就应该做什么”的诊疗决策路径。

2. **临床实体清单**
   - 例如：症状、体征、检验指标、影像检查、评分量表、分期字段、药物、治疗方案、不良反应、随访项目。
   - 重点是尽量完整列出指南里出现过的医学字段，方便后续做病历抽取或疾病配置。

这个 Skill 不是用来直接判断某个患者该怎么治疗，也不是替代医生决策。它的作用是帮助 Agent 从指南中提炼结构化信息。

## 适合什么时候用

适合这些场景：

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

这个 Skill 默认处理 **Markdown（.md）格式** 的指南文本。

如果原始资料是 PDF，不建议直接把 PDF 丢给这个 Skill。请先把 PDF 解析成 Markdown，再使用 `medical-guideline-parser-v2`。

推荐流程：

```text
PDF 指南 → 用 PaddleOCR 等工具解析成 Markdown → 再交给 medical-guideline-parser-v2
```

这样做的原因是：医学指南里的章节、表格、分级、推荐语和脚注很重要。先转成 Markdown，Agent 更容易看到完整文本结构，也更容易做章节覆盖和实体穷尽检查。

## 如何使用

在 Agent 里可以这样说：

```text
使用 medical-guideline-parser-v2，帮我把这份指南整理成完整诊疗逻辑和临床实体清单。
```

也可以更具体一点：

```text
使用 medical-guideline-parser-v2，解析这份乳腺癌指南，输出诊疗逻辑树、实体清单和章节覆盖表。
```

## 输出会包含什么

通常会包含：

- 诊疗逻辑树
- 临床实体清单
- 术语标准化映射
- 药物类别与通用名表
- 指南章节覆盖表
- 自检结果

Skill 运行到最后，会询问是否继续交给下游 Skill 生成疾病配置。

## 质量检查

仓库里带了一个简单的检查脚本。正常使用时，Agent 应该在输出最终结果前自动运行这个脚本，不需要医学同事手动执行。

脚本会检查输出文件有没有明显问题，例如：

- 缺少诊疗逻辑
- 缺少实体清单
- 缺少章节覆盖表
- 出现“节选”“等”“...”这类不完整写法

如果需要排查问题，也可以手动运行：

```bash
python3 skills/medical-guideline-parser-v2/scripts/validate_output.py path/to/output.md
```

这个脚本只能检查格式和常见遗漏，不能判断医学内容是否完全正确。医学准确性仍然需要人工复核。

## 仓库结构

```text
medical-skills/
├── skills/
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
