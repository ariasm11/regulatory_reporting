"""Streaming local reference for the SQL model. Fail closed before serialization."""
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path
from .common import ROOT, KINDS, CREDITS, load, month_end, pesos, valid_tax_id, digest


def require(condition, message):
    if not condition:
        raise ValueError(message)


def indexed(rows, key):
    out = {}
    for row in rows:
        require(row.get(key) and row[key] not in out, f'duplicate/missing {key}')
        out[row[key]] = row
    return out


def inputs(data, period):
    data = Path(data)
    cfg = load(ROOT/'config/reporting.json')
    require(period in cfg['valid_periods'], 'period outside reviewed rule/calendar range')
    manifest=load(data/'manifest.json')
    require(manifest.get('synthetic') is True, 'demo requires synthetic data')
    if manifest.get('transaction_sha256'):
        require(digest(data/'transactions.csv')==manifest['transaction_sha256'], 'source integrity failure; incomplete or modified dataset')
    people = indexed(load(data/'customers.json'),'customer_id')
    accounts = indexed(load(data/'accounts.json'),'account_id')
    require(len({p['document'] for p in people.values()}) == len(people), 'duplicate customer document')
    for p in people.values():
        require(p['person_type'] in ('PH','PJ') and p['document_type'] == '80' and valid_tax_id(p['document']), 'invalid customer identity')
        require(isinstance(p['excluded'],bool), 'exclusion must be explicit')
    owners = set()
    account_numbers, cbus = set(), set()
    for a in accounts.values():
        require(a['customer_id'] in people, 'orphan account')
        # A deliberate scenario restriction, not a claim about reporting for multi-account customers.
        require(a['customer_id'] not in owners, 'multi-account ownership requires an approved scope policy')
        owners.add(a['customer_id'])
        require(a['number'] not in account_numbers and a['cbu'] not in cbus, 'duplicate number/CBU')
        account_numbers.add(a['number']); cbus.add(a['cbu'])
        require(a['currency']=='ARS' and a['account_type'] in ('01','14'), 'unsupported currency/account type')
        require(a['event'] in ('','A','B','C','N'), 'invalid account event')
        date.fromisoformat(a['opened'])
        if a['event']:
            dt = date.fromisoformat(a['event_date'])
            require(dt >= date.fromisoformat(a['opened']), 'event before opening')
    members = defaultdict(list)
    member_docs = defaultdict(set)
    for m in load(data/'members.json'):
        require(m['account_id'] in accounts, 'orphan member')
        a = accounts[m['account_id']]
        require(m['role'] in ('03','04','05','06','07','08'), 'joint financial ownership not implemented')
        require(m['document_type']=='80' and valid_tax_id(m['document']), 'invalid member identity')
        require(m['document'] != people[a['customer_id']]['document'] and m['document'] not in member_docs[m['account_id']], 'duplicate holder/member')
        member_docs[m['account_id']].add(m['document'])
        members[m['account_id']].append(m)
    deposits = load(data/'term_deposits.json')
    seen = set()
    for d in deposits:
        require(d['number'] not in seen, 'duplicate deposit number'); seen.add(d['number'])
        require(d['customer_id'] in owners, 'deposit without supported primary account')
        require(d['currency']=='ARS' and d['deposit_type']=='01' and d['foreign_beneficiary']==2, 'unsupported deposit')
        require(d['principal_cents']>0 and d['interest_cents']>=0, 'invalid deposit amounts')
        require(d['event']=='A' and d['opened']==d['event_date'], 'only new term deposits supported')
        require(date.fromisoformat(d['maturity']) >= date.fromisoformat(d['opened']), 'maturity before constitution')
        require(d['opened'][:7].replace('-','')==d['period'], 'deposit period mismatch')
        docs = {people[d['customer_id']]['document']}
        for m in d['members']:
            require(m['role'] in ('03','04','05','06','07','08') and m['document_type']=='80'
                    and valid_tax_id(m['document']) and m['document'] not in docs, 'invalid deposit member')
            docs.add(m['document'])
    return cfg, people, accounts, members, deposits


