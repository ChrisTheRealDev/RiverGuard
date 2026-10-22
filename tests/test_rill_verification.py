import asyncio
import json
from pathlib import Path

import pytest

import rill_ai
from benchmark_rill_quality import fixture_frame
from rill_verification import authoritative_facts, verify_reply

BASELINE=json.loads((Path(__file__).parent/'fixtures/rill-baseline-answers.json').read_text(encoding='utf-8'))


def context(name):
    frame,settings=fixture_frame(name)
    return rill_ai.context_data(frame,**settings)


@pytest.mark.parametrize('name,answer',[
 ('stale','The current water level is 40 cm, below the watch level of 45 cm.'),
 ('future-clock','These are old readings; water levels have been dropping steadily.'),
 ('calibration-jump','In this demo, water rose by 10 cm in 1.61 seconds, a rise of 6.2 cm/min.'),
 ('elevated-level','In this demo, 85 cm has crossed the warning threshold of 100 cm.'),
 ('unicode-emoji','In this demo, a temperature of 27 °C is slightly above the reference range of 20–32 °C.'),
 ('unicode-malay','pH air sungai ini sekitar 7.1, aman untuk diminum oleh otter.'),
 ('drinking-safety','In this demo, pH is within the reference range for safe drinking water.'),
 ('calibrated-rise','The water level is rising at a rate of 120.0 cm/min, which is above the demo threshold of 70.0 cm.'),
 ('calibrated-rise','In this demo, the water level rose by 10 cm/min. This rate is within the crossing warning threshold of 10 cm/min.'),
 ('uncalibrated','Our pH is 7.1 and turbidity is 12 NTU. Everything looks ordinary.'),
])
def test_known_actual_baseline_failures_are_not_accepted(name,answer):
    result=verify_reply(answer,context(name),'What do our current readings mean?')
    assert not result['passed'] and result['reasons']
    assert result['can_continue'] is False


@pytest.mark.parametrize('name,answer',[
 ('future-clock','In this demo, the station clock is ahead of the laptop. Check its clock before interpreting the readings.'),
 ('calibration-jump','In this demo, the calibration changed, so I cannot calculate a valid speed. The level of 90 cm is below warning 100 cm.'),
 ('elevated-level','In this demo, 85 cm is above watch 70 cm, but it has not reached warning 100 cm.'),
 ('unicode-emoji','In this demo, 27 °C describes how warm the water is, within the 20–32 °C reference range.'),
 ('unicode-emoji','In this demo, 27 °C is within the 20-32 °C reference range.'),
 ('drinking-safety','In this demo, these sensors cannot establish whether the water is safe to drink.'),
 ('stale','In this demo, these are old readings, not current river conditions.'),
 ('calibrated-rise','In this demo, the observed rise is 120 cm/min, above the warning setting of 10 cm/min.'),
 ('uncalibrated','The real sensor readings are provisional until their calibration is verified.'),
])
def test_grounded_clear_answers_are_allowed(name,answer):
    assert verify_reply(answer,context(name),'What do our current readings mean?')['passed']


def test_compact_prompt_has_one_system_and_explicit_comparisons():
    payload=rill_ai._payload('What now?',[],context('elevated-level'))
    assert sum(message['role']=='system' for message in payload['messages'])==1
    system=payload['messages'][0]['content']
    assert '85 cm is ABOVE WATCH BUT BELOW WARNING' in system
    assert 'watch 70 cm, warning 100 cm' in system
    assert 'UNAVAILABLE' in rill_ai._payload('Speed?',[],context('calibration-jump'))['messages'][0]['content']


@pytest.mark.parametrize('name,answer',[
 ('elevated-level','In this demo, I cannot confirm pollution, but 85 cm is above the warning level of 100 cm.'),
 ('elevated-level','In this demo, no germ count is available, so this water is safe to drink.'),
 ('elevated-level','In this demo, this water is safe for otters and safe to swim in.'),
 ('missing-ph','In this demo, pH is 9.4.'),
 ('unicode-malay','In this demo, air di sungai ini aman dinomori dan tidak ada tanda-tanda keracunan.'),
])
def test_independent_review_counterexamples_are_blocked(name,answer):
    assert not verify_reply(answer,context(name),'What do our current river readings mean?')['passed']


@pytest.mark.parametrize('saved',BASELINE,ids=lambda item:item['case'])
def test_actual_twenty_case_baseline_known_hazards(saved):
    result=verify_reply(saved['answer'],context(saved['case']),saved['question'])
    if saved['must_block']:
        assert not result['passed'],saved['review']['notes']
    elif saved['review']['verdict']=='pass':
        assert result['passed'],result['reasons']
    # Style/clarity weaknesses remain explicit semantic-review evidence;
    # this guard does not claim to classify those as safety failures.
