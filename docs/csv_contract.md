# CSV input contract v1

The console publishes these exact columns in `/api/config` and the downloadable templates. All money is integer centavos; identifiers remain strings. Mandatory files may have no data rows only where the model can reconcile a no-activity population.

## transactions.csv

Required.

| Column | Type |
| --- | --- |
| `transaction_id` | `id` |
| `account_id` | `id` |
| `posted_date` | `date` |
| `kind` | `str` |
| `amount_cents` | `positive` |

## customers.csv

Required.

| Column | Type |
| --- | --- |
| `customer_id` | `id` |
| `person_type` | `str` |
| `document_type` | `str` |
| `document` | `tax_id` |
| `synthetic_name` | `str` |
| `excluded` | `bool` |

## accounts.csv

Required.

| Column | Type |
| --- | --- |
| `account_id` | `id` |
| `customer_id` | `id` |
| `number` | `digits` |
| `cbu` | `cbu` |
| `account_type` | `str` |
| `currency` | `str` |
| `branch` | `nonnegative` |
| `additional_cards` | `nonnegative` |
| `opened` | `date` |
| `event` | `optional` |
| `event_date` | `optional_date` |

## snapshots.csv

Required.

| Column | Type |
| --- | --- |
| `period` | `period` |
| `account_id` | `id` |
| `opening_cents` | `int` |
| `closing_cents` | `int` |
| `cutoff_cents` | `int` |

## members.csv

Optional when there are no corresponding records.

| Column | Type |
| --- | --- |
| `account_id` | `id` |
| `document_type` | `str` |
| `document` | `tax_id` |
| `role` | `str` |

## term_deposits.csv

Optional when there are no corresponding records.

| Column | Type |
| --- | --- |
| `period` | `period` |
| `customer_id` | `id` |
| `number` | `digits` |
| `deposit_type` | `str` |
| `branch` | `nonnegative` |
| `opened` | `date` |
| `maturity` | `date` |
| `principal_cents` | `positive` |
| `interest_cents` | `nonnegative` |
| `currency` | `str` |
| `foreign_beneficiary` | `nonnegative` |
| `event` | `str` |
| `event_date` | `date` |

## deposit_members.csv

Optional when there are no corresponding records.

| Column | Type |
| --- | --- |
| `deposit_number` | `digits` |
| `document_type` | `str` |
| `document` | `tax_id` |
| `role` | `str` |

## Type rules and relationships

- `id`: 1–64 ASCII letters, digits, underscores or hyphens. Stable substitutes shared across related files.
- `int`: signed base-10 integer, at most 18 digits. `positive` is greater than zero; `nonnegative` is zero or greater. No decimal or thousands separators.
- `digits`: 1–22 numeric characters, preserved as text. `tax_id` and `cbu` require valid CUIT/CBU checksums.
- `date`: `YYYY-MM-DD`; `period`: `YYYYMM`. Dates must exist. `optional_date` can be blank.
- `bool`: exactly `true` or `false`. `str` is nonempty text. `optional` can be blank. Maximum 200 characters per cell; control characters are rejected.
- `customers.person_type`: `PH` or `PJ`; `document_type`: `80`; `excluded` must explicitly state the applicable exclusion flag. `synthetic_name` is a fictitious display alias.
- `accounts.currency`: `ARS`; `account_type`: `01` or `14`; `event`: blank, `A`, `B`, `C` or `N`. Nonblank events require a date. One primary account per customer; unique account number and CBU.
- Transaction `kind`: `CREDIT`, `OWN_CREDIT`, `LOAN_CREDIT`, `TERM_MATURITY_CREDIT`, `CASH`, `CARD`, `CARD_REFUND`, `OTHER_DEBIT`. Amounts are positive; kind determines direction.
- Snapshots are unique by period/account and must include every account for the selected period. `opening_cents` is the opening balance, `closing_cents` the calendar-month close, `cutoff_cents` the last-business-day balance in the reviewed calendar. Both reconciliations must pass.
- Members reference an existing account. Role codes `03`–`08` represent the supported representative relationships, not financial co-ownership. Documents must differ from the holder and be unique within each parent.
- Term deposits reference a customer with a supported primary account. Only newly constituted deposits (`deposit_type=01`, `event=A`, `foreign_beneficiary=2`, `currency=ARS`) are supported. Opening and event dates coincide; maturity is no earlier than opening. Period matches opening month. `principal_cents` is positive; interest is nonnegative.
- Deposit members reference `term_deposits.number` through `deposit_number`. They use the same representative document and role rules as account members.

The four required files are not interchangeable: transactions alone cannot establish account ownership or reconcile balances. The preflight reuses the pipeline's business rules and independent TXT parser; passing a CSV type check alone does not authorize export. The complete supported scenario and regulatory limitations remain documented in the main README and specification.
