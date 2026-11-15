"""Check tracked publication files without reading or printing local credentials."""
import ast
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True)
paths = [ROOT / name for name in result.stdout.decode().split('\0') if name]
if not paths:
    raise SystemExit('Stage the intended public files before checking.')
forbidden = {'.private', 'runtime', 'evidence', 'memory', 'reference', 'profiles', '.venv', 'node_modules'}
binary = {'.wav', '.mp3', '.mp4', '.png', '.jpg', '.onnx', '.pth', '.ckpt', '.moc3', '.zip', '.img', '.pem', '.key', '.npz', '.bin'}
patterns = [re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
            re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{24,})\b')]
errors = []
for p in paths:
    relative = p.relative_to(ROOT)
    if forbidden.intersection(relative.parts) or p.suffix.lower() in binary or p.stat().st_size > 2_000_000:
        errors.append(str(relative) + ': excluded file category/size')
        continue
    text = p.read_text(encoding='utf-8')
    if any(pattern.search(text) for pattern in patterns):
        errors.append(str(relative) + ': credential-shaped text')
    if p.suffix == '.py':
        ast.parse(text, filename=str(relative))
    # Preserve third-party notices verbatim; their relative links target upstream.
    if p.suffix == '.md' and 'character-licenses' not in p.parts:
        for link in re.findall(r'\]\(([^)]+)\)', text):
            if '://' in link or link.startswith('#') or link.startswith('mailto:'):
                continue
            target = link.split('#')[0]
            if target and not (p.parent / target).exists():
                errors.append(str(relative) + ': missing relative link ' + target)
if errors:
    raise SystemExit('\n'.join(errors))
print(f'Public tree: {len(paths)} tracked files; category, syntax, link and token-pattern checks passed.')
