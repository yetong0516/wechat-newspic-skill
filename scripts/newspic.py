#!/usr/bin/env python3
"""BioSpark 微信贴图（newspic）确定性渲染与校验。

newspic.json 是唯一内容源；样式由 templates/newspic_cards.css 固定。
每篇 3–20 张 1080x1440：事件封面、按题材展开的证据页、收尾。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from themes import SECTION_THEME, apply_theme
from screenshot_cards import render_cards


FORMAT_CONTRACT = "wechat-newspic-v1"
MASTHEAD = "AI For Bios"
MIN_CARDS = 3
MAX_CARDS = 20
PANEL_COUNTS = {"grid-2": 6, "grid-3": 6, "lead-left": 3, "lead-top": 3}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
CANVAS_SIZE = (1080, 1440)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSS_PATH = PROJECT_ROOT / "templates" / "newspic_cards.css"


class NewspicError(RuntimeError):
    pass


def output_files(data: dict) -> tuple[str, ...]:
    return tuple(f"newspic-{index:02d}.png" for index in range(1, len(data["cards"]) + 1))


def _add(checks: list[dict], name: str, ok: bool, detail: str = ""):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def _is_http_url(value) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _cn_count(value: str) -> int:
    return len(re.findall(r"[一-鿿]", value or ""))


def _visible_count(value: str) -> int:
    return len(re.sub(r"\s+", "", value or ""))


def _safe_local_path(draft: Path, ref: str) -> Path | None:
    if not isinstance(ref, str) or not ref.strip():
        return None
    path = Path(ref)
    if path.is_absolute() or ".." in path.parts:
        return None
    resolved = (draft / path).resolve()
    try:
        resolved.relative_to(draft.resolve())
    except ValueError:
        return None
    return resolved


def load_newspic(draft: Path) -> dict:
    path = Path(draft) / "newspic.json"
    if not path.exists():
        raise NewspicError(f"缺文件: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise NewspicError(f"newspic.json 不是合法 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise NewspicError("newspic.json 顶层必须是对象")
    return data


def _load_sources(draft: Path) -> tuple[dict, str | None]:
    path = draft / "sources.json"
    if not path.exists():
        return {}, "缺 sources.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, f"sources.json 不是合法 JSON: {exc}"
    images = data.get("images")
    if not isinstance(images, list):
        return {}, "sources.json.images 不是列表"
    mapped = {}
    for item in images:
        if isinstance(item, dict) and item.get("file"):
            mapped[str(Path(str(item["file"])).as_posix())] = item
    return mapped, None


def validate_newspic(draft: Path, data: dict | None = None, *, require_rendered=True) -> dict:
    draft = Path(draft).resolve()
    checks: list[dict] = []
    warnings: list[dict] = []
    try:
        data = data or load_newspic(draft)
    except NewspicError as exc:
        return {"draft": str(draft), "passed": False,
                "checks": [{"name": "newspic.json 存在且可解析", "ok": False, "detail": str(exc)}],
                "warnings": []}

    _add(checks, "贴图合同版本正确", data.get("format_contract") == FORMAT_CONTRACT,
         str(data.get("format_contract") or "缺失"))
    section = data.get("section")
    _add(checks, "板块可识别", section in SECTION_THEME, str(section or "缺失"))

    title = str(data.get("title") or "").strip()
    title_count = _visible_count(title)
    _add(checks, "微信标题 12-24 字符", 12 <= title_count <= 24, f"{title_count} 字符")

    content = str(data.get("content") or "").strip()
    cn_count = _cn_count(content)
    content_bytes = len(content.encode("utf-8"))
    _add(checks, "发布文案简洁（80-180 个汉字）", 80 <= cn_count <= 180, f"{cn_count} 个汉字")
    _add(checks, "发布文案不超过 2KB", content_bytes <= 2048, f"{content_bytes} bytes")
    source_url = data.get("source_url")
    _add(checks, "原文链接可用且出现在文案中",
         _is_http_url(source_url) and str(source_url) in content, str(source_url or "缺失"))
    hashtags = data.get("hashtags")
    tags_ok = (
        isinstance(hashtags, list)
        and 2 <= len(hashtags) <= 4
        and all(isinstance(tag, str) and tag.startswith("#") and tag in content for tag in hashtags)
    )
    _add(checks, "文案含 2-4 个标签", tags_ok, str(hashtags or []))
    comment_values = (data.get("need_open_comment", 1), data.get("only_fans_can_comment", 0))
    _add(checks, "留言开关只能为 0/1", all(value in (0, 1) for value in comment_values), str(comment_values))

    cards = data.get("cards")
    roles = [card.get("role") for card in cards] if isinstance(cards, list) and all(isinstance(card, dict) for card in cards) else []
    roles_ok = (
        MIN_CARDS <= len(roles) <= MAX_CARDS
        and roles[0] == "cover"
        and roles[-1] == "boundary"
        and all(role == "evidence" for role in roles[1:-1])
    )
    _add(checks, "3–20 张，首张 cover，中间 evidence，末张 boundary", roles_ok, str(roles))
    sources, source_error = _load_sources(draft)
    _add(checks, "sources.json 可用", source_error is None, source_error or f"{len(sources)} 张图")

    card_issues = []
    if isinstance(cards, list):
        required = {
            "cover": ("image", "headline", "kicker", "credit"),
            "evidence": ("image", "headline", "stat", "stat_label", "note", "credit"),
            "boundary": ("image", "headline", "claim", "limit", "credit"),
        }
        density_limits = {
            "cover": {"headline": (12, 22), "kicker": (3, 42)},
            "evidence": {"headline": (4, 18), "stat": (1, 12), "stat_label": (4, 28), "note": (8, 44)},
            "boundary": {"headline": (6, 22), "claim": (8, 38), "limit": (8, 38)},
        }
        if len(cards) >= MIN_CARDS:
            density_limits = {
                "cover": {"headline": (12, 30), "kicker": (3, 42)},
                "evidence": {"headline": (4, 30), "stat": (1, 16), "stat_label": (4, 42), "note": (8, 105)},
                "boundary": {"headline": (6, 30), "claim": (8, 84), "limit": (8, 84)},
            }
        for index, card in enumerate(cards, 1):
            if not isinstance(card, dict):
                card_issues.append(f"图{index}不是对象")
                continue
            role = card.get("role")
            for field in required.get(role, ()):
                if not str(card.get(field) or "").strip():
                    card_issues.append(f"图{index}缺 {field}")
            for field, (minimum, maximum) in density_limits.get(role, {}).items():
                count = _visible_count(str(card.get(field) or ""))
                if not minimum <= count <= maximum:
                    card_issues.append(f"图{index}.{field}={count}，应为 {minimum}-{maximum}")
            image_refs = [card.get("image")]
            if card.get("companion_image"):
                image_refs.append(card["companion_image"])
            if "panels" in card:
                panels = card["panels"]
                layout = card.get("panel_layout")
                if (role == "cover" or
                        not isinstance(layout, str) or layout not in PANEL_COUNTS or not isinstance(panels, list) or
                        len(panels) != PANEL_COUNTS[layout]):
                    card_issues.append(f"图{index}组合图版式与数量不匹配")
                else:
                    for panel in panels:
                        if not isinstance(panel, dict):
                            card_issues.append(f"图{index}组合图条目必须是对象")
                            continue
                        image_refs.append(panel.get("image"))
                        if panel.get("fit", "contain") not in ("contain", "cover"):
                            card_issues.append(f"图{index}组合图 fit 无效")
                        if panel.get("position", "center") not in ("center", "top", "bottom"):
                            card_issues.append(f"图{index}组合图对齐方式无效")
            for image_ref in image_refs:
                image_path = _safe_local_path(draft, image_ref)
                if not image_path or not image_path.is_file():
                    card_issues.append(f"图{index}缺真实视觉文件: {image_ref}")
                elif image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                    card_issues.append(f"图{index}图片格式不支持: {image_path.suffix}")
                source = sources.get(str(Path(image_ref).as_posix())) if image_path else None
                if not source:
                    card_issues.append(f"图{index}未映射到 sources.json: {image_ref}")
                elif not source.get("origin_url") or not source.get("credit") or not source.get("license"):
                    card_issues.append(f"图{index}来源缺 origin_url/credit/license")
            focal = card.get("focal_point", {"x": 0.5, "y": 0.5})
            if not (
                isinstance(focal, dict)
                and isinstance(focal.get("x"), (int, float))
                and isinstance(focal.get("y"), (int, float))
                and 0 <= focal["x"] <= 1
                and 0 <= focal["y"] <= 1
            ):
                card_issues.append(f"图{index}.focal_point 必须为 0-1 坐标")
            if role == "evidence" and card.get("image_fit", "contain") not in {"contain", "cover"}:
                card_issues.append(f"图{index}.image_fit 只能为 contain/cover")
            if _visible_count(str(card.get("credit") or "")) > 90:
                card_issues.append(f"图{index}.credit 超过 90 字符")
    _add(checks, "每张都有真实视觉主体、简短文字与溯源", not card_issues, "、".join(card_issues))

    from manifest import check_sources
    problems = check_sources(draft, data)
    _add(checks, "图片来源哈希、尺寸与许可记录一致", not problems, "、".join(problems))
    if require_rendered:
        rendered_issues = []
        hashes = []
        try:
            from PIL import Image
            import hashlib
            names = output_files(data) if roles_ok else ()
            for name in names:
                path = draft / name
                if not path.is_file():
                    rendered_issues.append(f"缺 {name}")
                    continue
                if path.stat().st_size > MAX_IMAGE_BYTES:
                    rendered_issues.append(f"{name} 超过 10MB")
                with Image.open(path) as image:
                    if image.size != CANVAS_SIZE:
                        rendered_issues.append(f"{name}={image.size[0]}x{image.size[1]}")
                    if image.format not in {"PNG", "JPEG"}:
                        rendered_issues.append(f"{name} 格式={image.format}")
                hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
        except ImportError:
            rendered_issues.append("未安装 Pillow")
        except OSError as exc:
            rendered_issues.append(f"贴图无法读取: {exc}")
        if hashes and len(hashes) != len(set(hashes)):
            rendered_issues.append("输出存在重复图片")
        _add(checks, "输出为不重复的 1080x1440 PNG/JPEG，单张不超过 10MB",
             roles_ok and not rendered_issues and len(hashes) == len(roles), "、".join(rendered_issues))

    if require_rendered:
        from manifest import render_is_current
        _add(checks, "渲染产物与当前内容、模板和原图一致", render_is_current(draft, data))
    return {"draft": str(draft), "passed": all(item["ok"] for item in checks),
            "checks": checks, "warnings": warnings}


def _lines(value: str) -> str:
    return "<br>".join(html.escape(part) for part in str(value).splitlines())


def _position(card: dict) -> str:
    focal = card.get("focal_point") or {"x": 0.5, "y": 0.5}
    return f"{float(focal['x']) * 100:.1f}% {float(focal['y']) * 100:.1f}%"


def _card_image(card: dict) -> str:
    return html.escape(str(card["image"]), quote=True)


def _multi_card(card: dict, index: int, total: int, brand: str, section: str, date: str) -> str:
    page = f"{index:02d} / {total:02d}"
    headline = _lines(card["headline"])
    credit = _lines(card["credit"])
    if card["role"] == "cover":
        return f"""<section class="card multi-cover">
  <img class="media" src="{_card_image(card)}" style="object-position:{_position(card)}" alt="">
  <div class="multi-shade"></div>
  <header class="multi-cover-head"><b>{brand}</b><span>{section} · {date}</span></header>
  <div class="multi-cover-copy"><div class="multi-kicker">{_lines(card['kicker'])}</div>
    <h1>{headline}</h1><p>{_lines(card.get('dek', ''))}</p>
  </div>
  <footer class="multi-cover-foot"><span>{credit}</span><b>{page}</b></footer>
