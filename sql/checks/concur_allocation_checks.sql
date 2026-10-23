-- Concur allocation data-quality checks on dbo.concur.  Safe to re-run.
-- Reads dbo.concur only (SELECT); the only things it writes are the temp tables #entry, #parent and #pg
-- in tempdb, which are dropped when your session closes. T-SQL (SQL Server 2019): TRY_CONVERT,
-- SELECT INTO #temp and DROP TABLE IF EXISTS are T-SQL specific; Postgres would use CASE with a regex
-- test instead.
--
-- What the data looks like (verified 2026-10-23):
--   * dbo.concur has one row per expense entry x allocation (cost object). An entry with a single
--     allocation has one row; an entry split across cost objects has several rows sharing entry_key.
--   * expense_amount__reimbursement_currency_ is the FULL ENTRY amount, repeated on every allocation
--     row of the entry. Never sum it per row.
--   * expense_amount (stored as text) is the ALLOCATED amount = entry amount x percentage / 100.
--     This is the amount the predictions table uses, so summing it per row is correct IF each entry's
--     allocated amounts add up to the entry amount exactly once.
--   * transaction_type is Regular, Parent or Child. A Parent is an itemized expense: its allocation row
--     is always blank, and its Child entries (usually an allowable part and an alcohol/unallowable part)
--     carry the amounts and add up to the Parent. So Parents are EXCLUDED from checks 0 to 9 (they never
--     have an allocated amount by design) and are reconciled against their Children in checks 10 and 11.
--     The extract has no Parent -> Child key, so Children are matched to Parents by report_legacy_key
--     and vendor (dates can differ between a Parent and its Children).
--
-- Parsing: blank text is turned into NULL before converting, because TRY_CONVERT(float, '') returns 0
-- in SQL Server, which would make a blank amount look like a real $0.
--
-- Entry-level facts in #entry (one row per entry_key, Regular and Child entries only):
--   entry_amt  = the entry amount (MAX of the repeated values; check 8 asserts they are all equal).
--   alloc_sum  = sum of the allocated amounts. NULL when NO row of the entry has a numeric amount.
--   pct_sum    = sum of the allocation percentages; ~100 for a fully allocated entry.
--
-- How to read the result: status OK = nothing to fix, REVIEW = look at the entries counted, INFO = context.
-- Checks OVERLAP (one entry can fail several), so do not add the entries or dollars columns together.
-- dollars_basis says what the dollars figure is: 'entry amount' (the entries' full amounts) or
-- 'excess' / 'difference' (allocated total minus entry amount). Dollars are in reimbursement currency.
--
-- To see WHICH entries a check flagged: SELECT * FROM #entry WHERE <the check's condition>
-- (or #pg for checks 10, which is one row per report + vendor).

DROP TABLE IF EXISTS #entry;
DROP TABLE IF EXISTS #parent;
DROP TABLE IF EXISTS #pg;

-- Regular and Child entries (everything except Parents).
SELECT
    c.entry_key,
    MAX(c.transaction_type)                                        AS tt,
    MAX(c.report_legacy_key)                                       AS rk,
    MAX(c.vendor)                                                  AS vendor,
    COUNT(*)                                                       AS n_rows,
    MAX(c.expense_amount__reimbursement_currency_)                 AS entry_amt,
    MIN(c.expense_amount__reimbursement_currency_)                 AS entry_amt_min,
    COUNT(c.expense_amount__reimbursement_currency_)               AS n_entry_amt_rows,
    SUM(v.amt)                                                     AS alloc_sum,
    SUM(v.pct)                                                     AS pct_sum,
    SUM(CASE WHEN v.amt IS NULL THEN 1 ELSE 0 END)                 AS n_null_amt_rows,
    SUM(CASE WHEN v.pct IS NULL THEN 1 ELSE 0 END)                 AS n_null_pct_rows,
    -- rows where the allocated amount is not entry amount x percentage (about a cent of float tolerance)
    SUM(CASE WHEN ABS(v.amt - c.expense_amount__reimbursement_currency_ * v.pct / 100.0) > 0.011
             THEN 1 ELSE 0 END)                                    AS bad_amount_rows,
    -- expense_amount present but not readable as a number (blank, or text)
    SUM(CASE WHEN c.expense_amount IS NOT NULL AND v.amt IS NULL
             THEN 1 ELSE 0 END)                                    AS unreadable_amount_rows
INTO #entry
FROM dbo.concur AS c
CROSS APPLY (VALUES (
    TRY_CONVERT(float, NULLIF(LTRIM(RTRIM(c.expense_amount)), '')),
    TRY_CONVERT(float, NULLIF(LTRIM(RTRIM(REPLACE(c.percentage, '%', ''))), ''))
)) AS v(amt, pct)
-- A NULL or blank entry_key would collapse into one giant "entry"; it is counted by check 9 instead.
WHERE NULLIF(LTRIM(RTRIM(c.entry_key)), '') IS NOT NULL
  AND COALESCE(c.transaction_type, '') <> 'Parent'
GROUP BY c.entry_key;

-- Parent entries, one row per entry_key.
SELECT
    c.entry_key,
    MAX(c.report_legacy_key)                        AS rk,
    MAX(c.vendor)                                   AS vendor,
    MAX(c.expense_amount__reimbursement_currency_)  AS entry_amt,
    SUM(TRY_CONVERT(float, NULLIF(LTRIM(RTRIM(c.expense_amount)), ''))) AS alloc_sum
INTO #parent
FROM dbo.concur AS c
WHERE NULLIF(LTRIM(RTRIM(c.entry_key)), '') IS NOT NULL
  AND c.transaction_type = 'Parent'
GROUP BY c.entry_key;

-- Parents and Children compared per report + vendor (ISNULL so a missing report key or vendor still
-- matches itself). A group can hold several Parents (e.g. two dinners at one restaurant in a report).
SELECT
    g.rk, g.vendor, g.n_parents, g.parent_amt,
    COALESCE(ch.n_children, 0)                      AS n_children,
    ch.child_alloc
INTO #pg
FROM (
    SELECT ISNULL(rk, '') AS rk, ISNULL(vendor, '') AS vendor,
           COUNT(*) AS n_parents, SUM(entry_amt) AS parent_amt
    FROM #parent GROUP BY ISNULL(rk, ''), ISNULL(vendor, '')
) AS g
LEFT JOIN (
    SELECT ISNULL(rk, '') AS rk, ISNULL(vendor, '') AS vendor,
           COUNT(*) AS n_children, SUM(alloc_sum) AS child_alloc
    FROM #entry WHERE tt = 'Child' GROUP BY ISNULL(rk, ''), ISNULL(vendor, '')
) AS ch ON ch.rk = g.rk AND ch.vendor = g.vendor;

SELECT check_name, entries, dollars, dollars_basis, status, meaning
FROM (
    -- 0. Context: how big the table is (Regular and Child entries; Parents are counted in check 12).
    SELECT 0 AS ord, 'total entries (excluding Parents)' AS check_name,
           COUNT(*) AS entries, CAST(COALESCE(SUM(entry_amt), 0) AS decimal(19, 2)) AS dollars,
           'entry amount' AS dollars_basis, 'INFO' AS status,
           'Distinct entry_key values and the sum of their entry amounts (each counted once).' AS meaning
    FROM #entry

    UNION ALL
    -- 1. Entries with no usable allocated amount: they add nothing to predictions.amount.
    --    Parents are excluded because their allocation is blank by design.
    SELECT 1, 'entries with no allocated amount',
           COUNT(*), CAST(COALESCE(SUM(entry_amt), 0) AS decimal(19, 2)), 'entry amount',
           CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'REVIEW' END,
           'alloc_sum IS NULL on a Regular or Child entry: no row has a numeric expense_amount; spend is missing.'
    FROM #entry WHERE alloc_sum IS NULL

    UNION ALL
    -- 2. Overcounted entries: several allocation rows that EACH carry the full entry amount
    --    (allocated amounts add up to n_rows x the entry amount, not 1 x).
    SELECT 2, 'entries overcounted (n x entry amount)',
           COUNT(*), CAST(COALESCE(SUM(alloc_sum - entry_amt), 0) AS decimal(19, 2)), 'excess',
           CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'REVIEW' END,
           'n_rows > 1, entry_amt <> 0 and alloc_sum = n_rows x entry_amt: the amount is counted once per row.'
    FROM #entry
    WHERE n_rows > 1 AND entry_amt <> 0
      AND ABS(alloc_sum - n_rows * entry_amt) <= 0.005 * n_rows + 0.01

    UNION ALL
    -- 3. Entries whose allocated total is neither the entry amount nor n x the entry amount.
    --    The tolerance grows with the row count because each allocated amount is rounded to cents.
    SELECT 3, 'entries that do not reconcile',
           COUNT(*), CAST(COALESCE(SUM(alloc_sum - entry_amt), 0) AS decimal(19, 2)), 'difference',
           CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'REVIEW' END,
           'alloc_sum is not entry_amt (within rounding) and, for multi-row entries, not n_rows x entry_amt either.'
    FROM #entry
    WHERE alloc_sum IS NOT NULL
      AND ABS(alloc_sum - entry_amt) > 0.005 * n_rows + 0.01
      AND NOT (n_rows > 1 AND entry_amt <> 0 AND ABS(alloc_sum - n_rows * entry_amt) <= 0.005 * n_rows + 0.01)

    UNION ALL
    -- 4. Percentages that do not add up to 100 (any entry that has an allocated amount, one row or many).
    SELECT 4, 'entries with percentages not summing to 100',
           COUNT(*), CAST(COALESCE(SUM(entry_amt), 0) AS decimal(19, 2)), 'entry amount',
           CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'REVIEW' END,
           'alloc_sum is not NULL and pct_sum is NULL or more than 0.01 from 100.'
    FROM #entry
    WHERE alloc_sum IS NOT NULL AND (pct_sum IS NULL OR ABS(pct_sum - 100) > 0.01)

    UNION ALL
    -- 5. Row-level rule: expense_amount should equal entry amount x percentage / 100.
    --    Rows with a NULL amount or percentage are not tested here; check 6 counts them.
    SELECT 5, 'entries with rows where amount <> entry x percentage',
           COUNT(*), CAST(COALESCE(SUM(entry_amt), 0) AS decimal(19, 2)), 'entry amount',
           CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'REVIEW' END,
           'bad_amount_rows > 0.'
    FROM #entry WHERE bad_amount_rows > 0

    UNION ALL
    -- 6. Partly filled entries: some rows have an amount or percentage and others do not.
    SELECT 6, 'entries with some rows missing amount or percentage',
           COUNT(*), CAST(COALESCE(SUM(entry_amt), 0) AS decimal(19, 2)), 'entry amount',
           CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'REVIEW' END,
           'alloc_sum is not NULL but n_null_amt_rows > 0 or n_null_pct_rows > 0.'
    FROM #entry
    WHERE alloc_sum IS NOT NULL AND (n_null_amt_rows > 0 OR n_null_pct_rows > 0)

    UNION ALL
    -- 7. expense_amount holds something that is not a number (blank or text), so it is ignored in sums.
    SELECT 7, 'entries with blank or non-numeric expense_amount',
           COUNT(*), CAST(COALESCE(SUM(entry_amt), 0) AS decimal(19, 2)), 'entry amount',
           CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'REVIEW' END,
           'unreadable_amount_rows > 0 (expense_amount is not NULL but cannot be read as a number).'
    FROM #entry WHERE unreadable_amount_rows > 0

    UNION ALL
    -- 8. The entry amount is assumed identical on every row of the entry; assert it.
    SELECT 8, 'entries whose entry amount differs or is missing on some rows',
           COUNT(*), CAST(COALESCE(SUM(entry_amt), 0) AS decimal(19, 2)), 'entry amount',
           CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'REVIEW' END,
           'MAX and MIN of the entry amount differ by more than half a cent, or some rows have no entry amount.'
    FROM #entry
    WHERE ABS(entry_amt - entry_amt_min) > 0.005 OR n_entry_amt_rows < n_rows

    UNION ALL
    -- 9. Rows with no usable entry_key; they cannot be grouped into entries and are excluded above.
    SELECT 9, 'rows with NULL or blank entry_key',
           COUNT(*), CAST(COALESCE(SUM(expense_amount__reimbursement_currency_), 0) AS decimal(19, 2)),
           'row amount',
           CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'REVIEW' END,
           'Counted in ROWS (the entries column), not entries; dollars sum the entry amount per row.'
    FROM dbo.concur WHERE NULLIF(LTRIM(RTRIM(entry_key)), '') IS NULL

    UNION ALL
    -- 10. Parent vs Children: per report + vendor, the Children's allocated amounts should add up to the
    --     Parents' amounts. Groups with no Children count with child dollars of 0. Entries = groups.
    --     Dollars = Children minus Parents: about 2x the Parent suggests duplicated Children, about half
    --     or less suggests missing Children (for example days the allocations run did not run).
    SELECT 10, 'Parent groups (report + vendor) whose Children do not add up',
           COUNT(*), CAST(COALESCE(SUM(COALESCE(child_alloc, 0) - parent_amt), 0) AS decimal(19, 2)), 'difference',
           CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'REVIEW' END,
           'ABS(child_alloc - parent_amt) > 0.02, or no Children found. Inspect with SELECT * FROM #pg WHERE ...'
    FROM #pg
    WHERE n_children = 0 OR child_alloc IS NULL OR ABS(child_alloc - parent_amt) > 0.02

    UNION ALL
    -- 11. Parents are expected to carry NO allocated amount (their Children do). One that does would
    --     be counted on top of its Children.
    SELECT 11, 'Parent entries that have an allocated amount',
           COUNT(*), CAST(COALESCE(SUM(entry_amt), 0) AS decimal(19, 2)), 'entry amount',
           CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'REVIEW' END,
           'transaction_type = Parent and alloc_sum IS NOT NULL.'
    FROM #parent WHERE alloc_sum IS NOT NULL

    UNION ALL
    -- 12. Context: Parents, kept out of predictions and out of checks 0 to 9.
    SELECT 12, 'Parent entries (excluded from predictions)',
           COUNT(*), CAST(COALESCE(SUM(entry_amt), 0) AS decimal(19, 2)), 'entry amount', 'INFO',
           'Itemized expenses whose amounts live on their Child entries.'
    FROM #parent
) AS checks
ORDER BY ord;
