-- GoogleSQL. Execute in project regulatory-reporting-510011, location US.
-- Read-only discovery; no dependency on inferred CSV column names or types.
SELECT
  'regulatory-reporting-510011.Transactions.Sample' AS source_table,
  (SELECT COUNT(*) FROM `regulatory-reporting-510011.Transactions.Sample`) AS row_count,
  ARRAY(
    SELECT AS STRUCT ordinal_position, column_name, data_type, is_nullable
    FROM `regulatory-reporting-510011.Transactions.INFORMATION_SCHEMA.COLUMNS`
    WHERE table_name = 'Sample'
    ORDER BY ordinal_position
  ) AS columns,
  ARRAY(
    SELECT TO_JSON_STRING(t)
    FROM `regulatory-reporting-510011.Transactions.Sample` AS t
    LIMIT 3
  ) AS sample_rows;
