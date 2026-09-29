# Execution console v1

I extended the reporting console with an authenticated backend so an analyst can validate an anonymized dataset, generate a report and inspect their own results. The saved sample console remains available as an offline reference.

## Run locally

Python 3.10+ on Linux or macOS; no third-party dependency is needed for CSV processing. From the repository root:

```bash
python3 -m siter.server add-user analyst
python3 -m siter.server serve
```

The first command prompts for a password of at least 12 characters. Open **http://127.0.0.1:8000** and sign in. Use this exact hostname: requests to other hosts are rejected. Passwords are never command-line arguments. Rerunning `add-user` resets that user's password and revokes existing sessions without deleting their runs. There is no public registration or shared default password.

By default, private state is stored in the git-ignored `runtime/` folder. To use another location, put the global option before the command:

```bash
python3 -m siter.server --state /private/siter-state add-user analyst
python3 -m siter.server --state /private/siter-state serve
```

Do not place state inside `web/` or commit it to Git. Use a dedicated OS account and a private state directory. Only one server process can own a state directory; an OS lock prevents concurrent servers.

## Analyst workflow

1. Sign in and download the blank CSV templates or complete sample ZIP. Unzip it locally; the form accepts individual CSV files, not ZIP uploads. **Use sample** fills the form with the same synthetic data without a download.
2. Select a reviewed period and rules version, anonymized reporter CUIT, entity code and presentation. An original uses sequence 0; a full replacement uses 1–99. No-activity is determined by the selected population, not a user override.
3. Upload the four required CSVs and any applicable supplementary CSVs. Attest that names and identifiers have been replaced. The service does not anonymize inputs or prove that this declaration is true.
4. Select **Validate batch**. Schema errors identify filename, CSV row and column. Duplicate keys and orphan references are checked before the existing business rules, balance reconciliation and TXT parser. Up to 100 errors are returned; business-rule errors can be batch-level.
5. A valid batch becomes **Ready**. Select **Generate report** to run the Python pipeline. Only a successful execution exposes artifacts.
6. Open **Review results** for the existing summary, account decisions, controls and TXT inspector, now bound to this execution. Download TXT, ZIP, audit or account decisions.
7. Delete the run when finished. Other users cannot list, execute, read or delete it.

A failed upload is immutable: fix the files and submit a new batch. Browser polling can stop without cancelling a server-side job. Repeated execution of a running or completed batch is rejected.

## Data contract and limits

See [CSV contract](csv_contract.md). The authenticated `/api/config` response publishes the same contract used by validation; `/api/templates.zip` includes headers and `contract.json`.

- Four required files: `transactions.csv`, `customers.csv`, `accounts.csv`, `snapshots.csv`.
- Optional files: `members.csv`, `term_deposits.csv`, `deposit_members.csv`. Omit them or upload headers only when there are no records.
- UTF-8 (optional BOM), comma delimiter, exact column names, no unexpected columns. CSV column order can vary.
- Maximum 100,000 rows per file; 20 MiB of CSV selected in the browser and 24 MiB per encoded HTTP request. No million-row upload through this v1.
- Maximum ten retained runs per user, one active run per user, four queued/active jobs globally and one execution worker.
- Rules currently cover March–August 2026, ARS and one primary account per customer. Expanding dates or products requires a reviewed rule/calendar change; the UI does not edit regulatory thresholds.
- Names and identifiers must be substitutes. CUIT/CBU substitutes must retain valid checksums; arbitrary redaction such as `XXXX` is rejected. Keep referential relationships consistent across files.
- `synthetic_name` is the display alias, including for anonymized datasets. The manifest records the anonymization attestation and transaction content hash.

## Authorized BigQuery transaction sources (optional)

This v1 can **read an administrator-approved transaction table and process it locally**. It does not run the SQL reporting model from the UI, mutate a cloud dataset or claim cloud/local parity for new imports. The existing BigQuery SQL pipeline remains available via CLI.

