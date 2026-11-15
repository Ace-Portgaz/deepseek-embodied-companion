import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from speech_budget import reserve, BudgetExceeded, ensure_available, CHINA_TIME


class SpeechBudgetTests(unittest.TestCase):
    def test_limits_are_persisted_and_excess_is_rejected_before_submission(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'usage.json'
            p.write_text(json.dumps({'characters': 198, 'seconds': 59.9}))
            with patch.dict(os.environ, REM_TEST_BUDGET_FILE=str(p)):
                reserve(characters=2, seconds=.1)
                for increment in ({'characters': 1}, {'seconds': .001}):
                    with self.assertRaises(BudgetExceeded):
                        reserve(**increment)
            self.assertEqual(json.loads(p.read_text()), {'characters': 200, 'seconds': 60, 'paused': True})

    def test_missing_ledger_does_not_reset_allowance(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, REM_TEST_BUDGET_FILE=str(Path(folder) / 'missing.json')):
                with self.assertRaises(FileNotFoundError):
                    reserve(characters=1)

    def test_explicit_extension_keeps_usage_and_enforces_new_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'usage.json'
            p.write_text(json.dumps({'characters': 159, 'seconds': 59.993125,
                                    'limits': {'characters': 659, 'seconds': 359.993125}}))
            with patch.dict(os.environ, REM_TEST_BUDGET_FILE=str(p)):
                reserve(characters=500, seconds=300)
                with self.assertRaises(BudgetExceeded):
                    reserve(characters=1)
                with self.assertRaises(BudgetExceeded):
                    reserve(seconds=.001)
            state = json.loads(p.read_text())
            self.assertEqual(state['characters'], 659)
            self.assertEqual(state['seconds'], 359.993125)

    def test_daily_limit_resets_on_china_date_boundary_and_not_earlier(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'usage.json'
            p.write_text(json.dumps({'characters': 1000, 'seconds': 600,
                                    'limits': {'characters': 1000, 'seconds': 600},
                                    'period': 'day', 'date': '2026-11-11'}))
            with patch.dict(os.environ, REM_TEST_BUDGET_FILE=str(p)), patch('speech_budget.datetime') as clock:
                clock.now.return_value = datetime(2026, 11, 11, 23, 59, tzinfo=CHINA_TIME)
                with self.assertRaises(BudgetExceeded):
                    reserve(characters=1)
                clock.now.return_value = datetime(2026, 11, 12, 0, 0, tzinfo=CHINA_TIME)
                reserve(characters=7, seconds=1)
                clock.now.assert_called_with(CHINA_TIME)
            state = json.loads(p.read_text())
            self.assertEqual(state['date'], '2026-11-12')
            self.assertEqual(state['characters'], 7)
            self.assertEqual(state['seconds'], 1)
            self.assertFalse(state['paused'])

    def test_full_allowance_blocks_a_new_session_before_any_provider_call(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'usage.json'
            p.write_text(json.dumps({'characters': 200, 'seconds': 2}))
            with patch.dict(os.environ, REM_TEST_BUDGET_FILE=str(p)):
                with self.assertRaises(BudgetExceeded):
                    ensure_available()

    def test_one_day_topup_preserves_usage_and_expires_at_china_midnight(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'usage.json'
            p.write_text(json.dumps({'characters':1000,'seconds':100,'paused':False,
                'limits':{'characters':1000,'seconds':600},'period':'day','date':'2026-11-15',
                'one_day_extra':{'date':'2026-11-15','characters':1000}}))
            with patch.dict(os.environ,REM_TEST_BUDGET_FILE=str(p)),patch('speech_budget.datetime') as clock:
                clock.now.return_value=datetime(2026,11,15,23,59,tzinfo=CHINA_TIME)
                reserve(characters=1000)
                with self.assertRaises(BudgetExceeded):reserve(characters=1)
                state=json.loads(p.read_text());self.assertEqual(state['characters'],2000)
                self.assertEqual(state['limits'],{'characters':1000,'seconds':600})
                clock.now.return_value=datetime(2026,11,16,0,0,tzinfo=CHINA_TIME)
                reserve(characters=1000)
                with self.assertRaises(BudgetExceeded):reserve(characters=1)

    def test_one_day_topup_does_not_raise_recognition_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'usage.json'
            p.write_text(json.dumps({'characters':1,'seconds':600,'limits':{'characters':1000,'seconds':600},
                'period':'day','date':datetime.now(CHINA_TIME).date().isoformat(),
                'one_day_extra':{'date':datetime.now(CHINA_TIME).date().isoformat(),'characters':1000}}))
            with patch.dict(os.environ,REM_TEST_BUDGET_FILE=str(p)):
                with self.assertRaises(BudgetExceeded):reserve(seconds=.1)
