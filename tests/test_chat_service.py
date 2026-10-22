"""Durable chat, concurrency and transport tests; no model or real DB required."""
import asyncio
import json
import time

import httpx
import pandas as pd
import pytest

import core
import rill_ai
from chat_service import ChatService, ChatError, TERMINAL


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(core,'DB',tmp_path/'chat.db')
    monkeypatch.setenv('RILL_PROVIDER','ollama')


def frame(ph=7.1):
    return pd.DataFrame([dict(timestamp=pd.Timestamp.now(tz='UTC').isoformat(),source='simulation',
                             device_id='demo',ph=ph,turbidity=12.,temperature=27.,water_level=30.,
                             calibrated=True,anomaly=False)])


async def terminal(service,job_id):
    async with asyncio.timeout(3):
        while service.get_job(job_id)['state'] not in TERMINAL:
            await asyncio.sleep(.005)
    return service.get_job(job_id)


def test_atomic_append_idempotency_and_stale_tab_conflict(monkeypatch):
    gate=asyncio.Event()
    async def stream(*args,**kwargs):
        await gate.wait()
        yield 'A complete answer.'
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    async def scenario():
        service=ChatService(); await service.startup()
        try:
            chat=service.create_conversation('simulation')
            job=await service.submit(chat['id'],'Question A',chat['revision'],'request-A',frame(),{})
            duplicate=await service.submit(chat['id'],'Question A',chat['revision'],'request-A',frame(),{})
            assert duplicate['id']==job['id']
            with pytest.raises(ChatError) as exc:
                await service.submit(chat['id'],'Question B',chat['revision'],'request-B',frame(),{})
            assert exc.value.status==409
            assert service.get_conversation(chat['id'])['messages']==[{'role':'user','content':'Question A'}]
            gate.set(); assert (await terminal(service,job['id']))['state']=='completed'
            current=service.get_conversation(chat['id'])
            assert len(current['messages'])==2
            assert current['messages'][-1]['content']=='A complete answer.'
            with pytest.raises(ChatError):
                await service.submit(chat['id'],'Different',current['revision'],'request-A',frame(),{})
        finally:
            await service.shutdown()
    asyncio.run(scenario())


def test_job_identifies_exact_turn_when_answers_repeat(monkeypatch):
    async def stream(*args,**kwargs):
        yield 'A complete answer.'
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    async def scenario():
        service=ChatService();await service.startup()
        try:
            chat=service.create_conversation('simulation')
            jobs=[]
            for index in range(2):
                current=service.get_conversation(chat['id'])
                job=await service.submit(chat['id'],'Repeated question',current['revision'],f'repeated-{index}',frame(),{})
                done=await terminal(service,job['id'])
                assert done['state']=='completed'
                assert done['user_index']==index*2
                jobs.append(done)
            current=service.get_conversation(chat['id'])
            for job in jobs:
                assert current['messages'][job['user_index']]['content']==job['question']
                assert current['messages'][job['user_index']+1]['content']==job['text']
            assert service.get_job(jobs[0]['id'])['user_index']==0
        finally:
            await service.shutdown()
    asyncio.run(scenario())


@pytest.mark.parametrize('endpoint', ['conversation', 'job'])
def test_reply_completion_cannot_mix_read_snapshots(monkeypatch, endpoint):
    async def stream(*args,**kwargs):
        await asyncio.Event().wait()
        yield 'Not reached'
    monkeypatch.setattr(rill_ai, 'async_chat_stream', stream)
    async def scenario():
        service=ChatService();await service.startup()
        try:
            chat=service.create_conversation('simulation')
            job=await service.submit(chat['id'],'Keep this question',1,'snapshot',frame(),{})
            before=service.get_conversation(chat['id'])
            original=service._conversation
            triggered=False
            def complete_between_reads(con, chat_id):
                nonlocal triggered
                if triggered:
                    return original(con,chat_id)
                triggered=True
                if endpoint=='conversation':
                    row=original(con,chat_id)
                service._finish(job['id'],'failed','Test interruption')
                return row if endpoint=='conversation' else original(con,chat_id)
            monkeypatch.setattr(service,'_conversation',complete_between_reads)
            snapshot=(service.get_conversation(chat['id']) if endpoint=='conversation'
                      else service.get_job(job['id']))
            assert triggered
            assert snapshot['revision']==before['revision']
            if endpoint=='conversation':
                assert snapshot['active_job']==job['id']
                assert snapshot['failure'] is None
            else:
                assert snapshot['state'] in ('queued','generating')
            current=service.get_conversation(chat['id'])
            assert current['revision']==before['revision']+1
            assert current['active_job'] is None
            assert current['failure']['job_id']==job['id']
        finally:
            await service.shutdown()
    asyncio.run(scenario())


