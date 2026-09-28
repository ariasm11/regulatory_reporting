-- BigQuery Standard SQL. Identifiers substituted only after regex validation.
-- All assertions run before the final mart is replaced. No TXT is written by SQL.
CREATE TEMP TABLE tx AS
SELECT transaction_id,account_id,SAFE_CAST(posted_date AS DATE) AS posted_date,
 kind,SAFE_CAST(amount_cents AS INT64) AS amount_cents
FROM `__PROJECT__.__DATASET__.raw_transactions`;
ASSERT (SELECT COUNT(*)=COUNT(DISTINCT transaction_id) FROM tx) AS 'duplicate transaction';
ASSERT (SELECT COUNT(*)=0 FROM tx t LEFT JOIN `__PROJECT__.__DATASET__.accounts` a USING(account_id)
 WHERE t.transaction_id IS NULL OR t.transaction_id='' OR a.account_id IS NULL
 OR t.posted_date IS NULL OR t.amount_cents IS NULL OR t.amount_cents<=0 OR t.kind IS NULL
 OR t.kind NOT IN ('CREDIT','OWN_CREDIT','LOAN_CREDIT','TERM_MATURITY_CREDIT','CASH','CARD','CARD_REFUND','OTHER_DEBIT')
 OR t.posted_date<DATE(a.opened) OR (a.event='C' AND t.posted_date>SAFE_CAST(a.event_date AS DATE))) AS 'invalid transaction';

CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.stg_transactions`
PARTITION BY posted_date CLUSTER BY account_id AS SELECT * FROM tx;

CREATE TEMP TABLE snapshots AS
SELECT period,account_id,SAFE_CAST(opening_cents AS INT64) AS opening_cents,
 SAFE_CAST(closing_cents AS INT64) AS closing_cents,SAFE_CAST(cutoff_cents AS INT64) AS cutoff_cents
FROM `__PROJECT__.__DATASET__.raw_snapshots` WHERE period=@period;
ASSERT (SELECT COUNT(*)=COUNT(DISTINCT account_id) FROM snapshots) AS 'duplicate snapshot';
ASSERT (SELECT COUNT(*)=0 FROM snapshots WHERE opening_cents IS NULL OR closing_cents IS NULL OR cutoff_cents IS NULL) AS 'invalid snapshot amount';
ASSERT (SELECT COUNT(*)=0 FROM `__PROJECT__.__DATASET__.accounts` a
 FULL OUTER JOIN snapshots s USING(account_id) WHERE a.account_id IS NULL OR s.account_id IS NULL) AS 'snapshot coverage';

CREATE TEMP TABLE movements AS
SELECT account_id,
 SUM(IF(kind IN ('CASH','CARD','OTHER_DEBIT'),-amount_cents,amount_cents)) AS delta_cents,
 SUM(IF(posted_date<=@cutoff,IF(kind IN ('CASH','CARD','OTHER_DEBIT'),-amount_cents,amount_cents),0)) AS cutoff_delta_cents,
 SUM(IF(kind IN ('CREDIT','OWN_CREDIT','LOAN_CREDIT','TERM_MATURITY_CREDIT'),amount_cents,0)) AS credits_cents,
 SUM(IF(kind='OWN_CREDIT',amount_cents,0)) AS own_credits_cents,
 SUM(IF(kind='LOAN_CREDIT',amount_cents,0)) AS loan_credits_cents,
 SUM(IF(kind='TERM_MATURITY_CREDIT',amount_cents,0)) AS term_credits_cents,
 SUM(IF(kind='CASH',amount_cents,0)) AS cash_cents,
 SUM(CASE kind WHEN 'CARD' THEN amount_cents WHEN 'CARD_REFUND' THEN -amount_cents ELSE 0 END) AS card_cents
FROM `__PROJECT__.__DATASET__.stg_transactions`
WHERE posted_date BETWEEN @period_start AND @period_end GROUP BY account_id;

ASSERT (SELECT COUNT(*)=0 FROM snapshots s LEFT JOIN movements m USING(account_id)
 WHERE opening_cents+COALESCE(delta_cents,0) != closing_cents
 OR opening_cents+COALESCE(cutoff_delta_cents,0) != cutoff_cents) AS 'source balance reconciliation failed';
ASSERT (SELECT COUNT(*)=0 FROM snapshots JOIN `__PROJECT__.__DATASET__.accounts` USING(account_id)
 WHERE account_type!='14' AND cutoff_cents<0) AS 'negative savings balance';

CREATE TEMP TABLE metric AS
SELECT a.account_id,a.customer_id,p.person_type,p.excluded,a.event,a.event_date,
 s.cutoff_cents AS balance_cents,COALESCE(m.credits_cents,0) AS credits_cents,
 COALESCE(m.own_credits_cents,0) AS own_credits_cents,COALESCE(m.loan_credits_cents,0) AS loan_credits_cents,
 COALESCE(m.term_credits_cents,0) AS term_credits_cents,COALESCE(m.cash_cents,0) AS cash_cents,
 COALESCE(m.card_cents,0) AS card_cents,COALESCE(d.formed_cents,0) AS formed_cents
FROM `__PROJECT__.__DATASET__.accounts` a JOIN `__PROJECT__.__DATASET__.customers` p USING(customer_id)
JOIN snapshots s USING(account_id) LEFT JOIN movements m USING(account_id)
LEFT JOIN (SELECT customer_id,SUM(principal_cents) AS formed_cents
 FROM `__PROJECT__.__DATASET__.term_deposits` WHERE period=@period GROUP BY customer_id) d USING(customer_id);

CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.report___PERIOD__` AS
WITH flags AS (
 SELECT *,credits_cents>=IF(person_type='PH',@credit_ph,@credit_pj) AS hit_credit,
 ABS(balance_cents)>=IF(person_type='PH',@credit_ph,@credit_pj) AS hit_balance,
 cash_cents>=@cash AS hit_cash,card_cents>=@card AS hit_card,
 formed_cents>=IF(person_type='PH',@term_ph,@term_pj) AS hit_term,
 event!='' AND REPLACE(SUBSTR(event_date,1,7),'-','')=@period AS hit_event FROM metric
), reasoned AS (
 SELECT *,hit_credit OR hit_balance OR hit_cash OR hit_card OR hit_term AS financial_trigger,
 ARRAY(SELECT value FROM UNNEST([
 IF(hit_credit,'CREDITS',NULL),IF(hit_balance,'BALANCE',NULL),IF(hit_cash,'CASH',NULL),
 IF(hit_card,'CARD',NULL),IF(hit_term,'TERM',NULL),IF(hit_event,'ACCOUNT_EVENT',NULL)
 ]) value WHERE value IS NOT NULL) AS reasons FROM flags
)
SELECT account_id,balance_cents,credits_cents,own_credits_cents,loan_credits_cents,term_credits_cents,
 cash_cents,card_cents,financial_trigger,(financial_trigger OR hit_event) AND NOT excluded AS reportable,reasons
FROM reasoned;
