import asyncio
import json

import benchmark_rill_quality as benchmark
import rill_ai


def test_twenty_fixture_snapshots_match_review_expectations():
    assert len(benchmark.FIXTURES)==20
    assert len({row[0] for row in benchmark.FIXTURES})==20
    contexts={}
    for name,question,points in benchmark.FIXTURES:
        frame,thresholds=benchmark.fixture_frame(name)
        contexts[name]=rill_ai.context_data(frame,**thresholds)
        assert question and points
    assert contexts['missing-ph']['latest']['ph'] is None
    assert contexts['disabled-cloudiness']['latest']['turbidity'] is None
    assert contexts['partial-level-warning']['dashboard_status']['flood']=='Warning'
    assert contexts['future-clock']['clock_ahead']
    assert contexts['stale']['stale']
    assert contexts['calibrated-rise']['observed_rise_cm_per_min']==120.
    assert contexts['falling']['observed_rise_cm_per_min']==-30.
    assert contexts['calibration-jump']['observed_rise_cm_per_min'] is None
    assert contexts['out-of-order']['latest']['temperature']==30.


def test_failed_actual_preflight_stops_nineteen_cases_without_fallback(tmp_path,monkeypatch):
    calls=[]
    async def stream(*args,**kwargs):
        calls.append(args)
        kwargs['telemetry'].update(terminal_received=False)
        raise rill_ai.RillError('The local model could not fit in memory.')
        yield
    async def profile():return {'version':'mock'}
    monkeypatch.setenv('RILL_PROVIDER','ollama')
    monkeypatch.setattr(rill_ai,'MODEL','llama3.2:3b')
    monkeypatch.setattr(rill_ai,'HOST','http://127.0.0.1:11434')
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    monkeypatch.setattr(benchmark,'server_profile',profile)
    output=tmp_path/'benchmark.json'
    result=asyncio.run(benchmark.run_benchmark(output))
    assert len(calls)==1
    assert result['status']=='blocked'
    assert result['summary']['not_run']==19
    assert result['summary']['completed_requests']==0
    assert result['summary']['quality_pass_count'] is None
    assert result['fallback_used'] is False
    assert json.loads(output.read_text(encoding='utf-8'))['status']=='blocked'


def test_completed_mock_calls_remain_pending_human_review(tmp_path,monkeypatch):
    async def stream(*args,**kwargs):
        context=args[2]
        answer='In this demo, measurements need interpretation.'
        if context.get('clock_ahead'):answer+=' Check the station clock.'
        elif context.get('stale'):answer+=' These are old readings.'
        if context.get('latest',{}).get('source')=='esp32':answer+=' Real readings are provisional.'
        yield answer
        kwargs['telemetry'].update(terminal_received=True,done_reason='stop',eval_count=9,prompt_eval_count=400)
    async def profile():return {'version':'mock'}
    monkeypatch.setenv('RILL_PROVIDER','ollama')
    monkeypatch.setattr(rill_ai,'MODEL','llama3.2:3b')
    monkeypatch.setattr(rill_ai,'HOST','http://127.0.0.1:11434')
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    monkeypatch.setattr(benchmark,'server_profile',profile)
    result=asyncio.run(benchmark.run_benchmark(tmp_path/'mock-only.json'))
    assert result['status']=='completed'
    assert result['summary']['completed_requests']==20
    assert result['summary']['human_review_pending']==20
    assert result['summary']['quality_pass_count'] is None
    assert result['generation_options']['num_predict']==256
