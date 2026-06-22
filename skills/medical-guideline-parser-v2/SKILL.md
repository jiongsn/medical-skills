---
name: medical-guideline-parser-v2
description: >-
  Use when you have a medical guideline (PDF/text) for a specific condition and
  need to capture its diagnosis/treatment decision logic as a logic tree AND an
  exhaustive inventory of every clinical entity (fields, scores, biomarkers,
  drugs, exams) for downstream patient-record extraction or disease-config
  generation. Each condition gets its own structure — CAP uses NEWS/CURB-65,
  sepsis uses qSOFA/APACHE, ACS uses TIMI/GRACE. Symptoms: "How do I structure
  THIS guideline?", "What fields/entities for THIS condition?", "Feed this into
  generating-disease-json-configs", "Should I check supplementary files?"
---

# Medical Guideline Parser v2

## Overview
Turns an unstructured clinical guideline into two deliverables:

1. **Complete clinical logic tree** — the diagnosis → staging → stratification → treatment selection → evaluation/follow-up IF-THEN-ELSE logic, with scores and timing windows.
2. **Entity inventory** — an EXHAUSTIVE list of every clinical entity the guideline names (diagnostic criteria, staging fields, biomarkers, scores, drugs, exams, labs, complications), typed for downstream use.

**Core principle:** Guidelines are decision engines. Capture the full clinical decision logic AND every entity it references. The entities become the extraction/config substrate, so a missing entity is a downstream hole.

**Scope (v2):** Output ends at a self-checked clinical logic tree + entity inventory. This skill does NOT test against patient cases, generate extraction prompts, or generate disease configs.

## When to Use
**Use when:**
- Feeding a disease config generator (e.g. generating-disease-json-configs) or record-extraction pipeline
- Building clinical decision support (CDSS) or research-grade record databases
- Converting a guideline PDF/text into structured clinical logic and fields

**NOT for:**
- General PDF summarization or simple information retrieval
- Testing a patient case against a guideline
- Generating the final extraction prompt or JSON config

## Exhaustiveness is the job

The entity inventory must be **complete**, not representative. A downstream skill turns this entity list into an extraction schema or disease config; anything omitted here silently becomes un-extractable.

**Forbidden shortcuts — each is a defect:**
- "节选" / "representative sample" / "等" / "..." in an entity list
- "详见参考" / "see v1" / "see reference" instead of listing the entities here
- Parent categories without children (e.g. `检验` without each named lab; `TNM` without T/N/M components)
- Decision-rich chapters only, with screening/imaging/rehab/follow-up skipped

**Red flags — STOP and finish enumerating:**
- You wrote "核心字段" / "core fields (excerpt)"
- You referenced another document for the full list
- Your entity count is suspiciously round or small for the guideline size
- A whole guideline section has zero entities and no explicit reason

Organize the **logic tree by clinical decision flow**, not by source chapter order. Use chapter/section coverage only as QA evidence.

## Quick Reference

| Phase | Output | Completion criterion |
|---|---|---|
| **0. Prepare files** | Main file, supplementary file list, cross-reference ledger | Every cited external source is classified as resolved / unresolved gap / not needed |
| **1. Distill clinical logic** | Complete diagnosis-to-treatment logic tree | Every recommendation has IF condition, THEN action, population/stratum, timing window if present |
| **2. Extract entities** | Exhaustive typed entity inventory + mappings + coverage ledger | Every section is covered; every parent concept is decomposed into named children/components |
| **Final QA** | Agent-run script + manual checks, then handoff question | Validation script has been run by the agent; no shortcut placeholders remain; user is asked whether to hand off downstream |

## Phase 0: File Preparation

1. Read the **main guideline** first — it is the authority.
2. Mark sections that reference external content.
3. For each cross-reference, consult **supplementary files** only for the missing detail.
4. Integrate, and label any content sourced from supplementary files.

Check a supplementary file only when the main text shows a referral pattern:
`参照...` / `参考...` / `详见...` / `按照[分类标准]执行` / `与[其他来源]一致` / "as defined in [X] criteria" / a classification or score named but not explained.

Supplementary files add **detail** to referenced content; they never replace the main guideline's core recommendations.

**Phase 0 complete when:**
- Main guideline sections are listed.
- Supplementary files are listed with what each covers.
- Every external reference is marked `resolved`, `unresolved_gap`, or `not_needed`, with a short reason.

## Phase 1: Distill Complete Clinical Logic

Produce an explicit **logic tree** (nested IF-THEN-ELSE), organized by the clinical decision flow:

1. Diagnosis / inclusion / exclusion
2. Staging, typing, grading, molecular/pathology classification
3. Risk or severity stratification
4. Treatment selection by subtype, stage, line of therapy, contraindication, tolerance, or special population
5. Evaluation, response/progression, follow-up, surveillance, rehabilitation, or discharge when covered

For every recommendation capture the **IF condition** (`IF score >= X / subtype = Y / stage = Z`), the **THEN action**, population or stratum, and timing window if present. Do not collapse rules into vague recommendation summaries.

