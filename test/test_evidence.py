"""Negative controls for the offline source-evidence validator."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('evidence_validator', Path(__file__).resolve().parents[1] / 'scripts/validate.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hpc-evidence-test-')
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name)
        (self.source / 'source.cpp').write_text('// fixture\nint observed = 1;\n// end\n')
        subprocess.run(['git', 'init', '-q', str(self.source)], check=True)
        subprocess.run(['git', '-C', str(self.source), 'add', 'source.cpp'], check=True)
        subprocess.run(['git', '-C', str(self.source), '-c', 'user.name=Evidence Test',
                        '-c', 'user.email=evidence@example.invalid', 'commit', '-qm', 'fixture'], check=True)
        commit = validator.git(self.source, 'rev-parse', 'HEAD')
        self.ledger = {'schema_version': 2, 'source': {'project': 'fixture', 'commit': commit,
                                 'browse_base': f'https://example.invalid/repo/blob/{commit}/'},
                       'entries': [{'id': 'KE01', 'path': 'source.cpp', 'start': 2, 'end': 2,
                                    'symbol': 'observed', 'quote': 'int observed = 1;',
                                    'principles': ['G01'], 'observation': 'fixture', 'limits': 'fixture only', 'validation': 'fixture source check',
                                    'file_sha256': hashlib.sha256((self.source / 'source.cpp').read_bytes()).hexdigest()}]}

    def validate(self, ledger=None):
        return validator.validate_ledger(ledger or self.ledger, ['G01'], self.source)

    def test_pinned_source_passes(self):
        self.assertEqual(self.validate(), ['KE01'])

    def test_commit_mismatch_fails(self):
        ledger = copy.deepcopy(self.ledger)
        ledger['source']['commit'] = '0' * 40
        ledger['source']['browse_base'] = 'https://example.invalid/repo/blob/' + '0' * 40 + '/'
        with self.assertRaisesRegex(RuntimeError, 'HEAD differs'):
            self.validate(ledger)

    def test_quote_drift_fails(self):
        ledger = copy.deepcopy(self.ledger)
        ledger['entries'][0]['quote'] = 'int invented = 2;'
        with self.assertRaisesRegex(RuntimeError, 'Quote drift'):
            self.validate(ledger)

    def test_dirty_source_fails_even_if_quote_remains(self):
        with (self.source / 'source.cpp').open('a') as file:
            file.write('// changed outside excerpt\n')
        with self.assertRaisesRegex(RuntimeError, 'Local source edits'):
            self.validate()

    def test_hash_mismatch_fails(self):
        ledger = copy.deepcopy(self.ledger)
        ledger['entries'][0]['file_sha256'] = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'File hash drift'):
            self.validate(ledger)

    def test_missing_rich_fields_fail(self):
        for field in ('symbol', 'principles', 'observation', 'limits', 'validation', 'file_sha256'):
            with self.subTest(field=field):
                ledger = copy.deepcopy(self.ledger)
                del ledger['entries'][0][field]
                with self.assertRaises(RuntimeError):
                    self.validate(ledger)

    def test_legacy_entries_remain_valid(self):
        ledger = copy.deepcopy(self.ledger)
        ledger['schema_version'] = 1
        for field in ('principles', 'observation', 'limits', 'validation', 'file_sha256'):
            del ledger['entries'][0][field]
        self.assertEqual(self.validate(ledger), ['KE01'])

    def test_document_evidence_ids_include_legacy_suffixes(self):
        validator.validate_evidence_references('E11b KM01 KE01', ['E11b', 'KM01', 'KE01'])
        with self.assertRaisesRegex(RuntimeError, 'Unknown source evidence'):
            validator.validate_evidence_references('E99', ['E11b'])

    def test_bad_ledger_structure_fails_without_checkout(self):
        for key, value, expected in [('path', '../outside.cpp', 'Invalid evidence path'),
                                     ('principles', ['G99'], 'Unknown evidence principle'),
                                     ('quote', '', 'Empty evidence quote')]:
            with self.subTest(key=key):
                ledger = copy.deepcopy(self.ledger)
                ledger['entries'][0][key] = value
                with self.assertRaisesRegex(RuntimeError, expected):
                    validator.validate_ledger(ledger, ['G01'])


if __name__ == '__main__':
    unittest.main()
