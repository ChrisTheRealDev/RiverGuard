from time import monotonic
import core
import rill_store as store
import rill_jobs
import pandas as pd
import pytest

@pytest.fixture(autouse=True)
def database(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB',tmp_path/'chat.db')

def test_chat_and_failure_survive_reload_with_wall_clock_backoff():
    messages=[{'role':'user','content':'What changed?'}]
    failure=dict(question='What changed?',messages=[],partial='A partial reply',error='Limited',retry_at=monotonic()+30)
    store.save('simulation',messages,failure)
    restored=store.load('simulation')
    assert restored['messages']==messages
    assert restored['failure']['partial']=='A partial reply'
    assert 0<restored['failure']['retry_at']-monotonic()<=30
    assert store.load('esp32') is None

def test_pending_request_restores_as_retryable_after_restart():
    messages=[{'role':'user','content':'pH?'}]
    store.begin('simulation','pH?',[],messages)
    restored=store.load('simulation')
    assert restored['messages']==messages
    assert restored['failure']['question']=='pH?'
    assert 'interrupted' in restored['failure']['error']
    assert restored['failure']['retry_at']<=monotonic()

def test_late_worker_cannot_overwrite_cleared_or_newer_conversation():
    token=store.begin('simulation','old?',[],[{'role':'user','content':'old?'}])
    store.save('simulation',[])
    store.finish('simulation',token,'Old answer')
    assert store.load('simulation')['messages']==[]
    first=store.begin('simulation','first?',[],[])
    second=store.begin('simulation','second?',[],[])
    store.finish('simulation',first,'Wrong answer')
    assert store.load('simulation')['failure']['question']=='second?'
    store.finish('simulation',second,'Current answer')
    assert store.load('simulation')['messages']==[{'role':'assistant','content':'Current answer'}]

def test_background_reply_is_saved_without_ui_polling(monkeypatch):
    monkeypatch.setattr(rill_jobs,'chat_stream',lambda *args:iter(['Saved reply']))
    token=store.begin('simulation','pH?',[],[{'role':'user','content':'pH?'}])
    job=rill_jobs.ReplyJob('pH?',[],pd.DataFrame(),70,100,10,persist=('simulation',token))
    job.future.result(timeout=5)
    assert store.load('simulation')['messages'][-1]['content']=='Saved reply'

def test_background_failure_is_durable(monkeypatch):
    def limited(*args):
        yield 'Partial'
        raise rill_jobs.RillError('Cloud limit',retry_after=20)
    monkeypatch.setattr(rill_jobs,'chat_stream',limited)
    token=store.begin('simulation','pH?',[],[{'role':'user','content':'pH?'}])
    job=rill_jobs.ReplyJob('pH?',[],pd.DataFrame(),70,100,10,persist=('simulation',token))
    job.future.result(timeout=5)
    restored=store.load('simulation')
    assert restored['failure']['partial']=='Partial'
    assert restored['failure']['question']=='pH?'
    assert restored['messages']==[{'role':'user','content':'pH?'}]


def test_new_chat_preserves_history_and_retry_state():
    old_question=[{'role':'user','content':'Cloudy water?'}]
    store.save('simulation',old_question,dict(question='Cloudy water?',messages=[],error='Cloud limit',partial='Partial answer',retry_at=monotonic()+20))
    old_id=store.active('simulation')
    new_id=store.new_conversation('simulation')
    assert new_id!=old_id
    assert store.load('simulation')['messages']==[]
    assert store.load('simulation',old_id)['failure']['question']=='Cloudy water?'
    assert len(store.conversations('simulation'))==2
    assert store.conversations('simulation')[1]['title']=='Cloudy water?'
    store.activate('simulation',old_id)
    assert store.load('simulation')['messages']==old_question
    assert store.load('simulation')['failure']['partial']=='Partial answer'
    with pytest.raises(ValueError): store.activate('esp32',old_id)
    assert store.new_conversation('esp32') not in (old_id,new_id)

def test_background_reply_stays_in_original_chat_after_switch():
    first=store.new_conversation('simulation')
    token=store.begin('simulation','First question',[],[{'role':'user','content':'First question'}],chat_id=first)
    second=store.new_conversation('simulation')
    store.finish('simulation',token,'First answer')
    assert store.active('simulation')==second
    assert store.load('simulation',second)['messages']==[]
    assert store.load('simulation',first)['messages'][-1]['content']=='First answer'

def test_migrates_legacy_chat_without_losing_failure():
    import json
    with core.connect() as con:
        con.execute('CREATE TABLE rill_chats (source TEXT PRIMARY KEY, payload TEXT NOT NULL, attempt TEXT)')
        data=dict(messages=[{'role':'user','content':'Legacy question'}],failure=dict(question='Legacy question',messages=[],error='Limited',retry_until=0))
        con.execute('INSERT INTO rill_chats VALUES (?,?,NULL)',('simulation',json.dumps(data)))
    assert store.load('simulation')['failure']['question']=='Legacy question'
    assert store.conversations('simulation')[0]['title']=='Legacy question'
    store.new_conversation('simulation')
    assert len(store.conversations('simulation'))==2
    assert len(store.conversations('simulation'))==2


def test_rename_persists_through_replies_and_validates_name():
    chat=store.new_conversation('simulation')
    store.rename('simulation',chat,'  River   check  ')
    store.save('simulation',[{'role':'user','content':'pH?'}],chat_id=chat)
    token=store.begin('simulation','pH?',[],[{'role':'user','content':'pH?'}],chat_id=chat)
    store.finish('simulation',token,'Answer')
    assert store.conversations('simulation')[0]['title']=='River check'
    for invalid in ['   ','a'*65]:
        with pytest.raises(ValueError): store.rename('simulation',chat,invalid)
    with pytest.raises(ValueError): store.rename('esp32',chat,'Wrong source')

def test_delete_only_selected_chat_and_late_reply_cannot_restore_it():
    first=store.new_conversation('simulation')
    store.save('simulation',[{'role':'user','content':'First?'}],chat_id=first)
    second=store.new_conversation('simulation')
    token=store.begin('simulation','Second?',[],[{'role':'user','content':'Second?'}],chat_id=second)
    with pytest.raises(ValueError): store.delete('esp32',first)
    assert store.delete('simulation',second)==first
    store.finish('simulation',token,'Late answer')
    assert store.load('simulation',second) is None
    assert store.load('simulation')['messages'][0]['content']=='First?'
    next_chat=store.delete('simulation',first)
    assert next_chat not in (first,second)
    assert store.load('simulation')['messages']==[]