def test_cancel_blocked_read_releases_worker_and_queue_is_bounded(monkeypatch):
    blocked=asyncio.Event(); cancelled=asyncio.Event()
    async def stream(question,*args,**kwargs):
        if question=='Blocked':
            try:
                await blocked.wait()
            finally:
                cancelled.set()
        yield question+' answer'
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    async def scenario():
        service=ChatService(); await service.startup()
        try:
            chats=[service.create_conversation('simulation') for _ in range(5)]
            first=await service.submit(chats[0]['id'],'Blocked',1,'first',frame(),{})
            waiting=[]
            for i in range(1,4):
                waiting.append(await service.submit(chats[i]['id'],f'Queued {i}',1,f'req-{i}',frame(),{}))
            assert [service.get_job(item['id'])['queue_position'] for item in waiting]==[1,2,3]
            with pytest.raises(ChatError) as exc:
                await service.submit(chats[4]['id'],'Too many',1,'overflow',frame(),{})
            assert exc.value.status==429
            assert service.get_conversation(chats[4]['id'])['messages']==[]
            start=time.monotonic()
            result=await service.cancel(first['id'])
            assert result['state']=='cancelled'
            assert time.monotonic()-start<1
            assert cancelled.is_set()
            for job in waiting:
                assert (await terminal(service,job['id']))['state']=='completed'
            assert service.get_conversation(chats[0]['id'])['failure']['question']=='Blocked'
        finally:
            await service.shutdown()
    asyncio.run(scenario())


def test_refresh_keeps_healthy_job_and_sse_disconnect_does_not_cancel(monkeypatch):
    gate=asyncio.Event()
    async def stream(*args,**kwargs):
        yield 'Partial '
        await gate.wait()
        yield 'answer.'
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    async def scenario():
        service=ChatService();await service.startup()
        try:
            chat=service.create_conversation('simulation')
            job=await service.submit(chat['id'],'A question',1,'request',frame(),{})
            await service.startup()  # repeated lifespan/init must not recover healthy work
            current=service.get_conversation(chat['id'])
            assert current['active_job']==job['id']
            assert current['failure'] is None
            stream_events=service.events(job['id'])
            event=await anext(stream_events)
            assert 'event: reply' in event
            await stream_events.aclose()  # browser closes, generation remains alive
            assert service.get_job(job['id'])['state'] in ('queued','generating')
            gate.set();finished=await terminal(service,job['id'])
            replay=[event async for event in service.events(job['id'],after=finished['sequence']-1)]
            assert len(replay)==1 and 'Partial answer.' in replay[0]
            assert service.get_conversation(chat['id'])['failure'] is None
        finally:
            await service.shutdown()
    asyncio.run(scenario())


