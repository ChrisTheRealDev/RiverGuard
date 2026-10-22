"""Shared deterministic snapshots and ledger transitions, also consumed by Java/JS."""
import copy
import json
from pathlib import Path
import unittest
from v2.server import signals

FIXTURES = json.loads((Path(__file__).parent / 'fixtures/signal-repairs.json').read_text())

class SharedSignalParity(unittest.TestCase):
    def test_snapshot_vectors(self):
        for case in FIXTURES['cases']:
            with self.subTest(case=case['name']):
                result=signals.evaluate(case['records'],case['watch'],FIXTURES['now'])
                expected=case['expected']
                self.assertEqual(expected['fresh'],result['fresh'])
                self.assertEqual(sorted(expected['activeKinds']),sorted(v['kind'] for v in result['signals']))
                self.assertEqual(expected['evidence'],result['evidence'])
                self.assertEqual(expected['rate'],result['rate'])
                derived=signals.derive(case['records'][0],FIXTURES['now'])
                self.assertEqual(expected['values'],[derived['values'][k] for k in ('ph','turbidity','temperature','water_level')])
    def test_ledger_vectors(self):
        cases={c['name']:c for c in FIXTURES['cases']}
        for sequence in FIXTURES['sequences']:
            with self.subTest(sequence=sequence['name']):
                state=None
                for index,step in enumerate(sequence['steps']):
                    case=cases[step['case']];rows=copy.deepcopy(case['records']);rows[0]['payload']['sample_id']='step-'+str(index)
                    evaluation=signals.evaluate(rows,case['watch'],FIXTURES['now'])
                    evaluation.update(watchRevision=step['watchRevision'],watchSettings=case['watch'])
                    state,events=signals.apply(state,evaluation,FIXTURES['now'])
                    self.assertEqual(step['expectedEvents'],[[v['kind'],v['phase']] for v in events])
                self.assertEqual(sorted(sequence['finalActive']),sorted(k for k,v in state['conditions'].items() if v['active']))
