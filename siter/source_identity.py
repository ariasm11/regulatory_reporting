"""Order-independent content identity for CSV and typed BigQuery transactions.

This is distinct from the byte-level CSV hash: DATE/INT64 inference and row
ordering must not change the identity of the transaction population.
"""
import csv
import hashlib
import re
from datetime import date
from pathlib import Path
from .pipeline import require

FIELDS = ('transaction_id', 'account_id', 'posted_date', 'kind', 'amount_cents')


def table_id(value):
    require(bool(re.fullmatch(
        r'[a-z][a-z0-9-]{4,62}\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*', value)),
        'invalid fully qualified BigQuery table ID')
    return value


def row_hash(row):
    values = []
    for key in FIELDS:
        value = row[key]
        require(value is not None, 'null transaction identity field')
        if key == 'posted_date':
            value = date.fromisoformat(str(value)).isoformat()
        elif key == 'amount_cents':
            require(bool(re.fullmatch(r'[+-]?\d+', str(value))), 'noninteger transaction amount')
            value = str(int(value))
        else:
            value = str(value)
        raw = value.encode('utf-8')
        values.append(str(len(raw)).encode('ascii') + b':' + raw)
    return hashlib.sha256(b''.join(values)).hexdigest()


def combine_sorted_hashes(hashes):
    result = hashlib.sha256()
    count = 0
    for value in hashes:
        require(value is not None and bool(re.fullmatch(r'[0-9a-f]{64}', value)),
                'invalid or null transaction row hash')
        result.update(bytes.fromhex(value))
        count += 1
    return {'row_count': count, 'content_sha256': result.hexdigest()}


def csv_identity(path):
    with Path(path).open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        require(reader.fieldnames == list(FIELDS), 'unexpected transaction CSV columns')
        # Retain hashes, not the full rows; cloud ordering happens in BigQuery.
        return combine_sorted_hashes(sorted(row_hash(row) for row in reader))


def identity_sql(source):
    table_id(source)
    expressions = []
    for key in FIELDS:
        value = (f'CAST(SAFE_CAST({key} AS DATE) AS STRING)' if key == 'posted_date'
                 else f'CAST(SAFE_CAST({key} AS INT64) AS STRING)' if key == 'amount_cents'
                 else f'CAST({key} AS STRING)')
        expressions.extend([f'CAST(BYTE_LENGTH({value}) AS STRING)', "':'", value])
    # CONCAT propagates NULL; combine_sorted_hashes rejects it. Length prefixes
    # avoid collisions caused by concatenating ambiguous field boundaries.
    return ('SELECT TO_HEX(SHA256(CONCAT(' + ', '.join(expressions) +
            f'))) AS row_hash FROM `{source}` ORDER BY row_hash')
