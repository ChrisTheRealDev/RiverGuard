import json
import httpx
import pandas as pd
import rill_ai
import pytest

@pytest.fixture(autouse=True)
def local_default(monkeypatch):
    monkeypatch.setenv('RILL_PROVIDER','ollama')

def test_snapshot_preserves_missing_and_staleness():
    df=pd.DataFrame([{'timestamp':'2020-01-01T00:00:00Z','source':'simulation','ph':None}])
    ctx=rill_ai.snapshot(df)
    assert ctx['stale']
    assert ctx['recent_samples_oldest_first'][0]['ph'] is None
    assert rill_ai.snapshot(pd.DataFrame())['recent_samples_oldest_first']==[]

def test_stream_includes_fresh_context_and_history(monkeypatch):
    captured={}
    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200,text='{"message":{"content":"Hey! "}}\n{"message":{"content":"Let’s look."}}\n{"done":true}\n')
    def stream(method,url,**kwargs):
        kwargs.pop('trust_env',None)
        return httpx.Client(transport=httpx.MockTransport(handler)).stream(method,url,**kwargs)
    monkeypatch.setattr(httpx,'stream',stream)
    result=''.join(rill_ai.chat_stream('What now?',[{'role':'user','content':'Hi'}],pd.DataFrame()))
    assert result=='Hey! Let’s look.'
    assert 'fresh sensor context' in captured['messages'][-2]['content']
    assert captured['messages'][-1]['content']=='What now?'
    assert captured['messages'][1]['content']=='Hi'

def test_each_question_uses_new_readings(monkeypatch):
    requests=[]
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,text='{"message":{"content":"Reply"}}\n{"done":true}\n')
    def stream(method,url,**kwargs):
        kwargs.pop('trust_env',None)
        return httpx.Client(transport=httpx.MockTransport(handler)).stream(method,url,**kwargs)
    monkeypatch.setattr(httpx,'stream',stream)
    for ph in [7.1,8.2]:
        frame=pd.DataFrame([{'timestamp':'2026-10-20T00:00:00Z','device_id':'station','source':'simulation','ph':ph}])
        assert ''.join(rill_ai.chat_stream('How is pH?',[],frame))=='Reply'
    contexts=[json.loads(r['messages'][-2]['content'].split(': ',1)[1]) for r in requests]
    assert [ctx['latest']['ph'] for ctx in contexts]==[7.1,8.2]
    assert all(ctx['latest']['source']=='simulation' for ctx in contexts)

def test_cloud_streams_fresh_data_and_keeps_key_out_of_url(monkeypatch):
    monkeypatch.setenv('RILL_PROVIDER','gemini')
    monkeypatch.setenv('GEMINI_API_KEY','test-secret')
    captured={}
    def handler(request):
        captured.update(json.loads(request.content))
        assert request.headers['x-goog-api-key']=='test-secret'
        assert 'test-secret' not in str(request.url)
        return httpx.Response(200,text='data: {"candidates":[{"content":{"parts":[{"text":"Hi "}]}}]}\n\ndata: {"candidates":[{"content":{"parts":[{"text":"river"}]}}]}\n\n')
    def stream(method,url,**kwargs):
        kwargs.pop('trust_env',None)
        return httpx.Client(transport=httpx.MockTransport(handler)).stream(method,url,**kwargs)
    monkeypatch.setattr(httpx,'stream',stream)
    for ph in [7.1,8.2]:
        frame=pd.DataFrame([{'timestamp':'2026-10-20T00:00:00Z','source':'simulation','ph':ph}])
        assert ''.join(rill_ai.chat_stream('pH?',[{'role':'assistant','content':'Earlier answer'}],frame))=='Hi river'
        ctx=json.loads(captured['contents'][-1]['parts'][0]['text'].split(': ',1)[1])
        assert ctx['latest']['ph']==ph
        assert captured['contents'][0]['role']=='model'
    assert captured['generationConfig']['maxOutputTokens']==1024

@pytest.mark.parametrize('status',[403,429,503])
def test_cloud_errors_are_safe_and_do_not_silently_fall_back(monkeypatch,status):
    monkeypatch.setenv('RILL_PROVIDER','gemini')
    monkeypatch.setenv('GEMINI_API_KEY','test-secret')
    def stream(method,url,**kwargs):
        kwargs.pop('trust_env',None)
        return httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(status,text='test-secret'))).stream(method,url,**kwargs)
    monkeypatch.setattr(httpx,'stream',stream)
    with pytest.raises(rill_ai.RillError) as exc:
        list(rill_ai.chat_stream('hi',[],pd.DataFrame()))
    assert 'test-secret' not in str(exc.value)

def test_cloud_backoff_uses_provider_delay():
    assert rill_ai.retry_delay(httpx.Response(429,headers={'retry-after':'7'}))==7
    assert rill_ai.retry_delay(httpx.Response(429,json={'error':{'details':[{'@type':'type.googleapis.com/google.rpc.RetryInfo','retryDelay':'12.5s'}]}}))==12.5
    assert rill_ai.retry_delay(httpx.Response(429,text='unavailable'))==15


def test_cloud_key_does_not_enable_cloud_by_default(monkeypatch):
    monkeypatch.delenv('RILL_PROVIDER',raising=False)
    monkeypatch.setenv('GEMINI_API_KEY','unused-key')
    assert rill_ai.provider()=='ollama'
