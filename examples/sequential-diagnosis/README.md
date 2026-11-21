# Science 序列诊断：七页内容与裁图配方

这是实际七页编辑结构的脱敏示例，依据 *Sequential diagnosis with language models*, Science 394, 423–428 (2026), [DOI 10.1126/science.aeh7930](https://www.science.org/doi/10.1126/science.aeh7930)。保留标题、短文案、逐页内容和主文Figure 1–4的裁图坐标。

仓库不包含原PDF、论文图片、最终含论文图的PNG、公众号素材ID、后台快照或交付日志。图片公开转载许可未确认，因此不能从本仓库取得这些图或把代码许可当作图片许可。

自备合法取得的正式发表PDF后，在自己的草稿目录重建：

```bash
mkdir -p drafts
cp -R examples/sequential-diagnosis drafts/sequential-diagnosis
python -m pip install -r requirements-pdf.txt
python scripts/prepare_paper_example.py --pdf /your/local/article.pdf \
  --draft drafts/sequential-diagnosis
python scripts/newspic.py render drafts/sequential-diagnosis
python scripts/newspic.py validate drafts/sequential-diagnosis
```

脚本核对标题、DOI及594×756 pt版面，再在本地裁图、计算哈希并补齐来源记录；不会上传PDF。不同排版或预印本应重新设计裁图，不要套用坐标。未提供PDF前，校验因缺图失败是预期行为。

编辑重点：83.2%/5431美元与79.6%/1303美元对应不同预算配置；304例疑难病例库与56例医生对照子集分别说明；325次急诊入院记录仍为文字模拟。费用为估算值，未验证真实患者结局。文章正文可见图注只说明内容，完整权利信息在sources.json。
