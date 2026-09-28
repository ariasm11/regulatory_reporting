"""Measure a portfolio batch in a separate BigQuery dataset, with parity gates."""
import argparse
import csv
import json
from pathlib import Path
from siter.common import ROOT, load, dump
from siter.pipeline import require, inputs
from siter.bigquery import load_data
from siter.run import execute
from siter.cloud_demo import compare_runs


TRIAL_ROW_LIMIT=100_000


def check_trial_batch(data):
    """Check actual CSV rows before any cloud call, not just its manifest."""
    with (Path(data)/'transactions.csv').open(newline='',encoding='utf-8') as f:
        reader=csv.DictReader(f)
        count=0
        for count,_ in enumerate(reader,1):
            require(count<=TRIAL_ROW_LIMIT,'trial exceeds the 100,000 transaction limit; no cloud load started')
    require(count>0,'empty trial batch')
    require(load(Path(data)/'manifest.json')['transaction_count']==count,'trial row count/manifest mismatch')
    return count


def main():
    connection=load(ROOT/'config/bigquery.json')
    cfg=load(ROOT/'config/reporting.json')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',default=connection['project_id'])
    parser.add_argument('--dataset',default='siter_trial_100k')
    parser.add_argument('--location',default=connection['location'])
    parser.add_argument('--data',type=Path,default=ROOT/'data/trial_100k')
    parser.add_argument('--periods',nargs='+',choices=cfg['valid_periods'],default=['202608'])
    parser.add_argument('--out',type=Path,default=ROOT/'output/cloud_trial_100k')
    args=parser.parse_args()
    require(args.dataset not in (connection['source_dataset'],connection['working_dataset']),
            'use a separate dataset for the scale benchmark')
    require((args.data/'manifest.json').is_file(),
            'trial data missing; run python3 -m siter.generate --out data/trial_100k --transactions 100000 --customers 2000')
    row_count=check_trial_batch(args.data)
    for period in args.periods:
        inputs(args.data,period)
    result={'status':'FAIL','project':args.project,'dataset':args.dataset,
            'location':args.location,'requested_periods':args.periods,'row_count':row_count,
            'row_limit':TRIAL_ROW_LIMIT,'runs':[]}
    try:
        print('Loading portfolio batch into '+args.dataset,flush=True)
        result['load']=load_data(args.data,args.project,args.dataset,args.location)
        for period in args.periods:
            print('Comparing local and BigQuery: '+period,flush=True)
            local_dir,local=execute(args.data,args.out/'local',period)
            cloud_dir,cloud=execute(args.data,args.out/'bigquery',period,engine='bigquery',
                project=args.project,dataset=args.dataset,location=args.location)
            parity=compare_runs(local_dir,cloud_dir)
            result['runs'].append(dict(period=period,**parity,quality=cloud['quality'],
                local_total_seconds=local['total_seconds'],cloud_total_seconds=cloud['total_seconds'],
                local_directory=str(local_dir),cloud_directory=str(cloud_dir)))
        result['status']='PASS_LOCAL_BIGQUERY_PARITY_NOT_ARCA_ACCEPTANCE'
    except Exception as exc:
        result['error']=str(exc)
        raise
    finally:
        dump(args.out/'cloud_scale_result.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
