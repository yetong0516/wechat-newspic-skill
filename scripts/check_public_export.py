#!/usr/bin/env python3
"""Scan tracked/staged release files; report paths and rule names, never matched secrets."""
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
RULES={
    'personal_absolute_path':re.compile('/'+'Users'+r'/[^\s\"\']+|[A-Z]:\\'+'Users'+r'\\'),
    'wechat_app_id':re.compile(r'\bwx[0-9a-f]{16}\b'),
    'wechat_real_media_id':re.compile(r'\bYCHNZp[0-9A-Za-z_-]{20,}\b'),
    'github_token':re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}'),
    'private_key':re.compile('-----BEGIN '+'(?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'authenticated_url':re.compile(r'https?://[^\s\"\']+[?&](?:access_token|appsecret|secret)=[^\s\"\']+'),
    'assigned_secret':re.compile(r'(?i)[\"\'](?:app_?secret|api_?key|access_?token)[\"\']\s*:\s*[\"\'][A-Za-z0-9_-]{24,}[\"\']'),
}


def scan(paths):
    findings=[]
    for path in paths:
        rel=path.relative_to(ROOT)
        if (set(rel.parts)&{'.wechat','secrets','.venv','private'} or path.suffix.lower() in {'.pdf','.pem','.key'}
                or path.name.startswith('credentials') or path.name.startswith('wechat_') and path.suffix=='.json'):
            findings.append((str(rel),'private_or_restricted_file'))
        if path.stat().st_size>5*1024*1024:
            findings.append((str(rel),'oversized_release_file'))
        if path.suffix.lower() in {'.png','.jpg','.jpeg'}:
            if not (str(rel).startswith('assets/previews/') or str(rel).startswith('examples/demo')
                    or str(rel) in {'assets/brand/ai-for-bios-mark.png', 'assets/brand/ai-for-bios-horizontal-light.png', 'assets/brand/ai-for-bios-horizontal-dark.png'}):
                findings.append((str(rel),'unreviewed_binary_asset'))
            continue
        try:text=path.read_text(encoding='utf-8')
        except UnicodeError:
            findings.append((str(rel),'unreviewed_binary_file'));continue
        for name,pattern in RULES.items():
            if pattern.search(text):findings.append((str(rel),name))
    return findings


if __name__=='__main__':
    result=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True,check=True)
    paths=[ROOT/p for p in result.stdout.decode().split('\0') if p]
    if not paths:raise SystemExit('No staged/tracked release files; refusing an empty scan')
    issues=scan(paths)
    for path,rule in issues:print(f'{path}: {rule}')
    print(f'Scanned {len(paths)} public files; findings: {len(issues)}')
    sys.exit(bool(issues))
