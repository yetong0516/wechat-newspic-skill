#!/usr/bin/env python3
"""Create owned, clearly labeled layout fixtures; never research evidence."""
import argparse
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont
from manifest import digest, write_json
from newspic import FORMAT_CONTRACT


def create(out, pages=3):
    out=Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Destination must be absent or empty; existing work is preserved')
    (out/'images').mkdir(parents=True,exist_ok=True)
    colors=['#344BEE','#8063DF','#087E8B']
    records=[]
    for i in range(1,4):
        image=Image.new('RGB',(1600,1100),'#F0F3FE')
        draw=ImageDraw.Draw(image)
        color=colors[i-1]
        draw.rounded_rectangle((90,110,1510,990),radius=70,fill='white',outline=color,width=12)
        for x,y,r in [(470,480,170),(1080,470,230),(730,740,105)]:
            draw.ellipse((x-r,y-r,x+r,y+r),fill=color,outline='#D8DEFF',width=15)
        draw.line((470,480,1080,470,730,740,470,480),fill='#B5BFEA',width=12)
        try:font=ImageFont.truetype('DejaVuSans.ttf',42)
        except OSError:font=ImageFont.load_default(size=42)
        draw.text((145,155),f'LAYOUT DEMO {i} / NOT RESEARCH DATA',font=font,fill='#15213A')
        name=f'images/layout-{i}.png';path=out/name;image.save(path)
        records.append(dict(file=name,source_page_url='https://github.com/yetong0516/wechat-newspic-skill',
            origin_url='https://github.com/yetong0516/wechat-newspic-skill/blob/main/scripts/create_demo.py',
            credit='AI For Bios / layout demonstration',license='Repository LICENSE (BSL terms); generated layout fixture',
            asset_type='layout_demo',retrieval_method='generated-fixture',sha256=digest(path.read_bytes()),width=1600,height=1100))
    caption=('这是一份公众号贴图的排版演示，三幅几何图都是程序绘制的测试素材，用来检查封面、证据页、收尾页与中文排版。'
             '图中不含实验结果，也不代表任何模型性能。正式制作时，需要换成经过核验并记录来源与许可的真实图片，逐页查看成图后再保存草稿。'
             '\n\n示例：https://github.com/yetong0516/wechat-newspic-skill\n\n#排版演示 #科研传播')
    cards=[dict(role='cover',image='images/layout-1.png',headline='科研公众号贴图\n从材料到七页成图' if pages==7 else '科研公众号贴图\n从材料到三页成图',kicker='LAYOUT DEMO · 排版示例',
        dek='用明确标注的演示素材，检查中文、原图位置与页面顺序。',credit='图1｜几何形状仅用于排版演示')]
    for i in range(2,pages):
        cards.append(dict(role='evidence',image=f'images/layout-{1+(i%3)}.png',headline='每一页解释一个具体问题',stat='1080 × 1440',stat_label='微信贴图的输出像素尺寸',
            note='这里放一条经过原文核对的结果，并在同一页说明对应样本、指标或限制。本页仅为版式演示；图中形状不表示科学数据。',credit=f'图{i}｜不同形状用于检查图片缩放和文字位置'))
    cards.append(dict(role='boundary',image='images/layout-3.png',headline='交稿前，把证据和边界一起检查',claim='正式稿逐项核对关键数字、真实图源、图序和标题承诺，再查看全部页面。',
        limit='这个示例仅验证排版，保存命令会拒绝把它上传到公众号。请用自己的真实材料创建正式稿。',credit=f'图{pages}｜测试素材帮助发现版式问题'))
    write_json(out/'newspic.json',dict(format_contract=FORMAT_CONTRACT,title='科研公众号贴图的排版与交付示例',brand='Research Notes',section='顶刊精读',date='2026-11-21',author='Example Editor',
        demo_only=True,source_url='https://github.com/yetong0516/wechat-newspic-skill',hashtags=['#排版演示','#科研传播'],content=caption,cards=cards))
    write_json(out/'sources.json',dict(topic='Clearly labeled layout demo',images=records))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--pages',type=int,choices=[3,7],default=3)
    args=parser.parse_args();create(args.output,args.pages)