</section>"""

    def visual(panel: dict) -> str:
        style = f'object-fit:{panel.get("fit", "contain")};object-position:{panel.get("position", "center")}'
        return (f'<div class="multi-frame"><img src="{html.escape(panel["image"], quote=True)}" '
                f'style="{html.escape(style, quote=True)}" alt="">'
                f'<div class="multi-frame-label">{_lines(panel.get("label", ""))}</div></div>')

    layout_class = ""
    if "panels" in card:
        panels = card["panels"]
        layout_class = f' multi-panels panel-{card["panel_layout"]}'
    else:
        panels = [{"image": card["image"], "label": card.get("image_label", "")}]
        if card.get("companion_image"):
            panels.append({"image": card["companion_image"], "label": card.get("companion_label", "")})
    figures = "".join(visual(panel) for panel in panels)
    if card["role"] == "evidence":
        summary = f'<div class="multi-stat"><strong>{_lines(card["stat"])}</strong><span>{_lines(card["stat_label"])}</span></div>'
        copy = f'<p>{_lines(card["note"])}</p>'
    else:
        summary = ""
        copy = f'<p>{_lines(card["claim"])}</p><p class="multi-takeaway">{_lines(card["limit"])}</p>'
    return f"""<section class="card multi-page">
  <header class="multi-head"><b>{brand}</b><span>{section} · {page}</span></header>
  <h2>{headline}</h2>
  {summary}
  <figure class="multi-figure"><div class="multi-images{layout_class}">{figures}</div><figcaption>{credit}</figcaption></figure>
  <div class="multi-copy">{copy}</div>
