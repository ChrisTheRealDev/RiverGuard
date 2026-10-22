"""Versioned installation upgrades; old evidence is never rewritten."""
import json
import secrets
import sqlite3
import time

SCHEMA = '''
CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS stations(device_id TEXT PRIMARY KEY,token_hash TEXT UNIQUE NOT NULL,last_received TEXT,last_measured TEXT,ack_revision INTEGER);
CREATE TABLE IF NOT EXISTS configurations(device_id TEXT,revision INTEGER,settings TEXT,created_at TEXT,PRIMARY KEY(device_id,revision),FOREIGN KEY(device_id) REFERENCES stations(device_id));
CREATE TABLE IF NOT EXISTS readings(id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT NOT NULL,device_id TEXT NOT NULL,timestamp TEXT NOT NULL,measured_ms INTEGER NOT NULL,received_at TEXT NOT NULL,payload TEXT NOT NULL,settings_json TEXT,sample_id TEXT,UNIQUE(source,device_id,sample_id));
CREATE INDEX IF NOT EXISTS station_measurement ON readings(source,device_id,measured_ms DESC,id DESC);
CREATE TABLE IF NOT EXISTS alert_events(id INTEGER PRIMARY KEY AUTOINCREMENT,device_id TEXT NOT NULL,event_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS station_alert_events ON alert_events(device_id,id DESC);
CREATE INDEX IF NOT EXISTS event_sample ON alert_events(device_id,json_extract(event_json,'$.sample'));
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,hash TEXT UNIQUE NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS bootstrap(hash TEXT PRIMARY KEY,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pairing(hash TEXT PRIMARY KEY,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS attempts(address TEXT,attempted REAL);
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS watch(source TEXT,device_id TEXT,revision INTEGER NOT NULL,settings TEXT NOT NULL,needs_review INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(source,device_id));
CREATE TABLE IF NOT EXISTS alert_progress(device_id TEXT PRIMARY KEY,last_id INTEGER NOT NULL DEFAULT 0,current_ms INTEGER NOT NULL DEFAULT 0,current_id INTEGER NOT NULL DEFAULT 0,ledger TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS quarantine(id INTEGER PRIMARY KEY,key TEXT,value TEXT,created REAL);
CREATE TABLE IF NOT EXISTS session_details(session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,label TEXT NOT NULL,last_seen REAL NOT NULL);
'''


def migrate(db, path):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    application = db.execute('PRAGMA application_id').fetchone()[0]
    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    if (tables and application != 0x52475632) or application not in (0, 0x52475632):
        raise RuntimeError('This is not a RiverGuard V2 database. Choose a separate V2 file; the existing database was not changed.')
    if version not in (0, 1, 2):
        raise RuntimeError('Unsupported V2 database version; preserve the data folder.')
    if version == 2:
        return
    if version:
        backup = path.with_name(path.name + '.pre-v2-' + str(time.time_ns()) + '.backup')
        target = sqlite3.connect(backup)
        try: db.backup(target)
        finally: target.close()
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('BEGIN IMMEDIATE')
    try:
        for statement in SCHEMA.split(';'):
            if statement.strip(): db.execute(statement)
        db.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)', ('installation_id', secrets.token_hex(12)))
        for row in db.execute("SELECT key,value FROM state WHERE key LIKE 'watch:%'").fetchall():
            device = row['key'][6:]
            sources = ('simulation', 'esp32') if device == 'demo-station' else ('esp32',)
            for source in sources:
                db.execute('INSERT OR IGNORE INTO watch VALUES (?,?,?,?,?)', (source, device, 1, row['value'], 1))
        # Existing event wording is retained. Start new processing at the migration
        # ceiling; replaying years of data must not send a burst of old warnings.
        for row in db.execute("SELECT device_id,MAX(id) last_id FROM readings WHERE source='esp32' GROUP BY device_id").fetchall():
            newest = db.execute("SELECT id,measured_ms FROM readings WHERE source='esp32' AND device_id=? ORDER BY measured_ms DESC,id DESC LIMIT 1", (row['device_id'],)).fetchone()
            old = db.execute('SELECT value FROM state WHERE key=?', ('alert-status:'+row['device_id'],)).fetchone()
            ledger = old[0] if old else '{}'
            db.execute('INSERT OR IGNORE INTO alert_progress VALUES (?,?,?,?,?)', (row['device_id'], row['last_id'], newest['measured_ms'], newest['id'], ledger))
        for row in db.execute("SELECT key,value FROM state WHERE key LIKE 'draft:%'").fetchall():
            if not row['key'].startswith('draft:esp32:'):
                db.execute('INSERT OR IGNORE INTO state VALUES (?,?)', ('draft:esp32:'+row['key'][6:], row['value']))
        db.execute('PRAGMA application_id=1380406834')
        db.execute('PRAGMA user_version=2')
        db.commit()
    except BaseException:
        db.rollback()
        raise
