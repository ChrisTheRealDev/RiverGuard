from threading import Event
import pandas as pd
import rill_jobs

def test_reply_runs_in_background_and_streams(monkeypatch):
    gate=Event()
    def tokens(*args):
        yield 'Hello '
        gate.wait(3)
        yield 'river'
    monkeypatch.setattr(rill_jobs,'chat_stream',tokens)
    job=rill_jobs.ReplyJob('hello',[],pd.DataFrame(),70,100,10)
    # The call returned while generation is still blocked in another thread.
    assert not job.future.done()
    gate.set();job.future.result(timeout=4)
    assert job.poll()['text']=='Hello river'
    assert job.poll()['done']

def test_failed_generation_is_reported(monkeypatch):
    def broken(*args):
        raise RuntimeError('unavailable')
        yield
    monkeypatch.setattr(rill_jobs,'chat_stream',broken)
    job=rill_jobs.ReplyJob('hello',[],pd.DataFrame(),70,100,10)
    job.future.result(timeout=3)
    assert job.poll()['error']

def test_limit_keeps_retry_context_and_partial_reply(monkeypatch):
    def limited(*args):
        yield 'An unfinished answer'
        raise rill_jobs.RillError('Please retry',retry_after=5)
    monkeypatch.setattr(rill_jobs,'chat_stream',limited)
    past=[{'role':'assistant','content':'Earlier reply'}]
    job=rill_jobs.ReplyJob('What changed?',past,pd.DataFrame(),70,100,10)
    past.clear()
    job.future.result(timeout=3)
    state=job.poll()
    assert state['text']=='An unfinished answer'
    assert state['error']=='Please retry'
    assert 0<state['retry_in']<=5
    assert job.question=='What changed?'
    assert job.messages==[{'role':'assistant','content':'Earlier reply'}]