**Phase 1 complete when:**
- Every decision domain covered by the guideline appears in the logic tree.
- Every recommendation is represented as IF condition + THEN action.
- Timing windows, thresholds, contraindications, escalation/de-escalation conditions, and line-of-therapy rules are preserved.
- Branches that are absent or unclear in the guideline are marked `not_present_in_guideline` or `unresolved_gap`, not silently omitted.

## Phase 2: Entity Inventory (exhaustive)

List **every** entity the guideline names, grouped by clinical area. One row per entity.

| Entity | Type | Enum / range | Decision role |
|---|---|---|---|
| `[name]` | Enum/Number/Bool/String/Object | values from THIS guideline | diagnosis / staging / treatment_selection / monitoring / safety / none |

Cover at minimum, where the guideline has them: demographics, risk factors, comorbidities, diagnostic criteria, histology types, grading, staging, biomarkers and molecular tests, IHC markers, scores, lab indicators, imaging exams and findings, drugs by class, regimens, procedures/surgery, radiotherapy, response/progression concepts, complications/adverse events, follow-up and surveillance.

### Entity Granularity Rules

- If a parent concept has named children/components, list both the parent and each child/component.
- Scores require total-score rows plus component-factor rows.
- TNM/staging requires stage-system rows plus T/N/M/stage-group rows when named.
- Regimens require regimen rows plus drug rows; drug rows should include generic names when available.
- Exams require method rows plus named finding rows.
- Labs require each named indicator, not only a panel name.
- Entity inventory is the full set. Key indicators are a subset tagged through `Decision role`, not a replacement for exhaustive extraction.

Add required mapping tables:

| Raw term in record | Standardized value |
|---|---|
| "MI", "心梗", "myocardial infarction" | `myocardial_infarction` |

Add a drug category → generic-name table when the guideline drives therapy.

### Coverage Ledger

After the entity tables, output a coverage ledger. This ledger is QA evidence; it must not replace the clinical logic tree.

| Guideline section | Logic captured? | Entities captured? | Entity count | Status / gap reason |
|---|---|---|---|---|
| `[section title]` | yes/no/not_applicable | yes/no/not_applicable | number | captured / not_present_in_guideline / unresolved_gap |

**Phase 2 complete when:**
- Every guideline section appears in the coverage ledger.
- Every entity table avoids shortcut placeholders (`节选`, `等`, `...`, `see reference`).
- Every parent concept with named children/components has been decomposed.
- Missing or inapplicable content is explicitly marked `not_present_in_guideline`, `not_applicable`, or `unresolved_gap`.

## Final QA

The agent must run the deterministic QA script itself before final handoff. Do not ask the user to run this script manually.

Required flow:

1. Save the complete parser output as a markdown file.
2. Resolve `scripts/validate_output.py` relative to this `SKILL.md` file.
3. Run: `python3 <skill-dir>/scripts/validate_output.py <output.md>`.
4. If validation fails, fix the output and rerun the script.
5. Continue only after the script returns `PASS`, or after explicitly reporting why validation could not run.

The script checks for shortcut placeholders, required output sections, and the coverage ledger. Treat script failures as blockers until resolved or explicitly explained.

If the user did not provide an output path, choose a reasonable markdown filename in the working directory. If the environment cannot write files or cannot run shell commands, say that validation is blocked and do not present the result as validated.

Manual QA checklist:
- [ ] Complete clinical logic is organized by diagnosis-to-treatment flow, not chapter order.
- [ ] Entity inventory is exhaustive, not only decision-critical fields.
- [ ] Coverage ledger includes every guideline section.
- [ ] No entity list contains `节选`, `等`, `...`, `see v1`, or `see reference`.
- [ ] Every missing or unclear area has a status/gap reason.

## Handoff Gate

After the validation script has run and Final QA is complete, STOP and ask the user:

> 是否要把这份完整诊疗逻辑 + 实体清单交给 `generating-disease-json-configs` 继续生成疾病配置？

If the user says yes:
1. Read `generating-disease-json-configs` as the authoritative downstream contract.
2. Hand off the complete clinical logic tree, entity inventory, mappings, and coverage ledger.
3. Do not generate final JSON unless the user explicitly asks.

If the user says no, stop with the self-checked clinical logic tree + entity inventory.

## Common Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Entity list is a sample | "节选" / "等" / "see reference" | Enumerate every entity here |
| Logic is chapter-shaped | Output follows headings but misses diagnosis-to-treatment flow | Rebuild as clinical decision flow |
| A section is skipped | Screening/imaging/rehab/follow-up missing | Add ledger row and entities or gap reason |
| Reusing other-condition enums | COPD/CURB-65 on a cardiac schema | Derive enums from THIS guideline |
| Only recommendations | "should do" with no WHEN | Extract IF conditions into the tree |
| Missing timing windows | No door-to-needle time | Keep time-critical actions verbatim |
| Parent entity only | `TNM`, `blood routine`, or `regimen` without children | Add component/child rows |
| Key indicators replace entity inventory | Only trend-chart fields listed | Keep full inventory, then tag decision/monitoring roles |
