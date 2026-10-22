"""Server-owned durable Rill chat and cancellable generation.

The browser submits intentions, never an authoritative transcript. SQLite
transactions protect revisions, request idempotency and the bounded queue.
Only API startup recovers jobs left by an earlier process; reconnecting a
browser simply reads the same job and can resume its event stream.
"""
import asyncio
from contextlib import contextmanager
import json
import time
from uuid import uuid4

import rill_ai
from core import connect


ACTIVE = ('queued', 'generating')
TERMINAL = ('completed', 'failed', 'cancelled', 'incomplete')


class ChatError(RuntimeError):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class ChatService:
    def __init__(self):
        # Importing this module never opens the production database.
        self._started = False
        self._closing = False
        self._worker = None
        self._generation_tasks = {}
        self._wake = None
        self._warm_task = None
        self._warming = False
        self._warm_error = None

    @contextmanager
    def _db(self, write=False):
        con = connect()
        con.row_factory = __import__('sqlite3').Row
        try:
            if write:
                con.execute('BEGIN IMMEDIATE')
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def _initialize(self):
        with self._db() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS chat_conversations (
                    id TEXT PRIMARY KEY, source TEXT NOT NULL, device_id TEXT,
                    title TEXT, messages TEXT NOT NULL, failure TEXT,
                    revision INTEGER NOT NULL, created REAL NOT NULL,
                    updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS chat_jobs (
                    id TEXT PRIMARY KEY, chat_id TEXT NOT NULL,
                    request_id TEXT NOT NULL, question TEXT NOT NULL,
                    mode TEXT NOT NULL, parent_id TEXT,
                    state TEXT NOT NULL, text TEXT NOT NULL, error TEXT,
                    retry_at REAL NOT NULL DEFAULT 0,
                    created REAL NOT NULL, updated REAL NOT NULL,
                    sample TEXT, sequence INTEGER NOT NULL,
                    context TEXT NOT NULL, history TEXT NOT NULL,
                    user_index INTEGER NOT NULL, provider TEXT NOT NULL,
                    UNIQUE(chat_id, request_id));
                CREATE INDEX IF NOT EXISTS chat_jobs_queue ON chat_jobs(state, created);
                CREATE TABLE IF NOT EXISTS rill_ai_settings (
                    id INTEGER PRIMARY KEY CHECK(id=1), model TEXT NOT NULL,
                    revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS chat_migrations (
                    legacy_table TEXT NOT NULL, legacy_id TEXT NOT NULL,
                    PRIMARY KEY(legacy_table, legacy_id));
            ''')
            if 'verification' not in {row['name'] for row in con.execute('PRAGMA table_info(chat_jobs)')}:
                con.execute('ALTER TABLE chat_jobs ADD COLUMN verification TEXT')
            if 'metrics' not in {row['name'] for row in con.execute('PRAGMA table_info(chat_jobs)')}:
                con.execute('ALTER TABLE chat_jobs ADD COLUMN metrics TEXT')
        self._migrate()

    def _migrate(self):
        """Copy old histories once, retaining old tables as untouched backups."""
        with self._db(True) as con:
            tables={row['name'] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            sources=set()
            if 'rill_conversations' in tables:
                for row in con.execute('SELECT * FROM rill_conversations').fetchall():
                    sources.add(row['source'])
                    self._import_legacy(con, 'rill_conversations', row['id'], row['id'], row['source'],
                                        json.loads(row['payload']), row['created'], row['updated'])
            if 'rill_chats' in tables:
                for row in con.execute('SELECT * FROM rill_chats').fetchall():
                    # The legacy store already copied this backup into its
                    # conversations table. Import it only on older installs.
                    if row['source'] in sources:
                        continue
                    self._import_legacy(con, 'rill_chats', row['source'], uuid4().hex,
                                        row['source'], json.loads(row['payload']), time.time(), time.time())

    def _import_legacy(self, con, table, legacy_id, chat_id, source, data, created, updated):
        if con.execute('SELECT 1 FROM chat_migrations WHERE legacy_table=? AND legacy_id=?', (table, legacy_id)).fetchone():
            return
        messages=data.get('messages', [])
        failure=data.get('failure')
        if data.get('pending'):
            failure=dict(data['pending'], error='The app stopped before this reply finished. Your question is saved; retry when ready.', partial='', retry_until=0)
        if failure:
            failure=dict(failure)
            failure['retry_at']=failure.pop('retry_until', 0)
        con.execute('''INSERT OR IGNORE INTO chat_conversations
                       VALUES (?,?,NULL,?,?,?,1,?,?)''',
                    (chat_id, source, data.get('title'), json.dumps(messages),
                     json.dumps(failure) if failure else None, created, updated))
        if failure and failure.get('question'):
            job_id=uuid4().hex
            failure=dict(failure, job_id=job_id)
            question=failure['question']
            index=next((i for i in range(len(messages)-1, -1, -1)
                        if messages[i].get('role')=='user' and messages[i].get('content')==question), len(messages)-1)
            con.execute('''INSERT INTO chat_jobs
                (id,chat_id,request_id,question,mode,parent_id,state,text,error,retry_at,
                 created,updated,sample,sequence,context,history,user_index,provider)
                 VALUES (?,?,?,?,?,NULL,'failed',?,?,?,?,?,NULL,1,?,?,?,?)''',
                (job_id, chat_id, 'legacy:'+job_id, question, 'question', failure.get('partial',''),
                 failure.get('error','Reply interrupted. Retry your saved question.'), failure.get('retry_at',0),
                 updated, updated, '{}', json.dumps(failure.get('messages',messages[:index])), index,
                 json.dumps(rill_ai.provider_info())))
            con.execute('UPDATE chat_conversations SET failure=? WHERE id=?', (json.dumps(failure), chat_id))
        con.execute('INSERT INTO chat_migrations VALUES (?,?)', (table, legacy_id))

    async def startup(self):
        if self._started:
            return
        self._initialize()
        self._wake=asyncio.Event()
        self._closing=False
        # No request from this process exists yet. Only these jobs, persisted
        # before startup, can be classified as interrupted by a process exit.
        with self._db() as con:
            interrupted=[row['id'] for row in con.execute("SELECT id FROM chat_jobs WHERE state IN ('queued','generating')")]
        for job_id in interrupted:
            self._finish(job_id, 'failed', 'The app stopped before this reply finished. Your question and partial reply are saved; retry when ready.')
        self._started=True
        self._worker=asyncio.create_task(self._work(), name='rill-chat-worker')

    async def shutdown(self):
        if not self._started:
            return
        self._closing=True
        if self._warm_task:
            self._warm_task.cancel()
            await asyncio.gather(self._warm_task,return_exceptions=True)
        tasks=list(self._generation_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._worker:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
        with self._db() as con:
            pending=[row['id'] for row in con.execute("SELECT id FROM chat_jobs WHERE state IN ('queued','generating')")]
        for job_id in pending:
            self._finish(job_id, 'failed', 'The app stopped before this reply finished. Retry your saved question when ready.')
        self._generation_tasks.clear()
        self._started=False

    def _require_started(self):
        if not self._started or self._closing:
            raise ChatError(503, 'Chat is starting or shutting down. Try again shortly.')

    @staticmethod
    def _model_settings(con):
        row=con.execute('SELECT model,revision FROM rill_ai_settings WHERE id=1').fetchone()
        return dict(selected_model=row['model'],revision=row['revision']) if row else dict(selected_model=rill_ai.MODEL,revision=0)

    def ai_settings(self):
        self._require_started()
        with self._db() as con:
            con.execute('BEGIN')
            settings=self._model_settings(con)
            active=con.execute("SELECT count(*) FROM chat_jobs WHERE state IN ('queued','generating')").fetchone()[0]
        import rill_models
        return settings | dict(provider=rill_ai.provider_info(settings['selected_model']) | {'host':rill_models.destination()},
                               active_jobs=active,warming=self._warming,warm_error=self._warm_error)

    def select_model(self, model, expected_revision):
        """Called only after exact installed/local metadata validation by the API."""
        self._require_started()
        with self._db(True) as con:
            current=self._model_settings(con)
            if current['revision']!=expected_revision:
                raise ChatError(409,'The AI model changed in another window. Refresh the model list before saving.')
            if self._warming or con.execute("SELECT 1 FROM chat_jobs WHERE state IN ('queued','generating')").fetchone():
                raise ChatError(409,'Wait for Rill to finish or stop its replies before changing models. Preparing a model must also finish first.')
            con.execute('INSERT INTO rill_ai_settings VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET model=excluded.model,revision=excluded.revision',
                        (model,current['revision']+1))
        self._warm_error=None
        return self.ai_settings()

    def prepare_model(self, model):
        """One empty preload, serialized with the single generation worker."""
        self._require_started()
        settings=self.ai_settings()
        if settings['selected_model']!=model:
            raise ChatError(409,'The AI model changed. Refresh the model list before preparing it.')
        if self._warming or settings['active_jobs']:
            return settings
        self._warming=True
        self._warm_error=None
        async def prepare():
            import rill_models
            try:
                await rill_models.preload(model)
            except rill_ai.RillError as exc:
                self._warm_error=str(exc)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._warm_error='Could not prepare the model. Start Ollama and try again.'
            finally:
                self._warming=False
        self._warm_task=asyncio.create_task(prepare(),name='rill-preload')
        return self.ai_settings()

    @staticmethod
    def _conversation(con, chat_id):
        row=con.execute('SELECT * FROM chat_conversations WHERE id=?', (chat_id,)).fetchone()
        if row is None:
            raise ChatError(404, 'Conversation not found.')
        return row

    @staticmethod
    def _check_revision(row, expected_revision):
        if row['revision'] != expected_revision:
            raise ChatError(409, 'This conversation changed in another window. Reload it before trying again.')

    @staticmethod
    def _title(row):
        return row['title'] or next((str(message['content'])[:64] for message in json.loads(row['messages'])
                                    if message.get('role')=='user'), 'New conversation')

    def list_conversations(self, source):
        self._require_started()
        with self._db() as con:
            rows=con.execute('SELECT * FROM chat_conversations WHERE source=? ORDER BY updated DESC,id', (source,)).fetchall()
            return [dict(id=row['id'], source=row['source'], device_id=row['device_id'], title=self._title(row),
                         revision=row['revision'], updated=row['updated'], created=row['created'],
                         needs_retry=bool(row['failure'])) for row in rows]

    def create_conversation(self, source, device_id=None):
        self._require_started()
        if source not in ('simulation', 'esp32'):
            raise ChatError(422, 'Choose simulation or esp32 as the reading source.')
        if device_id is not None and (not isinstance(device_id,str) or not 1<=len(device_id)<=128):
            raise ChatError(422, 'Use a valid station identifier.')
        chat_id=uuid4().hex
        now=time.time()
        with self._db(True) as con:
            con.execute('INSERT INTO chat_conversations VALUES (?,?,?,NULL,?,NULL,1,?,?)',
                        (chat_id, source, device_id, '[]', now, now))
        return self.get_conversation(chat_id)

    def get_conversation(self, chat_id):
        self._require_started()
        with self._db() as con:
            # A reply can finish between these SELECTs. Keep the transcript,
            # revision and active job in the same committed snapshot.
            con.execute('BEGIN')
            row=self._conversation(con, chat_id)
            active=con.execute("SELECT id FROM chat_jobs WHERE chat_id=? AND state IN ('queued','generating') ORDER BY created DESC LIMIT 1", (chat_id,)).fetchone()
            result=dict(id=row['id'], source=row['source'], device_id=row['device_id'], title=self._title(row),
                        revision=row['revision'], created=row['created'], updated=row['updated'],
                        messages=json.loads(row['messages']), failure=json.loads(row['failure']) if row['failure'] else None,
                        active_job=active['id'] if active else None)
        return result

    def rename(self, chat_id, title, expected_revision):
        self._require_started()
        title=' '.join(title.split())
        if not 1<=len(title)<=64:
            raise ChatError(422, 'Use a name between 1 and 64 characters.')
        with self._db(True) as con:
            row=self._conversation(con, chat_id)
            self._check_revision(row, expected_revision)
            con.execute('UPDATE chat_conversations SET title=?,revision=revision+1,updated=? WHERE id=?', (title, time.time(), chat_id))
        return self.get_conversation(chat_id)

    def delete(self, chat_id, expected_revision):
        self._require_started()
        with self._db(True) as con:
            row=self._conversation(con, chat_id)
            self._check_revision(row, expected_revision)
            jobs=[item['id'] for item in con.execute("SELECT id FROM chat_jobs WHERE chat_id=? AND state IN ('queued','generating')", (chat_id,))]
            con.execute('DELETE FROM chat_jobs WHERE chat_id=?', (chat_id,))
            con.execute('DELETE FROM chat_conversations WHERE id=?', (chat_id,))
        for job_id in jobs:
            task=self._generation_tasks.get(job_id)
            if task:
                task.cancel()
        if self._wake:
            self._wake.set()
        return {'deleted':chat_id}

    async def submit(self, chat_id, question, expected_revision, request_id, frame, thresholds,
                     mode='question', job_id=None):
        self._require_started()
        if not isinstance(request_id,str) or not 1<=len(request_id)<=128:
            raise ChatError(422, 'A request identifier between 1 and 128 characters is required.')
        if mode not in ('question', 'retry', 'continue'):
            raise ChatError(422, 'Choose question, retry or continue.')
        question=(question or '').strip()
        if len(question)>1500 or (mode=='question' and not question):
            raise ChatError(422, 'Ask a question between 1 and 1500 characters.')
        with self._db(True) as con:
            row=self._conversation(con, chat_id)
            prior=con.execute('SELECT * FROM chat_jobs WHERE chat_id=? AND request_id=?', (chat_id, request_id)).fetchone()
            if prior:
                if prior['mode']!=mode or (mode=='question' and prior['question']!=question) or prior['parent_id']!=job_id:
                    raise ChatError(409, 'That request identifier was already used for a different request.')
                existing_id=prior['id']
            else:
                self._check_revision(row, expected_revision)
                if con.execute("SELECT 1 FROM chat_jobs WHERE chat_id=? AND state IN ('queued','generating')", (chat_id,)).fetchone():
                    raise ChatError(409, 'Rill is already answering in this conversation. Reopen the current reply or stop it first.')
                if con.execute("SELECT count(*) FROM chat_jobs WHERE state IN ('queued','generating')").fetchone()[0]>=4:
                    raise ChatError(429, 'Rill already has three replies waiting. Try again after a reply finishes.')
                messages=json.loads(row['messages'])
                context=None
                prefix=''
                parent=None
                if mode!='question':
                    if not job_id:
                        raise ChatError(422, 'Select the saved reply to retry or continue.')
                    parent=con.execute('SELECT * FROM chat_jobs WHERE id=? AND chat_id=?', (job_id, chat_id)).fetchone()
                    if parent is None:
                        raise ChatError(404, 'Saved reply not found in this conversation.')
                    failure=json.loads(row['failure']) if row['failure'] else None
                    if not failure or failure.get('job_id')!=job_id:
                        raise ChatError(409, 'This saved reply has been replaced by a newer attempt. Reopen the latest reply.')
                    if parent['state'] not in ('failed','cancelled','incomplete'):
                        raise ChatError(409, 'Only an unfinished reply can be retried or continued.')
                    if len(messages)!=parent['user_index']+1 or messages[-1].get('role')!='user' or messages[-1].get('content')!=parent['question']:
                        raise ChatError(409, 'This question has newer messages. Start a new conversation to revisit it.')
                    if parent['retry_at']>time.time():
                        raise ChatError(429, 'The AI service asked us to wait before retrying. Please wait for the countdown.')
                    question=parent['question']
                    history=json.loads(parent['history'])
                    user_index=parent['user_index']
                    if mode=='continue':
                        saved_provider=json.loads(parent['provider'])
                        if (saved_provider.get('provider')!=rill_ai.provider()
                                or saved_provider.get('local')!=rill_ai.provider_info().get('local')):
                            raise ChatError(409,'This reply used a different AI connection. Retry with fresh readings on the selected provider instead of continuing it.')
                        verification=json.loads(parent['verification']) if parent['verification'] else None
                        if verification is None and parent['text']:
                            from rill_verification import verify_reply
                            checked=verify_reply(parent['text'],rill_ai.refreshed_context(json.loads(parent['context'])),parent['question'],partial=True)
                            if not checked['passed']:verification=checked
                        if verification and not verification.get('can_continue',True):
                            raise ChatError(409,'That draft included unsupported claims. Retry with fresh readings instead of continuing it.')
                        if not parent['text'] or not json.loads(parent['context']):
                            raise ChatError(409, 'This reply has no saved partial answer and snapshot. Retry with fresh readings instead.')
                        context=json.loads(parent['context'])
                        prefix=parent['text']
                else:
                    history=list(messages)
                    user_index=len(messages)
                    messages.append({'role':'user','content':question})
                if context is None:
                    frame=frame.copy()
                    if not frame.empty:
                        if 'source' in frame:
                            frame=frame[frame.source==row['source']]
                        if row['device_id'] is not None and 'device_id' in frame:
                            frame=frame[frame.device_id==row['device_id']]
                    values=thresholds or {}
                    context=rill_ai.context_data(frame,values.get('elevated',70),values.get('warning',100),values.get('rise_limit',10))
                now=time.time()
                existing_id=uuid4().hex
                sample=(context.get('latest') or {}).get('timestamp')
                # Continue uses the original model and captured readings. A new
                # question or fresh Retry uses the current persisted selection.
                inference=(json.loads(parent['provider']) if mode=='continue'
                           else rill_ai.provider_info(self._model_settings(con)['selected_model']))
                con.execute('''INSERT INTO chat_jobs
                    (id,chat_id,request_id,question,mode,parent_id,state,text,error,retry_at,created,updated,sample,sequence,context,history,user_index,provider) VALUES
                    (?,?,?,?,?,?, 'queued',?,NULL,0,?,?,?,1,?,?,?,?)''',
                    (existing_id,chat_id,request_id,question,mode,job_id,prefix,now,now,sample,
                     json.dumps(context,allow_nan=False),json.dumps(history,allow_nan=False),user_index,json.dumps(inference)))
                con.execute('UPDATE chat_conversations SET messages=?,failure=NULL,revision=revision+1,updated=? WHERE id=?',
                            (json.dumps(messages,allow_nan=False),now,chat_id))
        self._wake.set()
        # Let the worker reserve the first slot before an immediate next call.
        await asyncio.sleep(0)
        return self.get_job(existing_id)

    def get_job(self, job_id):
        self._require_started()
        with self._db() as con:
            con.execute('BEGIN')
            row=con.execute('SELECT * FROM chat_jobs WHERE id=?', (job_id,)).fetchone()
            if row is None:
                raise ChatError(404, 'Reply not found.')
            position=0
            if row['state']=='queued':
                position=con.execute("SELECT count(*) FROM chat_jobs WHERE state='queued' AND (created<? OR (created=? AND id<=?))", (row['created'],row['created'],row['id'])).fetchone()[0]
            chat=self._conversation(con,row['chat_id'])
            return dict(id=row['id'],chat_id=row['chat_id'],state=row['state'],text=row['text'],error=row['error'],
                        retry_at=row['retry_at'],created=row['created'],updated=row['updated'],sample=row['sample'],
                        sequence=row['sequence'],queue_position=position,question=row['question'],mode=row['mode'],user_index=row['user_index'],
                        provider=json.loads(row['provider']),revision=chat['revision'],
                        metrics=json.loads(row['metrics']) if row['metrics'] else None,
                        verification=json.loads(row['verification']) if row['verification'] else None)

    def _finish(self, job_id, state, error=None, retry_after=0, verification=None):
        with self._db(True) as con:
            row=con.execute('SELECT * FROM chat_jobs WHERE id=?', (job_id,)).fetchone()
            if row is None or row['state'] in TERMINAL:
                return
            chat=con.execute('SELECT * FROM chat_conversations WHERE id=?',(row['chat_id'],)).fetchone()
            if chat is None:
                return
            now=time.time()
            retry_at=now+max(0,retry_after) if retry_after else 0
            if state!='completed' and verification is None and row['text'].strip():
                from rill_verification import verify_reply
                checked=verify_reply(row['text'],rill_ai.refreshed_context(json.loads(row['context'])),row['question'],partial=True)
                if not checked['passed']:verification=checked
            messages=json.loads(chat['messages'])
            failure=None
            if state=='completed':
                messages.append({'role':'assistant','content':row['text']})
            else:
                failure=dict(job_id=job_id,question=row['question'],error=error,
                             partial=row['text'],retry_at=retry_at,state=state,verification=verification)
            con.execute('UPDATE chat_jobs SET state=?,error=?,retry_at=?,updated=?,sequence=sequence+1,verification=? WHERE id=?',
                        (state,error,retry_at,now,json.dumps(verification) if verification is not None else None,job_id))
            con.execute('UPDATE chat_conversations SET messages=?,failure=?,revision=revision+1,updated=? WHERE id=?',
                        (json.dumps(messages,allow_nan=False),json.dumps(failure) if failure else None,now,row['chat_id']))

    async def cancel(self, job_id):
        self._require_started()
        job=self.get_job(job_id)
        if job['state'] in TERMINAL:
            return job
        task=self._generation_tasks.get(job_id)
        if task:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
        self._finish(job_id,'cancelled','Reply stopped. Your question and partial reply are saved; continue or retry when ready.')
        self._wake.set()
        return self.get_job(job_id)

    async def _work(self):
        while not self._closing:
            self._wake.clear()
            with self._db(True) as con:
                row=con.execute("SELECT * FROM chat_jobs WHERE state='queued' ORDER BY created,id LIMIT 1").fetchone()
                if row:
                    con.execute("UPDATE chat_jobs SET state='generating',updated=?,sequence=sequence+1 WHERE id=?", (time.time(),row['id']))
            if not row:
                await self._wake.wait()
                continue
            if self._warm_task and not self._warm_task.done():
                await self._warm_task
            try:
                if self.get_job(row['id'])['state']!='generating':
                    continue  # It may have been stopped while preload held the worker.
            except ChatError as exc:
                if exc.status==404:continue  # Chat deleted during preload.
                raise
            task=asyncio.create_task(self._generate(dict(row)),name='rill-'+row['id'])
            self._generation_tasks[row['id']]=task
            try:
                await task
            except asyncio.CancelledError:
                if self._closing:
                    raise
            finally:
                self._generation_tasks.pop(row['id'],None)

    async def _generate(self, row):
        continuation=row['text'] if row['mode']=='continue' else ''
        pending=[]
        last_flush=0
        metrics={}
        began=time.monotonic()
        def flush():
            nonlocal last_flush
            if not pending:return True
            text=''.join(pending)
            with self._db(True) as con:
                cursor=con.execute("UPDATE chat_jobs SET text=text||?,updated=?,sequence=sequence+1 WHERE id=? AND state='generating'",
                                   (text,time.time(),row['id']))
            pending.clear()
            last_flush=time.monotonic()
            return bool(cursor.rowcount)
        try:
            context=rill_ai.refreshed_context(json.loads(row['context']))
            async for token in rill_ai.async_chat_stream(row['question'],json.loads(row['history']),context,continuation,
                                                       model=json.loads(row['provider']).get('model'),telemetry=metrics,
                                                       require_local=json.loads(row['provider']).get('local',False)):
                if 'first_token_seconds' not in metrics:metrics['first_token_seconds']=round(time.monotonic()-began,3)
                pending.append(token)
                if time.monotonic()-last_flush>=.08 or sum(map(len,pending))>=256:
                    if not flush():return
            if not flush():return
            with self._db() as con:
                current=con.execute('SELECT text FROM chat_jobs WHERE id=?',(row['id'],)).fetchone()
            if current is not None:
                if not current['text'].strip() or (continuation and not current['text'][len(continuation):].strip()):
                    raise rill_ai.RillError('The AI returned no answer. Your question is saved; retry when ready.')
                from rill_verification import verify_reply
                verification=verify_reply(current['text'],context,row['question'])
                if not verification['passed']:
                    self._finish(row['id'],'incomplete',
                                 'This draft included claims that could not be matched to the readings. It is unverified. Retry with a fresh snapshot.',verification=verification)
                else:
                    self._finish(row['id'],'completed',verification=verification)
        except asyncio.CancelledError:
            flush()
            self._finish(row['id'],'failed' if self._closing else 'cancelled',
                         'The app stopped before this reply finished. Retry when ready.' if self._closing else 'Reply stopped. Continue or retry your saved question.')
            raise
        except rill_ai.IncompleteReply as exc:
            flush()
            self._finish(row['id'],'incomplete',str(exc),getattr(exc,'retry_after',0))
        except rill_ai.RillError as exc:
            flush()
            self._finish(row['id'],'failed',str(exc),getattr(exc,'retry_after',0))
        except Exception:
            flush()
            # Never send raw provider/network error bodies or credentials to UI.
            self._finish(row['id'],'failed','The AI could not finish that reply. Your question and partial answer are saved; retry when ready.')
        finally:
            metrics['generation_seconds']=round(time.monotonic()-began,3)
            with self._db(True) as con:
                con.execute('UPDATE chat_jobs SET metrics=? WHERE id=?',(json.dumps(metrics),row['id']))

    async def events(self, job_id, after=0):
        """Replay the latest persisted snapshot then stream future revisions.

        Every event is a complete snapshot, so reconnects can skip missed token
        events without losing text. Disconnecting only ends this observer.
        """
        sequence=max(0,int(after))
        last_heartbeat=time.monotonic()
        while True:
            job=self.get_job(job_id)
            if job['sequence']>sequence:
                sequence=job['sequence']
                yield f'id: {sequence}\nevent: reply\ndata: {json.dumps(job,ensure_ascii=False)}\n\n'
            if job['state'] in TERMINAL:
                return
            if time.monotonic()-last_heartbeat>=15:
                yield ': keep-alive\n\n'
                last_heartbeat=time.monotonic()
            await asyncio.sleep(.2)


service=ChatService()