def local_metrics(data, period, accounts, cfg):
    cutoff = cfg['cutoffs'][period]
    metrics = defaultdict(lambda: defaultdict(int))
    snapshots = {}
    with (Path(data)/'snapshots.csv').open(newline='') as f:
        seen_snapshots = set()
        for r in csv.DictReader(f):
            key=(r['period'],r['account_id'])
            require(key not in seen_snapshots, 'duplicate snapshot'); seen_snapshots.add(key)
            require(r['account_id'] in accounts, 'orphan snapshot')
            if r['period']==period:
                snapshots[r['account_id']]={k:int(r[k]) for k in ('opening_cents','closing_cents','cutoff_cents')}
    require(set(snapshots)==set(accounts), 'missing account snapshot')
    seen = set()
    total_rows = selected_rows = 0
    with (Path(data)/'transactions.csv').open(newline='') as f:
        for t in csv.DictReader(f):
            total_rows += 1
            tid, aid, kind = t['transaction_id'],t['account_id'],t['kind']
            require(tid and tid not in seen, 'duplicate transaction_id'); seen.add(tid)
            require(aid in accounts and kind in KINDS, 'unknown transaction account/kind')
            dt = date.fromisoformat(t['posted_date'])
            a = accounts[aid]
            require(dt >= date.fromisoformat(a['opened']), 'transaction before account opening')
            require(not(a['event']=='C' and t['posted_date']>a['event_date']), 'transaction after closure')
            amount = int(t['amount_cents'])
            require(amount>0, 'nonpositive transaction amount')
            if dt.strftime('%Y%m')!=period:
                continue
            selected_rows += 1
            m = metrics[aid]
            signed = amount*KINDS[kind]
            m['delta_cents'] += signed
            if t['posted_date'] <= cutoff:
                m['cutoff_delta_cents'] += signed
            m['credits_cents'] += amount if kind in CREDITS else 0
            for name, code in [('own_credits','OWN_CREDIT'),('loan_credits','LOAN_CREDIT'),('term_credits','TERM_MATURITY_CREDIT'),('cash','CASH')]:
                m[name+'_cents'] += amount if kind==code else 0
            m['card_cents'] += amount if kind=='CARD' else -amount if kind=='CARD_REFUND' else 0
    result=[]
    for aid in accounts:
        m=metrics[aid]
        s=snapshots[aid]
        require(s['opening_cents']+m['delta_cents']==s['closing_cents'], f'closing reconciliation: {aid}')
        require(s['opening_cents']+m['cutoff_delta_cents']==s['cutoff_cents'], f'cutoff reconciliation: {aid}')
        require(accounts[aid]['account_type']=='14' or s['cutoff_cents']>=0, 'negative savings balance')
        row=dict(account_id=aid,balance_cents=s['cutoff_cents'])
        row.update({k:m[k] for k in ('credits_cents','own_credits_cents','loan_credits_cents','term_credits_cents','cash_cents','card_cents')})
        result.append(row)
    return result,dict(input_transactions=total_rows,period_transactions=selected_rows,reconciliation_difference_cents=0)


def select_metrics(metrics, people, accounts, deposits, period, cfg):
    terms=defaultdict(int)
    for d in deposits:
        if d['period']==period:
            terms[d['customer_id']]+=d['principal_cents']
    for m in metrics:
        a=accounts[m['account_id']]; p=people[a['customer_id']]
        limit=cfg['credit_balance_pesos'][p['person_type']]*100
        reasons=[name for name,hit in (
            ('CREDITS',m['credits_cents']>=limit),('BALANCE',abs(m['balance_cents'])>=limit),
            ('CASH',m['cash_cents']>=cfg['cash_pesos']*100),('CARD',m['card_cents']>=cfg['card_pesos']*100),
            ('TERM',terms[a['customer_id']]>=cfg['term_pesos'][p['person_type']]*100)) if hit]
        m['financial_trigger']=bool(reasons)
        event = bool(a['event'] and a['event_date'][:7].replace('-','')==period)
        m['reportable']=(bool(reasons) or event) and not p['excluded']
        m['reasons']=reasons+(['ACCOUNT_EVENT'] if event else [])
    return metrics


def records(metrics, people, accounts, members, deposits, period):
    """Map approved report data to record fields, retaining all scoped measures."""
    out=[]; selected_owners=set()
    for m in sorted(metrics,key=lambda r:r['account_id']):
        if not m['reportable']:
            continue
        a=accounts[m['account_id']]; p=people[a['customer_id']]
        if m['financial_trigger']:
            selected_owners.add(p['customer_id'])
        event=a['event'] if a['event'] and a['event_date'][:7].replace('-','')==period else 'N'
        event_date=a['event_date'] if event==a['event'] else month_end(period).isoformat()
        r=dict(record_type='02',account_type=a['account_type'],number=a['number'],cbu=a['cbu'],
               currency='ARS',branch=a['branch'],document_type=p['document_type'],document=p['document'],
               caja_valores=0,role='01',member_count=len(members[a['account_id']]),additional_cards=a['additional_cards'],
               balance_sign=int(m['balance_cents']<0),balance=abs(pesos(m['balance_cents'])),
               card_sign=int(m['card_cents']<0),card=abs(pesos(m['card_cents'])),
               foreign_card_sign=0,foreign_card=0,event=event,event_date=event_date.replace('-',''))
        for k in ('credits','own_credits','loan_credits','term_credits','cash'):
            r[k]=pesos(m[k+'_cents'])
        out.append(r)
        for member in sorted(members[a['account_id']],key=lambda m:m['document']):
            out.append(dict(record_type='03',**{k:member[k] for k in ('document_type','document','role')}))
    for d in sorted(deposits,key=lambda d:int(d['number'])):
        if d['period']!=period or d['customer_id'] not in selected_owners:
            continue
        p=people[d['customer_id']]
        out.append(dict(record_type='04',deposit_type=d['deposit_type'],number=d['number'],branch=d['branch'],
                        opened=d['opened'].replace('-',''),foreign_beneficiary=d['foreign_beneficiary'],
                        maturity=d['maturity'].replace('-',''),document_type=p['document_type'],document=p['document'],
                        role='01',member_count=len(d['members']),caja_valores=0,
                        principal=pesos(d['principal_cents']),interest=pesos(d['interest_cents']),
                        principal_original=pesos(d['principal_cents']),interest_original=pesos(d['interest_cents']),
                        currency='ARS',event=d['event'],event_date=d['event_date'].replace('-','')))
        for m in d['members']:
            out.append(dict(record_type='05',document_type=m['document_type'],document=m['document'],
                            foreign_beneficiary=2,role=m['role']))
    return out