Install `requirements-bigquery.txt` and configure server-side Application Default Credentials. Give that principal read access only to the necessary tables. Never upload credentials through the UI.

Create a private `runtime/sources.json` file:

```json
{
  "sample_transactions": {
    "label": "Anonymized transaction sample",
    "project": "YOUR_PROJECT",
    "table": "YOUR_PROJECT.YOUR_DATASET.YOUR_TABLE",
    "users": ["analyst"]
  }
}
```

Then run:

```bash
python3 -m siter.server serve --sources runtime/sources.json
```

Only listed users see that source. The client submits its profile key, never arbitrary SQL or table identifiers. The server checks a physical table, expected transaction column types and a maximum 100,000 rows, then reads only the five required columns. Upload the remaining customer/account/snapshot CSVs alongside it. Import failures block validation and never return credentials or provider exception details.

There are no automatic BigQuery calls when opening the console. A selected import occurs only after submitting a batch. Use an immutable source table during import; this prototype does not lock external writers or implement a warehouse-wide snapshot. Cloud permissions and any transfer/storage costs remain governed by the Google Cloud account. The [BigQuery client methods](https://docs.cloud.google.com/python/docs/reference/bigquery/latest/google.cloud.bigquery.client.Client) define the table read API used here. The new import integration is covered by mocked tests; it has not been executed against a live cloud table as part of this release.

## Architecture and protection

The browser sends same-origin JSON to a Python HTTP service. SQLite stores users, hashed sessions and execution metadata; each user's generated UUID directory contains separate run inputs and outputs. A single bounded worker validates and executes jobs. Each execution supplies its own reporter and sequence to the exporter without modifying shared configuration.

Passwords use PBKDF2-HMAC-SHA256 with 600,000 iterations and a random salt. Session tokens are random, stored as SHA-256 hashes, expire after 12 hours and are sent in HttpOnly, SameSite=Strict cookies. Writes require an exact Origin and a session CSRF token; Host is restricted. Login is throttled by network address. Responses disable caching, MIME sniffing and framing. Static serving uses an explicit asset allowlist; artifact downloads require successful status and ownership. No request bodies, source data or credentials are logged.

Inputs, outputs and execution metadata expire 24 hours after upload. Expired runs become inaccessible immediately; cleanup removes inactive run directories at startup and approximately once a minute while the server is running. Active jobs finish before deletion. If the server is stopped, physical cleanup resumes at the next startup. Manual deletion is immediate for inactive runs. Session/user records are separate from report retention. Deletion is ordinary filesystem/SQLite deletion, not certified secure erasure; host snapshots/backups need their own retention policy.

On restart, interrupted validation or execution is marked failed; jobs are not silently resumed. Adding a user while the server runs does not reset active jobs.

The server binds to loopback by default. A non-loopback binding requires an explicit HTTPS origin and a TLS reverse proxy that preserves the expected Host. The cookie becomes Secure for HTTPS. This is a single-process demonstration service, not a hardened public banking platform: no SSO/MFA, encryption-at-rest management, antivirus scanning, distributed queue, production observability or regulatory sign-off is claimed. Do not expose the Python server directly to the internet or use real banking data. The previous static hosting deployment cannot run this backend; public hosting is a separate next step.

## Verification

```bash
python3 -m unittest discover -s tests -v
node --check web/workspace.js
node --check web/app.js
```

`tests/test_console.py` covers CSV contracts, duplicates, orphan references, bad dates and amounts, row limits, configuration, HTTP upload/validation/execution/download/deletion, sample TXT parity, balance failures, user isolation, authentication, CSRF/Origin/Host checks, request limits, expiry and scoped report identity. BigQuery source authorization is tested without cloud calls.

The release was also exercised in Chromium: sign-in, loading the example, validation, generation, all report views and run deletion. The workspace was checked at desktop and mobile widths. The saved static demo remains unchanged in scope.
