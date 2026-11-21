# Content and asset contract

`newspic.json` is the ordered content source. See the runnable [demo](../examples/demo/newspic.json) and the [Science paper recipe](../examples/sequential-diagnosis/newspic.json).

| Field | Meaning |
| --- | --- |
| `format_contract` | `wechat-newspic-v1` |
| `title` | 12–24 visible characters |
| `brand`, `author` | Visible masthead and submitted author; author is mandatory for saving |
| `section` | 前沿科创 / 顶刊精读 / 人物专访 / 工具介绍 |
| `date` | Editorial card date, not a fabricated publication date |
| `source_url` | Primary source URL, also included in `content` |
| `topic_keywords` | Optional distinctive title aliases for duplicate detection |
| `content`, `hashtags` | 80–180 Chinese characters, at most 2 KB UTF-8, 2–4 hashtags |
| `demo_only` | True for layout fixtures; upload is blocked |
| `need_open_comment`, `only_fans_can_comment` | 0/1; existing backend settings are preserved on update |
| `cards` | 3–20 objects in order: cover, evidence(s), boundary |

Cover fields: `image`, `headline`, `kicker`, `credit`; optional `dek`. Evidence: `image`, `headline`, `stat`, `stat_label`, `note`, `credit`. Boundary: `image`, `headline`, `claim`, `limit`, `credit`. The last two fields become natural paragraphs rather than canned “did/did not prove” badges.

All pages need a local image. Optional `companion_image` gives a second panel. `panels` with `panel_layout` supports `grid-2`/`grid-3` (six panels) or `lead-left`/`lead-top` (three panels). Each panel uses `image`, optional `label`, `fit` (`contain`/`cover`) and `position` (`center`/`top`/`bottom`). Keep panel order, scales and labels faithful to the original. Review crops visually.

`sources.json.images` maps exact relative paths to records, not basenames. Each used image needs `file`, `source_page_url`, `origin_url`, `asset_type`, `retrieval_method`, `credit`, `license`, `sha256`, `width`, `height`. The validator compares bytes and dimensions. Symlinks escaping the draft and parent traversal are rejected.

For a PDF crop, add the original PDF hash, one-based page, `crop_box_points` in top-left page coordinates, render scale and description of changes. Keep download-original, webpage screenshot and PDF crop distinct. Public availability alone is not a reuse license.

Use explicit source uncertainty, short paragraphs and a concrete ending. Keep a claim ledger for numbers and comparisons. Do not combine a high-accuracy configuration with a different low-cost configuration. Do not describe a physician subset as testing the entire AI dataset.

`render_manifest.json` binds the JSON, source manifest, original images, renderer and template to the final PNG hashes. Any content or asset change requires rendering again. `layout_report.json` checks canvas bounds, but visual review remains necessary.
