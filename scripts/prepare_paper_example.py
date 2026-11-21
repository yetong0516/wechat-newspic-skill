#!/usr/bin/env python3
"""Render a local, lawfully obtained Science PDF for the source-only example."""
import argparse
import json
from pathlib import Path
import pypdfium2 as pdfium
from manifest import digest, write_json


def prepare(pdf_path, draft):
    pdf_path=Path(pdf_path);draft=Path(draft)
    doc=pdfium.PdfDocument(pdf_path)
    if len(doc) not in (6,7):
        raise ValueError('Expected the 6–7 page Science article, not a preprint or supplement')
    text=doc[0].get_textpage().get_text_range()+doc[len(doc)-1].get_textpage().get_text_range()
    if 'Sequential diagnosis' not in text or 'aeh7930' not in text:
        raise ValueError('PDF title/DOI does not match this example')
    sources=json.loads((draft/'sources.json').read_text(encoding='utf-8'))
    source_hash=digest(pdf_path.read_bytes())
    for record in sources['images']:
        page=doc[record['page']-1]
        width,height=page.get_size()
        if abs(width-594)>1 or abs(height-756)>1:
            raise ValueError('Page geometry differs; review crop coordinates before rendering')
        x0,y0,x1,y1=record['crop_box_points']
        bitmap=page.render(scale=4,crop=(x0,height-y1,width-x1,y0))
        image=bitmap.to_pil()
        target=draft/record['file'];target.parent.mkdir(parents=True,exist_ok=True)
        image.save(target)
        record.update(sha256=digest(target.read_bytes()),width=image.width,height=image.height,
                      source_pdf_sha256=source_hash,retrieval_method='pdf-render-crop',
                      source_pdf='User-provided local copy; not redistributed')
        bitmap.close();page.close()
    doc.close()
    write_json(draft/'sources.json',sources)
    print('Prepared source images locally. This does not grant republication rights or upload anything.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',required=True,type=Path)
    parser.add_argument('--draft',default=Path(__file__).resolve().parents[1]/'examples/sequential-diagnosis',type=Path)
    args=parser.parse_args();prepare(args.pdf,args.draft)
