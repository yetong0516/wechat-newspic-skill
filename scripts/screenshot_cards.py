#!/usr/bin/env python3
"""screenshot_cards.py — 将卡片 HTML 截图为 PNG（默认 1080x1440 @2x，小红书）。

也可用于公众号封面（900x383）等其它尺寸：用 --width/--height 指定视口，
用 --name 指定输出文件前缀。

用法:
    # 小红书 6 卡片（默认尺寸，行为与旧版完全一致）
    python3 screenshot_cards.py <html_file> [--out DIR] [--scale N]

    # 公众号封面 900x383 @2x → cover_gzh-1.png
    python3 screenshot_cards.py cover_gzh.html --out DIR \
        --width 900 --height 383 --name cover_gzh

输出:
    <name>-1.png, <name>-2.png, ... 到指定目录（默认与 HTML 同目录）
    默认 name=card，即 card-1.png ...
"""

import argparse
import sys
import json
from pathlib import Path


def render_cards(html_path: Path, out_dir: Path, *, width=1080, height=1440,
                 name="card", scale=2, zero_pad=1):
    """渲染 HTML 中的 .card 元素，返回输出路径列表。"""
    html_path = Path(html_path).resolve()
    out_dir = Path(out_dir).resolve()
    if not html_path.exists():
        raise FileNotFoundError(f"文件不存在: {html_path}")
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "需要安装 playwright (pip install playwright && playwright install chromium)"
        ) from exc

    outputs = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=scale,
        )
        page.goto(html_path.as_uri(), wait_until="networkidle")
        page.evaluate('document.fonts.ready')
        page.wait_for_function("Array.from(document.images).every(i => i.complete && i.naturalWidth > 0)")
        layout = page.evaluate("""() => Array.from(document.querySelectorAll('.card')).map((card,i) => {
          const r=card.getBoundingClientRect();
          const overflow=Array.from(card.querySelectorAll('h1,h2,p,figcaption,header,footer,.multi-stat')).filter(el => {
            const b=el.getBoundingClientRect(); return b.left<r.left-1 || b.right>r.right+1 || b.top<r.top-1 || b.bottom>r.bottom+1;
          }).map(el=>el.tagName);
          return {page:i+1,overflow};
        })""")
        (out_dir / 'layout_report.json').write_text(json.dumps(layout,indent=2),encoding='utf-8')
        if any(item['overflow'] for item in layout):
            browser.close()
            raise RuntimeError('Text extends outside a card; shorten copy or adjust layout')
        cards = page.query_selector_all(".card")
        if not cards:
            browser.close()
            raise RuntimeError("未找到 .card 元素")
        for index, card in enumerate(cards, 1):
            suffix = str(index).zfill(zero_pad)
            path = out_dir / f"{name}-{suffix}.png"
            card.screenshot(path=str(path))
            outputs.append(path)
        browser.close()

    from PIL import Image
    expected = (width * scale, height * scale)
    for path in outputs:
        with Image.open(path) as image:
            actual = image.size
        if actual != expected:
            raise RuntimeError(f"{path.name} 尺寸 {actual[0]}x{actual[1]}, 预期 {expected[0]}x{expected[1]}")
    return outputs


def main():
    ap = argparse.ArgumentParser(description="卡片 HTML → PNG 截图")
    ap.add_argument("html", help="卡片 HTML 文件路径")
    ap.add_argument("--out", default=None, help="输出目录（默认与 HTML 同目录）")
    ap.add_argument("--scale", type=int, default=2, help="设备缩放因子（默认 2）")
    ap.add_argument("--width", type=int, default=1080, help="视口宽度（默认 1080）")
    ap.add_argument("--height", type=int, default=1440, help="视口高度（默认 1440）")
    ap.add_argument("--name", default="card", help="输出文件前缀（默认 card → card-1.png）")
    ap.add_argument("--zero-pad", type=int, default=1,
                    help="序号补零位数（默认 1；贴图使用 2）")
    args = ap.parse_args()

    html_path = Path(args.html).resolve()
    if not html_path.exists():
        print(f"错误: 文件不存在: {html_path}", file=sys.stderr)
        return 1

    out_dir = Path(args.out) if args.out else html_path.parent
    try:
        outputs = render_cards(
            html_path,
            out_dir,
            width=args.width,
            height=args.height,
            name=args.name,
            scale=args.scale,
            zero_pad=args.zero_pad,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    print(f"找到 {len(outputs)} 张卡片")
    for path in outputs:
        print(f"  {path.name} ({path.stat().st_size // 1024} KB)")
    print(f"\n完成: {len(outputs)} 张卡片 → {Path(out_dir).resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
