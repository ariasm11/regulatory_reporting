"""Versioned CSV boundary for the execution console. No arbitrary mappings or paths."""
import csv
import io
import re
import zipfile
from datetime import date
from pathlib import Path
from .common import ROOT, dump, load, digest, valid_tax_id, KINDS
from .validate import valid_cbu, validate
from .pipeline import inputs, local_metrics, select_metrics, records
from .export import serialize

VERSION = 'csv-v1'
MAX_ROWS = 100_000
# CSV header -> exact type; identifiers stay strings, including leading zeroes.
SCHEMAS = {
 'transactions.csv': {'transaction_id':'id','account_id':'id','posted_date':'date','kind':'str','amount_cents':'positive'},
 'customers.csv': {'customer_id':'id','person_type':'str','document_type':'str','document':'tax_id','synthetic_name':'str','excluded':'bool'},
 'accounts.csv': {'account_id':'id','customer_id':'id','number':'digits','cbu':'cbu','account_type':'str','currency':'str','branch':'nonnegative','additional_cards':'nonnegative','opened':'date','event':'optional','event_date':'optional_date'},
 'snapshots.csv': {'period':'period','account_id':'id','opening_cents':'int','closing_cents':'int','cutoff_cents':'int'},
 'members.csv': {'account_id':'id','document_type':'str','document':'tax_id','role':'str'},
 'term_deposits.csv': {'period':'period','customer_id':'id','number':'digits','deposit_type':'str','branch':'nonnegative','opened':'date','maturity':'date','principal_cents':'positive','interest_cents':'nonnegative','currency':'str','foreign_beneficiary':'nonnegative','event':'str','event_date':'date'},
 'deposit_members.csv': {'deposit_number':'digits','document_type':'str','document':'tax_id','role':'str'},
}
REQUIRED = {'transactions.csv','customers.csv','accounts.csv','snapshots.csv'}
UNIQUE = {'transactions.csv':('transaction_id',),'customers.csv':('customer_id',),'accounts.csv':('account_id',),'snapshots.csv':('period','account_id'),'members.csv':('account_id','document'),'term_deposits.csv':('number',),'deposit_members.csv':('deposit_number','document')}


def contract():
    return {'version':VERSION,'max_rows_per_file':MAX_ROWS,'encoding':'UTF-8','delimiter':',',
            'money':'integer centavos; reportable aggregates must be exact pesos',
            'files':{name:{'required':name in REQUIRED,'columns':schema} for name,schema in SCHEMAS.items()}}


def options(value):
    if not isinstance(value,dict):
        raise ValueError('configuration must be an object')
    cfg=load(ROOT/'config/reporting.json')
    if value.get('rules_id')!=cfg['rules_id'] or value.get('period') not in cfg['valid_periods']:
        raise ValueError('Select a reviewed rules version and period')
    reporter=value.get('reporter_cuit','')
    entity=value.get('entity_code','')
    sequence=value.get('sequence',0)
    if not isinstance(reporter,str) or not valid_tax_id(reporter):
        raise ValueError('Invalid anonymized reporter CUIT checksum')
    if not isinstance(entity,str) or not re.fullmatch(r'[0-9]{5}',entity) or int(entity)==0:
        raise ValueError('Entity code must contain five digits and be positive')
    if type(sequence) is not int or not 0<=sequence<=99:
        raise ValueError('Sequence must be an integer between 0 and 99')
    presentation=value.get('presentation')
    if presentation not in ('original','replacement') or (presentation=='original') != (sequence==0):
        raise ValueError('Original requires sequence 0; replacement requires 1–99')
    return dict(period=value['period'],rules_id=cfg['rules_id'],reporter_cuit=reporter,entity_code=entity,
                sequence=sequence,presentation=presentation)


def converted(value,typ):
    if value is None or len(value)>200:
        raise ValueError('missing or oversized value (maximum 200 characters)')
    if typ.startswith('optional') and not value:
        return ''
    if not value or any(ord(c)<32 or 127<=ord(c)<=159 for c in value):
        raise ValueError('empty value or control character')
    if typ in ('int','positive','nonnegative'):
        if not re.fullmatch(r'-?[0-9]{1,18}',value):
            raise ValueError('expected integer, without decimal or thousands separators')
        result=int(value)
        if typ=='positive' and result<=0 or typ=='nonnegative' and result<0:
            raise ValueError('amount or count outside allowed range')
        return result
    if typ=='bool':
        if value not in ('true','false'):
            raise ValueError('expected true or false')
        return value=='true'
    if typ in ('date','optional_date'):
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value):
            raise ValueError('expected YYYY-MM-DD')
        date.fromisoformat(value)
    if typ=='period':
        if not re.fullmatch(r'[0-9]{6}',value):
            raise ValueError('expected YYYYMM')
        date(int(value[:4]),int(value[4:]),1)
    if typ=='id' and not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value):
        raise ValueError('identifier: 1–64 letters, digits, underscores or hyphens')
    if typ=='digits' and not re.fullmatch(r'[0-9]{1,22}',value):
        raise ValueError('expected 1–22 digits')
    if typ=='tax_id' and not valid_tax_id(value):
        raise ValueError('invalid substitute CUIT checksum')
    if typ=='cbu' and not valid_cbu(value):
        raise ValueError('invalid substitute CBU checksum')
    return value


