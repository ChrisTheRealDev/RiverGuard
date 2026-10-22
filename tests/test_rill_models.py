"""Local-only model selection, immutable replies and preloading with no real AI."""
import asyncio
import json

import httpx
import pytest

import core
import rill_ai
import rill_models
from chat_service import ChatService, ChatError
from tests.test_chat_service import frame, terminal
from tests.test_web_access import web, owner


def test_catalog_excludes_cloud_aliases_and_non_chat_models(monkeypatch):
    monkeypatch.setenv('RILL_PROVIDER','ollama')
    monkeypatch.setattr(rill_ai,'HOST','http://127.0.0.1:11434')
    requests=[]
    def respond(request):
        requests.append(request)
        if request.url.path=='/api/tags':
            return httpx.Response(200,json={'models':[
                {'name':'qwen3.5:4b','size':3400000000},
                {'name':'hidden-alias','size':1},
                {'name':'embedding','size':1},
                {'name':'large:cloud','size':1},
                {'name':'remote-alias','remote_host':'https://ollama.com'},
                {'name':'unsafe; command','size':1}]})
        if request.url.path=='/api/ps':
            return httpx.Response(200,json={'models':[{'name':'qwen3.5:4b','size':400,'size_vram':0}]})
        name=json.loads(request.content)['model']
        return httpx.Response(200,json={'capabilities':['embedding'] if name=='embedding' else ['completion','thinking'],
                                       'remote_host':'https://ollama.com' if name=='hidden-alias' else None,
                                       'details':{'parameter_size':'4B','quantization_level':'Q4_K_M'}})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result=await rill_models.catalog(client)
        assert [v['name'] for v in result['models']]==['qwen3.5:4b']
        assert result['models'][0]['thinking']
        assert result['loaded']==[{'name':'qwen3.5:4b','processor':'CPU'}]
        assert all(request.url.host=='127.0.0.1' for request in requests)
        assert not any(request.url.path=='/api/pull' for request in requests)
    asyncio.run(scenario())


def test_remote_server_is_not_a_local_model_selector(monkeypatch):
    monkeypatch.setenv('RILL_PROVIDER','ollama')
    monkeypatch.setattr(rill_ai,'HOST','http://192.0.2.2:11434')
    async def scenario():
        with pytest.raises(rill_ai.RillError,match='local Ollama'):
            await rill_models.catalog()
    asyncio.run(scenario())


def test_explicit_model_keeps_live_grounding_and_answer_budget(monkeypatch):
    monkeypatch.setenv('RILL_PROVIDER','ollama')
    context=rill_ai.context_data(frame(7.6))
    captured=[]
    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200,text='{"message":{"content":"In this demo, pH is 7.6."}}\n{"done":true,"done_reason":"stop"}\n')
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            answer=''.join([token async for token in rill_ai.async_chat_stream('pH?',[],context,client=client,model='qwen3.5:4b')])
        assert '7.6' in answer
        assert captured[0]['model']=='qwen3.5:4b'
        assert captured[0]['options']['num_ctx']==4096
        assert captured[0]['options']['num_predict']==256
        assert 'think' not in captured[0]  # Never silently turn off a new model's reasoning.
        assert '7.6' in captured[0]['messages'][0]['content']
    asyncio.run(scenario())


def test_model_api_is_authenticated_revisioned_and_installed_only(web,monkeypatch):
    async def catalog():
        return {'models':[{'name':'llama3.2:3b'},{'name':'qwen3.5:4b'}],'loaded':[]}
    monkeypatch.setattr(rill_models,'catalog',catalog)
    assert web.get('/api/ui/ai/models').status_code==401
    assert web.put('/api/ui/ai/model',json={'model':'qwen3.5:4b','expected_revision':0}).status_code==401
    owner(web)
    assert web.put('/api/ui/ai/model',json={'model':'qwen3.5:4b','expected_revision':0},headers={'X-CSRF-Token':'bad'}).status_code==403
    assert web.put('/api/ui/ai/model',json={'model':'not-installed','expected_revision':0}).status_code==422
    saved=web.put('/api/ui/ai/model',json={'model':'qwen3.5:4b','expected_revision':0})
    assert saved.status_code==200,saved.text
    assert saved.json()['revision']==1
    assert web.get('/api/ui/session').json()['provider']['model']=='qwen3.5:4b'
    assert web.put('/api/ui/ai/model',json={'model':'llama3.2:3b','expected_revision':0}).status_code==409


