#!/usr/bin/env python3
"""Validate package docs and optionally the exact local source evidence (no network)."""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, help='Optional AMReX checkout for pinned evidence validation')
    options = parser.parse_args()
    ledger = json.loads((ROOT / 'evidence/base-evidence.json').read_text())
    entries = ledger['entries']
    ids = [entry['id'] for entry in entries]
    require(len(ids) == len(set(ids)), 'Duplicate evidence ids')
    rules = ROOT / 'skills/hpc-style-for-ai/references/rules.md'
    rule_ids = re.findall(r'^### (G\d\d)：', rules.read_text(), re.M)
    require(rule_ids == [f'G{i:02d}' for i in range(1, 13)], 'Expected G01 through G12 in order')
    skill_root = ROOT / 'skills/hpc-style-for-ai'
    core_docs = [skill_root / 'SKILL.md', rules, skill_root / 'references/binding-strategies.md']
    for core_doc in core_docs:
        text = core_doc.read_text()
        require(not re.search(r'AMReX|FabArray|BoxArray|MFIter', text, re.I), f'Case-specific core dependency: {core_doc}')
        for link in re.findall(r'\]\(<([^>]+)>\)', text):
            require((core_doc.parent / link.split('#')[0]).resolve().is_relative_to(skill_root),
                    f'Core instructions depend on external case files: {core_doc}: {link}')
    required_docs = [ROOT / 'README.md', ROOT / 'docs/base-study.md',
                     ROOT / 'docs/principle-evidence.md', *core_docs]
    source_links = 0
    for doc in required_docs:
        require(doc.is_file(), f'Missing document: {doc}')
        text = doc.read_text()
        mentioned_principles = set(re.findall(r'\bG\d{2}\b', text))
        require(mentioned_principles <= set(rule_ids), f'Unknown principle reference: {doc}')
        require(not re.search(r'\b[HTPM]\d{2}\b', text), f'Obsolete rule reference: {doc}')
        prose = re.sub(r'```[^\n]*\n.*?```', '', text, flags=re.S)
        require(len(re.findall(r'^# ', prose, re.M)) == 1, f'Expected one H1: {doc}')
        require(text.count('```') % 2 == 0, f'Unbalanced fences: {doc}')
        for target in re.findall(r'\]\(<([^>]+)>\)', text):
            if target.startswith(('http:', 'https:', '#')):
                continue
            path, _, anchor = target.partition('#')
            resolved = (doc.parent / path).resolve()
            # Source links are optional workspace conveniences; portable evidence uses pinned URLs.
            if not resolved.is_relative_to(ROOT):
                source_links += 1
                if not options.source:
                    continue
                expected_source = (ROOT.parent / 'amrex').resolve()
                require(resolved.is_relative_to(expected_source), f'Unexpected external file link: {target}')
                resolved = options.source.resolve() / resolved.relative_to(expected_source)
            require(resolved.exists(), f'Broken local link in {doc}: {target}')
            if anchor.startswith('L'):
                match = re.fullmatch(r'L(\d+)(?:-L(\d+))?', anchor)
                require(match is not None, f'Bad line anchor: {target}')
                start, end = int(match[1]), int(match[2] or match[1])
                require(1 <= start <= end <= len(resolved.read_text().splitlines()), f'Bad line range: {target}')
        for diagram in re.findall(r'```mermaid\n(.*?)```', text, re.S):
            require('accTitle:' in diagram and 'accDescr:' in diagram, f'Missing diagram accessibility: {doc}')
            require('%%{init' not in diagram and not re.search(r'^\s*style ', diagram, re.M), f'Nonportable diagram style: {doc}')
    if options.source:
        source = options.source.resolve()
        require(git(source, 'rev-parse', 'HEAD') == ledger['source']['commit'], 'AMReX HEAD differs from pinned commit')
        for entry in entries:
            relative = Path(entry['path'])
            require(not relative.is_absolute() and '..' not in relative.parts, 'Invalid evidence path')
            path = source / relative
            lines = path.read_text().splitlines()
            require(1 <= entry['start'] <= entry['end'] <= len(lines), f'Bad range: {entry["id"]}')
            snippet = '\n'.join(lines[entry['start'] - 1:entry['end']])
            require(entry['quote'] in snippet, f'Quote drift: {entry["id"]}: {entry["quote"]}')
            require(not git(source, 'diff', 'HEAD', '--', entry['path']), f'Local source edits: {entry["path"]}')
        require((source / 'LICENSE').read_bytes() == (ROOT / 'third_party/AMReX-LICENSE').read_bytes(), 'Attribution copy differs')
    print(json.dumps({'documents': len(required_docs), 'rules': len(rule_ids),
                      'evidence_entries': len(entries), 'source_links': source_links,
                      'source_evidence_checked': bool(options.source),
                      'mermaid_status': 'structure checked; visual rendering not tested',
                      'status': 'passed'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
