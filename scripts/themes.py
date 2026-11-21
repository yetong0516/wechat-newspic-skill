"""Theme tokens derived from the BioSpark pipeline (see LICENSE)."""
THEMES = {
    "aqua":   {"accent": "#4ecdc4", "accent_rgb": "78,205,196", "accent_text": "#16a394",
               "tint_bg": "#f0fbfa", "tint_bg2": "#f4fbfa",
               "border": "#e0f3f1", "border2": "#cfeae6", "hl_bg": "#c7f0eb"},
    "indigo": {"accent": "#6366f1", "accent_rgb": "99,102,241", "accent_text": "#4f46e5",
               "tint_bg": "#f0f1fe", "tint_bg2": "#f4f4fe",
               "border": "#dfe0fb", "border2": "#cdcef6", "hl_bg": "#dcdefb"},
    "orange": {"accent": "#ec7a26", "accent_rgb": "236,122,38", "accent_text": "#cf6411",
               "tint_bg": "#fef3ea", "tint_bg2": "#fff6f0",
               "border": "#f7ddc4", "border2": "#f2cba6", "hl_bg": "#fde2c4"},
    "blue":   {"accent": "#2563eb", "accent_rgb": "37,99,235", "accent_text": "#1d4ed8",
               "tint_bg": "#eef3fd", "tint_bg2": "#f3f7fe",
               "border": "#d3e0fb", "border2": "#b9d0f8", "hl_bg": "#cddffb"},
}

# 板块 → 主题（公众号各板块固定一个主题色）
SECTION_THEME = {
    "前沿科创": "aqua",
    "顶刊精读": "orange",
    "人物专访": "indigo",
    "工具介绍": "blue",
}

ROLES = ["accent", "accent_rgb", "accent_text", "tint_bg", "tint_bg2", "border", "border2", "hl_bg"]
DEFAULT_FILES = ["gongzhonghao.html", "gongzhonghao_preview.html", "cover_gzh.html"]

def apply_theme(text: str, target: str) -> tuple:
    """把 text 里任何已知主题的色值，按角色替换为 target 主题的色值。返回 (新文本, 替换次数)。"""
    tgt = THEMES[target]
    n = 0
    for role in ROLES:
        tv = tgt[role]
        for name, theme in THEMES.items():
            sv = theme[role]
            if sv == tv:
                continue
            # hex 大小写都换
            for variant in {sv, sv.lower(), sv.upper()}:
                cnt = text.count(variant)
                if cnt:
                    text = text.replace(variant, tv)
                    n += cnt
    return text, n
