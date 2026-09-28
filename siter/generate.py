"""Deterministic configurable source data. No names or identities from real people."""
import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path
from .common import ROOT, KINDS, cbu, tax_id, dump, load, month_end, digest


def write_csv(path, fields, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def generate(out, count=1_000_000, customers=20_000, seed=4298):
    if customers < 10 or count < 0:
        raise ValueError('at least 10 customers and nonnegative transaction count required')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    config = load(ROOT/'config/reporting.json')
    periods = config['valid_periods']
    people, accounts, members = [], [], []
    balances = {}
    for i in range(1, customers+1):
        cid, aid = f'C{i:07}', f'A{i:07}'
        typ = 'PJ' if i % 4 == 0 else 'PH'
        # Widely separated body ranges avoid collisions after checksum adjustment.
        doc = tax_id((3000000000 if typ == 'PJ' else 2000000000) + i*10)
        people.append(dict(customer_id=cid, person_type=typ, document_type='80', document=doc,
                           synthetic_name=f'PERSONA FICTICIA {i}', excluded=False))
        accounts.append(dict(account_id=aid, customer_id=cid, number=str(i), cbu=cbu(i),
                             account_type='01', currency='ARS', branch=1, additional_cards=0,
                             opened='2026-01-01', event='', event_date=''))
        if i % 20 == 0:
            # Representative, not co-owner: avoids unsupported mixed ownership threshold policy.
            members.append(dict(account_id=aid, document_type='80',
                                document=tax_id(2700000000+i*10), role='04'))
        balances[aid] = rng.randint(10_000, 45_000_000)*100
    dump(out/'customers.json', people)
    dump(out/'accounts.json', accounts)
    dump(out/'members.json', members)
    # Independently generated source-system snapshots, not copied from report aggregation.
    snapshots, deposits = [], []
    tx_path = out/'transactions.csv'
    serial = 0
    with tx_path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['transaction_id','account_id','posted_date','kind','amount_cents'])
        for mi, period in enumerate(periods):
            first = date(int(period[:4]), int(period[4:]), 1)
            end = month_end(period)
            cutoff = date.fromisoformat(config['cutoffs'][period])
            opening = balances.copy()
            cutoff_balances = None
            n = count//6 + (1 if mi < count%6 else 0)
            for day in range(1,end.day+1):
                dt = first.replace(day=day)
                daily_n = n//end.day + (1 if day <= n%end.day else 0)
                for _ in range(daily_n):
                    # A small active group produces a large share of operations.
                    idx = 1+min(customers-1, int(rng.random()**2*customers))
                    aid = f'A{idx:07}'
                    kind = rng.choices(list(KINDS), weights=[27,8,4,2,9,22,2,26])[0]
                    amount = max(1,int(rng.lognormvariate(11.8,1.8)))*100
                    if KINDS[kind] < 0:
                        if balances[aid] <= 0:
                            kind = 'CREDIT'
                        else:
                            amount = min(amount, balances[aid])
                    balances[aid] += KINDS[kind]*amount
                    serial += 1
                    w.writerow([f'T{serial:012}',aid,dt.isoformat(),kind,amount])
                if dt == cutoff:
                    cutoff_balances = balances.copy()
            for a in accounts:
                aid = a['account_id']
                snapshots.append(dict(period=period, account_id=aid, opening_cents=opening[aid],
                                      closing_cents=balances[aid], cutoff_cents=cutoff_balances[aid]))
            for i in range(25,customers+1,25):
                # Separate externally funded product; no debit to the demo deposit account.
                deposits.append(dict(period=period, customer_id=f'C{i:07}', number=str(mi*customers+i),
                                     deposit_type='01', branch=1, opened=first.isoformat(),
                                     maturity=(first+timedelta(days=365)).isoformat(),
                                     principal_cents=rng.randint(100_000,150_000_000)*100,
                                     interest_cents=rng.randint(1000,100_000)*100,
                                     currency='ARS', foreign_beneficiary=2,
                                     event='A', event_date=first.isoformat(), members=[]))
    write_csv(out/'snapshots.csv', ['period','account_id','opening_cents','closing_cents','cutoff_cents'], snapshots)
    dump(out/'term_deposits.json', deposits)
    dump(out/'manifest.json', dict(synthetic=True, seed=seed, transaction_count=serial,
                                  customers=customers, accounts=customers, periods=periods,
                                  transaction_sha256=digest(tx_path),
                                  disclaimer='Artificial numeric IDs may coincide by chance with real IDs. Never submit.'))
    return dict(transactions=serial, customers=customers, bytes=sum(p.stat().st_size for p in out.iterdir()))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, default=ROOT/'data/portfolio')
    p.add_argument('--transactions', type=int, default=1_000_000)
    p.add_argument('--customers', type=int, default=20_000)
    p.add_argument('--seed', type=int, default=4298)
    a = p.parse_args()
    print(generate(a.out,a.transactions,a.customers,a.seed))


if __name__ == '__main__':
    main()
