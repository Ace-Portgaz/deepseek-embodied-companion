"""Validate that the progress display never treats old packs as new traffic."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('transfer', Path(__file__).resolve().parents[1] / 'scripts/source_transfer.py')
transfer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transfer)


class TransferTests(unittest.TestCase):
    def test_existing_large_pack_is_only_a_baseline(self):
        row = {'group': 10, 'observed': 1, 'files': {'a': 10**9}}
        self.assertIsNone(transfer.estimate_rate(None, row))
        self.assertEqual(transfer.estimate_rate(row, dict(row, observed=11)), 0)

    def test_growth_and_new_packs_count_but_completed_packs_never_subtract(self):
        first = {'group': 10, 'observed': 1, 'files': {'a': 1000, 'done': 10**9}}
        second = {'group': 10, 'observed': 11, 'files': {'a': 2000, 'new': 3000}}
        self.assertEqual(transfer.estimate_rate(first, second), 400)

    def test_restart_establishes_new_baseline(self):
        first = {'group': 10, 'observed': 1, 'files': {'a': 1000}}
        second = {'group': 20, 'observed': 11, 'files': {'a': 2000}}
        self.assertIsNone(transfer.estimate_rate(first, second))


if __name__ == '__main__':
    unittest.main()
