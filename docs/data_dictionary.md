# Source contracts

| File | Grain/key | Important fields |
|---|---|---|
| customers.json | One synthetic customer/customer_id | PH/PJ, document type/number, explicit exclusion flag |
| accounts.json | One primary account/account_id | Manual type 01/14, number, CBU, owner, ARS, branch, opening date, optional one monthly lifecycle event |
| members.json | Account + member document | Roles 03–08; members do not repeat the primary holder |
| transactions.csv | One posted transaction/transaction_id | Account, ISO date, kind, positive amount_cents; kind determines direction |
| snapshots.csv | Period + account | Source opening, calendar closing and regulatory cutoff balance, all signed centavos |
| term_deposits.json | One term product/number | Owner, month formed, opening/maturity, principal/interest in centavos, members |
| manifest.json | Dataset | Seed, volume, synthetic flag, transaction digest |

The main generator has one primary account per customer. This is a scope restriction for reproducible account-level thresholds, not a model of a real bank's complete customer graph. Representatives are not co-owners. Arbitrary joint ownership and many accounts per taxpayer require a separate reporting-population policy.

No real names, documents, transaction samples or API extracts are used. Generated numeric identities are checksum-consistent where tested, but not reserved by ARCA or verified to be unassigned. Never submit them as actual customers. The artificial bank uses demonstration identifiers.

Monthly balance reconciliation covers all source account movements. ARCA credits comprise CREDIT, OWN_CREDIT, LOAN_CREDIT and TERM_MATURITY_CREDIT; these last three are non-overlapping subdivisions of total credits. CASH is cash withdrawal only; OTHER_DEBIT is excluded from that measure. CARD_REFUND reduces domestic card consumption and increases the ledger balance. Unsupported accounting corrections/error reversals fail as unknown kinds until their attribution rules are designed.
