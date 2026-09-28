# BigQuery execution guide

I ran the August 2026 sample report in BigQuery on 2026-09-28. See `examples/cloud_sample_202608.json` for the result and provenance. Source content, TXT and ZIP hashes match the stored local sample reference. This evidence covers the sample and one period, not the million-row dataset or all regulatory scenarios.

## Existing source table

For `regulatory-reporting-510011.Transactions.Sample` (US), start with [the Spanish integration guide](your_bigquery_setup_es.md) and `python3 -m siter.cloud_demo`. The source contains 1,200 rows with STRING/DATE/INT64 columns; the recorded execution confirms the content identity check. The loader supports `--source-table project.dataset.table` with a separate working dataset.

## Setup

1. Select a Google Cloud project with billing/API configuration appropriate for BigQuery. Use a dedicated `siter_portfolio` dataset.
2. Install the optional dependency: `python3 -m pip install -r requirements-bigquery.txt`.
3. Configure Application Default Credentials outside the repo, for example with `gcloud auth application-default login`. Never commit credential files.
4. The principal needs permission to create query/load jobs and to create/update tables in the selected dataset. A dataset admin can precreate the dataset to avoid broader dataset-creation permissions. All datasets/jobs must use the same location.

## Load and run

```bash
python3 -m siter.bigquery --data data/sample --project YOUR_PROJECT --dataset siter_portfolio --location US
python3 -m siter.run --data data/sample --period 202608 --out output --engine bigquery --project YOUR_PROJECT --dataset siter_portfolio --location US
```

The load command replaces the named portfolio tables in the working dataset. An existing source supplied with `--source-table` is copied into a temporary table, compared with the CSV using canonical content hashes, then imported as `raw_transactions`; the source is not modified. A failed content match stops before replacing auxiliary tables. An old success manifest is invalidated before any auxiliary load, and a new manifest is written only after all loads and content checks succeed. A successful load writes a source SHA-256 manifest and source binding. The export checks that the local source files used for identity/member mapping match that loaded manifest. SQL filters the requested month, uses the configured last business day for the regulatory balance, and checks source-snapshot reconciliation before replacing the period mart.

The main script has a 20 GB `maximum_bytes_billed` guard. This is a processing limit, not a dollar budget and not a cap on all account activity. Load, storage and queries follow your Google Cloud billing configuration. BigQuery source validation scans the batch; the metric aggregation uses the partitioned staging table. Rebuilding staging for every run is a deliberate prototype limitation; production would use immutable batches plus incremental loads.

## Acceptance checks

1. Run the same sample through `--engine local` and `--engine bigquery`.
2. Compare `txt_sha256` values and `account_decisions.json` after sorting by account_id. They must match.
3. Inspect the query job ID, bytes processed, slot milliseconds and source reconciliation in the cloud `audit.json`.
4. Introduce a duplicate transaction in a copy of the sample; reload it and confirm the SQL assertion fails and no new TXT is produced.
5. Load `data/portfolio`, repeat all six periods, and retain actual query metrics.

Sample job metrics are retained in the recorded execution summary. Large-scale cloud performance and actual billed cost remain unmeasured. I populated the sample working dataset with the included loader.

## Content identity and operating limits

`source_identity.py` normalizes DATE and integer cents, frames every field using its UTF-8 byte length, hashes each row with SHA-256, sorts the row hashes, and hashes their concatenated binary values. Duplicate rows remain significant. BigQuery computes and sorts the row hashes; Python streams that result. CSV identity keeps sorted hashes in memory (O(N) hashes, not full rows). This verifies the typed transaction population independently of CSV byte encoding and row ordering.

The export rechecks the imported transaction content, and retains its source binding and verification job in `audit.json`. The cloud demo compares TXT/ZIP hashes and all account decisions against the local reference. This is an integrity/parity check, not a regulator acceptance test.

Use one loader/export at a time per working dataset. The prototype does not provide transactional publication across all tables or protect against concurrent manual edits between verification and modeling. Auxiliary table values are reconciled and checked through the manifest and model, but are not individually rehashed from BigQuery. Production would require immutable batches and a batch-specific publication pointer. Temporary import tables are removed in a finally block; an abruptly terminated process may require their cleanup. Legacy loads need to be rerun once to create the new source binding.

Official API/function references: [Python BigQuery client](https://docs.cloud.google.com/python/docs/reference/bigquery/latest/google.cloud.bigquery.client.Client), [hash functions](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/hash_functions), [string functions](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/string_functions).