def test_opening_chat_does_not_reset_an_already_loaded_model(web,monkeypatch):
    async def catalog():
        return {'models':[{'name':rill_ai.MODEL}],
                'loaded':[{'name':rill_ai.MODEL,'processor':'CPU','context_length':4096}]}
    async def unexpected(model):
        pytest.fail('A loaded model must retain its useful prompt cache.')
    monkeypatch.setattr(rill_models,'catalog',catalog)
    monkeypatch.setattr(rill_models,'preload',unexpected)
    owner(web)
    response=web.post('/api/ui/ai/warmup')
    assert response.status_code==200
    assert not response.json()['warming']
    assert web.app.state.chat._warm_task is None


def test_model_changed_during_catalog_does_not_report_old_model_prepared(web,monkeypatch):
    async def catalog():
        web.app.state.chat.select_model('qwen3.5:4b',0)
        return {'models':[{'name':rill_ai.MODEL},{'name':'qwen3.5:4b'}],
                'loaded':[{'name':rill_ai.MODEL,'processor':'CPU','context_length':4096}]}
    monkeypatch.setattr(rill_models,'catalog',catalog)
    owner(web)
    response=web.post('/api/ui/ai/warmup')
    assert response.status_code==409
    assert web.app.state.chat._warm_task is None


def test_continue_retains_original_model_retry_uses_new_choice(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB',tmp_path/'models.db')
    monkeypatch.setenv('RILL_PROVIDER','ollama')
    seen=[]
    async def stream(*args,model=None,**kwargs):
        seen.append(model)
        yield 'The river ' if len(seen)==1 else 'is calm.' if len(seen)==2 else 'A fresh answer.'
        if len(seen)<3:raise rill_ai.IncompleteReply('Test limit')
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    async def scenario():
        service=ChatService();await service.startup()
        try:
            original=service.ai_settings()['selected_model']
            chat=service.create_conversation('simulation')
            job=await service.submit(chat['id'],'How is it?',1,'first',frame(),{})
            assert (await terminal(service,job['id']))['state']=='incomplete'
            service.select_model('qwen3.5:4b',0)
            current=service.get_conversation(chat['id'])
            continued=await service.submit(chat['id'],'',current['revision'],'continue',frame(),{},'continue',job['id'])
            assert (await terminal(service,continued['id']))['state']=='incomplete'
            current=service.get_conversation(chat['id'])
            retry=await service.submit(chat['id'],'',current['revision'],'retry',frame(),{},'retry',continued['id'])
            assert (await terminal(service,retry['id']))['state']=='completed'
            assert seen==[original,original,'qwen3.5:4b']
            assert service.get_job(job['id'])['provider']['model']==original
        finally:await service.shutdown()
        restored=ChatService();await restored.startup()
        try:assert restored.ai_settings()['selected_model']=='qwen3.5:4b'
        finally:await restored.shutdown()
    asyncio.run(scenario())


def test_warmup_blocks_switch_and_cancelled_waiting_job_never_runs(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB',tmp_path/'warm.db')
    gate=asyncio.Event()
    called=[]
    async def preload(model):await gate.wait()
    async def stream(question,*args,**kwargs):
        called.append(question)
        yield 'A complete answer.'
    monkeypatch.setattr(rill_models,'preload',preload)
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    async def scenario():
        service=ChatService();await service.startup()
        try:
            settings=service.ai_settings()
            assert service.prepare_model(settings['selected_model'])['warming']
            with pytest.raises(ChatError):service.select_model('qwen3.5:4b',settings['revision'])
            chat=service.create_conversation('simulation')
            job=await service.submit(chat['id'],'Cancelled while preparing',1,'first',frame(),{})
            assert not called
            await service.cancel(job['id'])
            another=service.create_conversation('simulation')
            queued=await service.submit(another['id'],'Next question',1,'next',frame(),{})
            gate.set()
            assert (await terminal(service,queued['id']))['state']=='completed'
            assert called==['Next question']
            assert not service.ai_settings()['warming']
            assert service.get_conversation(chat['id'])['failure']['question']=='Cancelled while preparing'
        finally:await service.shutdown()
    asyncio.run(scenario())


def test_batched_tokens_preserve_partial_when_stream_fails(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB',tmp_path/'batch.db')
    async def stream(*args,telemetry=None,**kwargs):
        telemetry['eval_count']=201
        for _ in range(201):yield 'word '
        raise rill_ai.RillError('Test interruption')
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    async def scenario():
        service=ChatService();await service.startup()
        try:
            chat=service.create_conversation('simulation')
            job=await service.submit(chat['id'],'Explain?',1,'first',frame(),{})
            done=await terminal(service,job['id'])
            assert done['state']=='failed'
            assert done['text']=='word '*201
            assert done['sequence']<20  # Batches, not a durable transaction per token.
            assert done['metrics']['eval_count']==201
            assert done['metrics']['first_token_seconds']>=0
            assert service.get_conversation(chat['id'])['failure']['partial']==done['text']
        finally:await service.shutdown()
    asyncio.run(scenario())


def test_cancel_flushes_buffered_tokens_without_restarting_reply(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB',tmp_path/'cancel.db')
    buffered=asyncio.Event()
    async def stream(*args,**kwargs):
        yield 'First '
        yield 'buffered '
        buffered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    async def scenario():
        service=ChatService();await service.startup()
        try:
            chat=service.create_conversation('simulation')
            job=await service.submit(chat['id'],'Explain?',1,'cancel',frame(),{})
            await asyncio.wait_for(buffered.wait(),3)
            done=await service.cancel(job['id'])
            assert done['state']=='cancelled'
            assert done['text']=='First buffered '
            assert service.get_conversation(chat['id'])['failure']['partial']=='First buffered '
        finally:await service.shutdown()
    asyncio.run(scenario())


def test_remote_retag_is_rejected_before_sending_question(monkeypatch):
    monkeypatch.setenv('RILL_PROVIDER','ollama')
    monkeypatch.setattr(rill_ai,'HOST','http://127.0.0.1:11434')
    requests=[]
    def respond(request):
        requests.append(request)
        return httpx.Response(200,json={'remote_host':'https://ollama.com','capabilities':['completion']})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(rill_ai.RillError,match='not a local chat model'):
                async for _ in rill_ai.async_chat_stream('Private river question',[],rill_ai.context_data(frame()),
                                                         client=client,model='renamed-alias',require_local=True):pass
        assert [request.url.path for request in requests]==['/api/show']
        assert 'Private river question' not in requests[0].content.decode()
    asyncio.run(scenario())


def test_preload_is_empty_and_failed_preparation_releases_busy(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB',tmp_path/'failed-warm.db')
    requests=[]
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={'done':True})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            await rill_models.preload('qwen3.5:4b',client)
        assert requests==[{'model':'qwen3.5:4b','messages':[],'stream':False,'keep_alive':'15m',
                           'options':{'num_ctx':4096,'num_predict':256}}]
        async def failed(model):raise rill_ai.RillError('Not enough memory')
        monkeypatch.setattr(rill_models,'preload',failed)
        service=ChatService();await service.startup()
        try:
            settings=service.ai_settings()
            service.prepare_model(settings['selected_model'])
            await asyncio.sleep(0)
            assert not service.ai_settings()['warming']
            assert service.ai_settings()['warm_error']=='Not enough memory'
            assert service.list_conversations('simulation')==[]
            assert service.select_model('qwen3.5:4b',0)['selected_model']=='qwen3.5:4b'
        finally:await service.shutdown()
    asyncio.run(scenario())


def test_deleted_chat_during_prepare_does_not_stop_next_reply(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB',tmp_path/'deleted-warm.db')
    gate=asyncio.Event()
    async def preload(model):await gate.wait()
    calls=[]
    async def stream(question,*args,**kwargs):
        calls.append(question)
        yield 'A complete answer.'
    monkeypatch.setattr(rill_models,'preload',preload)
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    async def scenario():
        service=ChatService();await service.startup()
        try:
            service.prepare_model(service.ai_settings()['selected_model'])
            chat=service.create_conversation('simulation')
            await service.submit(chat['id'],'Deleted question',1,'deleted',frame(),{})
            service.delete(chat['id'],service.get_conversation(chat['id'])['revision'])
            other=service.create_conversation('simulation')
            queued=await service.submit(other['id'],'Remaining question',1,'next',frame(),{})
            gate.set()
            assert (await terminal(service,queued['id']))['state']=='completed'
            assert calls==['Remaining question']
        finally:await service.shutdown()
    asyncio.run(scenario())
