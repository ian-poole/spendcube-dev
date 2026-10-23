-- Snapshot of view definitions from the spendcube database (read-only extract).

-- =====================================================
-- dbo.V_Predictions
-- =====================================================
CREATE VIEW dbo.V_Predictions AS

SELECT [level_0]
      ,[supplier]
      ,[gl_name]
      ,[product_description]
      ,[product_category]
      ,[line_of_business]
      ,[supplier_id]
      ,[transaction_num]
      ,[transaction_date]
      ,SUBSTRING(REPLACE(REPLACE(funding_source,' ',''),'''',''),PATINDEX('%[^0]%', REPLACE(REPLACE(funding_source,' ',''),'''','')),len(REPLACE(REPLACE(funding_source,' ',''),'''',''))) AS funding_source
      ,TRY_CONVERT(float,REPLACE([amount],',','')) AS amount
      ,[datasource]
      ,[spendsource]
      ,TRY_CONVERT(int,[index]) as [index]
      ,[join_key_datasource]
      ,[bag_of_words]
      ,[0]
  FROM dbo.predictions
WHERE transaction_date >= (CASE WHEN MONTH(GETDATE()) >= 7 THEN DATEFROMPARTS(YEAR(GETDATE())-4,7,1) ELSE DATEFROMPARTS(YEAR(GETDATE())-5,7,1) END)
GO

-- =====================================================
-- dbo.V_Predictions_With_Funds_Sources
-- =====================================================
CREATE VIEW dbo.V_Predictions_With_Funds_Sources
AS
SELECT        v.funds_source, p.level_0, p.supplier, p.gl_name, p.product_description, p.product_category, p.line_of_business, p.supplier_id, p.transaction_num, p.transaction_date, p.funding_source AS amount, p.amount AS datasource, 
                         p.datasource AS spendsource, p.spendsource AS [index], p.[index] AS join_key_datasource, p.join_key_datasource AS bag_of_words, p.bag_of_words AS [0], p.[0] AS Expr1
FROM            dbo.V_all_funds_sources AS v LEFT OUTER JOIN
                         dbo.predictions AS p ON v.join_key_datasource = p.join_key_datasource

GO

-- =====================================================
-- dbo.V_all_funds_sources
-- =====================================================
CREATE VIEW V_all_funds_sources AS WITH amex AS (
SELECT dbo.amex_pcard.join_key_datasource, dbo.amex_pcard.cost_center AS funds_source
FROM   dbo.amex_pcard), concur AS
    (SELECT dbo.concur.join_key_datasource, dbo.concur.custom_1___code AS funds_source
    FROM    dbo.concur), boa AS
    (SELECT dbo.boa_pcard.join_key_datasource, dbo.boa_pcard.gl__cost_object AS funds_source
    FROM    dbo.boa_pcard), srm AS
    (SELECT DISTINCT dbo.srm.join_key_datasource, dbo.srm.srm_funds_center_ AS funds_source
    FROM    dbo.srm), disbursements AS
    (SELECT dbo.disbursements.join_key_datasource, dbo.disbursements.disbursement_funds_center_ AS funds_source
    FROM    dbo.disbursements),
    ariba AS (SELECT dbo.ariba.join_key_datasource, 
                CASE WHEN dbo.ariba.invinternal_order__internal_order_id_ <> 'Unclassified' THEN dbo.ariba.invinternal_order__internal_order_id_ WHEN dbo.ariba.invwbselement__wbselement_id_ <> 'Unclassified' THEN dbo.ariba.invwbselement__wbselement_id_ ELSE dbo.ariba.invcost_center__cost_center_id_
                 END AS funds_source
   FROM    dbo.ariba),
combined_union AS (
SELECT * 
from ariba
UNION ALL
SELECT *
FROM   amex
UNION ALL
SELECT *
FROM   concur
UNION ALL
SELECT *
FROM   boa
UNION ALL
SELECT *
FROM   srm
UNION ALL
SELECT *
FROM   disbursements)
SELECT * FROM combined_union
GO

-- Dependencies (view -> referenced object):
--   V_all_funds_sources -> dbo.amex_pcard
--   V_all_funds_sources -> dbo.ariba
--   V_all_funds_sources -> dbo.boa_pcard
--   V_all_funds_sources -> dbo.concur
--   V_all_funds_sources -> dbo.disbursements
--   V_all_funds_sources -> dbo.srm
--   V_Predictions -> dbo.predictions
--   V_Predictions_With_Funds_Sources -> dbo.predictions
--   V_Predictions_With_Funds_Sources -> dbo.V_all_funds_sources
