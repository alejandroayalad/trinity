#!/usr/bin/env python3
"""Read-only function length and complexity inventory for Trinity.

Usage:
    python trinity_function_audit.py /path/to/trinity --output /tmp/trinity-audit

For exact TypeScript parsing, install frontend dependencies (`cd frontend && npm ci`).
No code in the target repository is modified.
"""
from __future__ import annotations

import argparse
import ast
import csv
import html
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from collections import Counter

EXTENSIONS = {'.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'}
SKIP_DIRS = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 'dist', 'build', '.next', 'coverage', '.pytest_cache'}
FIELDS = ['area', 'file', 'function', 'start', 'end', 'lines', 'cyclomatic', 'nesting', 'score', 'priority', 'language', 'source_url']
REF = '014f3064689ff8f8fda6be264d9bb17c46497989'


def bucket(path: str) -> str:
    p = path.replace('\\', '/')
    if p.startswith('backend/tests/') or p.startswith('frontend/tests/') or '.test.' in p or '.spec.' in p or '/test_' in p:
        return 'Tests'
    if p.startswith('backend/migrations/') or p.startswith('scripts/') or p.startswith('deploy/') or '/src/test/' in p:
        return 'Tools and migrations'
    return 'Production'


def rating(lines: int, cc: int, nesting: int) -> int:
    """Heuristic 1-5 review score; not a prediction of defects.

    A short function with many branches can score high. So can a very long
    function with few branches. Higher nesting also increases review effort.
    """
    if lines <= 25 and cc <= 4 and nesting <= 2:
        return 1
    if lines <= 50 and cc <= 7 and nesting <= 3:
        return 2
    if lines <= 85 and cc <= 12 and nesting <= 4:
        return 3
    if lines <= 130 and cc <= 21 and nesting <= 6:
        return 4
    return 5


def row(path: str, name: str, start: int, end: int, cc: int, nesting: int, lang: str) -> dict:
    lines = end - start + 1
    score = rating(lines, cc, nesting)
    return {
        'area': bucket(path), 'file': path, 'function': name,
        'start': start, 'end': end, 'lines': lines,
        'cyclomatic': cc, 'nesting': nesting, 'score': score,
        'priority': {1:'Low',2:'Low',3:'Medium',4:'High',5:'Very high'}[score],
        'language': lang,
        'source_url': f'https://github.com/alejandroayalad/trinity/blob/{REF}/{path}#L{start}-L{end}',
    }


class PythonMetric(ast.NodeVisitor):
    """Count decisions within one function, not its nested functions."""
    def __init__(self):
        self.cc = 1
        self.nesting = 0
        self.level = 0

    def generic_visit(self, node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            return
        decision = isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler, ast.Assert))
        if isinstance(node, ast.BoolOp):
            self.cc += max(0, len(node.values) - 1)
        if isinstance(node, ast.comprehension):
            self.cc += 1 + len(node.ifs)
        if isinstance(node, ast.match_case):
            decision = not (isinstance(node.pattern, ast.MatchAs) and node.pattern.name is None)
        if decision:
            self.cc += 1
            self.level += 1
            self.nesting = max(self.nesting, self.level)
        super().generic_visit(node)
        if decision:
            self.level -= 1


def python_rows(source: str, filename: str):
    out = []
    try:
        module = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError) as error:
        return out, f'{filename}: {error}'

    def walk(node, chain):
        for item in ast.iter_child_nodes(node):
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = '.'.join([*chain, item.name])
                metric = PythonMetric()
                for statement in item.body:
                    metric.visit(statement)
                out.append(row(filename, name, item.lineno, item.end_lineno or item.lineno, metric.cc, metric.nesting, 'Python'))
                walk(item, [*chain, item.name])
            elif isinstance(item, ast.ClassDef):
                walk(item, [*chain, item.name])
            elif isinstance(item, ast.Lambda):
                metric = PythonMetric()
                metric.visit(item.body)
                out.append(row(filename, '.'.join([*chain, f'<lambda@{item.lineno}>']), item.lineno, item.end_lineno or item.lineno, metric.cc, metric.nesting, 'Python'))
                walk(item, chain)
            else:
                walk(item, chain)

    walk(module, [])
    return out, None


