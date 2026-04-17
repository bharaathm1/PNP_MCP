"""Show section-by-section size breakdown of prompt files to identify bloat."""
from pathlib import Path

for fpath in [
    r'c:\pnp_mcp\.github\agents\power_socwatch_analysis.agent.md',
    r'c:\pnp_mcp\src\prompts\power_socwatch_prompt.txt',
]:
    text = Path(fpath).read_text(encoding='utf-8')
    lines = text.split('\n')
    print(f'\n=== {Path(fpath).name} ({len(text):,} chars  ~{len(text)//4:,} tok) ===')
    current = 'preamble'; start = 0
    sections = []
    for i, line in enumerate(lines):
        if line.startswith('## ') or line.startswith('# '):
            sections.append((current, start, i))
            current = line.strip()
            start = i
    sections.append((current, start, len(lines)))
    for name, s, e in sections:
        chunk = '\n'.join(lines[s:e])
        print(f'  {len(chunk):>6,} chars   {name[:75]}')
