"""Independent fixed-position parser; deliberately does not import writer/layout JSON."""
import argparse
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from .common import valid_tax_id

# Positions transcribed separately from the official table (1-based, inclusive).
FIELDS = {
 '01': [('record_type',1,2),('reporter_cuit',3,13),('period',14,19),('sequence',20,21),('entity',22,26),('tax',27,30),('concept',31,33),('form',34,37),('filler',38,249),('version',250,254),('no_activity',255,255)],
 '02': [('record_type',1,2),('account_type',3,4),('number',5,26),('cbu',27,48),('currency',49,51),('branch',52,56),('document_type',57,58),('document',59,69),('caja',70,74),('role',75,76),('members',77,78),('cards',79,80),('credits',81,98),('own',99,116),('loan',117,134),('term',135,152),('cash',153,170),('balance_sign',171,171),('balance',172,189),('card_sign',190,190),('card',191,208),('foreign_sign',209,209),('foreign',210,227),('event',228,228),('date',229,236)],
 '03': [('record_type',1,2),('document_type',3,4),('document',5,15),('role',16,17)],
 '04': [('record_type',1,2),('deposit_type',3,4),('number',5,26),('branch',27,31),('opened',32,39),('beneficiary',40,40),('maturity',41,48),('document_type',49,50),('document',51,61),('role',62,63),('members',64,65),('caja',66,70),('principal',71,88),('interest',89,106),('principal_original',107,124),('interest_original',125,142),('currency',143,145),('event',146,146),('date',147,154)],
 '05': [('record_type',1,2),('document_type',3,4),('document',5,15),('beneficiary',16,16),('role',17,18)]
}
LENGTHS={'01':255,'02':236,'03':17,'04':154,'05':18}


def check(ok,message):
    if not ok:
        raise ValueError(message)


def valid_cbu(s):
    if len(s)!=22 or not s.isascii() or not s.isdigit() or int(s)==0:
        return False
    block1=sum(int(x)*w for x,w in zip(s[:7],[7,1,3,9,7,1,3]))
    block2=sum(int(x)*w for x,w in zip(s[8:21],[3,9,7,1,3,9,7,1,3,9,7,1,3]))
    return int(s[7])==(10-block1%10)%10 and int(s[21])==(10-block2%10)%10


def validate(data,filename=None):
    check(isinstance(data,bytes),'expected bytes')
    check(not any(b<32 and b not in (10,13) or 127<=b<=159 for b in data),'control character')
    check(b'\r' not in data.replace(b'\r\n',b''),'bare CR')
    lines=data.replace(b'\r\n',b'\n').split(b'\n')
    if lines and lines[-1]==b'': lines.pop()
    check(bool(lines),'empty file')
    counts=Counter(); totals=Counter(); parent=None; child_count=0; docs=set(); seen_accounts=set();seen_deposits=set()
    parsed=[]
    def flush():
        if parent:
            check(child_count==int(parent['members']),'member count mismatch')
    for index,raw in enumerate(lines,1):
        line=raw.decode('iso-8859-1')
        typ=line[:2]
        check(typ in LENGTHS,f'unsupported record type at line {index}')
        check(len(raw)==LENGTHS[typ],f'length mismatch at line {index}: expected {LENGTHS[typ]}, got {len(raw)}')
        r={name:line[start-1:end] for name,start,end in FIELDS[typ]}
        for name,value in r.items():
            if name not in ('filler','currency','event'):
                check(value.isascii() and value.isdigit(),f'invalid numeric {name}')
        counts[typ]+=1;parsed.append(r)
        if typ=='01':
            check(index==1,'header must be first and unique')
            check(valid_tax_id(r['reporter_cuit']),'invalid reporter CUIT checksum')
            check(r['tax']=='0103' and r['concept']=='911' and r['form']=='0943' and r['version']=='00500','header constants')
            check(r['filler']==' '*212,'header filler must contain spaces')
            check(int(r['entity'])>0 and r['no_activity'] in ('0','1'),'invalid header flags')
            period=datetime.strptime(r['period'],'%Y%m').strftime('%Y%m')
            check(period>= '202203','v500 period before supported interface date')
            header=r
            continue
        check(counts['01']==1,'missing header')
        check(r['document_type']=='80' and valid_tax_id(r['document']),'unsupported/invalid document')
        if typ in ('02','04'):
            flush();parent=r;child_count=0;docs={r['document']}
            check(int(r['number'])>0 and r['currency']=='ARS' and r['role']=='01','invalid number/currency/primary role')
            check(int(r['caja'])==0,'securities accounts outside scope')
            dt=datetime.strptime(r['date'],'%Y%m%d')
            check(dt.strftime('%Y%m')==header['period'] or (r['event']=='A' and dt.strftime('%Y%m')<header['period']),'event outside period')
        if typ=='02':
            check(r['number'] not in seen_accounts,'duplicate account record'); seen_accounts.add(r['number'])
            check(r['account_type'] in ('01','14') and valid_cbu(r['cbu']),'invalid account type/CBU')
            check(r['event'] in ('A','B','N','C'),'invalid account event')
            check(all(r[k] in ('0','1') for k in ('balance_sign','card_sign','foreign_sign')),'invalid sign')
            check(int(r['foreign'])==0 and r['foreign_sign']=='0','foreign card activity requires F8103; unsupported')
            check(sum(int(r[k]) for k in ('own','loan','term'))<=int(r['credits']),'credit breakdown exceeds total')
            for k in ('credits','cash'):
                totals[k]+=int(r[k])
            totals['balance']+=int(r['balance'])*(-1 if r['balance_sign']=='1' else 1)
            totals['card']+=int(r['card'])*(-1 if r['card_sign']=='1' else 1)
        elif typ=='04':
            check(r['number'] not in seen_deposits,'duplicate deposit record'); seen_deposits.add(r['number'])
            check(r['deposit_type']=='01' and r['beneficiary']=='2' and r['event']=='A','unsupported term deposit flags')
            opened=datetime.strptime(r['opened'],'%Y%m%d')
            maturity=datetime.strptime(r['maturity'],'%Y%m%d')
            check(opened<=maturity and opened.strftime('%Y%m')==header['period'],'invalid deposit dates')
            check(r['date']==r['opened'],'constitution/event date mismatch')
            check(int(r['principal'])>0 and r['principal']==r['principal_original'] and r['interest']==r['interest_original'],'invalid ARS deposit amounts')
            totals['principal']+=int(r['principal']);totals['interest']+=int(r['interest'])
        elif typ in ('03','05'):
            check(parent is not None and parent['record_type']==('02' if typ=='03' else '04'),'orphan member record')
            check(r['document'] not in docs,'duplicate member document'); docs.add(r['document'])
            check(r['role'] in ('03','04','05','06','07','08'),'unsupported member role')
            if typ=='05':check(r['beneficiary']=='2','nonresident member outside scope')
            child_count+=1
    flush()
    check(counts['01']==1,'missing/duplicate header')
    check((header['no_activity']=='1')==(len(lines)==1),'no-activity flag/detail mismatch')
    if filename:
        expected=f"F0943.{header['reporter_cuit']}.{header['period']}00.{int(header['sequence']):04}.txt"
        check(Path(filename).name==expected,'filename/header mismatch')
    return dict(records=len(lines),counts=dict(counts),totals_pesos=dict(totals),header=header)


def main():
    p=argparse.ArgumentParser();p.add_argument('file',type=Path);a=p.parse_args()
    result=validate(a.file.read_bytes(),a.file.name)
    print({k:v for k,v in result.items() if k!='header'})


if __name__=='__main__':main()
