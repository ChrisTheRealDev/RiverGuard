"""Background generation; worker threads never call Streamlit APIs."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from time import monotonic
from math import ceil
from rill_ai import chat_stream, RillError, provider

POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix='rill')

class ReplyJob:
    def __init__(self,question,messages,frame,elevated,warning,rise_limit,persist=None):
        self.question=question
        self.persist=persist
        self.messages=[dict(message) for message in messages]
        self.created=monotonic()
        self.stop=Event()
        self.lock=Lock()
        self.text=''
        self.stage='Queued'
        self.error=None
        self.retry_at=0
        self.done=False
        self.sample=str(frame.iloc[-1].timestamp) if not frame.empty else None
        self.future=POOL.submit(self._run,self.messages,frame.copy(),elevated,warning,rise_limit)

    def _run(self,messages,frame,elevated,warning,rise_limit):
        try:
            with self.lock: self.stage='Thinking'
            if self.stop.is_set(): return
            for token in chat_stream(self.question,messages,frame,elevated,warning,rise_limit):
                if self.stop.is_set(): break
                with self.lock:
                    self.stage='Writing'
                    self.text+=token
            if not self.text and not self.stop.is_set(): raise RuntimeError('Empty response')
        except Exception as exc:
            message=str(exc) if isinstance(exc,RillError) else ('Cloud chat couldn’t finish that reply. Check your connection and try again.' if provider()=='gemini' else 'The local model couldn’t finish that reply. Check Ollama and try again.')
            with self.lock: self.error=message
            self.retry_at=monotonic()+max(0,getattr(exc,'retry_after',0))
        finally:
            if self.persist:
                from rill_store import finish
                try:
                    finish(*self.persist,self.text,self.error or ('Reply stopped. You can retry your question.' if self.stop.is_set() else None),self.retry_at)
                except Exception:
                    with self.lock: self.error='Rill could not save this reply locally. Your question is still in the chat; please retry.'
            with self.lock: self.done=True

    def poll(self):
        with self.lock:
            return dict(text=self.text,stage=self.stage,error=self.error,done=self.done,elapsed=int(monotonic()-self.created),sample=self.sample,retry_at=self.retry_at,retry_in=max(0,ceil(self.retry_at-monotonic())))

    def cancel(self):
        self.stop.set()
        self.future.cancel()
