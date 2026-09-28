import csv
import tempfile
import unittest
from pathlib import Path
from siter.common import dump, load, tax_id, cbu, pesos, ROOT, valid_tax_id
from siter.pipeline import inputs, local_metrics, select_metrics, records
from siter.export import serialize, encode_record
from siter.validate import validate
from siter.run import execute


def fixture(path):
    people=[]; accounts=[];snapshot=[]
    for i in range(1,11):
        people.append(dict(customer_id=str(i),person_type='PJ' if i==3 else 'PH',document_type='80',
                           document=tax_id((3000000000 if i==3 else 2000000000)+i*10),excluded=i==9))
        accounts.append(dict(account_id=str(i),customer_id=str(i),number=str(i),cbu=cbu(i),
                             account_type='14' if i==5 else '01',currency='ARS',branch=1,additional_cards=0,
                             opened='2026-08-02' if i==8 else '2026-01-01',event='A' if i==8 else '',
                             event_date='2026-08-02' if i==8 else ''))
    tx=[('1','CREDIT',50_000_000),('1','OTHER_DEBIT',49_000_000),
        ('2','CREDIT',49_999_999),('2','OTHER_DEBIT',49_000_000),
        ('3','CREDIT',30_000_000),('3','OTHER_DEBIT',29_000_000),
        ('4','CASH',10_000_000),('6','CARD',50_000_000),('9','CREDIT',100_000_000)]
    opening=[0,0,0,12_000_000,-50_000_000,60_000_000,0,0,0,0]
    closing=[1_000_000,999_999,1_000_000,2_000_000,-50_000_000,10_000_000,0,0,100_000_000,0]
    for i in range(1,11):
        snapshot.append(['202608',str(i),opening[i-1]*100,closing[i-1]*100,closing[i-1]*100])
    dump(path/'customers.json',people);dump(path/'accounts.json',accounts)
    dump(path/'members.json',[dict(account_id='1',document_type='80',document=tax_id(2700000010),role='04')])
    dump(path/'term_deposits.json',[dict(period='202608',customer_id='7',number='1',deposit_type='01',branch=1,
        opened='2026-08-01',maturity='2027-08-01',principal_cents=10_000_000_000,interest_cents=100_000,
        currency='ARS',foreign_beneficiary=2,event='A',event_date='2026-08-01',
        members=[dict(document_type='80',document=tax_id(2700000020),role='04')])])
    dump(path/'manifest.json',{'synthetic':True})
    with (path/'transactions.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['transaction_id','account_id','posted_date','kind','amount_cents'])
        for j,(aid,kind,amount) in enumerate(tx):w.writerow([str(j),aid,'2026-08-15',kind,amount*100])
    with (path/'snapshots.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['period','account_id','opening_cents','closing_cents','cutoff_cents']);w.writerows(snapshot)


class SiterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.data=self.base/'data';self.data.mkdir();fixture(self.data)
        self.cfg,self.people,self.accounts,self.members,self.deposits=inputs(self.data,'202608')

    def tearDown(self):self.temp.cleanup()

    def metrics(self):
        values,_=local_metrics(self.data,'202608',self.accounts,self.cfg)
        return select_metrics(values,self.people,self.accounts,self.deposits,'202608',self.cfg)

    def artifact(self):
        detail=records(self.metrics(),self.people,self.accounts,self.members,self.deposits,'202608')
        return serialize(detail,'202608')

    def test_report_population_boundary_and_exclusion(self):
        metrics={m['account_id']:m for m in self.metrics()}
        self.assertEqual({k for k,m in metrics.items() if m['reportable']},{'1','3','4','5','6','7','8'})
        self.assertEqual(metrics['1']['reasons'],['CREDITS'])
        self.assertEqual(metrics['7']['reasons'],['TERM'])
        self.assertEqual(metrics['8']['reasons'],['ACCOUNT_EVENT'])

    def test_golden_positions_lengths_and_money_units(self):
        name,raw=self.artifact();lines=raw.splitlines()
        self.assertEqual(len(lines[0]),255)
        self.assertEqual(lines[0][13:37],b'202608009999901039110943')
        self.assertEqual(lines[0][37:249],b' '*212)
        self.assertEqual(lines[0][249:],b'005000')
        self.assertEqual(lines[1][80:98],b'000000000050000000')
        self.assertEqual(lines[1][76:78],b'01')
        self.assertEqual(lines[2][:2],b'03')
        parsed=validate(raw,name)
        self.assertEqual(parsed['counts'],{'01':1,'02':7,'03':1,'04':1,'05':1})
        self.assertEqual(parsed['totals_pesos']['credits'],80_000_000)
        self.assertEqual(parsed['totals_pesos']['balance'],-36_000_000)
        self.assertEqual(parsed['totals_pesos']['principal'],100_000_000)

    def test_empty_and_rectification(self):
        name,raw=serialize([],'202608',sequence=2)
        self.assertTrue(name.endswith('.0002.txt'))
        self.assertEqual(raw[19:21],b'02');self.assertEqual(raw[254:255],b'1')
        self.assertEqual(validate(raw,name)['records'],1)

    def test_corrupted_length_and_header_constant(self):
        name,raw=self.artifact()
        for bad in [raw[1:],raw[:26]+b'9999'+raw[30:],raw.replace(b'\r\n',b'\t',1)]:
            with self.subTest(), self.assertRaises(ValueError):validate(bad,name)

    def test_missing_member_rejected(self):
        name,raw=self.artifact()
        broken=b'\r\n'.join(x for x in raw.split(b'\r\n') if not x.startswith(b'03'))
        with self.assertRaisesRegex(ValueError,'member count'):validate(broken,name)

    def test_duplicate_and_orphan_input(self):
        p=self.data/'transactions.csv'
        original=p.read_text()
        p.write_text(original+original.splitlines()[1]+'\n')
        with self.assertRaisesRegex(ValueError,'duplicate transaction'):self.metrics()
        p.write_text(original.replace('0,1,','0,UNKNOWN,',1))
        with self.assertRaisesRegex(ValueError,'unknown transaction'):self.metrics()

    def test_reconciliation_failure_blocks_export(self):
        p=self.data/'snapshots.csv'
        p.write_text(p.read_text().replace('100000000,100000000','100000001,100000000',1))
        with self.assertRaisesRegex(ValueError,'reconciliation'):
            execute(self.data,self.base/'out','202608')
        self.assertFalse((self.base/'out').exists())

    def test_overflow_fractional_and_bad_encoding(self):
        with self.assertRaisesRegex(ValueError,'fractional'):pesos(101)
        detail=records(self.metrics(),self.people,self.accounts,self.members,self.deposits,'202608')[0]
        detail['credits']=10**18
        with self.assertRaisesRegex(ValueError,'overflow'):encode_record(detail)
        detail['credits']=0;detail['currency']='€RS'
        with self.assertRaises(UnicodeEncodeError):encode_record(detail)

    def test_idempotent_bytes(self):
        p,a=execute(self.data,self.base/'out','202608')
        q,b=execute(self.data,self.base/'out','202608')
        self.assertEqual(p,q);self.assertEqual(a['txt_sha256'],b['txt_sha256']);self.assertEqual(a['zip_sha256'],b['zip_sha256'])

    def test_business_cutoff_not_calendar_end(self):
        # May 31 is Sunday. A weekend credit changes monthly credits/closing but not May 29 balance.
        p=self.data/'snapshots.csv'
        with p.open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['period','account_id','opening_cents','closing_cents','cutoff_cents'])
            for i in range(1,11):w.writerow(['202605',str(i),0,5000000000 if i==1 else 0,0])
        with (self.data/'transactions.csv').open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['transaction_id','account_id','posted_date','kind','amount_cents'])
            w.writerow(['X','1','2026-05-31','CREDIT',5000000000])
        values,_=local_metrics(self.data,'202605',self.accounts,self.cfg)
        row=next(r for r in values if r['account_id']=='1')
        self.assertEqual(row['balance_cents'],0);self.assertEqual(row['credits_cents'],5000000000)

    def test_unsupported_currency_fails(self):
        a=load(self.data/'accounts.json');a[0]['currency']='USD';dump(self.data/'accounts.json',a)
        with self.assertRaisesRegex(ValueError,'unsupported currency'):inputs(self.data,'202608')

    def test_source_manifest_integrity(self):
        dump(self.data/'manifest.json',{'synthetic':True,'transaction_sha256':'0'*64})
        with self.assertRaisesRegex(ValueError,'source integrity'):inputs(self.data,'202608')


if __name__=='__main__':unittest.main()
