"""Build offline UX assets from the validated sample; never connects to cloud."""
import argparse
import shutil
from pathlib import Path
from siter.common import ROOT, load, dump
from siter.run import execute


def export(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    data=ROOT/'data/sample'
    accounts={r['account_id']:r for r in load(data/'accounts.json')}
    people={r['customer_id']:r for r in load(data/'customers.json')}
    evidence=load(ROOT/'examples/cloud_sample_202608.json')
    reports=[]
    for period in load(ROOT/'config/reporting.json')['valid_periods']:
        folder,audit=execute(data,ROOT/'output/ux_reference',period)
        target=out/period;target.mkdir(exist_ok=True)
        txt=folder/audit['file'];zipname=audit['file'][:-4]+'.zip'
        for name in (audit['file'],zipname,'audit.json','account_decisions.json'):
            shutil.copy2(folder/name,target/name)
        metrics=load(folder/'account_decisions.json')
        for row in metrics:
            person=people[accounts[row['account_id']]['customer_id']]
            row.update(customer_id=person['customer_id'],name=person['synthetic_name'],person_type=person['person_type'])
        cloud=evidence if period==evidence['result']['period'] else None
        if cloud:
            assert audit['txt_sha256']==cloud['result']['txt_sha256']
            assert audit['zip_sha256']==cloud['result']['zip_sha256']
        reports.append(dict(period=period,audit=audit,accounts=metrics,cloud=cloud,
            lines=txt.read_bytes().decode('iso-8859-1').split('\r\n')[:-1],
            files={'txt':f'data/{period}/{audit["file"]}',
                   'zip':f'data/{period}/{zipname}',
                   'audit':f'data/{period}/audit.json',
                   'accounts':f'data/{period}/account_decisions.json'}))
    dump(out/'reporting.json',dict(dataset='sample',source_transactions=1200,account_count=50,
        cloud_scope='August 2026 only; user-supplied execution summary',
        synthetic=True,live_connection=False,reports=reports,
        layout=load(ROOT/'config/layout_v500.json')['records']))
    dump(out/'cloud_evidence.json',evidence)
    return {'periods':len(reports),'out':str(out),'cloud_connections':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    print(export(parser.parse_args().out))