def parse_files(files):
    errors=[];tables={};counts={}
    def error(file,row,field,message):
        if len(errors)<100:
            errors.append(dict(file=file,row=row,field=field,message=message))
    if not isinstance(files,dict):
        return {},[dict(file='',row=0,field='',message='files must be an object')],{}
    for name in files.keys()-SCHEMAS.keys():
        error(name,0,'','unknown file; use the published templates')
    for name,schema in SCHEMAS.items():
        tables[name]=[]
        if name not in files:
            if name in REQUIRED: error(name,0,'','required file is missing')
            continue
        text=files[name]
        if not isinstance(text,str):
            error(name,0,'','expected UTF-8 CSV text');continue
        try:
            reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff'),newline=''),strict=True)
            if reader.fieldnames is None or len(reader.fieldnames)!=len(schema) or set(reader.fieldnames)!=set(schema):
                error(name,1,'','header must contain exactly: '+','.join(schema));continue
            seen=set()
            for index,row in enumerate(reader,2):
                if index>MAX_ROWS+1:
                    error(name,index,'',f'maximum {MAX_ROWS} rows');break
                if None in row or None in row.values():
                    error(name,index,'','column count does not match header');continue
                result={}
                for field,typ in schema.items():
                    try: result[field]=converted(row[field],typ)
                    except ValueError as exc: error(name,index,field,str(exc))
                if len(result)!=len(schema): continue
                key=tuple(result[f] for f in UNIQUE[name])
                if key in seen: error(name,index,','.join(UNIQUE[name]),'duplicate key')
                seen.add(key);tables[name].append(result)
            counts[name]=len(tables[name])
        except (csv.Error,ValueError) as exc:
            error(name,0,'','invalid CSV: '+str(exc))
    if not errors:
        customers={r['customer_id'] for r in tables['customers.csv']}
        accounts={r['account_id'] for r in tables['accounts.csv']}
        deposits={r['number'] for r in tables['term_deposits.csv']}
        for name,field,keys in [('accounts.csv','customer_id',customers),('transactions.csv','account_id',accounts),('snapshots.csv','account_id',accounts),('members.csv','account_id',accounts),('term_deposits.csv','customer_id',customers),('deposit_members.csv','deposit_number',deposits)]:
            for i,row in enumerate(tables[name],2):
                if row[field] not in keys: error(name,i,field,'reference does not exist in the related file')
        for i,row in enumerate(tables['transactions.csv'],2):
            if row['kind'] not in KINDS: error('transactions.csv',i,'kind','unsupported transaction kind')
    return tables,errors,counts


def csv_text(name,rows):
    out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=SCHEMAS[name],extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow({k:str(v).lower() if isinstance(v,bool) else v for k,v in row.items() if k in SCHEMAS[name]})
    return out.getvalue()


def write_inputs(data,tables,source):
    data=Path(data);data.mkdir(parents=True,exist_ok=True)
    for name in ('transactions.csv','snapshots.csv'):
        (data/name).write_text(csv_text(name,tables[name]),encoding='utf-8',newline='')
    for name in ('customers','accounts','members'):
        dump(data/(name+'.json'),tables[name+'.csv'])
    deposits=tables['term_deposits.csv']
    children={}
    for member in tables['deposit_members.csv']:
        children.setdefault(member['deposit_number'],[]).append({k:v for k,v in member.items() if k!='deposit_number'})
    for deposit in deposits: deposit['members']=children.get(deposit['number'],[])
    dump(data/'term_deposits.json',deposits)
    dump(data/'manifest.json',{'data_classification':'anonymized','anonymization_attested':True,
         'contract_version':VERSION,'source':source,'transaction_sha256':digest(data/'transactions.csv')})


def preflight(data,config):
    cfg,people,accounts,members,deposits=inputs(data,config['period'])
    metrics,quality=local_metrics(data,config['period'],accounts,cfg)
    metrics=select_metrics(metrics,people,accounts,deposits,config['period'],cfg)
    detail=records(metrics,people,accounts,members,deposits,config['period'])
    name,raw=serialize(detail,config['period'],config['sequence'],config['reporter_cuit'],config['entity_code'])
    checked=validate(raw,name)
    return dict(quality=quality,record_counts=checked['counts'],reported_accounts=sum(r['reportable'] for r in metrics))


def sample_files():
    data=ROOT/'data/sample';files={}
    for name in ('transactions.csv','snapshots.csv'): files[name]=(data/name).read_text()
    for name in ('customers','accounts','members'): files[name+'.csv']=csv_text(name+'.csv',load(data/(name+'.json')))
    deposits=load(data/'term_deposits.json')
    files['term_deposits.csv']=csv_text('term_deposits.csv',deposits)
    files['deposit_members.csv']=csv_text('deposit_members.csv',[dict(deposit_number=d['number'],**m) for d in deposits for m in d['members']])
    return files


def template_zip(sample=False):
    out=io.BytesIO()
    files=sample_files() if sample else {n:csv_text(n,[]) for n in SCHEMAS}
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,text in files.items(): z.writestr(name,text)
        z.writestr('contract.json',__import__('json').dumps(contract(),indent=2))
    return out.getvalue()
