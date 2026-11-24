#!/usr/bin/env python3
"""Validate curated docs and optional pinned source evidence, without network access."""
import argparse
import hashlib
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


def validate_ledger(ledger, rule_ids, source=None, license_copy=None):
    schema = ledger.get('schema_version', 1)
    require(schema in (1, 2), 'Unsupported evidence schema')
    rich_entries = schema == 2
    commit = ledger['source']['commit']
    require(re.fullmatch(r'[0-9a-f]{40}', commit), 'Invalid pinned commit')
    require(ledger['source']['browse_base'].endswith(f'/blob/{commit}/'), 'Unpinned browse URL')
    entries = ledger['entries']
    require(entries, 'Empty evidence ledger')
    ids = [entry['id'] for entry in entries]
    require(len(ids) == len(set(ids)), 'Duplicate evidence ids')
    for entry in entries:
        relative = Path(entry['path'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'Invalid evidence path')
        require(isinstance(entry['start'], int) and isinstance(entry['end'], int)
                and 1 <= entry['start'] <= entry['end'], f'Bad range: {entry["id"]}')
        require(isinstance(entry.get('quote'), str) and bool(entry['quote'].strip()), 'Empty evidence quote')
        require(isinstance(entry.get('symbol'), str) and bool(entry['symbol'].strip()), 'Missing evidence symbol')
        if rich_entries or 'principles' in entry:
            require(isinstance(entry.get('principles'), list) and bool(entry['principles'])
                    and all(isinstance(value, str) for value in entry['principles'])
                    and set(entry['principles']) <= set(rule_ids),
                    f'Unknown evidence principle: {entry["id"]}')
            for field in ('observation', 'limits', 'validation'):
                require(isinstance(entry.get(field), str) and bool(entry[field].strip()),
                        f'Missing evidence {field}: {entry["id"]}')
        if rich_entries or 'file_sha256' in entry:
            require(isinstance(entry.get('file_sha256'), str)
                    and re.fullmatch(r'[0-9a-f]{64}', entry['file_sha256']), 'Invalid evidence file hash')
    if source is None:
        return ids
    source = source.resolve()
    require(git(source, 'rev-parse', 'HEAD') == commit, f'{ledger["source"]["project"]} HEAD differs from pinned commit')
    for entry in entries:
        path = (source / entry['path']).resolve()
        require(path.is_relative_to(source), 'Evidence resolves outside source checkout')
        # The evidence must refer to tracked source, not a locally generated substitute.
        git(source, 'ls-files', '--error-unmatch', '--', entry['path'])
        lines = path.read_text().splitlines()
        require(entry['end'] <= len(lines), f'Bad range: {entry["id"]}')
        snippet = '\n'.join(lines[entry['start'] - 1:entry['end']])
        require(entry['quote'] in snippet, f'Quote drift: {entry["id"]}')
        require(not git(source, 'diff', 'HEAD', '--', entry['path']), f'Local source edits: {entry["path"]}')
        if 'file_sha256' in entry:
            require(hashlib.sha256(path.read_bytes()).hexdigest() == entry['file_sha256'],
                    f'File hash drift: {entry["id"]}')
    if license_copy is not None:
        require((source / 'LICENSE').read_bytes() == license_copy.read_bytes(), 'Attribution copy differs')
    return ids


def validate_evidence_references(text, known_ids):
    mentioned = set(re.findall(r'\b(?:E\d{2}[a-z]?|KM\d{2}|KE\d{2})\b', text))
    require(mentioned <= set(known_ids), 'Unknown source evidence reference: ' + ', '.join(sorted(mentioned - set(known_ids))))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, help='Optional AMReX checkout (legacy option)')
    parser.add_argument('--kokkos-source', type=Path, help='Optional Kokkos checkout for pinned evidence validation')
    options = parser.parse_args()
    rules = ROOT / 'skills/hpc-style-for-ai/references/rules.md'
    rule_ids = re.findall(r'^### (G\d\d)：', rules.read_text(), re.M)
    require(rule_ids == [f'G{i:02d}' for i in range(1, 13)], 'Expected G01 through G12 in order')
    cases = [('base-evidence.json', options.source, 'AMReX-LICENSE'),
             ('kokkos-evidence.json', options.kokkos_source, 'Kokkos-LICENSE')]
    all_ids, counts, checked = [], {}, {}
    for filename, source, license_name in cases:
        ledger = json.loads((ROOT / 'evidence' / filename).read_text())
        ids = validate_ledger(ledger, rule_ids, source, ROOT / 'third_party' / license_name)
        all_ids.extend(ids)
        counts[filename] = len(ids)
        checked[filename] = source is not None
    require(len(all_ids) == len(set(all_ids)), 'Evidence IDs collide between projects')
    skill_root = ROOT / 'skills/hpc-style-for-ai'
    core_docs = [skill_root / 'SKILL.md', *sorted((skill_root / 'references').glob('*.md'))]
    for core_doc in core_docs:
        text = core_doc.read_text()
        require(not re.search(r'AMReX|FabArray|BoxArray|MFIter|Kokkos|DualView|MDRangePolicy', text, re.I),
                f'Case-specific core dependency: {core_doc}')
        for link in re.findall(r'\]\(<([^>]+)>\)', text):
            require((core_doc.parent / link.split('#')[0]).resolve().is_relative_to(skill_root),
                    f'Core instructions depend on external case files: {core_doc}: {link}')
    required_docs = [ROOT / 'README.md', *sorted((ROOT / 'docs').glob('*.md')), *core_docs]
    source_links = 0
    for doc in required_docs:
        text = doc.read_text()
        mentioned_principles = set(re.findall(r'\bG\d{2}\b', text))
        require(mentioned_principles <= set(rule_ids), f'Unknown principle reference: {doc}')
        require(not re.search(r'\b[HTPM]\d{2}\b', text), f'Obsolete rule reference: {doc}')
        validate_evidence_references(text, all_ids)
        prose = re.sub(r'```[^\n]*\n.*?```', '', text, flags=re.S)
        require(len(re.findall(r'^# ', prose, re.M)) == 1, f'Expected one H1: {doc}')
        require(text.count('```') % 2 == 0, f'Unbalanced fences: {doc}')
        for target in re.findall(r'\]\(<([^>]+)>\)', text):
            if target.startswith(('http:', 'https:', '#')):
                continue
            path, _, anchor = target.partition('#')
            resolved = (doc.parent / path).resolve()
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
    print(json.dumps({'documents': len(required_docs), 'rules': len(rule_ids),
                      'evidence_entries': counts, 'source_links': source_links,
                      'source_evidence_checked': checked,
                      'mermaid_status': 'structure checked; visual rendering not tested',
                      'status': 'passed'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
