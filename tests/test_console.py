"""Console acceptance and security boundaries, exercised over real HTTP locally."""
import copy
import hashlib
import http.client
import io
import json
import sys
import types
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from siter.common import ROOT, load, tax_id
from siter.contracts import parse_files, sample_files, options, template_zip, MAX_ROWS
from siter.server import Server
from siter.service import Service, Problem
from siter.validate import validate


def settings():
    cfg=load(ROOT/'config/reporting.json')
    return dict(period='202608',rules_id=cfg['rules_id'],reporter_cuit=cfg['synthetic_reporter_cuit'],
                entity_code=str(cfg['synthetic_entity_code']),presentation='original',sequence=0)


class ContractTests(unittest.TestCase):
    def test_templates_and_sample_round_trip(self):
        for sample in (False,True):
            with zipfile.ZipFile(io.BytesIO(template_zip(sample))) as z:
                self.assertIn('contract.json',z.namelist())
                self.assertIn('transactions.csv',z.namelist())
        tables,errors,counts=parse_files(sample_files())
        self.assertFalse(errors)
        self.assertEqual(counts['transactions.csv'],1200)
        self.assertEqual(tables['customers.csv'][0]['excluded'],False)

    def test_row_errors_duplicate_orphan_and_wrong_header(self):
        files=sample_files();lines=files['transactions.csv'].splitlines()
        files['transactions.csv']='\n'.join(lines+[lines[1]])
        _,errors,_=parse_files(files)
        self.assertEqual(errors[0]['row'],1202)
        self.assertIn('duplicate',errors[0]['message'])
        files=sample_files();files['transactions.csv']=files['transactions.csv'].replace('A0000001','MISSING')
        self.assertTrue(any(e['field']=='account_id' for e in parse_files(files)[1]))
        files=sample_files();files['customers.csv']='wrong,header\nx,y'
        self.assertEqual(parse_files(files)[1][0]['row'],1)

    def test_numeric_date_and_row_limits(self):
        files=sample_files();lines=files['transactions.csv'].splitlines();row=lines[1].split(',');row[2]='2026-02-30';row[4]='1.25'
        files['transactions.csv']=lines[0]+'\n'+','.join(row)
        self.assertEqual({e['field'] for e in parse_files(files)[1]},{'posted_date','amount_cents'})
        with patch('siter.contracts.MAX_ROWS',2):
            self.assertTrue(any('maximum 2 rows' in e['message'] for e in parse_files(sample_files())[1]))

    def test_configuration_is_closed_and_versioned(self):
        for key,value in [('period','202609'),('rules_id','arbitrary'),('sequence',True),('entity_code','<x>'),('reporter_cuit','123')]:
            cfg=settings();cfg[key]=value
            with self.assertRaises(ValueError): options(cfg)
        cfg=settings();cfg.update(presentation='replacement',sequence=1)
        self.assertEqual(options(cfg)['sequence'],1)


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.service=Service(Path(self.temp.name))
        self.uid=self.service.add_user('analyst','example-test-pass-1')
        self.other=self.service.add_user('reviewer','example-test-pass-2')
        self.server=Server(('127.0.0.1',0),self.service,'http://127.0.0.1:0')
        self.origin=f'http://127.0.0.1:{self.server.server_port}';self.server.origin=self.origin
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.cookie='';self.csrf='';self.login()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.service.close();self.temp.cleanup()

    def request(self,path,method='GET',body=None,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        hdr={'Origin':self.origin,'Cookie':self.cookie,'X-CSRF-Token':self.csrf}
        if body is not None: body=json.dumps(body);hdr['Content-Type']='application/json'
        hdr.update(headers or {})
        c.request(method,path,body=body,headers=hdr)
        r=c.getresponse();raw=r.read();status=r.status;response_headers=dict(r.getheaders());c.close()
        result=json.loads(raw) if r.getheader('Content-Type','').startswith('application/json') else raw
        return status,result,response_headers

    def login(self,user='analyst',password='example-test-pass-1'):
        status,result,headers=self.request('/api/login','POST',dict(username=user,password=password))
        self.assertEqual(status,200)
        self.cookie=headers['Set-Cookie'].split(';')[0];self.csrf=result['csrf']
        return headers

    def payload(self): return dict(files=sample_files(),config=settings(),anonymized=True,source='csv')

    def wait_for(self,rid,states):
        until=time.monotonic()+8
        while time.monotonic()<until:
            status,run,_=self.request('/api/runs/'+rid)
            self.assertEqual(status,200)
            if run['state'] in states:return run
            time.sleep(.01)
        self.fail('Run did not complete')

    def ready(self,payload=None):
        status,run,_=self.request('/api/runs','POST',payload or self.payload())
        self.assertEqual(status,202,run)
        completed=self.wait_for(run['id'],{'READY','INVALID','FAILED'})
        self.assertEqual(completed['state'],'READY',completed)
        return run['id']

    def completed(self,payload=None):
        rid=self.ready(payload)
        self.assertEqual(self.request('/api/runs/'+rid+'/execute','POST')[0],202)
        run=self.wait_for(rid,{'SUCCEEDED','FAILED'})
        self.assertEqual(run['state'],'SUCCEEDED',run)
        return rid

    def test_full_upload_validate_execute_download_and_delete(self):
        rid=self.completed()
        status,raw,_=self.request('/api/runs/'+rid+'/files/txt')
        self.assertEqual(status,200)
        expected=load(ROOT/'examples/cloud_sample_202608.json')['result']['txt_sha256']
        self.assertEqual(hashlib.sha256(raw).hexdigest(),expected)
        self.assertEqual(validate(raw)['counts']['02'],4)
        report=self.request('/api/runs/'+rid+'/reporting')[1]
        self.assertEqual(report['reports'][0]['audit']['quality']['reconciliation_difference_cents'],0)
        self.assertEqual(report['source_transactions'],1200)
        self.assertIsNone(report['reports'][0]['cloud'])
        self.assertEqual(self.request('/api/runs/'+rid+'/execute','POST')[0],409)
        self.assertEqual(self.request('/api/runs/'+rid,'DELETE')[0],200)
        self.assertFalse(self.service.folder(self.uid,rid).exists())
        self.assertEqual(self.request('/api/runs/'+rid+'/files/txt')[0],404)

    def test_owner_isolation_including_download_execute_delete(self):
        rid=self.completed();self.login('reviewer','example-test-pass-2')
        self.assertEqual(self.request('/api/runs')[1],[])
        for path,method in [(f'/api/runs/{rid}','GET'),(f'/api/runs/{rid}/files/txt','GET'),(f'/api/runs/{rid}/reporting','GET'),(f'/api/runs/{rid}/execute','POST'),(f'/api/runs/{rid}','DELETE')]:
            self.assertEqual(self.request(path,method)[0],404)

    def test_auth_csrf_origin_host_and_logout(self):
        headers=self.login();self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        self.assertEqual(self.request('/api/runs',headers={'Cookie':''})[0],401)
        self.assertEqual(self.request('/api/runs','POST',self.payload(),{'X-CSRF-Token':''})[0],403)
        self.assertEqual(self.request('/api/runs','POST',self.payload(),{'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/config',headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('/api/logout','POST')[0],200)
        self.assertEqual(self.request('/api/config')[0],401)

    def test_invalid_lot_cannot_execute_or_download(self):
        payload=self.payload();payload['files']['transactions.csv']+='\n'+payload['files']['transactions.csv'].splitlines()[1]
        status,run,_=self.request('/api/runs','POST',payload);self.assertEqual(status,202)
        run=self.wait_for(run['id'],{'INVALID','FAILED'})
        self.assertEqual(run['state'],'INVALID')
        self.assertIn('duplicate',run['detail']['errors'][0]['message'])
        self.assertEqual(self.request('/api/runs/'+run['id']+'/execute','POST')[0],409)
        self.assertEqual(self.request('/api/runs/'+run['id']+'/files/txt')[0],409)

    def test_balance_error_blocks_generation(self):
        payload=self.payload();rows=payload['files']['snapshots.csv'].splitlines()
        for i,line in enumerate(rows):
            if line.startswith('202608,'):
                fields=line.split(',');fields[3]=str(int(fields[3])+100);rows[i]=','.join(fields);break
        payload['files']['snapshots.csv']='\n'.join(rows)
        status,run,_=self.request('/api/runs','POST',payload);self.assertEqual(status,202)
        run=self.wait_for(run['id'],{'INVALID','FAILED'})
        self.assertEqual(run['state'],'INVALID');self.assertIn('reconciliation',run['detail']['errors'][0]['message'])

    def test_reporter_and_replacement_are_run_scoped(self):
        payload=self.payload();payload['config'].update(reporter_cuit=tax_id(3099999998),entity_code='12345',presentation='replacement',sequence=2)
        rid=self.completed(payload);raw=self.request('/api/runs/'+rid+'/files/txt')[1]
        self.assertEqual(raw[2:13].decode(),payload['config']['reporter_cuit'])
        self.assertEqual(raw[19:21],b'02');self.assertEqual(raw[21:26],b'12345')
        self.assertEqual(load(ROOT/'config/reporting.json')['synthetic_entity_code'],99999)

    def test_sources_require_per_user_allowlist_and_no_upload_paths(self):
        payload=self.payload();payload['source']='project.secret.table'
        self.assertEqual(self.request('/api/runs','POST',payload)[0],403)
        payload=self.payload();payload['files']['../../escape.csv']='x'
        self.assertEqual(self.request('/api/runs','POST',payload)[0],400)
        payload=self.payload();payload['anonymized']=False
        self.assertEqual(self.request('/api/runs','POST',payload)[0],400)
        self.assertEqual(self.request('/api/runs/../../state.sqlite3/files/txt')[0],404)

    def test_bigquery_import_adapter_is_not_cloud_parity(self):
        self.service.sources={'sample':{'users':['analyst'],'label':'Authorized source'}}
        payload=self.payload();transactions=payload['files'].pop('transactions.csv');payload['source']='sample'
        with patch.object(self.service,'import_bigquery',return_value=transactions) as imp:
            rid=self.completed(payload);imp.assert_called_once_with('sample')
        self.assertIsNone(self.request('/api/runs/'+rid+'/reporting')[1]['reports'][0]['cloud'])
        self.login('reviewer','example-test-pass-2')
        self.assertEqual(self.request('/api/config')[1]['sources'],[])

    def test_expiry_removes_source_and_outputs(self):
        rid=self.completed()
        with self.service.connect() as db: db.execute('UPDATE runs SET expires=? WHERE id=?',(time.time()-1,rid))
        self.assertEqual(self.request('/api/runs/'+rid)[0],404)
        self.service.cleanup()
        self.assertFalse(self.service.folder(self.uid,rid).exists())

    def test_server_lock_and_user_management_do_not_reset_jobs(self):
        with self.assertRaises(ValueError): Service(Path(self.temp.name))
        rid=self.ready()
        self.service.set_state(rid,'RUNNING')
        admin=Service(Path(self.temp.name),recover=False)
        try:
            admin.add_user('another','another-test-password')
            self.assertEqual(self.service.get(self.uid,rid)['state'],'RUNNING')
        finally:
            admin.close();self.service.set_state(rid,'READY')

    def test_authorized_bigquery_reader_caps_rows_and_projects_columns(self):
        from unittest.mock import MagicMock
        schema=[types.SimpleNamespace(name=k,field_type=t,mode='NULLABLE') for k,t in
                [('transaction_id','STRING'),('account_id','STRING'),('posted_date','DATE'),('kind','STRING'),('amount_cents','INTEGER')]]
        client=MagicMock();table=types.SimpleNamespace(table_type='TABLE',num_rows=1,schema=schema)
        client.get_table.return_value=table
        client.list_rows.return_value=[dict(transaction_id='t1',account_id='a1',posted_date='2026-08-01',kind='CREDIT',amount_cents=100)]
        bq=types.ModuleType('google.cloud.bigquery');bq.Client=MagicMock(return_value=client)
        cloud=types.ModuleType('google.cloud');cloud.bigquery=bq
        google=types.ModuleType('google');google.cloud=cloud
        self.service.sources={'safe':{'project':'project','table':'project.dataset.allowed','users':['analyst']}}
        with patch.dict(sys.modules,{'google':google,'google.cloud':cloud,'google.cloud.bigquery':bq}):
            text=self.service.import_bigquery('safe')
            self.assertIn('t1,a1,2026-08-01,CREDIT,100',text)
            self.assertEqual(client.list_rows.call_args.kwargs['max_results'],MAX_ROWS+1)
            self.assertEqual(len(client.list_rows.call_args.kwargs['selected_fields']),5)
            client.close.assert_called()
            table.num_rows=MAX_ROWS+1
            with self.assertRaises(ValueError): self.service.import_bigquery('safe')
            self.assertEqual(client.list_rows.call_count,1)
            table.num_rows=1;table.table_type='VIEW'
            with self.assertRaises(ValueError): self.service.import_bigquery('safe')

    def test_body_limit_and_session_revocation(self):
        self.assertEqual(self.request('/api/runs','POST',{}, {'Content-Length':str(25*1024*1024)})[0],413)
        self.service.add_user('analyst','new-example-password')
        self.assertEqual(self.request('/api/config')[0],401)


if __name__=='__main__':unittest.main()
