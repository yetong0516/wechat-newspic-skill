"""Asset provenance and render freshness. No network or credentials."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def image_refs(data):
    refs = set()
    for card in data.get('cards', []):
        if not isinstance(card, dict):
            continue
        for name in ('image', 'companion_image'):
            if isinstance(card.get(name), str):
                refs.add(card[name])
        for panel in card.get('panels', []):
            if isinstance(panel, dict) and isinstance(panel.get('image'), str):
                refs.add(panel['image'])
    return sorted(refs)


def local_image(draft, ref):
    path = Path(ref)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Image path must stay inside the draft')
    full = (draft / path).resolve()
    full.relative_to(draft.resolve())
    if not full.is_file():
        raise ValueError('Image file is missing')
    return full


def check_sources(draft, data):
    errors = []
    try:
        records = json.loads((draft / 'sources.json').read_text(encoding='utf-8'))['images']
        mapped = {str(Path(r['file']).as_posix()): r for r in records}
        if len(mapped) != len(records):
            errors.append('Duplicate source paths')
        for ref in image_refs(data):
            path = local_image(draft, ref)
            entry = mapped.get(str(Path(ref).as_posix()), {})
            with Image.open(path) as image:
                size = list(image.size)
            if entry.get('sha256') != digest(path.read_bytes()):
                errors.append(f'{ref}: source hash mismatch')
            if size != [entry.get('width'), entry.get('height')]:
                errors.append(f'{ref}: source dimensions mismatch')
            if not all(entry.get(k) for k in ('license', 'credit', 'source_page_url', 'origin_url', 'asset_type', 'retrieval_method')):
                errors.append(f'{ref}: missing source/rights metadata')
    except (OSError, ValueError, KeyError, TypeError):
        errors.append('Invalid source manifest or unsafe/missing image')
    return errors


def input_fingerprint(draft, data):
    payload = {'content': data, 'sources': digest((draft/'sources.json').read_bytes()),
               'images': {r: digest(local_image(draft,r).read_bytes()) for r in image_refs(data)},
               'renderer': {r: digest((ROOT/r).read_bytes()) for r in
                   ('scripts/newspic.py','scripts/screenshot_cards.py','scripts/themes.py','templates/newspic_cards.css')}}
    return digest(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8'))


def write_render_manifest(draft, data):
    write_json(draft / 'render_manifest.json', {
        'input_sha256': input_fingerprint(draft,data),
        'images': {f'newspic-{i:02d}.png': digest((draft/f'newspic-{i:02d}.png').read_bytes())
                   for i in range(1,len(data['cards'])+1)}})


def render_is_current(draft, data):
    try:
        saved = json.loads((draft/'render_manifest.json').read_text(encoding='utf-8'))
        expected = [f'newspic-{i:02d}.png' for i in range(1,len(data['cards'])+1)]
        return (saved['input_sha256'] == input_fingerprint(draft,data)
                and list(saved['images']) == expected
                and all(digest((draft/n).read_bytes()) == saved['images'][n] for n in expected))
    except (ValueError, OSError, KeyError, TypeError):
        return False
