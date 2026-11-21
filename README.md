# WeChat Newspic Skill

把论文或已核验资讯做成 **3–20 页公众号贴图（1080×1440）**，并将获授权的内容保存到微信草稿箱、完成回读。来自 **AI For Bios** 的实际编辑流程，包含可安装技能、独立 Python 工具、模板、离线测试和示例。

![七页排版演示](assets/previews/demo-seven.jpg)

> 上图为明确标注的几何排版素材，不是实验数据。可运行示例默认禁止上传。

## 包含什么

| 内容 | 入口 |
| --- | --- |
| 可安装的智能体技能 | [SKILL.md](SKILL.md) |
| 内容、来源与图片合同 | [content-contract.md](references/content-contract.md) |
| JSON → HTML → 按顺序编号的 PNG | `scripts/newspic.py` |
| 查重、更新保护、草稿保存、完整回读 | `scripts/wechat_draft.py` |
| 三页 / 七页本地可运行示例 | [examples/demo](examples/demo)、[examples/demo-seven](examples/demo-seven) |
| Science 序列诊断七页内容与裁图配方 | [examples/sequential-diagnosis](examples/sequential-diagnosis) |

图片来源、许可、哈希和尺寸逐图记录；渲染清单绑定内容与最终PNG。草稿交付使用UTF-8、完整分页查重、按账号分开的图片缓存、更新前后台快照检查和写后原字节核验。**仅存草稿，不发布、不群发、不删除。**

## 快速运行

需要 Python 3.9+。Linux 建议安装 Noto CJK 字体；macOS 使用系统中文字体。

```bash
git clone https://github.com/yetong0516/wechat-newspic-skill.git
cd wechat-newspic-skill
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium

python scripts/newspic.py render examples/demo
python scripts/newspic.py render examples/demo-seven
python scripts/newspic.py validate examples/demo-seven
python scripts/wechat_draft.py plan examples/demo-seven
```

用浏览器打开示例中的 `newspic.html`，或查看 `newspic-01.png` 起的文件。上述命令无需微信账号，`plan` 的网络请求数为0。更换素材或文字后重新渲染；旧图片不会因JSON已改而被误认为最新。

新建自己的排版练习：

```bash
python scripts/create_demo.py output/my-demo --pages 7
```

演示稿有 `demo_only: true`，保存命令会拒绝上传。正式稿应另放在默认被Git忽略的 `drafts/` 下，填写真实来源、授权状态、品牌及作者，经过事实和图片审阅后再使用交付命令。

## 作为技能使用

本仓库根目录就是一个完整技能包。将它复制或链接到所用智能体的技能目录，并命名为 `wechat-newspic`。例如，本机使用标准 Codex 技能目录时可创建符号链接：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$PWD" "${CODEX_HOME:-$HOME/.codex}/skills/wechat-newspic"
```

如果该路径已有技能，先检查现有内容，不要覆盖。示例请求：

> 用 `$wechat-newspic` 根据这篇论文做一组公众号贴图，保留实验设置和关键限制。

> 把已审核的这组贴图保存到我的公众号草稿箱，完成查重和回读；不要发布。

## 保存到公众号草稿箱

先阅读 [交付与故障恢复](references/wechat-delivery.md)。凭证来自环境变量 `WECHAT_APP_ID` / `WECHAT_APP_SECRET`，或仓库外的私有配置文件；不放在提示词、代码或示例里。

```bash
python scripts/wechat_draft.py inspect drafts/my-post
# 完成本地审阅，并确认已有本次账号与稿件的保存授权后：
python scripts/wechat_draft.py save drafts/my-post --confirm-draft-save
python scripts/wechat_draft.py verify drafts/my-post
```

已有稿使用 `--update EXISTING_MEDIA_ID --snapshot drafts/my-post/.wechat/snapshot.json`；先把用户后台修改合入本地。后台版本在上传期间变化时，脚本停止更新。若保存响应丢失，先 `inspect` 恢复同一ID再 `verify`，不直接重复创建。

所有私有运行记录写入被Git忽略的 `.wechat/`。40164时只报告微信返回的IP；工具不会改动系统代理、VPN或网络设置。`--direct` 只影响本次Python进程是否采用环境代理。

## 示例的来源边界

- 三页和七页演示中的几何素材由本仓库脚本生成，明确标注为排版测试，随仓库许可分发。
- Science示例保留编辑文字、论文链接、裁图坐标和数据口径。**PDF、论文图片、真实公众号ID和后台记录均不随仓库分发。** 自备合法PDF可在本地复现，代码许可不授予论文图片的转载权。
- 本次抽取的独立草稿工具通过离线API模拟验证；测试不使用真实账号。它继承的原产线流程已用于七页草稿保存和完整回读。详见 [来源与范围](docs/provenance.json)。

## 验证

```bash
python -m unittest discover -s tests -v
python scripts/check_public_export.py
```

测试覆盖重复稿、分页、中文编码、并发编辑、上传中断、保存响应丢失、只读恢复、作者字段缺失与远端图片不一致。GitHub Actions还实际渲染三页与七页示例。测试和演示不调用微信接口。

## 许可与归属

本仓库沿用上游 [BSL 1.1 条款](LICENSE)，属于公开源码（source-available），**不是无商用限制的MIT项目**。学习、评估和约定的非商业用途按LICENSE执行；商业使用需要另行许可。图片、论文和第三方依赖按各自条款，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

BioSpark · AI For Bios

Based on BioSpark WeChat OA Automation Pipeline

Copyright (c) 2026 BioSpark / AI For Bios

Licensed under BSL 1.1

https://github.com/yetong0516/BioSpark_AI-For-Bios_WeChat-OA-Automation-Pipeline