def test_retry_is_fresh_and_continue_retains_original_snapshot(monkeypatch):
    calls=[]
    async def stream(question,history,context,continuation,**kwargs):
        calls.append((context,continuation))
        if len(calls)==1:
            yield 'The river '
            raise rill_ai.IncompleteReply('Length limit')
        if len(calls)==2:
            yield 'is calm.'
            raise rill_ai.IncompleteReply('Another limit')
        yield 'A fresh answer.'
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    async def scenario():
        service=ChatService();await service.startup()
        try:
            chat=service.create_conversation('simulation')
            job=await service.submit(chat['id'],'How is it?',1,'initial',frame(7.1),{})
            assert (await terminal(service,job['id']))['state']=='incomplete'
            chat=service.get_conversation(chat['id'])
            continuation=await service.submit(chat['id'],'',chat['revision'],'continue',frame(8.2),{},'continue',job['id'])
            finished=await terminal(service,continuation['id'])
            assert finished['text']=='The river is calm.'
            assert calls[1][0]['latest']['ph']==7.1
            assert calls[1][1]=='The river '
            chat=service.get_conversation(chat['id'])
            retry=await service.submit(chat['id'],'',chat['revision'],'retry',frame(8.2),{},'retry',continuation['id'])
            assert (await terminal(service,retry['id']))['state']=='completed'
            assert calls[2][0]['latest']['ph']==8.2
            assert calls[2][1]==''
            messages=service.get_conversation(chat['id'])['messages']
            assert messages==[{'role':'user','content':'How is it?'},{'role':'assistant','content':'A fresh answer.'}]
        finally:
            await service.shutdown()
    asyncio.run(scenario())


def test_migrates_legacy_messages_failure_title_without_resurrection():
    with core.connect() as con:
        con.execute('CREATE TABLE rill_conversations(id TEXT PRIMARY KEY,source TEXT,payload TEXT,attempt TEXT,created REAL,updated REAL)')
        data={'title':'Saved river chat','messages':[{'role':'user','content':'Cloudy?'}],
              'failure':{'question':'Cloudy?','messages':[],'error':'Limited','partial':'Old partial','retry_until':0}}
        con.execute('INSERT INTO rill_conversations VALUES (?,?,?,?,?,?)',('legacy','simulation',json.dumps(data),None,1,2))
    async def scenario():
        service=ChatService();await service.startup()
        chat=service.get_conversation('legacy')
        assert chat['title']=='Saved river chat'
        assert chat['messages']==data['messages']
        assert chat['failure']['partial']=='Old partial'
        assert service.get_job(chat['failure']['job_id'])['text']=='Old partial'
        renamed=service.rename('legacy','Renamed',chat['revision'])
        assert renamed['title']=='Renamed'
        with pytest.raises(ChatError): service.delete('legacy',chat['revision'])
        service.delete('legacy',renamed['revision'])
        await service.shutdown()
        replacement=ChatService();await replacement.startup()
        assert replacement.list_conversations('simulation')==[]
        await replacement.shutdown()
    asyncio.run(scenario())


def test_crashed_jobs_recover_only_on_startup(monkeypatch):
    async def stream(*args,**kwargs):
        yield 'Stored partial'
        await asyncio.Event().wait()
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    async def scenario():
        service=ChatService();await service.startup()
        chat=service.create_conversation('simulation')
        job=await service.submit(chat['id'],'Explain',1,'request',frame(),{})
        while service.get_job(job['id'])['text']!='Stored partial':await asyncio.sleep(.005)
        # Model a process exit: leave its persisted state active, but end the
        # task without invoking normal service terminal handling.
        original_finish=service._finish
        service._finish=lambda *args,**kwargs:None
        await service.shutdown()
        service._finish=original_finish
        replacement=ChatService();await replacement.startup()
        try:
            restored=replacement.get_job(job['id'])
            assert restored['state']=='failed' and restored['text']=='Stored partial'
            assert replacement.get_conversation(chat['id'])['failure']['job_id']==job['id']
        finally:
            await replacement.shutdown()
    asyncio.run(scenario())


def test_async_transport_detects_truncation_eof_and_cancels_socket(monkeypatch):
    async def scenario():
        for ending in ('{"done":true,"done_reason":"length"}\n',''):
            content='{"message":{"content":"Partial"}}\n'+ending
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,text=content))) as client:
                tokens=[]
                with pytest.raises(rill_ai.IncompleteReply):
                    async for token in rill_ai.async_chat_stream('Hi',[],{},client=client):tokens.append(token)
                assert tokens==['Partial']
        entered=asyncio.Event();closed=asyncio.Event()
        class BlockedBody(httpx.AsyncByteStream):
            async def __aiter__(self):
                entered.set()
                await asyncio.Event().wait()
                yield b''
            async def aclose(self):closed.set()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=BlockedBody()))) as client:
            async def consume():
                async for token in rill_ai.async_chat_stream('Hi',[],{},client=client):pass
            task=asyncio.create_task(consume());await entered.wait();task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            assert closed.is_set()
    asyncio.run(scenario())


