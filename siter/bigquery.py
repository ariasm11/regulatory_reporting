"""Optional cloud adapter. Run locally without installing Google dependencies."""
import argparse
import json
import re
import uuid
from datetime import date
from pathlib import Path
from .common import ROOT, load, digest, month_end
from .pipeline import inputs, require
from .source_identity import csv_identity, combine_sorted_hashes, identity_sql, table_id, FIELDS


def client_for(project,dataset,location):
    require(bool(project) and re.fullmatch(r'[a-z][a-z0-9-]{4,62}',project), 'invalid GCP project ID')
    require(bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',dataset)), 'invalid dataset ID')
    from google.cloud import bigquery
    return bigquery,bigquery.Client(project=project,location=location)


def cloud_identity(bq,client,source):
    job=client.query(identity_sql(source),job_config=bq.QueryJobConfig(maximum_bytes_billed=20_000_000_000))
    identity=combine_sorted_hashes(row['row_hash'] for row in job.result())
    return identity,{'identity_job_id':job.job_id,'identity_bytes_processed':job.total_bytes_processed}


def check_schema(table):
    allowed={key:{'STRING'} for key in FIELDS}
    allowed['posted_date']={'STRING','DATE'}
    allowed['amount_cents']={'STRING','INTEGER','INT64'}
    require({f.name for f in table.schema}==set(FIELDS),'unexpected source transaction columns')
    for f in table.schema:
        require(f.field_type in allowed[f.name] and f.mode!='REPEATED',
                'unsupported source column type: '+f.name)


def load_data(data,project,dataset='siter_portfolio',location='US',source_table=None):
    data=Path(data)
    # Validate supported dimensional scope before replacing any portfolio tables.
    cfg=load(ROOT/'config/reporting.json')
    inputs(data,cfg['valid_periods'][-1])
    expected=csv_identity(data/'transactions.csv')
    if source_table:
        table_id(source_table)
        require('.'.join(source_table.split('.')[:2])!=f'{project}.{dataset}',
                'use a separate working dataset to protect the source tables')
    bq,client=client_for(project,dataset,location)
    if source_table:
        check_schema(client.get_table(source_table))
        source_ds=client.get_dataset('.'.join(source_table.split('.')[:2]))
        require(source_ds.location.upper()==location.upper(),'source dataset location mismatch')
    ds=bq.Dataset(f'{project}.{dataset}');ds.location=location
    ds=client.create_dataset(ds,exists_ok=True)
    require(ds.location.upper()==location.upper(),'working dataset location mismatch')
    candidate=None
    try:
        if source_table:
            # Copy first: verification and ingestion refer to the same stable
            # batch even if Sample changes while we are checking its contents.
            candidate=f'{project}.{dataset}._siter_import_{uuid.uuid4().hex}'
            client.copy_table(source_table,candidate,job_config=bq.CopyJobConfig(
                write_disposition='WRITE_EMPTY'),location=location).result()
            actual,identity_job=cloud_identity(bq,client,candidate)
            require(actual==expected,
                    'Sample/local CSV content mismatch; use auxiliary files from the same batch')
        # Invalidate a prior successful load before replacing its tables. A
        # failed partial load must not be exportable using the old manifest.
        client.delete_table(f'{project}.{dataset}.source_manifest',not_found_ok=True)
        _load_tables(data,project,dataset,bq,client,skip_transactions=bool(source_table))
        if candidate:
            client.copy_table(candidate,f'{project}.{dataset}.raw_transactions',
                job_config=bq.CopyJobConfig(write_disposition='WRITE_TRUNCATE'),location=location).result()
        actual,identity_job=cloud_identity(bq,client,f'{project}.{dataset}.raw_transactions')
        require(actual==expected,'loaded transaction content mismatch')
        binding=dict(source_table=source_table or 'local:transactions.csv',**actual)
        client.load_table_from_json([binding],f'{project}.{dataset}.source_binding',job_config=bq.LoadJobConfig(
            schema=[bq.SchemaField('source_table','STRING'),bq.SchemaField('row_count','INTEGER'),
                    bq.SchemaField('content_sha256','STRING')],write_disposition='WRITE_TRUNCATE')).result()
        hashes=[dict(filename=p.name,sha256=digest(p)) for p in sorted(data.iterdir()) if p.is_file()]
        client.load_table_from_json(hashes,f'{project}.{dataset}.source_manifest',job_config=bq.LoadJobConfig(
            schema=[bq.SchemaField('filename','STRING'),bq.SchemaField('sha256','STRING')],write_disposition='WRITE_TRUNCATE')).result()
        return {'loaded_project':project,'dataset':dataset,**binding,**identity_job}
    finally:
        if candidate:
            client.delete_table(candidate,not_found_ok=True)


def _load_tables(data,project,dataset,bq,client,skip_transactions=False):
    for table in ('customers','accounts','members','term_deposits'):
        rows=load(data/f'{table}.json')
        if table=='term_deposits': rows=[{k:v for k,v in r.items() if k!='members'} for r in rows]
        if not rows:
            # Supported empty product populations still need fixed schemas.
            defaults={
              'members':dict(account_id='',document_type='',document='',role=''),
              'term_deposits':dict(period='',customer_id='',number='',deposit_type='',branch=0,opened='',maturity='',principal_cents=0,interest_cents=0,currency='',foreign_beneficiary=0,event='',event_date='')}
            sample=defaults[table]
        else: sample=rows[0]
        schema=[bq.SchemaField(k,'BOOLEAN' if isinstance(v,bool) else 'INTEGER' if isinstance(v,int) else 'STRING',mode='REQUIRED') for k,v in sample.items()]
        job=client.load_table_from_json(rows,f'{project}.{dataset}.{table}',
                job_config=bq.LoadJobConfig(schema=schema,write_disposition='WRITE_TRUNCATE'))
        job.result()
    for file,table,fields in (
        ('transactions.csv','raw_transactions',['transaction_id','account_id','posted_date','kind','amount_cents']),
        ('snapshots.csv','raw_snapshots',['period','account_id','opening_cents','closing_cents','cutoff_cents'])):
        if skip_transactions and table=='raw_transactions':
            continue
        config=bq.LoadJobConfig(schema=[bq.SchemaField(f,'STRING',mode='REQUIRED') for f in fields],
                   source_format=bq.SourceFormat.CSV,skip_leading_rows=1,write_disposition='WRITE_TRUNCATE',max_bad_records=0)
        with (data/file).open('rb') as f:
            client.load_table_from_file(f,f'{project}.{dataset}.{table}',job_config=config).result()


def query_metrics(project,dataset,location,period,cfg,people,accounts):
    bq,client=client_for(project,dataset,location)
    sql=(ROOT/'sql/monthly.sql').read_text().replace('__PROJECT__',project).replace('__DATASET__',dataset).replace('__PERIOD__',period)
    scalars={'credit_ph':cfg['credit_balance_pesos']['PH']*100,'credit_pj':cfg['credit_balance_pesos']['PJ']*100,
             'term_ph':cfg['term_pesos']['PH']*100,'term_pj':cfg['term_pesos']['PJ']*100,
             'cash':cfg['cash_pesos']*100,'card':cfg['card_pesos']*100}
    params=[bq.ScalarQueryParameter(k,'INT64',v) for k,v in scalars.items()]
    params += [bq.ScalarQueryParameter('period','STRING',period),
               bq.ScalarQueryParameter('period_start','DATE',month_end(period).replace(day=1)),
               bq.ScalarQueryParameter('period_end','DATE',month_end(period)),
               bq.ScalarQueryParameter('cutoff','DATE',date.fromisoformat(cfg['cutoffs'][period]))]
    job=client.query(sql,job_config=bq.QueryJobConfig(query_parameters=params,maximum_bytes_billed=20_000_000_000));job.result()
    values=[dict(row) for row in client.query(f'SELECT * FROM `{project}.{dataset}.report_{period}` ORDER BY account_id').result()]
    require(len(values)==len(accounts) and {v['account_id'] for v in values}==set(accounts),'cloud account coverage mismatch')
    return values,dict(query_job_id=job.job_id,bytes_processed=job.total_bytes_processed,slot_millis=job.slot_millis,
                       reconciliation_difference_cents=0)


def verify_source(data,project,dataset,location):
    bq,client=client_for(project,dataset,location)
    loaded={r['filename']:r['sha256'] for r in client.query(f'SELECT * FROM `{project}.{dataset}.source_manifest`').result()}
    local={p.name:digest(p) for p in Path(data).iterdir() if p.is_file()}
    require(loaded==local,'cloud/local source manifest mismatch; reload data first')
    bindings=list(client.query(f'SELECT * FROM `{project}.{dataset}.source_binding`').result())
    require(len(bindings)==1,'missing or ambiguous source binding; reload data first')
    binding=dict(bindings[0])
    actual,job=cloud_identity(bq,client,f'{project}.{dataset}.raw_transactions')
    expected={key:binding[key] for key in ('row_count','content_sha256')}
    require(actual==expected==csv_identity(Path(data)/'transactions.csv'),
            'transaction content changed since load; reload the matching batch')
    return dict(**binding,**job)


def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=ROOT/'data/portfolio')
    p.add_argument('--project',required=True);p.add_argument('--dataset',default='siter_portfolio');p.add_argument('--location',default='US')
    p.add_argument('--source-table',help='Existing fully qualified transaction table; verified against the local CSV')
    a=p.parse_args();print(json.dumps(load_data(a.data,a.project,a.dataset,a.location,a.source_table),indent=2))


if __name__=='__main__':main()