</section>"""


def build_html(draft: Path, data: dict) -> str:
    css = CSS_PATH.read_text(encoding="utf-8")
    css, _ = apply_theme(css, SECTION_THEME[data["section"]])
    date = html.escape(str(data.get("date") or ""))
    section = html.escape(str(data["section"]))
    brand = html.escape(str(data.get("brand") or MASTHEAD))
    sections = "\n".join(_multi_card(card, index, len(data["cards"]), brand, section, date)
        for index, card in enumerate(data["cards"], 1))
    return f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'><title>{html.escape(data['title'])}</title><style>{css}</style></head><body>{sections}</body></html>"


def preview_payload(data: dict) -> dict:
    return {
        "articles": [{
            "article_type": "newspic",
            "title": data["title"],
            "content": data["content"],
            "need_open_comment": int(data.get("need_open_comment", 1)),
            "only_fans_can_comment": int(data.get("only_fans_can_comment", 0)),
            "image_info": {"image_list": [
                {"local_file": name} for name in output_files(data)
            ]},
            "cover_info": {"crop_percent_list": [
                {"ratio": "1_1", "x1": "0", "y1": "0", "x2": "1", "y2": "0.75"},
                {"ratio": "16_9", "x1": "0", "y1": "0", "x2": "1", "y2": "0.421875"},
                {"ratio": "2.35_1", "x1": "0", "y1": "0.075", "x2": "1", "y2": "0.394149"}
            ]},
        }]
    }


def render_newspic(draft: Path) -> dict:
    draft = Path(draft).resolve()
    data = load_newspic(draft)
    before = validate_newspic(draft, data, require_rendered=False)
    if not before["passed"]:
        raise NewspicError("渲染前校验未通过: " + "; ".join(
            item["name"] + "=" + item["detail"] for item in before["checks"] if not item["ok"]
        ))
    html_path = draft / "newspic.html"
    html_path.write_text(build_html(draft, data), encoding="utf-8")
    outputs = render_cards(
        html_path, draft, width=1080, height=1440, name="newspic", scale=1, zero_pad=2
    )
    preview = preview_payload(data)
    (draft / "newspic_preview_payload.json").write_text(
        json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    from manifest import write_render_manifest
    write_render_manifest(draft, data)
    result = validate_newspic(draft, data, require_rendered=True)
    if not result["passed"]:
        raise NewspicError("渲染后校验未通过")
    return {"html": str(html_path), "images": [str(path) for path in outputs],
            "preview_payload": str(draft / "newspic_preview_payload.json"), "validation": result}


def print_result(result: dict):
    for item in result["checks"]:
        print(f"  {'✅' if item['ok'] else '❌'} {item['name']}" + (f" — {item['detail']}" if item["detail"] else ""))
    print("\n校验通过。" if result["passed"] else "\n❌ 校验未通过。")


def main(argv=None):
    parser = argparse.ArgumentParser(description="BioSpark 微信贴图渲染/校验")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("render", "validate"):
        item = sub.add_parser(command)
        item.add_argument("draft", help="草稿目录（内含 newspic.json）")
        item.add_argument("--json", action="store_true", help="输出 JSON")
        if command == "validate":
            item.add_argument("--no-render", action="store_true", help="只校验内容与原图，不要求已渲染")
    args = parser.parse_args(argv)
    draft = Path(args.draft).resolve()
    try:
        if args.command == "render":
            rendered = render_newspic(draft)
            if args.json:
                print(json.dumps(rendered, ensure_ascii=False, indent=2))
            else:
                print(f"✅ 已渲染 {len(rendered['images'])} 张微信贴图")
                for path in rendered["images"]:
                    print(f"  {path}")
            return 0
        result = validate_newspic(draft, require_rendered=not args.no_render)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print_result(result)
        return 0 if result["passed"] else 1
    except NewspicError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