def test_actual_provider_label_and_typed_timestamp(monkeypatch):
    monkeypatch.setattr(rill_ai,'HOST','http://192.0.2.2:11434')
    assert rill_ai.provider_info()['label']=='Remote Ollama'
    assert not rill_ai.provider_info()['local']
    monkeypatch.setattr(rill_ai,'HOST','http://[::1]:11434')
    assert rill_ai.provider_info()['local']
    data=frame();data['timestamp']=pd.to_datetime(data.timestamp,utc=True)
    result=rill_ai.context_data(data)
    assert result['latest_sample_age_seconds']<5
    assert not result['stale']


def test_model_errors_are_actionable_and_do_not_leak_raw_payload():
    async def scenario():
        for code,body,expected in [(404,'model missing','not installed'),(500,'failed to allocate memory secret-credential','memory')]:
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(code,text=body))) as client:
                with pytest.raises(rill_ai.RillError) as exc:
                    async for token in rill_ai.async_chat_stream('Hi',[],{},client=client):pass
                assert expected in str(exc.value)
                assert 'secret-credential' not in str(exc.value)
    asyncio.run(scenario())


def test_cloud_backoff_and_failed_question_survive_service_restart(monkeypatch):
    async def stream(*args,**kwargs):
        yield 'Saved partial'
        raise rill_ai.RillError('Cloud limit',retry_after=20)
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    async def scenario():
        service=ChatService();await service.startup()
        chat=service.create_conversation('simulation')
        job=await service.submit(chat['id'],'Keep my question',1,'initial',frame(),{})
        failed=await terminal(service,job['id'])
        assert time.time()<failed['retry_at']<=time.time()+20
        current=service.get_conversation(chat['id'])
        with pytest.raises(ChatError) as exc:
            await service.submit(chat['id'],'',current['revision'],'too-soon',frame(),{},'retry',job['id'])
        assert exc.value.status==429
        await service.shutdown()
        replacement=ChatService();await replacement.startup()
        try:
            restored=replacement.get_conversation(chat['id'])
            assert restored['messages']==[{'role':'user','content':'Keep my question'}]
            assert restored['failure']['partial']=='Saved partial'
            assert restored['failure']['retry_at']==failed['retry_at']
        finally:
            await replacement.shutdown()
    asyncio.run(scenario())


def test_older_single_chat_pending_migrates_and_deleted_job_cannot_restore(monkeypatch):
    with core.connect() as con:
        con.execute('CREATE TABLE rill_chats(source TEXT PRIMARY KEY,payload TEXT,attempt TEXT)')
        data={'messages':[{'role':'user','content':'Old pending?'}],
              'pending':{'question':'Old pending?','messages':[]},'title':'First install'}
        con.execute('INSERT INTO rill_chats VALUES (?,?,?)',('simulation',json.dumps(data),'old-attempt'))
    async def stream(*args,**kwargs):
        await asyncio.Event().wait()
        yield 'Must not restore'
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    async def scenario():
        service=ChatService();await service.startup()
        try:
            [listed]=service.list_conversations('simulation')
            migrated=service.get_conversation(listed['id'])
            assert migrated['title']=='First install'
            assert migrated['messages']==data['messages']
            assert migrated['failure']['question']=='Old pending?'
            retried=await service.submit(migrated['id'],'',migrated['revision'],'retry',frame(),{},'retry',migrated['failure']['job_id'])
            current=service.get_conversation(migrated['id'])
            service.delete(current['id'],current['revision'])
            await asyncio.sleep(.01)
            with pytest.raises(ChatError) as exc:service.get_job(retried['id'])
            assert exc.value.status==404
            assert service.list_conversations('simulation')==[]
        finally:
            await service.shutdown()
    asyncio.run(scenario())


