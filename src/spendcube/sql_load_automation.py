import os
import glob
import pandas as pd
import numpy as np
import datetime
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
import sys

from spendcube import config
from sklearn.linear_model import SGDClassifier
from joblib import load


from ScriptImportStart import (
    columnreplaceforsqlload,
    error_function,
    convertcolumnswithdateinname,
    continue_from_sql_index,
    find_files_created_today,
    LoadFilesFromFolder,
    LoadFilesFromFolderSwitchable
)

def assign_values(row, column_name_1,column_name_2,column_name_3):
    if row[column_name_1] != 'Unclassified':
        return row[column_name_1]
    elif row[column_name_2] != 'Unclassified':
        return row[column_name_2] 
    else:
        return row[column_name_3] 

# script montioring end imports all our script monitoring
# it pushes to sql and asana as a first passs
# and csv and email as a backup
from ScriptMonitoringEnd import scriptmonitoring


def main():
    from ScriptImportStart import user, failure, _uuid

    if sys.argv[0].find("ipykernel") != -1:
        script = user + " Testing"
    else:
        script = os.path.basename(sys.executable)
    scriptstart = datetime.datetime.now()
    scriptstart = scriptstart.strftime("%Y-%m-%d %H:%M:%S")
    ####The below four are placeholders and should be updated as needed within the code
    scriptinput = "Scheduled Monthly"
    scriptoutput = ""
    result = ""
    failure = 0
    try:
        server = "CIDA-SQL-T-01"
        database = "spendcube"
        username = "cidadata"
        password = config.require("CIDA_SQL_PASSWORD")
        schema = "dbo"
        directory = (
            r"C:\Users"
            + "\\"
            + user
            + r"\Boston University\Continuous Improvement & Data Analytics - Documents\Automation and Data"
        )
        os.chdir(directory)
        # Creates connection to sql server and the meta engine that will allow us to accss the tables
        connection_string = (
            "DRIVER={ODBC Driver 13 for SQL Server};SERVER="
            + server
            + ";DATABASE="
            + database
            + ";UID="
            + username
            + ";PWD="
            + password
        )
        connection_url = URL.create(
            "mssql+pyodbc", query={"odbc_connect": connection_string}
        )
        engine = create_engine(connection_url, fast_executemany=True)
        ### Extra files for disambiguationn

        gl = pd.read_excel(r"SAP-GL_Export\GL_EXPORT.XLSX")

        gl = columnreplaceforsqlload(gl)
        gl = gl[gl["chart_of_accounts"] == "0010"].loc[:, ["g/l_account", "g/l_acct_long_text"]]

        supplierdetailsxlsx = glob.glob(
            "Output-Supplier List-S&P Version\Suppliers SandP*.xlsx"
        )
        supplierdetails = pd.read_excel(
            max(supplierdetailsxlsx, key=os.path.getctime), dtype=str
        )

        smallsupplierdetails = supplierdetails[["Supplier ID", "Line of Business"]]

        columnreplaceforsqlload(smallsupplierdetails)

        column_names = [
            "supplier",
            "gl_name",
            "product_description",
            "product_category",
            "line_of_business",
            "supplier_id",
            "transaction_num",
            "transaction_date",
            "funding_source",
            "amount",
            "datasource",
            "spendsource",
            "index",
            "join_key_datasource",
        ]
        try:
            # first we check whether or not there are any files created today
            disbursementdirectory = directory + "\\" + "SAP HANA-ZPU_CP05 - Disbursements"
            try:
                disbursementscreatedtoday = find_files_created_today(disbursementdirectory)
            except:
                disbursementscreatedtoday = pd.DataFrame()

            if disbursementscreatedtoday.empty or len(disbursementscreatedtoday) == 0:
                scriptoutput += "No New Disbursement Files | "
            else:
                disbursementblank = LoadFilesFromFolderSwitchable(
                    "SAP HANA-ZPU_CP05 - Disbursements/Export*.csv",
                    filetype="csv",
                    filestoload="recent",
                )
                # we set out our sql table and schema
                table = "disbursements"
                schemaandtable = schema + "." + table
                columnreplaceforsqlload(disbursementblank)
                disbursementblank = disbursementblank.replace(np.nan, None)
                disbursementblank.reset_index(drop=True, inplace=True)
                disbursementblank = convertcolumnswithdateinname(disbursementblank)
                disbursementblank[
                    [c for c in disbursementblank if (c.find("zpu") == -1)]
                ] = disbursementblank[
                    [c for c in disbursementblank if (c.find("zpu") == -1)]
                ].astype(
                    float
                )
                disbursementblank.columns = disbursementblank.columns.str.replace(
                    "zpu_cp05_v01", "disbursement"
                )
                disbursementblank = (
                    disbursementblank.reset_index()
                    .assign(
                        DataSource="SAP HANA-ZPU_CP05_V01",
                        SpendSource="Disbursements",
                        disbursement_document_description_=disbursementblank.disbursement_document_description_.str.replace(
                            "[^A-Za-z0-9 ]+", "", regex=True
                        ),
                        productcat="",
                    )
                    .merge(
                        smallsupplierdetails,
                        how="left",
                        left_on="disbursement_vendor_",
                        right_on="supplier_id",
                    )
                )

                # set the index to continue from last index
                try:
                    disbursementblank = continue_from_sql_index(
                        schemaandtable, disbursementblank, engine
                    )
                except:
                    pass

                disbursementblank = disbursementblank.assign(
                        join_key_datasource=lambda disbursementblank_: disbursementblank_.index.astype(
                            str
                        )
                        + disbursementblank_.DataSource,
                    ).reset_index()
                
                disbursementblank = disbursementblank.assign(
                        funding_source = disbursementblank.disbursement_funds_center_       
                )

                disbursementblank.to_sql(
                    table,
                    engine,
                    schema,
                    if_exists="append",
                    index=True,
                    chunksize=1000,
                )

                disbursementsmall = disbursementblank[
                    [
                        "disbursement_text_column_for_attribute_0vendor_",
                        "disbursement_text_column_for_attribute_0gl_account_",
                        "disbursement_document_description_",
                        "productcat",
                        "line_of_business",
                        "disbursement_vendor_",
                        "disbursement_fi_document_number_",
                        "disbursement_posting_date_in_the_document_",
                        "funding_source",
                        "amount",
                        "DataSource",
                        "SpendSource",
                        "index",
                        "join_key_datasource",
                    ]
                ]

                disbursementsmall.columns = column_names
                # write to SQL using 1000 chunks

                scriptoutput += "Disbursements written to SQL | "
        except:
            scriptoutput += "Disbursement failed to write to SQL" + error_function() + "|"
            failure = 1
        try:
            boadirectory = directory + "\\" + "BOA_PCARD-SpendViz"
            try:
                boacreatedtoday = find_files_created_today(boadirectory)
            except:
                boacreatedtoday = pd.DataFrame()
            if boacreatedtoday.empty or len(boacreatedtoday) == 0:
                scriptoutput += "No new BOA_PCARD | "
            else:
                # we set out our sql table and schema

                table = "boa_pcard"
                schemaandtable = schema + "." + table
                # read the most recent boa csv
                boadf = LoadFilesFromFolderSwitchable(
                    "BOA_PCARD-SpendViz/*Pcard*.txt",
                    filetype="csv",
                    filestoload="recent",
                )
                boadf = columnreplaceforsqlload(boadf)
                try:
                    boadf = continue_from_sql_index(schemaandtable, boadf, engine)
                except:
                    pass
                boadf = convertcolumnswithdateinname(boadf)
                boadf[
                    [
                        c
                        for c in boadf
                        if (
                            c.find("amount") != -1
                            or c.find("quantity") != -1
                            or c.find("total") != -1
                            or c.find("_tax") != -1
                        )
                    ]
                ] = boadf[
                    [
                        c
                        for c in boadf
                        if (
                            c.find("amount") != -1
                            or c.find("quantity") != -1
                            or c.find("total") != -1
                            or c.find("_tax") != -1
                        )
                    ]
                ].astype(
                    float
                )
                boadf = (
                    boadf[~pd.isna(boadf.item_description)]
                    .drop(
                        ["detail_description", "detail_amount", "quantity", "detail_type"],
                        axis="columns",
                    )
                    .drop_duplicates()
                    .merge(
                        boadf[
                            (~pd.isna(boadf.detail_description))
                            & (boadf.detail_type != "Tax")
                        ][
                            [
                                "txn_number",
                                "detail_description",
                                "detail_amount",
                                "quantity",
                                "detail_type",
                            ]
                        ].drop_duplicates(),
                        how="left",
                        on="txn_number",
                    )
                )

                boadf2 = (
                    boadf.groupby("txn_number")
                    .agg({"txn_number": "count", "amount": "mean"})
                    # here we assign and round the approximate average by assigning each line an equal
                    # amount of the total
                    .assign(
                        approx_avg=lambda df_: np.round(
                            (df_.amount.astype(float) / df_.txn_number.astype(float)), 2
                        )
                    )
                    # drop and merge back
                    .rename({"txn_number": "txn_count"}, axis="columns")
                    .reset_index(drop=False)
                    .drop(["txn_count", "amount"], axis="columns")
                    .merge(boadf, how="right", on="txn_number")
                    .assign(
                        DataSource="BankOfAmerica-PcardSpendviz",
                        SpendSource="pCard",
                        item_description=boadf.item_description.str.replace(
                            "[^A-Za-z0-9 ]+", "", regex=True
                        ),
                        detail_description=boadf.detail_description.str.replace(
                            "[^A-Za-z0-9 ]+", "", regex=True
                        ),
                        lineofbusiness="",
                    )
                    .reset_index()
                )
                
                try:
                    boadf2 = continue_from_sql_index(schemaandtable, boadf2, engine)
                except:
                    pass
                
                boadf2 = boadf2.assign(
                    combodescript=lambda boadf2: boadf2.item_description.fillna("")
                    + " "
                    + boadf2.detail_description.fillna(""),
                    join_key_datasource=lambda boadf2: boadf2.index.astype(str)
                    + " "
                    + boadf2.DataSource,).reset_index()
                
                boadf2.to_sql(
                    table, engine, schema, if_exists="append", index=True, chunksize=1000
                )

                boadf2 = boadf2.assign(
                    funding_source = boadf.gl__cost_object 
                )                

                boasmall = boadf2[
                    [
                        "comp_supp_name",
                        "gl__gl_account_desc",
                        "combodescript",
                        "mcc_description",
                        "lineofbusiness",
                        "vendor_id",
                        "txn_number",
                        "post_date",
                        "funding_source",
                        "approx_avg",
                        "DataSource",
                        "SpendSource",
                        "index",
                        "join_key_datasource",
                    ]
                ]

                boasmall.columns = column_names

                scriptoutput += "BOA written to SQL | "
        except:
            scriptoutput += "BOA_Pcard failed to write to SQL" + error_function() + "|"
            failure = 1
        try:
            concurdirectory = directory + "\\" + "Concur-Spendcube-Entries"
            try:
                concurcreatedtoday = find_files_created_today(concurdirectory)
            except:
                concurcreatedtoday = pd.DataFrame()
            if concurcreatedtoday.empty or len(concurcreatedtoday) == 0:
                scriptoutput += "No New Concur Files | "
            else:
                table = "concur"
                schemaandtable = schema + "." + table

                concur_entry_location = "Concur-Spendcube-Entries/*SpendCube-Entries*.csv"
                concur_allocation_location = (
                    "Concur-SpendcubeEntriesAllocations/*SpendCube-Entries-Allocation*.csv"
                )
                concurallocationnewestfile = LoadFilesFromFolderSwitchable(
                    regexfilepath=concur_allocation_location,
                    filetype="csv",
                    filestoload="recent",
                    file_encoding="utf_16",
                )
                concurnewestfile = LoadFilesFromFolderSwitchable(
                    regexfilepath=concur_entry_location,
                    filetype="csv",
                    filestoload="recent",
                    file_encoding="utf_16",
                )
                concurnewestfile = columnreplaceforsqlload(concurnewestfile)

                concurnewestfile = convertcolumnswithdateinname(concurnewestfile)

                concurnewestfile.expense_amount__reimbursement_currency_ = (
                    concurnewestfile.expense_amount__reimbursement_currency_.astype(float)
                )

                concurnewestfile = concurnewestfile.assign(
                    SpendSource=concurnewestfile.payment_type,
                    DataSource="Concur-Spendcube Entries",
                ).reset_index(drop=True)

                concurallocationnewestfile = columnreplaceforsqlload(
                    concurallocationnewestfile
                )

                concurallocationnewestfile = convertcolumnswithdateinname(
                    concurallocationnewestfile
                )

                # concurallocationnewestfile.expense_amount__reimbursement_currency_ = concurallocationnewestfile.expense_amount__reimbursement_currency_.astype(float)

                concurallocationnewestfile = concurallocationnewestfile.reset_index(
                    drop=True
                )
                concurallocationnewestfile = concurallocationnewestfile.loc[
                    ~pd.isna(concurallocationnewestfile.percentage)
                ].drop_duplicates()

                concurnewestfile_merged = concurnewestfile.merge(
                    concurallocationnewestfile,
                    how="left",
                    left_on="entry_key",
                    right_on="entry_key",
                ).drop_duplicates()

                concurnewestfile_merged_2 = (
                    concurnewestfile_merged.assign(
                        account_code_1=concurnewestfile_merged.account_code_1.fillna(
                            0
                        ).astype(int),
                        product_description=concurnewestfile_merged["spend_category"],
                        Line_of_Business="",
                        report_name=concurnewestfile_merged.report_name.fillna("")
                        .astype(str)
                        .str.replace("[^A-Za-z0-9 ]+", "", regex=True),
                        purpose=concurnewestfile_merged.purpose.fillna("")
                        .astype(str)
                        .str.replace("[^A-Za-z0-9 ]+", "", regex=True),
                        vendor=concurnewestfile_merged.vendor.fillna("")
                        .astype(str)
                        .str.replace("[^A-Za-z0-9 ]+", "", regex=True),
                    )
                    .merge(gl, how="left", left_on="account_code_1", right_on="g/l_account")
                    .reset_index()
                )


                try:
                    concurnewestfile_merged_2 = continue_from_sql_index(
                        schemaandtable, concurnewestfile_merged_2, engine
                    )
                except:
                    pass
                
                concurnewestfile_merged_2 = concurnewestfile_merged_2.assign(
                        join_key_datasource=lambda concurnewestfile_merged_2: concurnewestfile_merged_2.index.astype(
                            str
                        )
                        + " "
                        + concurnewestfile_merged_2.DataSource,).reset_index()
                
                concurnewestfile_merged_2.to_sql(
                    table, engine, schema, if_exists="append", index=True, chunksize=1000
                )

                concurnewestfile_merged_2 = concurnewestfile_merged_2.assign(
                        funding_source = concurnewestfile_merged_2.custom_1___code
                    ).reset_index()

                concursmall = concurnewestfile_merged_2[
                    [
                        "vendor",
                        "g/l_acct_long_text",
                        "product_description",
                        "expense_type",
                        "Line_of_Business",
                        "vendor",
                        "entry_key",
                        "paid_date_x",
                        "funding_source",
                        "expense_amount",
                        "DataSource",
                        "SpendSource",
                        "index",
                        "join_key_datasource",
                    ]
                ]


                concursmall.columns = column_names
                

                scriptoutput += "Concur written to SQL | "
        except:
            scriptoutput += "Concur failed to write to SQL" + error_function() + "|"
            failure = 1
        try:
            aribadirectory = directory + "\\" + "Ariba-InvoceDetailsWDescription"
            try:
                aribacreatedtoday = find_files_created_today(aribadirectory)
            except:
                aribacreatedtoday = pd.DataFrame()
            if aribacreatedtoday.empty or len(aribacreatedtoday) == 0:
                scriptoutput += "No New Ariba Files | "
            else:
                table = "ariba"
                schemaandtable = schema + "." + table
                invoice_location = (
                    "Ariba-InvoceDetailsWDescription\*InvoiceDetailsWDescription*.csv"
                )
                newestinvoicedetail = LoadFilesFromFolderSwitchable(
                    invoice_location, "csv", "recent"
                )
                newestinvoicedetail = newestinvoicedetail.drop(
                    newestinvoicedetail.iloc[:, 0].name, axis="columns"
                )
                newestinvoicedetail = columnreplaceforsqlload(newestinvoicedetail)

                newestinvoicedetail = convertcolumnswithdateinname(newestinvoicedetail)

                newestinvoicedetail[
                    [c for c in newestinvoicedetail if (c.startswith("sum"))]
                ] = (
                    newestinvoicedetail[
                        [c for c in newestinvoicedetail if (c.startswith("sum"))]
                    ]
                    .astype(str)
                    .apply(lambda x: x.str.replace(",", ""))
                    .apply(lambda x: x.str.replace("NaT", ""))
                    .astype(float, errors="ignore")
                )

                newestinvoicedetail = newestinvoicedetail.reset_index(drop=True)

                linetypeconditons = [
                    (newestinvoicedetail.inv_line_type == "Punch-Out Item"),
                    (newestinvoicedetail.inv_line_type == "Catalog Item"),
                    (newestinvoicedetail.inv_line_type == "Non-Catalog Item"),
                    (newestinvoicedetail.inv_line_type == "Fee Item"),
                    (newestinvoicedetail.inv_line_type == "Misc Expense Item"),
                    (newestinvoicedetail.inv_line_type == "Freight Charge"),
                    (newestinvoicedetail.inv_line_type == "Handling Charge"),
                    (newestinvoicedetail.inv_line_type == "Discount"),
                    (newestinvoicedetail.inv_line_type == "Value Added Tax"),
                    (newestinvoicedetail.inv_line_type == "Withholding Tax"),
                    (newestinvoicedetail.inv_line_type == "SalesTax"),
                ]

                linetypevalues = [
                    "Catalog",
                    "Catalog",
                    "Non-Catalog",
                    "BPO Scheduled Payment",
                    "BPO Expense",
                    "Charge",
                    "Charge",
                    "Discount",
                    "Tax",
                    "Tax",
                    "Tax",
                ]

                newestinvoicedetail["Updatedlinetype"] = np.select(
                    linetypeconditons, linetypevalues
                )
                buyerhtml = glob.glob("Ariba-Purchase Order Details\Purchase*.xls")
                buyerdf = LoadFilesFromFolder(buyerhtml, "html")

                buyercsv = glob.glob("Ariba-Purchase Order Details\Purchase*.csv")
                buyerdf2 = LoadFilesFromFolder(buyercsv, "csv")

                buyerdf = pd.concat([buyerdf, buyerdf2], axis=0, join="outer").copy()

                buyerdf = columnreplaceforsqlload(buyerdf)

                orderswithspend = buyerdf[["order_id", "sum_po_spend_"]]
                orderswithspend.loc[:, "sum_po_spend_"] = (
                    orderswithspend["sum_po_spend_"]
                    .astype(str)
                    .str.replace(",", "")
                    .astype(float)
                )
                orderswithspend = orderswithspend.groupby("order_id")[
                    ["sum_po_spend_"]
                ].sum()
                buyerapprovedorders = orderswithspend[
                    orderswithspend["sum_po_spend_"] >= 10000
                ]
                buyerapprovedorders = buyerapprovedorders.assign(
                    ApprovedByBuyer="S&P Approved"
                )

                orderstype = buyerdf[["order_id", "order_type_1"]].copy()
                orderstype = orderstype.sort_values(by=["order_type_1"]).drop_duplicates(
                    subset=["order_id"]
                )
                allorders = orderstype.merge(buyerapprovedorders, how="left", on="order_id")
                allorders = allorders.assign(
                    ordertypeandapproval=(
                        allorders.order_type_1.astype(str)
                        + " "
                        + allorders.ApprovedByBuyer.astype(str)
                    ).str.replace("nan", "")
                )
                allorders = allorders[allorders["order_id"] != "Unclassified"]
                allorderssmall = allorders[["order_id", "ordertypeandapproval"]]
                newestinvoicedetailordertypes = newestinvoicedetail.merge(
                    allorderssmall, how="left", left_on="inv_order_id", right_on="order_id"
                )
                newestinvoicedetailordertypes = newestinvoicedetailordertypes.assign(
                    SpendSource=(
                        newestinvoicedetailordertypes.inv_invoice_source_document.astype(
                            str
                        )
                        + " "
                        + newestinvoicedetailordertypes.Updatedlinetype.astype(str)
                        + " "
                        + newestinvoicedetailordertypes.ordertypeandapproval.astype(str)
                    )
                    .str.replace("nan", "")
                    .str.replace("None", "")
                    .str.strip(),
                    DataSource="Ariba-Invoice Details With Description",
                )

                newestinvoicedetailordertypes = (
                    newestinvoicedetailordertypes.assign(
                        inv_description=newestinvoicedetailordertypes.inv_description.str.replace(
                            "[^A-Za-z0-9 ]+", "", regex=True
                        ),
                        invsupplier__erp_supplier_id_=newestinvoicedetailordertypes.invsupplier__erp_supplier_id_.str.replace(
                            "'", ""
                        ),
                    )
                    .merge(
                        smallsupplierdetails,
                        how="left",
                        left_on="invsupplier__erp_supplier_id_",
                        right_on="supplier_id",
                    )
                    .reset_index()
                )
                try:
                    newestinvoicedetailordertypes = newestinvoicedetailordertypes.drop(
                        columns="updatedlinetype"
                    )
                except:
                    pass

                newestinvoicedetailordertypes = continue_from_sql_index(
                    schemaandtable, newestinvoicedetailordertypes, engine
                )
                newestinvoicedetailordertypes=newestinvoicedetailordertypes.assign(
                        join_key_datasource=lambda newestinvoicedetailordertypes_: newestinvoicedetailordertypes_.index.astype(
                            str
                        )
                        + " "
                        + newestinvoicedetailordertypes_.DataSource
                    ).reset_index()

                newestinvoicedetailordertypes.to_sql(
                    "ariba", engine, schema, if_exists="append", index=True, chunksize=1000
                )
                
                newestinvoicedetailordertypes['funding_source'] = newestinvoicedetailordertypes.apply(
                    lambda row: assign_values(row, 'invinternal_order__internal_order_id_',
                                            'invwbselement__wbselement_id_',
                                            'invcost_center__cost_center_id_'), axis = 1
                )

                aribasmall = newestinvoicedetailordertypes[
                    [
                        "invsupplier__erp_supplier_",
                        "invgl_account__gl_account_name_",
                        "inv_description",
                        "inverp_commodity__product_category_",
                        "line_of_business",
                        "invsupplier__erp_supplier_id_",
                        "ipt_erp_invoice_number",
                        "invaccounting_date__date_",
                        "funding_source",
                        "sum_invoice_spend_",
                        "DataSource",
                        "SpendSource",
                        "index",
                        "join_key_datasource",
                    ]
                ]

                aribasmall.columns = column_names

                scriptoutput += "AribaInvoices written to SQL | "
        except:
            scriptoutput += "AribaInvoices failed to write to SQL" + error_function() + "|"
            failure = 1
        try:
            supplierdetailsxlsx = directory + "\\" + "Output-Supplier List-S&P Version"
            try:
                supplierdetailscreatedtoday = find_files_created_today(supplierdetailsxlsx)
            except:
                supplierdetailscreatedtoday = pd.DataFrame()
            if supplierdetailscreatedtoday.empty or len(supplierdetailscreatedtoday) == 0:
                scriptoutput += "No New Supplier Files|"
            else:
                supplierdetails = columnreplaceforsqlload(
                    pd.read_excel(
                        supplierdetailsxlsx + '\\'+supplierdetailscreatedtoday.sort_values(by = 'created',ascending=False).iloc[0,0],
                        dtype=str,
                    )
                )
                supplierdetails.to_sql(
                    "suppliers",
                    engine,
                    schema,
                    if_exists="replace",
                    index=True,
                    chunksize=1000,
                )
                scriptoutput += "Suppliers written to SQL | "
        except:
            scriptoutput += "Suppliers failed to write to SQL" + error_function() + "|"
            failure = 1
        try:
            clf = load("Python-AutomationEXEs/Spendcube_Algorithm/SpendCube_ML.joblib")
            table = "predictions"
            schemaandtable = schema + "." + table
            combineddata = pd.DataFrame()
            if len(concurcreatedtoday) > 0:
                combineddata = pd.concat([combineddata, concursmall])
            if len(aribacreatedtoday) > 0:
                combineddata = pd.concat([combineddata, aribasmall])
            if len(boacreatedtoday) > 0:
                combineddata = pd.concat([combineddata, boasmall])
            if len(disbursementscreatedtoday) > 0:
                combineddata = pd.concat([combineddata, disbursementsmall])

            if len(combineddata) == 0:
                scriptoutput += "No new predictions"
            else:
                combineddata["bag_of_words"] = (
                    combineddata[
                        [
                            "supplier",
                            "gl_name",
                            "product_description",
                            "product_category",
                            "line_of_business",
                        ]
                    ]
                    .astype(str)
                    .T.agg(" ".join)
                )

                predicted_svm = clf.predict(combineddata.bag_of_words)
                predicted_df = pd.DataFrame(predicted_svm)
                predictions = pd.concat(
                    [combineddata.reset_index(drop=True), predicted_df], axis=1
                )
                try:
                    predictions = continue_from_sql_index(
                        schemaandtable, predictions, engine
                    )
                except:
                    pass
                predictions = predictions.replace({',': ''}, regex=True)
                predictions.reset_index()
                predictions.to_sql(
                    table, engine, schema, if_exists="append", index=False, chunksize=1000
                )
                scriptoutput += "Entered Predictions"
            result = "Success"
        except:
            scriptoutput += "Failed at predictions" + error_function() + "|"
            failure = 1
            result = "Failure"
    except:
        ###Here is where your total unredemeemable failure goes
        ###there ought to be other tries that fix issues but this is if something has failed so bad it can't be recovered

        scriptoutput = error_function()
        failure = 1
        result = "Failure"

    scriptfinish = datetime.datetime.now()
    scriptfinish = scriptfinish.strftime("%Y-%m-%d %H:%M:%S")
    # finally we run the data either to the SQL server or if ti fails to get to the sql server as a backup to a csv
    scriptmonitoring(
        script,
        scriptstart,
        scriptfinish,
        scriptinput,
        scriptoutput,
        user,
        _uuid,
        result,
        failure,
    )
    print(scriptoutput)



if __name__ == "__main__":
    main()
