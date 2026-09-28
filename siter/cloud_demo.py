"""Run the user-configured sample and prove local/BigQuery output parity."""
import argparse
import json
from pathlib import Path
from .common import ROOT, dump, load
from .pipeline import require
from .bigquery import load_data
from .run import execute


def compare_runs(local_dir,cloud_dir):
    local_dir,cloud_dir=Path(local_dir),Path(cloud_dir)
    a,b=load(local_dir/'audit.json'),load(cloud_dir/'audit.json')
    require(a['txt_sha256']==b['txt_sha256'],'local/BigQuery TXT mismatch')
    require(a['zip_sha256']==b['zip_sha256'],'local/BigQuery ZIP mismatch')
    decisions=lambda p: sorted(load(p/'account_decisions.json'),key=lambda row:row['account_id'])
    require(decisions(local_dir)==decisions(cloud_dir),'local/BigQuery account decisions mismatch')
    return {'txt_sha256':a['txt_sha256'],'zip_sha256':a['zip_sha256'],
            'reported_accounts':a['reported_accounts'],'record_counts':a['record_counts']}


def run_demo(connection,data,period,out):
    cfg=load(connection)
    source='.'.join([cfg['project_id'],cfg['source_dataset'],cfg['source_table']])
    out=Path(out)
    # Fail locally on invalid data/specifications before any cloud writes.
    local_dir,_=execute(data,out/'local',period)
    result=dict(status='FAIL',source_table=source,period=period,local_directory=str(local_dir))
    try:
        result['load']=load_data(data,cfg['project_id'],cfg['working_dataset'],cfg['location'],source)
        cloud_dir,cloud=execute(data,out/'bigquery',period,engine='bigquery',
            project=cfg['project_id'],dataset=cfg['working_dataset'],location=cfg['location'])
        result['cloud_directory']=str(cloud_dir)
        result.update(compare_runs(local_dir,cloud_dir))
        result['quality']=cloud['quality']
        result['status']='PASS_LOCAL_BIGQUERY_PARITY_NOT_ARCA_ACCEPTANCE'
    except Exception as exc:
        result['error']=str(exc)
        raise
    finally:
        dump(out/'cloud_demo_result.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection',type=Path,default=ROOT/'config/bigquery.json')
    parser.add_argument('--data',type=Path,default=ROOT/'data/sample')
    parser.add_argument('--period',default='202608')
    parser.add_argument('--out',type=Path,default=ROOT/'output/cloud_demo')
    args=parser.parse_args()
    print(json.dumps(run_demo(args.connection,args.data,args.period,args.out),indent=2))


if __name__=='__main__':main()