def test_grounding_orders_measurements_masks_legacy_faults_and_marks_future():
    now=pd.Timestamp.now(tz='UTC')
    newest=frame(8.2).iloc[0].to_dict()
    newest.update(timestamp=now.isoformat(),sensor_health_json='{"ph":"missing","water_level":"timeout"}')
    old=frame(7.1).iloc[0].to_dict();old['timestamp']=(now-pd.Timedelta(seconds=10)).isoformat()
    # Arrival order deliberately puts an old packet last.
    data=rill_ai.context_data(pd.DataFrame([newest,old]))
    assert data['latest']['timestamp']==now.isoformat()
    assert data['latest']['ph'] is None and data['latest']['water_level'] is None
    assert not data['latest']['calibrated']
    assert data['dashboard_status']['title']=='Part of the picture is missing'
    assert 'ph' not in data.get('change_since_previous_sample',{})
    assert not any(item['kind']=='level' for item in data['signals'])
    future=frame();future['timestamp']=(now+pd.Timedelta(minutes=1)).isoformat()
    data=rill_ai.context_data(future)
    assert data['latest_sample_age_seconds'] < -5
    assert data['stale'] and data['clock_ahead']
    assert data['dashboard_status']['title']=='Check the station clock'
    assert data['signals']==[]
    encoded=rill_ai._payload('Now?',[],data,compact=False)['messages'][-2]['content'].split(': ',1)[1]
    refreshed=json.loads(encoded)
    assert refreshed['clock_ahead'] and refreshed['stale']


def test_grounding_handles_partial_frames_without_inventing_values():
    partial=pd.DataFrame([{'timestamp':pd.Timestamp.now(tz='UTC').isoformat(),'ph':7.2}])
    data=rill_ai.context_data(partial)
    assert data['latest']['ph']==7.2
    assert data['latest']['water_level'] is None
    assert data['latest']['device_id'] is None
    assert data['dashboard_status']['title']=='Part of the picture is missing'


def test_unverified_reply_is_not_completed_and_cannot_be_continued(monkeypatch):
    calls=[]
    async def stream(*args,**kwargs):
        calls.append(args)
        yield ('In this demo, the water is safe to drink.' if len(calls)==1
               else 'In this demo, these sensors cannot establish drinking-water safety.')
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    async def scenario():
        service=ChatService();await service.startup()
        try:
            chat=service.create_conversation('simulation')
            job=await service.submit(chat['id'],'Can I drink our river water?',1,'first',frame(),{})
            failed=await terminal(service,job['id'])
            assert failed['state']=='incomplete'
            assert failed['verification']['passed'] is False
            chat=service.get_conversation(chat['id'])
            assert len(chat['messages'])==1
            assert chat['failure']['partial']==failed['text']
            assert chat['failure']['verification']['can_continue'] is False
            with pytest.raises(ChatError):
                await service.submit(chat['id'],'',chat['revision'],'continue',frame(),{},'continue',job['id'])
            retry=await service.submit(chat['id'],'',chat['revision'],'retry',frame(),{},'retry',job['id'])
            assert (await terminal(service,retry['id']))['state']=='completed'
            assert len(service.get_conversation(chat['id'])['messages'])==2
        finally:await service.shutdown()
    asyncio.run(scenario())


def test_unsafe_partial_at_token_limit_cannot_be_continued(monkeypatch):
    async def stream(*args,**kwargs):
        yield 'In this demo, this water is safe to drink.'
        raise rill_ai.IncompleteReply('Token limit')
    monkeypatch.setattr(rill_ai,'async_chat_stream',stream)
    async def scenario():
        service=ChatService();await service.startup()
        try:
            chat=service.create_conversation('simulation')
            job=await service.submit(chat['id'],'Can I drink our water?',1,'unsafe',frame(),{})
            failed=await terminal(service,job['id'])
            assert not failed['verification']['can_continue']
            chat=service.get_conversation(chat['id'])
            with pytest.raises(ChatError):
                await service.submit(chat['id'],'',chat['revision'],'continue',frame(),{},'continue',job['id'])
            assert len(chat['messages'])==1
        finally:await service.shutdown()
    asyncio.run(scenario())
