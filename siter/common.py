import calendar
import hashlib
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KINDS = {'CREDIT': 1, 'OWN_CREDIT': 1, 'LOAN_CREDIT': 1,
         'TERM_MATURITY_CREDIT': 1, 'CASH': -1, 'CARD': -1,
         'CARD_REFUND': 1, 'OTHER_DEBIT': -1}
CREDITS = {'CREDIT', 'OWN_CREDIT', 'LOAN_CREDIT', 'TERM_MATURITY_CREDIT'}


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def tax_id(body):
    """Generate checksum-consistent artificial values, NOT identities validated by ARCA."""
    while True:
        text = str(body).zfill(10)
        n = 11 - sum(int(a) * b for a, b in zip(text, [5,4,3,2,7,6,5,4,3,2])) % 11
        if n != 10:
            return text + str(0 if n == 11 else n)
        body += 1


def valid_tax_id(value):
    if len(value) != 11 or not value.isascii() or not value.isdigit():
        return False
    n = 11 - sum(int(a) * b for a, b in zip(value[:10], [5,4,3,2,7,6,5,4,3,2])) % 11
    return n != 10 and int(value[-1]) == (0 if n == 11 else n)


def cbu(account):
    def dv(s, weights):
        return str((10 - sum(int(x)*w for x,w in zip(s,weights)) % 10) % 10)
    bank = '9990001'
    number = str(account).zfill(13)
    return bank + dv(bank,[7,1,3,9,7,1,3]) + number + dv(number,[3,9,7,1,3,9,7,1,3,9,7,1,3])


def month_end(period):
    if len(period) != 6 or not period.isdigit():
        raise ValueError('period must be YYYYMM')
    y, m = int(period[:4]), int(period[4:])
    return date(y,m,calendar.monthrange(y,m)[1])


def pesos(cents):
    # Manual specifies integer amounts but does not define a universal rounding rule.
    # Reject fractions rather than silently inventing a regulatory rounding policy.
    if not isinstance(cents, int) or cents % 100:
        raise ValueError('fractional peso: explicit approved rounding policy required')
    return cents // 100