NODE_ANALYZER = r'''
const fs = require('fs');
const path = require('path');
const ts = require(process.argv[2]);
const root = process.argv[3];
const files = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
const output = [];
function functionNode(n) {
  return ts.isFunctionDeclaration(n) || ts.isFunctionExpression(n) ||
    ts.isArrowFunction(n) || ts.isMethodDeclaration(n) ||
    ts.isConstructorDeclaration(n) || ts.isGetAccessorDeclaration(n) ||
    ts.isSetAccessorDeclaration(n);
}
function label(n, sf) {
  if (n.name) return n.name.getText(sf);
  const p = n.parent;
  if (p && (ts.isVariableDeclaration(p) || ts.isPropertyAssignment(p) || ts.isPropertyDeclaration(p)))
    return p.name.getText(sf);
  if (p && ts.isBinaryExpression(p) && p.operatorToken.kind === ts.SyntaxKind.EqualsToken)
    return p.left.getText(sf);
  if (ts.isConstructorDeclaration(n)) return 'constructor';
  return `<callback@${sf.getLineAndCharacterOfPosition(n.getStart(sf)).line+1}>`;
}
function metric(n) {
  let cc = 1, maxDepth = 0;
  function descend(item, depth) {
    if (item !== n && functionNode(item)) return;
    let d = 0;
    if (ts.isIfStatement(item) || ts.isForStatement(item) ||
        ts.isForOfStatement(item) || ts.isForInStatement(item) ||
        ts.isWhileStatement(item) || ts.isDoStatement(item) ||
        ts.isConditionalExpression(item) || ts.isCatchClause(item) ||
        ts.isCaseClause(item) || ts.isDefaultClause(item)) {
      cc++; d = 1;
    }
    if (ts.isBinaryExpression(item) && [ts.SyntaxKind.AmpersandAmpersandToken,
        ts.SyntaxKind.BarBarToken, ts.SyntaxKind.QuestionQuestionToken].includes(item.operatorToken.kind))
      cc++;
    maxDepth = Math.max(maxDepth, depth + d);
    ts.forEachChild(item, child => descend(child, depth + d));
  }
  if (n.body) descend(n.body, 0);
  return {cc, nesting:maxDepth};
}
for (const relative of files) {
  const filename = path.join(root, relative);
  const source = fs.readFileSync(filename, 'utf8');
  const kind = relative.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const sf = ts.createSourceFile(relative, source, ts.ScriptTarget.Latest, true, kind);
  function visit(node, parents) {
    if (functionNode(node) && node.body) {
      const n = label(node, sf);
      const start = sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;
      const end = sf.getLineAndCharacterOfPosition(node.getEnd()-1).line + 1;
      const m = metric(node);
      output.push({file:relative, function:[...parents,n].join('.'), start, end,
         cyclomatic:m.cc, nesting:m.nesting});
      ts.forEachChild(node, child => visit(child, [...parents,n]));
    } else if (ts.isClassDeclaration(node) && node.name) {
      ts.forEachChild(node, child => visit(child, [...parents,node.name.text]));
    } else {
      ts.forEachChild(node, child => visit(child, parents));
    }
  }
  visit(sf, []);
}
process.stdout.write(JSON.stringify(output));
'''


def ts_rows(root: Path, paths: list[str]):
    compiler = root / 'frontend/node_modules/typescript'
    if not compiler.exists():
        return [], 'TypeScript compiler not installed. Run `cd frontend && npm ci` for full JS/TS function coverage.'
    if not shutil.which('node'):
        return [], 'Node.js not found. Install Node.js for JS/TS function coverage.'
    with tempfile.TemporaryDirectory(prefix='trinity-audit-') as td:
        helper = Path(td) / 'analyze.cjs'
        listing = Path(td) / 'files.json'
        helper.write_text(NODE_ANALYZER, encoding='utf-8')
        listing.write_text(json.dumps(paths), encoding='utf-8')
        proc = subprocess.run(['node', str(helper), str(compiler), str(root), str(listing)],
                              capture_output=True, text=True, timeout=120)
    if proc.returncode:
        return [], 'TypeScript analysis failed: ' + proc.stderr.strip()[-800:]
    try:
        records = json.loads(proc.stdout)
    except ValueError as error:
        return [], 'TypeScript analysis JSON error: ' + str(error)
    return [row(x['file'], x['function'], x['start'], x['end'],
                x['cyclomatic'], x['nesting'], 'TypeScript/JavaScript') for x in records], None


