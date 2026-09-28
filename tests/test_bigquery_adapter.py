import csv
import hashlib
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from siter.common import ROOT, dump, load, digest
from siter.source_identity import row_hash, csv_identity, combine_sorted_hashes, table_id
from siter.bigquery import load_data, verify_source, check_schema
from siter.cloud_demo import compare_runs
from siter.run import execute


class SourceIdentityTests(unittest.TestCase):
    def test_typed_rows_match_csv_and_preserve_field_boundaries(self):
        row=dict(transaction_id='ab',account_id='c',posted_date='2026-08-01',kind='CREDIT',amount_cents='100')
        # Independently specified byte representation (lengths are UTF-8 bytes).
        expected=hashlib.sha256(b'2:ab1:c10:2026-08-016:CREDIT3:100').hexdigest()
        self.assertEqual(row_hash(row),expected)
        self.assertEqual(row_hash(dict(row,posted_date=date(2026,8,1),amount_cents=100)),expected)
        self.assertNotEqual(row_hash(dict(row,transaction_id='a',account_id='bc')),expected)
        with self.assertRaises(ValueError):row_hash(dict(row,amount_cents=None))
        with self.assertRaises(ValueError):row_hash(dict(row,amount_cents='100.5'))

    def test_reordering_is_equal_but_duplicate_and_changed_amount_are_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'transactions.csv'
            source=ROOT/'data/sample/transactions.csv'
            with source.open(newline='') as f: rows=list(csv.reader(f))
            def write(values):
                with p.open('w',newline='') as f:csv.writer(f).writerows([rows[0]]+values)
            write(list(reversed(rows[1:])))
            expected=csv_identity(source)
            self.assertEqual(csv_identity(p),expected)
            write(rows[1:]+[rows[1]])
            self.assertNotEqual(csv_identity(p),expected)
            altered=[r.copy() for r in rows[1:]];altered[0][-1]=str(int(altered[0][-1])+1)
            write(altered)
            self.assertNotEqual(csv_identity(p),expected)
        with self.assertRaises(ValueError):combine_sorted_hashes([None])

    def test_schema_and_identifier_guard(self):
        fields=[SimpleNamespace(name=k,field_type=t,mode='NULLABLE') for k,t in
                [('transaction_id','STRING'),('account_id','STRING'),('posted_date','DATE'),('kind','STRING'),('amount_cents','INTEGER')]]
        check_schema(SimpleNamespace(schema=fields))
        fields[-1].field_type='FLOAT'
        with self.assertRaisesRegex(ValueError,'unsupported source'):check_schema(SimpleNamespace(schema=fields))
        with self.assertRaises(ValueError):table_id('project.dataset.table`; DROP TABLE x; --')


class IngestionGateTests(unittest.TestCase):
    def setUp(self):
        self.data=ROOT/'data/sample'
        self.expected=csv_identity(self.data/'transactions.csv')
        self.bq,self.client=MagicMock(),MagicMock()
        self.client.get_dataset.return_value.location='US'
        self.client.create_dataset.return_value.location='US'
        self.source='regulatory-reporting-510011.Transactions.Sample'
        self.job={'identity_job_id':'mock-only','identity_bytes_processed':0}

    def call_load(self):
        return load_data(self.data,'regulatory-reporting-510011','siter_portfolio','US',self.source)

    def test_wrong_batch_stops_before_auxiliary_writes(self):
        with patch('siter.bigquery.client_for',return_value=(self.bq,self.client)), \
             patch('siter.bigquery.check_schema'), \
             patch('siter.bigquery.cloud_identity',return_value=({'row_count':1200,'content_sha256':'wrong'},self.job)):
            with self.assertRaisesRegex(ValueError,'content mismatch'):self.call_load()
        self.client.load_table_from_json.assert_not_called()
        self.client.load_table_from_file.assert_not_called()
        self.assertEqual(self.client.copy_table.call_count,1)
        # Only our unique temporary copy is removed; no source or prior manifest.
        self.assertEqual(self.client.delete_table.call_count,1)
        self.assertIn('._siter_import_',self.client.delete_table.call_args.args[0])

    def test_success_uses_existing_table_and_commits_manifest_last(self):
        with patch('siter.bigquery.client_for',return_value=(self.bq,self.client)), \
             patch('siter.bigquery.check_schema'), \
             patch('siter.bigquery.cloud_identity',return_value=(self.expected,self.job)):
            result=self.call_load()
        self.assertEqual(result['row_count'],1200)
        self.assertEqual(self.client.copy_table.call_count,2)
        self.assertEqual(self.client.copy_table.call_args_list[0].args[0],self.source)
        self.assertTrue(self.client.copy_table.call_args_list[1].args[1].endswith('.raw_transactions'))
        self.assertEqual(self.client.load_table_from_file.call_count,1)  # snapshots only
        self.assertTrue(self.client.load_table_from_json.call_args.args[1].endswith('.source_manifest'))
        self.assertTrue(all(c.args[0]!=self.source for c in self.client.delete_table.call_args_list))

    def test_failed_auxiliary_load_leaves_no_success_manifest(self):
        self.client.load_table_from_json.side_effect=RuntimeError('load failed')
        with patch('siter.bigquery.client_for',return_value=(self.bq,self.client)), \
             patch('siter.bigquery.check_schema'), \
             patch('siter.bigquery.cloud_identity',return_value=(self.expected,self.job)):
            with self.assertRaisesRegex(RuntimeError,'load failed'):self.call_load()
        self.assertTrue(self.client.delete_table.call_args_list[0].args[0].endswith('.source_manifest'))
        self.assertFalse(any(c.args[1].endswith('.source_manifest') for c in self.client.load_table_from_json.call_args_list))

    def test_changed_cloud_transactions_block_export(self):
        manifest=[{'filename':p.name,'sha256':digest(p)} for p in self.data.iterdir() if p.is_file()]
        self.client.query.return_value.result.side_effect=[manifest,[dict(source_table=self.source,**self.expected)]]
        with patch('siter.bigquery.client_for',return_value=(self.bq,self.client)), \
             patch('siter.bigquery.cloud_identity',return_value=({'row_count':1200,'content_sha256':'drift'},self.job)):
            with self.assertRaisesRegex(ValueError,'changed since load'):
                verify_source(self.data,'regulatory-reporting-510011','siter_portfolio','US')

    def test_source_dataset_and_region_are_protected(self):
        with self.assertRaisesRegex(ValueError,'separate working dataset'):
            load_data(self.data,'regulatory-reporting-510011','Transactions','US',self.source)
        self.client.get_dataset.return_value.location='EU'
        with patch('siter.bigquery.client_for',return_value=(self.bq,self.client)),patch('siter.bigquery.check_schema'):
            with self.assertRaisesRegex(ValueError,'location mismatch'):self.call_load()
        self.client.create_dataset.assert_not_called()


class ParityGateTests(unittest.TestCase):
    def test_unreported_account_difference_fails_even_when_txt_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,_=execute(ROOT/'data/sample',Path(tmp)/'local','202608')
            b,_=execute(ROOT/'data/sample',Path(tmp)/'other','202608')
            compare_runs(a,b)
            rows=load(b/'account_decisions.json')
            rows[0]['credits_cents']+=100
            dump(b/'account_decisions.json',rows)
            with self.assertRaisesRegex(ValueError,'account decisions mismatch'):compare_runs(a,b)


if __name__=='__main__':unittest.main()
