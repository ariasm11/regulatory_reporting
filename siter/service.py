"""Local execution service: SQLite metadata, isolated run folders, bounded worker queue."""
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from .common import ROOT, load, dump
from . import contracts
from .run import execute

ACTIVE={'VALIDATING','RUNNING'}
TTL=24*60*60


class Problem(Exception):
    def __init__(self,status,message):
        self.status=status;self.message=message
        super().__init__(message)


def password_hash(password,salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600_000).hex()


class Service:
    def __init__(self,root,bigquery_sources=None,recover=True,ephemeral=False):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(self.root,0o700)
        self.instance_lock=None
        if recover:
            self.instance_lock=(self.root/'server.lock').open('a')
            try: fcntl.flock(self.instance_lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                self.instance_lock.close()
                raise ValueError('Another server is already using this state directory')
        self.db=self.root/'state.sqlite3'
        self.lock=threading.RLock();self.pool=ThreadPoolExecutor(max_workers=1)
        self.pending=0
        self.sources=bigquery_sources or {}
        self.ephemeral=ephemeral
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE, salt TEXT, hash TEXT);
              CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT, csrf TEXT, expires REAL);
              CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,user_id TEXT,state TEXT,created REAL,expires REAL,config TEXT,detail TEXT,result TEXT);
            ''')
            if recover:
                db.execute("UPDATE runs SET state='FAILED',detail=? WHERE state IN ('VALIDATING','RUNNING')",(json.dumps({'errors':[{'message':'Server restarted; create a new run.'}]}),))
        self.cleanup()

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.db,timeout=15)
        try:
            with db: yield db
        finally: db.close()

    def add_user(self,username,password):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}',username) or not 12<=len(password)<=256:
            raise ValueError('Username: 3–64 letters/digits/._-; password: 12–256 characters')
        salt=secrets.token_hex(16)
        with self.connect() as db:
            old=db.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()
            uid=old[0] if old else uuid.uuid4().hex
            db.execute('INSERT OR REPLACE INTO users VALUES (?,?,?,?)',(uid,username,salt,password_hash(password,salt)))
            db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
        return uid

    def login(self,username,password):
        if not isinstance(username,str) or not isinstance(password,str) or len(password)>256 or len(username)>64:
            raise Problem(401,'Invalid credentials')
        with self.connect() as db:
            row=db.execute('SELECT id,salt,hash FROM users WHERE username=?',(username,)).fetchone()
            calculated=password_hash(password,row[1] if row else '0'*32)
            if not row or not hmac.compare_digest(calculated,row[2]):
                raise Problem(401,'Invalid credentials')
            token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row[0],csrf,time.time()+12*3600))
        return token,csrf

    def session(self,token):
        with self.connect() as db:
            row=db.execute('SELECT s.user_id,u.username,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id WHERE token=? AND expires>?',
                           (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        if not row: raise Problem(401,'Sign in to continue')
        return dict(user_id=row[0],username=row[1],csrf=row[2])

    def logout(self,token):
        with self.connect() as db: db.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),))

    def source_options(self,username):
        return [{'id':key,'label':value.get('label',key)} for key,value in self.sources.items() if username in value.get('users',[])]

    def config(self,username):
        cfg=load(ROOT/'config/reporting.json')
        return dict(rules=cfg,contract=contracts.contract(),sources=self.source_options(username),retention_hours=24,ephemeral=self.ephemeral,max_body_bytes=24*1024*1024)

    def get(self,user_id,run_id):
        if not re.fullmatch(r'[a-f0-9]{32}',run_id): raise Problem(404,'Run not found')
        with self.connect() as db:
            row=db.execute('SELECT id,state,created,expires,config,detail,result FROM runs WHERE id=? AND user_id=? AND expires>?',
                           (run_id,user_id,time.time())).fetchone()
        if not row: raise Problem(404,'Run not found')
        return dict(id=row[0],state=row[1],created=row[2],expires=row[3],config=json.loads(row[4]),detail=json.loads(row[5]),result=row[6])

    def public_run(self,user_id,run_id):
        r=self.get(user_id,run_id);r.pop('result');return r

    def list_runs(self,user_id):
        with self.connect() as db:
            rows=db.execute('SELECT id FROM runs WHERE user_id=? AND expires>? ORDER BY created DESC',(user_id,time.time())).fetchall()
        return [self.public_run(user_id,row[0]) for row in rows]

    def folder(self,user_id,run_id):
        # Both ids are server-generated, never taken from a filename or source profile.
        return self.root/'runs'/user_id/run_id

    def set_state(self,run_id,state,detail=None,result=None):
        with self.connect() as db:
            db.execute('UPDATE runs SET state=?,detail=?,result=? WHERE id=?',(state,json.dumps(detail or {}),result,run_id))

    def enqueue(self,fn,*args):
        # Caller holds the service lock; limit also covers queued jobs.
        if self.pending>=4: raise Problem(429,'Execution queue is full; try again later')
        self.pending+=1
        def work():
            try: fn(*args)
            finally:
                with self.lock: self.pending-=1
        self.pool.submit(work)

    def create(self,session,payload):
        if payload.get('anonymized') is not True:
            raise Problem(400,'Confirm that every identifier and name has been anonymized')
        try: config=contracts.options(payload.get('config'))
        except ValueError as exc: raise Problem(400,str(exc)) from exc
        files=payload.get('files',{})
        if not isinstance(files,dict) or any(k not in contracts.SCHEMAS or not isinstance(v,str) for k,v in files.items()):
            raise Problem(400,'Upload only the CSV filenames listed in the contract')
        source=payload.get('source','csv')
        if not isinstance(source,str): raise Problem(400,'Invalid source')
        if source!='csv':
            if source not in {s['id'] for s in self.source_options(session['username'])}:
                raise Problem(403,'Source not authorized')
            if 'transactions.csv' in files: raise Problem(400,'Choose CSV transactions or a BigQuery source, not both')
        uid=session['user_id']
        with self.lock:
            if self.pending>=4: raise Problem(429,'Execution queue is full; try again later')
            current=self.list_runs(uid)
            if len(current)>=10: raise Problem(409,'Maximum 10 retained runs; delete one before uploading')
            if any(r['state'] in ACTIVE for r in current): raise Problem(409,'Wait for your active run to finish')
            rid=uuid.uuid4().hex;now=time.time()
            folder=self.folder(uid,rid);folder.mkdir(parents=True,mode=0o700)
            dump(folder/'upload.json',files)
            with self.connect() as db:
                db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',(rid,uid,'VALIDATING',now,now+TTL,json.dumps(config),json.dumps({'source':source}),None))
            self.enqueue(self.validate_job,uid,rid,source)
        return self.public_run(uid,rid)

    def import_bigquery(self,source):
        # Table names are only read from administrator config, never request input.
        profile=self.sources[source]
        from google.cloud import bigquery
        client=bigquery.Client(project=profile['project'])
        try:
            table=client.get_table(profile['table'],timeout=30,retry=None)
            if table.table_type!='TABLE' or table.num_rows>contracts.MAX_ROWS:
                raise ValueError('BigQuery source must be a physical table with at most 100000 rows')
            expected={'transaction_id':'STRING','account_id':'STRING','posted_date':'DATE','kind':'STRING','amount_cents':'INTEGER'}
            fields={f.name:f for f in table.schema}
            if any(k not in fields or fields[k].field_type!=v or fields[k].mode=='REPEATED' for k,v in expected.items()):
                raise ValueError('BigQuery schema does not match the transaction contract')
            rows=[]
            for row in client.list_rows(table,selected_fields=[fields[k] for k in expected],max_results=contracts.MAX_ROWS+1,timeout=30,retry=None):
                rows.append(dict(row.items()))
                if len(rows)>contracts.MAX_ROWS: raise ValueError('BigQuery row limit exceeded')
            return contracts.csv_text('transactions.csv',rows)
        finally: client.close()

    def validate_job(self,uid,rid,source):
        folder=self.folder(uid,rid)
        try:
            files=load(folder/'upload.json')
            if source!='csv':
                try: files['transactions.csv']=self.import_bigquery(source)
                except Exception:
                    self.set_state(rid,'INVALID',{'errors':[{'file':'transactions.csv','row':0,'field':'','message':'BigQuery import failed. Check the authorized table schema, row limit and server credentials.'}]});return
            tables,errors,counts=contracts.parse_files(files)
            if errors:
                self.set_state(rid,'INVALID',{'errors':errors,'counts':counts,'source':source});return
            contracts.write_inputs(folder/'input',tables,source)
            config=self.get(uid,rid)['config']
            summary=contracts.preflight(folder/'input',config)
            self.set_state(rid,'READY',{'validation':summary,'counts':counts,'source':source})
        except ValueError as exc:
            self.set_state(rid,'INVALID',{'errors':[{'file':'business rules','row':0,'field':'','message':str(exc)[:500]}]})
        except Exception:
            self.set_state(rid,'FAILED',{'errors':[{'message':'Unexpected validation error; create a new run or contact the administrator.'}]})
        finally:
            (folder/'upload.json').unlink(missing_ok=True)

    def start(self,uid,rid):
        with self.lock:
            run=self.get(uid,rid)
            if run['state']!='READY': raise Problem(409,'Run must pass validation before execution')
            if self.pending>=4 or any(r['state'] in ACTIVE for r in self.list_runs(uid)):
                raise Problem(409,'Wait for the active execution to finish')
            self.set_state(rid,'RUNNING',run['detail'])
            self.enqueue(self.execute_job,uid,rid)
        return self.public_run(uid,rid)

    def execute_job(self,uid,rid):
        run=self.get(uid,rid);cfg=run['config'];folder=self.folder(uid,rid)
        try:
            dest,audit=execute(folder/'input',folder/'output',cfg['period'],cfg['sequence'],
                               reporter=cfg['reporter_cuit'],entity=cfg['entity_code'])
            detail=run['detail'];detail['audit']=audit
            self.set_state(rid,'SUCCEEDED',detail,str(dest.relative_to(folder)))
        except ValueError as exc:
            self.set_state(rid,'FAILED',{'errors':[{'message':str(exc)[:500]}]})
        except Exception:
            self.set_state(rid,'FAILED',{'errors':[{'message':'Execution failed; no artifacts are available.'}]})

    def artifacts(self,uid,rid):
        run=self.get(uid,rid)
        if run['state']!='SUCCEEDED': raise Problem(409,'Artifacts are available only after a successful run')
        folder=self.folder(uid,rid)/run['result'];audit=load(folder/'audit.json')
        return folder,{'txt':audit['file'],'zip':audit['file'][:-4]+'.zip','audit':'audit.json','accounts':'account_decisions.json','fields':'record_fields.json'}

    def reporting(self,uid,rid):
        run=self.get(uid,rid);folder,names=self.artifacts(uid,rid)
        data=self.folder(uid,rid)/'input'
        people={p['customer_id']:p for p in load(data/'customers.json')}
        accounts={a['account_id']:a for a in load(data/'accounts.json')}
        metrics=load(folder/names['accounts']);audit=load(folder/names['audit'])
        for row in metrics:
            p=people[accounts[row['account_id']]['customer_id']]
            row.update(customer_id=p['customer_id'],name=p['synthetic_name'],person_type=p['person_type'])
        report=dict(period=run['config']['period'],audit=audit,accounts=metrics,cloud=None,
                    lines=(folder/names['txt']).read_bytes().decode('iso-8859-1').split('\r\n')[:-1],
                    files={k:f'/api/runs/{rid}/files/{k}' for k in names})
        return dict(dataset='uploaded',run_id=rid,source_transactions=audit['quality']['input_transactions'],
                    account_count=audit['account_count'],synthetic=False,live_connection=False,
                    reports=[report],layout=load(ROOT/'config/layout_v500.json')['records'])

    def delete(self,uid,rid):
        with self.lock:
            run=self.get(uid,rid)
            if run['state'] in ACTIVE: raise Problem(409,'Wait for the active job before deleting')
            shutil.rmtree(self.folder(uid,rid),ignore_errors=False)
            with self.connect() as db: db.execute('DELETE FROM runs WHERE id=? AND user_id=?',(rid,uid))

    def cleanup(self):
        with self.lock,self.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires<=?',(time.time(),))
            rows=db.execute("SELECT id,user_id FROM runs WHERE expires<=? AND state NOT IN ('VALIDATING','RUNNING')",(time.time(),)).fetchall()
            for rid,uid in rows:
                shutil.rmtree(self.folder(uid,rid),ignore_errors=True)
                db.execute('DELETE FROM runs WHERE id=?',(rid,))

    def close(self):
        self.pool.shutdown(wait=True)
        if self.instance_lock: self.instance_lock.close()