def html_report(rows, warnings, directory: Path):
    summary = Counter(x['score'] for x in rows)
    area = Counter(x['area'] for x in rows)
    data = json.dumps(rows, ensure_ascii=False).replace('</', '<\\/')
    banner = f'{len(rows):,} functions | {area["Production"]:,} production | {area["Tests"]:,} tests | {summary[5]:,} with score 5'
    doc = '''<!doctype html><html lang="en"><head><meta charset="utf-8"/>
<title>Trinity function complexity audit</title>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>body{font-family:system-ui,-apple-system,sans-serif;margin:2rem;line-height:1.45;color:#18202b}
h1{margin-bottom:.25rem}.muted{color:#596579}header{margin-bottom:1.5rem}
.controls{display:flex;flex-wrap:wrap;gap:.75rem;margin:1rem 0}input,select{font:inherit;padding:.5rem;border:1px solid #adb5bd;border-radius:6px}
input{min-width:280px;flex:1}table{width:100%;border-collapse:collapse;font-size:13px}th{position:sticky;top:0;background:#1e293b;color:#fff;text-align:left;cursor:pointer}
th,td{padding:8px 10px;border-bottom:1px solid #d6dae1}td.path{max-width:360px;overflow-wrap:anywhere}
tr:hover{background:#f1f5f9}a{color:#1749a1}code{font-size:12px}p.note{max-width:920px}.score{font-weight:700}
.score-5{color:#9c1c1c}.score-4{color:#a35900}.score-3{color:#7b5e00}@media(max-width:800px){body{margin:.5rem}table{font-size:12px}th,td{padding:6px 4px}}</style></head><body>
<header><h1>Trinity function complexity audit</h1><div class="muted">__BANNER__</div>
<p class="note">Complexity uses source syntax trees, counts decision points (cyclomatic estimate), measures nesting, and assigns a 1–5 review score. The score is a prioritization aid, not a defect prediction. Select a row to open the exact source lines. Test functions are counted separately.</p>__WARN__</header>
<div class="controls"><input id="search" placeholder="Search function or file" aria-label="Search function or file">
<select id="area"><option value="">All areas</option><option>Production</option><option>Tests</option><option>Tools and migrations</option></select>
<select id="score"><option value="">All scores</option><option value="5">5 · Very high</option><option value="4">4 · High</option><option value="3">3 · Medium</option><option value="2">2 · Low</option><option value="1">1 · Very low</option></select></div>
<p id="count"></p><table><thead><tr><th data-sort="score">Score ↕</th><th data-sort="lines">Lines ↕</th><th data-sort="cyclomatic">CC ↕</th><th data-sort="nesting">Nesting ↕</th><th data-sort="function">Function ↕</th><th data-sort="file">File ↕</th><th data-sort="area">Area ↕</th></tr></thead><tbody id="rows"></tbody></table>
<script>const data=__DATA__; let sortBy='score',descending=true;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function render(){const q=document.getElementById('search').value.toLowerCase(),a=document.getElementById('area').value,s=document.getElementById('score').value;
let r=data.filter(x=>(!a||x.area===a)&&(!s||String(x.score)===s)&&(!q||(x.file+' '+x.function).toLowerCase().includes(q)));
r.sort((x,y)=>{let p=x[sortBy],z=y[sortBy];let c=typeof p==='number'?p-z:String(p).localeCompare(String(z));return descending?-c:c});
document.getElementById('count').textContent=`Showing ${r.length.toLocaleString()} of ${data.length.toLocaleString()}`;
document.getElementById('rows').innerHTML=r.map(x=>`<tr><td class="score score-${x.score}">${x.score}</td><td>${x.lines}</td><td>${x.cyclomatic}</td><td>${x.nesting}</td><td>${esc(x.function)}</td><td class="path"><a href="${esc(x.source_url)}" target="_blank" rel="noopener">${esc(x.file)}:${x.start}</a></td><td>${esc(x.area)}</td></tr>`).join('');}
['search','area','score'].forEach(id=>document.getElementById(id).addEventListener(id==='search'?'input':'change',render));
document.querySelectorAll('[data-sort]').forEach(x=>x.addEventListener('click',()=>{const k=x.dataset.sort;descending=k===sortBy?!descending:true;sortBy=k;render()}));render();</script></body></html>'''
    doc = doc.replace('__BANNER__', html.escape(banner)).replace('__DATA__', data).replace('__WARN__',
         '<p style="color:#9c1c1c">' + html.escape('; '.join(warnings)) + '</p>' if warnings else '')
    (directory / 'trinity_functions.html').write_text(doc, encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description='Create read-only function inventory and complexity scores.')
    p.add_argument('root', type=Path, help='Path to the Trinity repository root')
    p.add_argument('--output', type=Path, default=Path(tempfile.gettempdir())/'trinity-function-report', help='Output folder (default: system temporary directory)')
    args=p.parse_args()
    root=args.root.expanduser().resolve()
    if not (root/'backend').is_dir() or not (root/'frontend').is_dir():
        p.error(f'{root} does not look like a Trinity checkout (backend and frontend required).')
    global REF
    try:
        detected = subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,timeout=4)
        if detected.returncode == 0 and len(detected.stdout.strip()) == 40:
            REF = detected.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    paths=[]
    for directory in ('backend','frontend','scripts','deploy'):
        base=root/directory
        if not base.exists(): continue
        for candidate in base.rglob('*'):
            if candidate.is_file() and candidate.suffix.lower() in EXTENSIONS and not any(part in SKIP_DIRS for part in candidate.relative_to(root).parts):
                paths.append(candidate.relative_to(root).as_posix())
    paths.sort()
    rows=[];warnings=[]
    py=[f for f in paths if f.endswith('.py')]
    js=[f for f in paths if not f.endswith('.py')]
    for rel in py:
        rec,error=python_rows((root/rel).read_text(encoding='utf-8-sig'),rel)
        rows.extend(rec)
        if error:warnings.append(error)
    rec,error=ts_rows(root,js)
    rows.extend(rec)
    if error:warnings.append(error)
    rows.sort(key=lambda x:(-x['score'],-x['cyclomatic'],-x['lines'],x['file'],x['start']))
    out=args.output.expanduser().resolve()
    out.mkdir(parents=True,exist_ok=True)
    with (out/'trinity_functions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerows(rows)
    with (out/'trinity_functions.json').open('w',encoding='utf-8') as f:
        json.dump({'source_ref':REF,'warnings':warnings,'functions':rows},f,ensure_ascii=False,indent=2)
    html_report(rows,warnings,out)
    with (out/'README.txt').open('w',encoding='utf-8') as f:
        f.write('Trinity function audit.\nOpen trinity_functions.html to search and sort.\nOpen trinity_functions.csv in Excel.\n')
        f.write('Score criteria: 1 if <=25 LOC, <=4 CC, <=2 nesting; 2 if <=50 LOC, <=7 CC, <=3 nesting;\n')
        f.write('3 if <=85 LOC, <=12 CC, <=4 nesting; 4 if <=130 LOC, <=21 CC, <=6 nesting; otherwise 5.\n')
        f.write('CC counts branches and conditions; no data flow or runtime path analysis.\n')
        f.write('Python AST exact spans; frontend exact AST spans only with TypeScript installed.\n')
        f.write('Warnings: '+'; '.join(warnings)+'\n')
    print(f'Analyzed {len(paths)} source files. Found {len(rows)} functions.\nOutput: {out}')
    print('Distribution:',dict(sorted(Counter(x['score'] for x in rows).items())))
    print('By area:',dict(Counter(x['area'] for x in rows)))
    for warning in warnings: print('WARNING:',warning)
    print('Top 15:')
    for x in rows[:15]: print(f"  {x['score']}  CC={x['cyclomatic']:>3}  LOC={x['lines']:>3}  {x['file']}::{x['function']}")

if __name__=='__main__':
    main()
