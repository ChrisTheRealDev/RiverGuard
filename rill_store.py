"""Durable local Rill conversations and history, separated by reading source."""
import json
from time import time, monotonic
from uuid import uuid4
from core import connect


def connection():
    con=connect()
    con.execute('CREATE TABLE IF NOT EXISTS rill_chats (source TEXT PRIMARY KEY, payload TEXT NOT NULL, attempt TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS rill_conversations (id TEXT PRIMARY KEY, source TEXT NOT NULL, payload TEXT NOT NULL, attempt TEXT, created REAL NOT NULL, updated REAL NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS rill_active (source TEXT PRIMARY KEY, chat_id TEXT NOT NULL)')
    con.execute('BEGIN IMMEDIATE')
    # Preserve existing installations; the old table remains untouched as a backup.
    for source,payload,attempt in con.execute('SELECT source,payload,attempt FROM rill_chats WHERE source NOT IN (SELECT source FROM rill_active)').fetchall():
        chat_id=uuid4().hex;now=time()
        con.execute('INSERT INTO rill_conversations VALUES (?,?,?,?,?,?)',(chat_id,source,payload,attempt,now,now))
        con.execute('INSERT INTO rill_active VALUES (?,?)',(source,chat_id))
    con.commit()
    return con


def active(source):
    with connection() as con:
        row=con.execute('SELECT chat_id FROM rill_active WHERE source=?',(source,)).fetchone()
    return row[0] if row else None


def new_conversation(source):
    chat_id=uuid4().hex;now=time()
    with connection() as con:
        con.execute('INSERT INTO rill_conversations VALUES (?,?,?,NULL,?,?)',(chat_id,source,json.dumps(dict(messages=[],failure=None)),now,now))
        con.execute('INSERT INTO rill_active VALUES (?,?) ON CONFLICT(source) DO UPDATE SET chat_id=excluded.chat_id',(source,chat_id))
    return chat_id


def activate(source,chat_id):
    with connection() as con:
        if not con.execute('SELECT 1 FROM rill_conversations WHERE id=? AND source=?',(chat_id,source)).fetchone():
            raise ValueError('Conversation not found for this reading source')
        con.execute('INSERT INTO rill_active VALUES (?,?) ON CONFLICT(source) DO UPDATE SET chat_id=excluded.chat_id',(source,chat_id))


def conversations(source):
    current=active(source)
    with connection() as con:
        rows=con.execute('SELECT id,payload,created,updated FROM rill_conversations WHERE source=? ORDER BY updated DESC,id',(source,)).fetchall()
    result=[]
    for chat_id,payload,created,updated in rows:
        data=json.loads(payload)
        if not data['messages'] and chat_id!=current: continue
        title=data.get('title') or next((m['content'] for m in data['messages'] if m['role']=='user'),'New conversation')
        result.append(dict(id=chat_id,title=' '.join(title.split())[:64],created=created,updated=updated,needs_retry=bool(data.get('failure') or data.get('pending'))))
    return result


def load(source,chat_id=None):
    chat_id=chat_id or active(source)
    with connection() as con:
        row=con.execute('SELECT payload FROM rill_conversations WHERE source=? AND id=?',(source,chat_id)).fetchone()
    if not row: return None
    data=json.loads(row[0]);failure=data.get('failure')
    if data.get('pending'):
        failure=dict(data['pending'],error='That reply was interrupted. Your question and chat are saved. You can retry it.',partial='',retry_until=0)
    if failure: failure=dict(failure,retry_at=monotonic()+max(0,failure.get('retry_until',0)-time()))
    return dict(messages=data['messages'],failure=failure)


def save(source,messages,failure=None,chat_id=None):
    chat_id=chat_id or active(source) or new_conversation(source)
    if failure:
        failure=dict(failure,retry_until=time()+max(0,failure.get('retry_at',0)-monotonic()))
        failure.pop('retry_at',None)
    with connection() as con:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT payload FROM rill_conversations WHERE source=? AND id=?',(source,chat_id)).fetchone()
        if not row: raise ValueError('Conversation not found')
        data=dict(messages=messages,failure=failure,title=json.loads(row[0]).get('title'))
        con.execute('UPDATE rill_conversations SET payload=?,attempt=NULL,updated=? WHERE source=? AND id=?',(json.dumps(data,allow_nan=False),time(),source,chat_id))


def begin(source,question,past,messages,chat_id=None):
    chat_id=chat_id or active(source) or new_conversation(source)
    attempt=uuid4().hex
    data=dict(messages=messages,pending=dict(question=question,messages=past))
    with connection() as con:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT payload FROM rill_conversations WHERE source=? AND id=?',(source,chat_id)).fetchone()
        if not row: raise ValueError('Conversation not found')
        data['title']=json.loads(row[0]).get('title')
        con.execute('UPDATE rill_conversations SET payload=?,attempt=?,updated=? WHERE source=? AND id=?',(json.dumps(data,allow_nan=False),attempt,time(),source,chat_id))
    return attempt


def finish(source,attempt,text,error=None,retry_at=0):
    # Match the original attempt, even if another conversation is now active.
    with connection() as con:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT id,payload FROM rill_conversations WHERE source=? AND attempt=?',(source,attempt)).fetchone()
        if not row: return
        chat_id,payload=row;data=json.loads(payload);pending=data.pop('pending')
        if error: data['failure']=dict(pending,error=error,partial=text,retry_until=time()+max(0,retry_at-monotonic()))
        else:
            data['messages'].append(dict(role='assistant',content=text));data['failure']=None
        con.execute('UPDATE rill_conversations SET payload=?,attempt=NULL,updated=? WHERE id=? AND attempt=?',(json.dumps(data,allow_nan=False),time(),chat_id,attempt))


def rename(source,chat_id,title):
    title=' '.join(title.split())
    if not title or len(title)>64: raise ValueError('Use a name between 1 and 64 characters.')
    with connection() as con:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT payload FROM rill_conversations WHERE source=? AND id=?',(source,chat_id)).fetchone()
        if not row: raise ValueError('Conversation not found')
        data=json.loads(row[0]);data['title']=title
        con.execute('UPDATE rill_conversations SET payload=?,updated=? WHERE source=? AND id=?',(json.dumps(data,allow_nan=False),time(),source,chat_id))


def delete(source,chat_id):
    with connection() as con:
        con.execute('BEGIN IMMEDIATE')
        if not con.execute('SELECT 1 FROM rill_conversations WHERE source=? AND id=?',(source,chat_id)).fetchone():
            raise ValueError('Conversation not found')
        con.execute('DELETE FROM rill_conversations WHERE source=? AND id=?',(source,chat_id))
        con.execute('DELETE FROM rill_chats WHERE source=?',(source,))
        current=con.execute('SELECT chat_id FROM rill_active WHERE source=?',(source,)).fetchone()
        if current and current[0]!=chat_id: return current[0]
        next_chat=con.execute('SELECT id FROM rill_conversations WHERE source=? ORDER BY updated DESC LIMIT 1',(source,)).fetchone()
        if next_chat: selected=next_chat[0]
        else:
            selected=uuid4().hex;now=time()
            con.execute('INSERT INTO rill_conversations VALUES (?,?,?,NULL,?,?)',(selected,source,json.dumps(dict(messages=[],failure=None)),now,now))
        con.execute('UPDATE rill_active SET chat_id=? WHERE source=?',(selected,source))
        return selected
