#!/usr/bin/env python3
"""医学指南 OCR 图片转 Mermaid 辅助脚本。

子命令：
  from-pdf  从 PDF 开始，调用 PaddleOCR-VL 并准备 VLM 转 Mermaid 工作区。
  finalize  在 VLM 生成 Mermaid 映射后，回填并输出最终 Markdown。
  paddleocr  单独调用 PaddleOCR-VL 版面解析接口并保存 Markdown/图片。
  extract    单独从 PaddleOCR Markdown 中抽取图片块。
  apply      根据 Mermaid JSON 映射回填图片块。
  validate   检查图片、Mermaid 数量和未解决占位符。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

IMG_TAG_RE = re.compile(r'<img\s+[^>]*src=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)
MD_IMG_RE = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')
MERMAID_FENCE_RE = re.compile(r'```mermaid\s*\n.*?\n```', re.DOTALL)
PLACEHOLDER_RE = re.compile(r'TODO_MERMAID|\[unconverted\]', re.IGNORECASE)

VLM_PROMPT = """请把这张医学指南图片转换为 Mermaid。

规则：
1. 只使用图片中可见的文字和可见结构。
2. 尽量保留原图中的英文术语、阈值、符号、脚注标记和药物名称。
3. 不要添加图片中没有出现的医学解释、翻译、建议或推荐意见。
4. 只输出一段 Mermaid 源码，不要输出 Markdown 代码围栏。
5. 垂直决策树、算法图和风险分层优先使用 flowchart TB；左右路径图优先使用 flowchart LR。
6. 节点内换行和项目列表使用 <br/>。
7. 标签中的比较符号按需要转义为 &lt; 和 &gt;。
8. 如果局部文字无法辨认，只在该片段标记 [unreadable]，不要猜测。
"""


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def infer_file_type(path: Path) -> int:
    return 0 if path.suffix.lower() == ".pdf" else 1


def guess_ext(src: str, content_type: Optional[str] = None) -> str:
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext:
            return ".jpg" if ext == ".jpe" else ext
    suffix = Path(urllib.parse.urlparse(src).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
        return suffix
    return ".jpg"


def safe_output_path(base: Path, rel_path: str, fallback_name: str) -> Path:
    raw_path = urllib.parse.unquote(urllib.parse.urlparse(str(rel_path)).path or str(rel_path))
    parts = [part for part in Path(raw_path).parts if part not in ("", ".", "..", os.sep)]
    if not parts:
        parts = [fallback_name]
    return base.joinpath(*parts)


def decode_base64_image(value: str) -> Optional[Tuple[bytes, str]]:
    if value.startswith("data:image/"):
        header, payload = value.split(",", 1)
        ext = "." + header.split("data:image/", 1)[1].split(";", 1)[0].replace("jpeg", "jpg")
        return base64.b64decode(payload), ext
    compact = re.sub(r"\s+", "", value)
    if len(compact) < 64:
        return None
    try:
        data = base64.b64decode(compact, validate=True)
    except Exception:
        return None
    if data.startswith(b"\xff\xd8"):
        return data, ".jpg"
    if data.startswith(b"\x89PNG"):
        return data, ".png"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return data, ".webp"
    return data, ".jpg"


def fetch_url(url: str, timeout: int = 60) -> Tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read()
        content_type = response.headers.get("content-type")
    return data, guess_ext(url, content_type)


def save_image_source(src: str, dest_stem: Path, image_root: Optional[Path] = None, download: bool = True) -> Tuple[Optional[Path], Optional[str]]:
    decoded = decode_base64_image(src)
    if decoded:
        data, ext = decoded
        dest = dest_stem.with_suffix(ext)
        write_bytes(dest, data)
        return dest, None

    parsed = urllib.parse.urlparse(src)
    if parsed.scheme in {"http", "https"}:
        if not download:
            return None, "download_disabled"
        data, ext = fetch_url(src)
        dest = dest_stem.with_suffix(ext)
        write_bytes(dest, data)
        return dest, None

    candidates = []
    raw = Path(src)
    if raw.is_absolute():
        candidates.append(raw)
    if image_root:
        candidates.append(image_root / src)
        candidates.append(image_root / "images" / src)
    for candidate in candidates:
        if candidate.exists():
            ext = candidate.suffix or ".jpg"
            dest = dest_stem.with_suffix(ext)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, dest)
            return dest, None
    return None, "source_not_found"


def sha256_file(path: Optional[Path]) -> Optional[str]:
    if not path or not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_image_blocks(markdown: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for line_no, line in enumerate(markdown.splitlines(), 1):
        src = None
        kind = None
        m = IMG_TAG_RE.search(line)
        if m:
            src = m.group(1)
            kind = "html_img"
        else:
            m = MD_IMG_RE.search(line)
            if m:
                src = m.group(1)
                kind = "markdown_img"
        if src:
            items.append({"line": str(line_no), "block": line, "src": src, "kind": kind or "image"})
    return items


def surrounding_context(lines: List[str], line_no: int, context_lines: int) -> Tuple[str, str, str]:
    idx = line_no - 1
    before = "\n".join(lines[max(0, idx - context_lines):idx]).strip()
    after = "\n".join(lines[idx + 1:idx + 1 + context_lines]).strip()
    caption = ""
    for line in lines[idx + 1:idx + 12]:
        clean = re.sub(r"<[^>]+>", " ", line).strip()
        clean = re.sub(r"\s+", " ", clean)
        if re.search(r"Figure\s+\d+", clean, re.IGNORECASE):
            caption = clean
            break
    return before, after, caption


def command_paddleocr(args: argparse.Namespace) -> int:
    api_url = args.api_url or os.environ.get("PADDLEOCR_API_URL")
    token = args.token or os.environ.get("PADDLEOCR_TOKEN")
    if not api_url:
        print("FAIL: 缺少 --api-url 或 PADDLEOCR_API_URL", file=sys.stderr)
        return 2
    if not token:
        print("FAIL: 缺少 --token 或 PADDLEOCR_TOKEN", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    file_bytes = input_path.read_bytes()
    payload: Dict[str, Any] = {
        "file": base64.b64encode(file_bytes).decode("ascii"),
        "fileType": args.file_type if args.file_type is not None else infer_file_type(input_path),
        "useDocOrientationClassify": args.use_doc_orientation,
        "useDocUnwarping": args.use_doc_unwarping,
        "useLayoutDetection": args.use_layout_detection,
        "useChartRecognition": args.use_chart_recognition,
        "layoutShapeMode": args.layout_shape_mode,
        "repetitionPenalty": args.repetition_penalty,
        "temperature": args.temperature,
        "restructurePages": args.restructure_pages,
        "mergeTables": args.merge_tables,
        "relevelTitles": args.relevel_titles,
        "prettifyMarkdown": args.prettify_markdown,
        "visualize": args.visualize,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=data,
        headers={"Authorization": f"token {token}", "Content-Type": "application/json"},
        method="POST",
    )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        print(f"FAIL: PaddleOCR HTTP {exc.code}: {body[:1000]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"FAIL: PaddleOCR 连接失败：{exc.reason}", file=sys.stderr)
        return 1
    if status != 200:
        print(f"FAIL: PaddleOCR HTTP {status}", file=sys.stderr)
        return 1
    write_bytes(out_dir / "raw_response.json", raw)
    response_json = json.loads(raw.decode("utf-8"))
    if response_json.get("errorCode") not in (None, 0):
        print(f"FAIL: PaddleOCR error {response_json.get('errorCode')}: {response_json.get('errorMsg')}", file=sys.stderr)
        return 1
    result = response_json.get("result", {})
    pages = result.get("layoutParsingResults", [])
    combined: List[str] = []
    image_dir = out_dir / "images"
    for i, page in enumerate(pages, 1):
        md = page.get("markdown", {}).get("text", "")
        write_text(out_dir / f"page_{i:03d}.md", md)
        combined.append(md)
        for rel_path, image_value in page.get("markdown", {}).get("images", {}).items():
            decoded = decode_base64_image(str(image_value))
            if decoded:
                data, ext = decoded
            elif str(image_value).startswith(("http://", "https://")):
                data, ext = fetch_url(str(image_value))
            else:
                continue
            safe_rel = safe_output_path(image_dir, rel_path, f"image_{i:03d}")
            if safe_rel.suffix:
                dest = safe_rel
            else:
                dest = safe_rel.with_suffix(ext)
            write_bytes(dest, data)
    write_text(out_dir / "combined.md", "\n\n".join(combined))
    print(f"PASS: 已保存 {len(pages)} 个页面结果到 {out_dir}")
    return 0


def command_extract(args: argparse.Namespace) -> int:
    md_path = Path(args.markdown)
    markdown = read_text(md_path)
    blocks = find_image_blocks(markdown)
    out_dir = Path(args.out_dir)
    images_dir = out_dir / "images"
    prompts_dir = out_dir / "prompts"
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = markdown.splitlines()
    seen_hashes: Dict[str, str] = {}
    manifest_items: List[Dict[str, Any]] = []
    mermaid_template: Dict[str, str] = {}
    for idx, block in enumerate(blocks, 1):
        image_id = f"image_{idx:03d}"
        line_no = int(block["line"])
        dest_stem = images_dir / image_id
        saved_path, error = save_image_source(
            block["src"],
            dest_stem,
            image_root=Path(args.image_root) if args.image_root else md_path.parent,
            download=not args.no_download,
        )
        digest = sha256_file(saved_path)
        duplicate_of = seen_hashes.get(digest) if digest else None
        if digest and not duplicate_of:
            seen_hashes[digest] = image_id
        before, after, caption = surrounding_context(lines, line_no, args.context_lines)
        item = {
            "id": image_id,
            "ordinal": idx,
            "line": line_no,
            "kind": block["kind"],
            "src": block["src"],
            "image_path": str(saved_path) if saved_path else None,
            "sha256": digest,
            "duplicate_of": duplicate_of,
            "error": error,
            "caption_after": caption,
            "context_before": before,
            "context_after": after,
            "original_block": block["block"],
        }
        manifest_items.append(item)
        mermaid_template[image_id] = f"TODO_MERMAID_{image_id}"
        prompt = (
            VLM_PROMPT
            + "\n图片 id：" + image_id
            + "\n图片路径：" + (str(saved_path) if saved_path else "[未保存]")
            + "\n图注或后文上下文：\n" + (caption or after[:1200])
            + "\n前文上下文：\n" + before[-1200:]
            + "\n"
        )
        write_text(prompts_dir / f"{image_id}.md", prompt)
    manifest = {"source_markdown": str(md_path), "image_count": len(blocks), "items": manifest_items}
    write_text(out_dir / "image_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    write_text(out_dir / "mermaid_map_template.json", json.dumps(mermaid_template, ensure_ascii=False, indent=2))
    print(f"PASS: 已抽取 {len(blocks)} 个图片块到 {out_dir}")
    return 0



def write_pdf_workflow_notes(work_dir: Path, state: Dict[str, Any]) -> None:
    figures_dir = Path(state["figures_dir"])
    body = f"""# VLM 图片转 Mermaid 任务

