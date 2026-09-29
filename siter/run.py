import argparse
import json
import platform
import time
import zipfile
from pathlib import Path
from .common import ROOT, load, dump, digest, pesos
from .pipeline import inputs, local_metrics, select_metrics, records, require
from .export import serialize
from .validate import validate


def execute(data,out,period,sequence=0,engine='local',project=None,dataset='siter_portfolio',location='US',reporter=None,entity=None):
    data,out=Path(data),Path(out)
    begin=time.perf_counter()
    cfg,people,accounts,members,deposits=inputs(data,period)
    if engine=='bigquery':
        from .bigquery import query_metrics, verify_source
        source_binding=verify_source(data,project,dataset,location)
        metrics,quality=query_metrics(project,dataset,location,period,cfg,people,accounts)
        quality['source_binding']=source_binding
    else:
        metrics,quality=local_metrics(data,period,accounts,cfg)
        metrics=select_metrics(metrics,people,accounts,deposits,period,cfg)
    modeled=time.perf_counter()
    detail=records(metrics,people,accounts,members,deposits,period)
    name,raw=serialize(detail,period,sequence,reporter,entity)
    checked=validate(raw,name)
    # Compare independently parsed TXT totals against pre-serialization model values.
    selected=[r for r in metrics if r['reportable']]
    expected={key:sum(pesos(r[col]) for r in selected) for key,col in
              [('credits','credits_cents'),('cash','cash_cents'),('balance','balance_cents'),('card','card_cents')]}
    financial_owners={accounts[r['account_id']]['customer_id'] for r in selected if r['financial_trigger']}
    selected_deposits=[d for d in deposits if d['period']==period and d['customer_id'] in financial_owners]
    expected['principal']=sum(pesos(d['principal_cents']) for d in selected_deposits)
    expected['interest']=sum(pesos(d['interest_cents']) for d in selected_deposits)
    for key,value in expected.items():
        require(checked['totals_pesos'].get(key,0)==value,'TXT/model total mismatch: '+key)
    require(checked['counts'].get('02',0)==len(selected),'TXT/model account count mismatch')
    require(checked['counts'].get('04',0)==len(selected_deposits),'TXT/model deposit count mismatch')
    source_hashes={p.name:digest(p) for p in sorted(data.iterdir()) if p.is_file()}
    code_hashes={str(p.relative_to(ROOT)):digest(p) for folder in ('siter','config','sql') for p in sorted((ROOT/folder).glob('*')) if p.is_file()}
    import hashlib
    run_id=hashlib.sha256(json.dumps([source_hashes,code_hashes,period,sequence,engine,reporter,entity],sort_keys=True).encode()).hexdigest()[:16]
    dest=out/f'{period}_{sequence:02}_{run_id}'
    dest.mkdir(parents=True,exist_ok=True)
    txt=dest/name;txt.write_bytes(raw)
    zipped=dest/(name[:-4]+'.zip')
    with zipfile.ZipFile(zipped,'w',zipfile.ZIP_DEFLATED) as z:
        # Deterministic zip bytes; one official-named TXT, no control file invented.
        info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
    dump(dest/'account_decisions.json',metrics)
    dump(dest/'record_fields.json',detail)
    summary=dict(status='PASS_LOCAL_CONTROLS_NOT_ARCA_ACCEPTANCE',engine=engine,run_id=run_id,period=period,
                 sequence=sequence,reporter_cuit=reporter or cfg['synthetic_reporter_cuit'],
                 entity_code=entity or cfg['synthetic_entity_code'],rules_id=cfg['rules_id'],input_hashes=source_hashes,code_hashes=code_hashes,
                 txt_sha256=digest(txt),zip_sha256=digest(zipped),file=name,bytes=len(raw),
                 quality=quality,record_counts=checked['counts'],totals_pesos=checked['totals_pesos'],
                 account_count=len(accounts),reported_accounts=len(selected),
                 model_seconds=round(modeled-begin,3),total_seconds=round(time.perf_counter()-begin,3),
                 python=platform.python_version(),platform=platform.platform(),
                 limitations=['Synthetic or anonymized identifiers; never transmit this demo',
                              'Header length 255 follows positions; prose says 43',
                              'No official ARCA validator or registered identity verification'])
    dump(dest/'audit.json',summary)
    return dest,summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=ROOT/'data/sample')
    p.add_argument('--out',type=Path,default=ROOT/'output')
    p.add_argument('--period',default='202608');p.add_argument('--sequence',type=int,default=0)
    p.add_argument('--engine',choices=['local','bigquery'],default='local')
    p.add_argument('--project');p.add_argument('--dataset',default='siter_portfolio');p.add_argument('--location',default='US')
    a=p.parse_args()
    dest,result=execute(a.data,a.out,a.period,a.sequence,a.engine,a.project,a.dataset,a.location)
    print(json.dumps(dict(directory=str(dest),**{k:result[k] for k in ('engine','reported_accounts','record_counts','total_seconds','txt_sha256')}),indent=2))


if __name__=='__main__':main()