这个工作区由 `from-pdf` 生成，PaddleOCR 已经完成，下一步是把图片转换成 Mermaid 并回填。

## 路径

- OCR Markdown：`{state['ocr_markdown']}`
- 图片清单：`{state['manifest']}`
- 图片目录：`{figures_dir / 'images'}`
- VLM 提示词目录：`{figures_dir / 'prompts'}`
- Mermaid 映射文件：`{state['mermaid_map']}`
- 目标最终 Markdown：`{state['final_markdown']}`

## 操作

1. 逐一查看 `image_manifest.json` 里的图片。
2. 对每张图片使用同名 `prompts/image_XXX.md` 作为 VLM 提示词。
3. 把 VLM 输出的 Mermaid 源码写入 `mermaid_map.json` 对应的图片 id。
4. JSON 值里不要写 Markdown 代码围栏，只写 Mermaid 源码。
5. 全部图片完成后运行：

```bash
python3 {Path(__file__).name} finalize --work-dir {work_dir}
```
"""
    write_text(work_dir / "vlm_tasks.md", body)


def command_from_pdf(args: argparse.Namespace) -> int:
    work_dir = Path(args.work_dir)
    if work_dir.exists() and any(work_dir.iterdir()) and not args.force:
        print("FAIL: 工作目录已存在且非空；请换一个 --work-dir，或确认后加 --force", file=sys.stderr)
        return 2
    work_dir.mkdir(parents=True, exist_ok=True)

    paddleocr_dir = work_dir / "paddleocr"
    figures_dir = work_dir / "figures"
    input_path = Path(args.input)
    final_markdown = Path(args.output) if args.output else work_dir / f"{input_path.stem}.with-mermaid.md"

    paddleocr_args = argparse.Namespace(
        input=args.input,
        api_url=args.api_url,
        token=args.token,
        out_dir=str(paddleocr_dir),
        file_type=args.file_type if args.file_type is not None else infer_file_type(input_path),
        timeout=args.timeout,
        use_doc_orientation=args.use_doc_orientation,
        use_doc_unwarping=args.use_doc_unwarping,
        use_layout_detection=args.use_layout_detection,
        use_chart_recognition=args.use_chart_recognition,
        restructure_pages=args.restructure_pages,
        merge_tables=args.merge_tables,
        relevel_titles=args.relevel_titles,
        prettify_markdown=args.prettify_markdown,
        visualize=args.visualize,
        layout_shape_mode=args.layout_shape_mode,
        repetition_penalty=args.repetition_penalty,
        temperature=args.temperature,
    )
    rc = command_paddleocr(paddleocr_args)
    if rc:
        return rc

    ocr_markdown = paddleocr_dir / "combined.md"
    if not ocr_markdown.exists() or not read_text(ocr_markdown).strip():
        print(f"FAIL: PaddleOCR 没有生成有效 Markdown：{ocr_markdown}", file=sys.stderr)
        return 1

    extract_args = argparse.Namespace(
        markdown=str(ocr_markdown),
        out_dir=str(figures_dir),
        image_root=str(paddleocr_dir),
        context_lines=args.context_lines,
        no_download=args.no_download,
    )
    rc = command_extract(extract_args)
    if rc:
        return rc

    manifest_path = figures_dir / "image_manifest.json"
    template_path = figures_dir / "mermaid_map_template.json"
    mermaid_map_path = figures_dir / "mermaid_map.json"
    manifest = json.loads(read_text(manifest_path))
    image_count = int(manifest.get("image_count", 0))
    if template_path.exists() and not mermaid_map_path.exists():
        shutil.copyfile(template_path, mermaid_map_path)

    state = {
        "status": "awaiting_vlm_mermaid_map" if image_count else "complete_no_images",
        "input_pdf": str(input_path),
        "work_dir": str(work_dir),
        "paddleocr_dir": str(paddleocr_dir),
        "ocr_markdown": str(ocr_markdown),
        "figures_dir": str(figures_dir),
        "manifest": str(manifest_path),
        "mermaid_map_template": str(template_path),
        "mermaid_map": str(mermaid_map_path),
        "final_markdown": str(final_markdown),
        "image_count": image_count,
    }
    write_text(work_dir / "workflow_state.json", json.dumps(state, ensure_ascii=False, indent=2))
    write_pdf_workflow_notes(work_dir, state)

    if image_count == 0:
        shutil.copyfile(ocr_markdown, final_markdown)
        print(f"PASS: PaddleOCR 已完成，未发现图片块，已输出最终 Markdown：{final_markdown}")
        return 0

    print(f"PASS: PDF 已完成 PaddleOCR 和图片抽取，发现 {image_count} 个图片块")
    print(f"NEXT: 用 VLM 填写 {mermaid_map_path}，然后运行 finalize 输出最终 Markdown")
    print(f"STATE: {work_dir / 'workflow_state.json'}")
    return 0

def normalize_mermaid(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```mermaid"):
        stripped = re.sub(r"^```mermaid\s*\n", "", stripped)
        stripped = re.sub(r"\n```\s*$", "", stripped)
    elif stripped.startswith("```"):
        stripped = re.sub(r"^```\s*\n", "", stripped)
        stripped = re.sub(r"\n```\s*$", "", stripped)
    return "```mermaid\n" + stripped.strip() + "\n```"


def load_mermaid_map(path: Path) -> Dict[str, str]:
    data = json.loads(read_text(path))
    if isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items()}
    if isinstance(data, list):
        out: Dict[str, str] = {}
        for row in data:
            out[str(row["id"])] = str(row.get("mermaid") or row.get("code") or "")
        return out
    raise ValueError("Mermaid 映射必须是 JSON object 或 list")


def command_apply(args: argparse.Namespace) -> int:
    md_path = Path(args.markdown)
    manifest = json.loads(read_text(Path(args.manifest)))
    mermaid_map = load_mermaid_map(Path(args.mermaid_map))
    text = read_text(md_path)
    missing: List[str] = []
    replaced = 0
    for item in manifest.get("items", []):
        image_id = item["id"]
        code = mermaid_map.get(image_id)
        if not code or PLACEHOLDER_RE.search(code):
            missing.append(image_id)
            continue
        block = item["original_block"]
        if block not in text:
            print(f"FAIL: 找不到 {image_id} 对应的原始图片块", file=sys.stderr)
            return 1
        text = text.replace(block, normalize_mermaid(code), 1)
        replaced += 1
    if missing and not args.allow_missing:
        print("FAIL: 缺少 Mermaid：" + ", ".join(missing), file=sys.stderr)
        return 1
    out_path = Path(args.output)
    write_text(out_path, text)
    expected = replaced if args.allow_missing else int(manifest.get("image_count", replaced))
    ok, messages = validate_markdown(text, expected_mermaid_count=expected)
    for message in messages:
        print(message)
    if not ok:
        return 1
    print(f"PASS: 已在 {out_path} 中替换 {replaced} 个图片块")
    return 0



def command_finalize(args: argparse.Namespace) -> int:
    work_dir = Path(args.work_dir)
    state_path = work_dir / "workflow_state.json"
    if not state_path.exists():
        print(f"FAIL: 找不到工作区状态文件：{state_path}", file=sys.stderr)
        return 2
    state = json.loads(read_text(state_path))
    mermaid_map = Path(args.mermaid_map) if args.mermaid_map else Path(state["mermaid_map"])
    if not mermaid_map.exists():
        print(f"FAIL: 找不到 Mermaid 映射文件：{mermaid_map}", file=sys.stderr)
        return 2
    output = Path(args.output) if args.output else Path(state["final_markdown"])
    apply_args = argparse.Namespace(
        markdown=state["ocr_markdown"],
        manifest=state["manifest"],
        mermaid_map=str(mermaid_map),
        output=str(output),
        allow_missing=args.allow_missing,
    )
    rc = command_apply(apply_args)
    if rc:
        return rc
    state["status"] = "complete_with_mermaid" if not args.allow_missing else "complete_with_allowed_missing"
    state["final_markdown"] = str(output)
    write_text(state_path, json.dumps(state, ensure_ascii=False, indent=2))
    print(f"PASS: 最终 Markdown 已输出：{output}")
    return 0

def validate_markdown(text: str, expected_mermaid_count: Optional[int] = None) -> Tuple[bool, List[str]]:
    messages: List[str] = []
    ok = True
    html_imgs = len(IMG_TAG_RE.findall(text))
    md_imgs = len(MD_IMG_RE.findall(text))
    mermaid = len(MERMAID_FENCE_RE.findall(text))
    fence_count = text.count("```")
    messages.append(f"image_tags={html_imgs + md_imgs} html_img={html_imgs} markdown_img={md_imgs}")
    messages.append(f"mermaid_blocks={mermaid}")
    if expected_mermaid_count is not None:
        messages.append(f"expected_mermaid_blocks={expected_mermaid_count}")
        if mermaid != expected_mermaid_count:
            ok = False
            messages.append("FAIL: Mermaid 代码块数量与预期不一致")
    if html_imgs or md_imgs:
        ok = False
        messages.append("FAIL: 仍有图片引用残留")
    if fence_count % 2:
        ok = False
        messages.append("FAIL: Markdown 代码围栏未闭合")
    if PLACEHOLDER_RE.search(text):
        ok = False
        messages.append("FAIL: 仍有未解决的 Mermaid 占位符")
    if ok:
        messages.append("PASS")
    return ok, messages


def command_validate(args: argparse.Namespace) -> int:
    text = read_text(Path(args.markdown))
    ok, messages = validate_markdown(text, args.expected_mermaid_count)
    for message in messages:
        print(message)
    return 0 if ok else 1


def add_bool_pair(parser: argparse.ArgumentParser, name: str, default: Optional[bool], help_text: str) -> None:
    dest = name.replace("-", "_")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(f"--{name}", dest=dest, action="store_true", help=help_text)
    group.add_argument(f"--no-{name}", dest=dest, action="store_false", help=f"关闭：{help_text}")
    parser.set_defaults(**{dest: default})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="医学指南 OCR 图片转 Mermaid 辅助脚本")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("from-pdf", help="从 PDF 开始运行 PaddleOCR 并准备 VLM 转 Mermaid 工作区")
    p.add_argument("--input", required=True, help="PDF 或图片路径")
    p.add_argument("--work-dir", required=True, help="工作区目录，用于保存 OCR、图片、prompt 和状态文件")
    p.add_argument("--output", help="最终 Markdown 输出路径；默认放在 work-dir 下")
    p.add_argument("--api-url", help="PaddleOCR 版面解析 API URL；也可使用 PADDLEOCR_API_URL")
    p.add_argument("--token", help="PaddleOCR token；也可使用 PADDLEOCR_TOKEN")
    p.add_argument("--file-type", type=int, choices=[0, 1], help="0 表示 PDF，1 表示图片；默认按输入后缀判断")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--context-lines", type=int, default=8)
    p.add_argument("--no-download", action="store_true", help="不下载远程图片 URL")
    p.add_argument("--force", action="store_true", help="允许使用非空工作区并覆盖同名输出文件")
    add_bool_pair(p, "use-doc-orientation", False, "使用文档方向识别")
    add_bool_pair(p, "use-doc-unwarping", False, "使用文档扭曲矫正")
    add_bool_pair(p, "use-layout-detection", True, "使用版面检测")
    add_bool_pair(p, "use-chart-recognition", True, "使用图表识别")
    add_bool_pair(p, "restructure-pages", True, "请求重构多页结果")
    add_bool_pair(p, "merge-tables", True, "在支持时合并跨页表格")
    add_bool_pair(p, "relevel-titles", True, "在支持时恢复段落标题层级")
    add_bool_pair(p, "prettify-markdown", True, "请求更整洁的 Markdown")
    add_bool_pair(p, "visualize", False, "返回可视化图片")
    p.add_argument("--layout-shape-mode", default="auto")
    p.add_argument("--repetition-penalty", type=float, default=1.0)
    p.add_argument("--temperature", type=float, default=0.0)
    p.set_defaults(func=command_from_pdf)

    p = sub.add_parser("finalize", help="根据 VLM 生成的 Mermaid 映射输出最终 Markdown")
    p.add_argument("--work-dir", required=True, help="from-pdf 生成的工作区目录")
    p.add_argument("--output", help="最终 Markdown 输出路径；默认使用 workflow_state.json 中的路径")
    p.add_argument("--mermaid-map", help="Mermaid 映射 JSON；默认使用工作区 figures/mermaid_map.json")
    p.add_argument("--allow-missing", action="store_true", help="允许部分图片未转换；仅在明确需要时使用")
    p.set_defaults(func=command_finalize)

    p = sub.add_parser("paddleocr", help="调用 PaddleOCR-VL 版面解析接口")
    p.add_argument("--input", required=True, help="PDF 或图片路径")
    p.add_argument("--api-url", help="PaddleOCR 版面解析 API URL；也可使用 PADDLEOCR_API_URL")
    p.add_argument("--token", help="PaddleOCR token；也可使用 PADDLEOCR_TOKEN")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--file-type", type=int, choices=[0, 1], help="0 表示 PDF，1 表示图片")
    p.add_argument("--timeout", type=int, default=300)
    add_bool_pair(p, "use-doc-orientation", False, "使用文档方向识别")
    add_bool_pair(p, "use-doc-unwarping", False, "使用文档扭曲矫正")
    add_bool_pair(p, "use-layout-detection", True, "使用版面检测")
    add_bool_pair(p, "use-chart-recognition", True, "使用图表识别")
    add_bool_pair(p, "restructure-pages", True, "请求重构多页结果")
    add_bool_pair(p, "merge-tables", True, "在支持时合并跨页表格")
    add_bool_pair(p, "relevel-titles", True, "在支持时恢复段落标题层级")
    add_bool_pair(p, "prettify-markdown", True, "请求更整洁的 Markdown")
    add_bool_pair(p, "visualize", False, "返回可视化图片")
    p.add_argument("--layout-shape-mode", default="auto")
    p.add_argument("--repetition-penalty", type=float, default=1.0)
    p.add_argument("--temperature", type=float, default=0.0)
    p.set_defaults(func=command_paddleocr)

    p = sub.add_parser("extract", help="从 Markdown 中抽取图片块")
    p.add_argument("--markdown", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--image-root", help="相对图片引用的基准路径；默认使用 Markdown 所在目录")
    p.add_argument("--context-lines", type=int, default=8)
    p.add_argument("--no-download", action="store_true", help="不下载远程图片 URL")
    p.set_defaults(func=command_extract)

    p = sub.add_parser("apply", help="根据 Mermaid 映射替换图片块")
    p.add_argument("--markdown", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--mermaid-map", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--allow-missing", action="store_true")
    p.set_defaults(func=command_apply)

    p = sub.add_parser("validate", help="验证最终 Markdown")
    p.add_argument("--markdown", required=True)
    p.add_argument("--expected-mermaid-count", type=int)
    p.set_defaults(func=command_validate)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
