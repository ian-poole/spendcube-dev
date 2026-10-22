"""Monthly spendcube load: today's source files -> SQL Server tables, then ML predictions.

Run as a scheduled job. Each source (disbursements, BOA pCard, Concur, Ariba, suppliers) loads in
its own try block, so one failing source does not stop the others; failures are recorded on the
monitored run (failure = 1) and the job still finishes.
"""
import glob
import os
from functools import partial

import numpy as np
import pandas as pd
from cida_toolkit import (
    LoadFilesFromFolder,
    LoadFilesFromFolderSwitchable,
    columnreplaceforsqlload,
    continue_from_sql_index,
    convertcolumnswithdateinname,
    error_function,
    find_files_created_today,
    make_engine,
    monitored_run,
)
from joblib import load
from sklearn.linear_model import SGDClassifier  # noqa: F401  (needed to bundle the model into the exe)

from spendcube import config

JOB_NAME = "spendcube_sql_load"
SCHEMA = "dbo"
ODBC_DRIVER = "ODBC Driver 13 for SQL Server"

# Keep the pre-0.3.0 column naming ("g/l_account" keeps its slash): the SQL tables and downstream
# reports use these names. See docs/decisions.md.
columnreplaceforsqlload = partial(columnreplaceforsqlload, strict=False)


def assign_values(row, column_name_1, column_name_2, column_name_3):
    if row[column_name_1] != "Unclassified":
        return row[column_name_1]
    elif row[column_name_2] != "Unclassified":
        return row[column_name_2]
    else:
        return row[column_name_3]


def run_load(run):
    schema = SCHEMA
    engine = make_engine(
        config.require("CIDA_SQL_SERVER"),
        config.require("SPENDCUBE_SQL_DATABASE"),
        config.require("CIDA_SQL_USERNAME"),
        config.require("CIDA_SQL_PASSWORD"),
        driver=ODBC_DRIVER,
    )
    ### Extra files for disambiguationn

    gl = pd.read_excel(config.GL_EXPORT_FILE)

    gl = columnreplaceforsqlload(gl)
    gl = gl[gl["chart_of_accounts"] == "0010"].loc[:, ["g/l_account", "g/l_acct_long_text"]]

    supplierdetailsxlsx = glob.glob(
        str(config.SUPPLIER_DIR / "Suppliers SandP*.xlsx")
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
        disbursementdirectory = str(config.DISBURSEMENT_DIR)
        try:
            disbursementscreatedtoday = find_files_created_today(disbursementdirectory)
        except:
            disbursementscreatedtoday = pd.DataFrame()

        if disbursementscreatedtoday.empty or len(disbursementscreatedtoday) == 0:
            run.output += "No New Disbursement Files | "
        else:
            disbursementblank = LoadFilesFromFolderSwitchable(
                str(config.DISBURSEMENT_DIR / "Export*.csv"),
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

            run.output += "Disbursements written to SQL | "
    except:
        run.output += "Disbursement failed to write to SQL" + error_function() + "|"
        run.failure = 1
    try:
        boadirectory = str(config.BOA_PCARD_DIR)
        try:
            boacreatedtoday = find_files_created_today(boadirectory)
        except:
            boacreatedtoday = pd.DataFrame()
        if boacreatedtoday.empty or len(boacreatedtoday) == 0:
            run.output += "No new BOA_PCARD | "
        else:
            # we set out our sql table and schema

            table = "boa_pcard"
            schemaandtable = schema + "." + table
            # read the most recent boa csv
            boadf = LoadFilesFromFolderSwitchable(
                str(config.BOA_PCARD_DIR / "*Pcard*.txt"),
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

            run.output += "BOA written to SQL | "
    except:
        run.output += "BOA_Pcard failed to write to SQL" + error_function() + "|"
        run.failure = 1
    try:
        concurdirectory = str(config.CONCUR_ENTRIES_DIR)
        try:
            concurcreatedtoday = find_files_created_today(concurdirectory)
        except:
            concurcreatedtoday = pd.DataFrame()
        if concurcreatedtoday.empty or len(concurcreatedtoday) == 0:
            run.output += "No New Concur Files | "
        else:
            table = "concur"
            schemaandtable = schema + "." + table

            concur_entry_location = str(config.CONCUR_ENTRIES_DIR / "*SpendCube-Entries*.csv")
            concur_allocation_location = (
                str(config.CONCUR_ALLOCATIONS_DIR / "*SpendCube-Entries-Allocation*.csv")
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


            run.output += "Concur written to SQL | "
    except:
        run.output += "Concur failed to write to SQL" + error_function() + "|"
        run.failure = 1
    try:
        aribadirectory = str(config.ARIBA_INVOICE_DIR)
        try:
            aribacreatedtoday = find_files_created_today(aribadirectory)
        except:
            aribacreatedtoday = pd.DataFrame()
        if aribacreatedtoday.empty or len(aribacreatedtoday) == 0:
            run.output += "No New Ariba Files | "
        else:
            table = "ariba"
            schemaandtable = schema + "." + table
            invoice_location = (
                str(config.ARIBA_INVOICE_DIR / "*InvoiceDetailsWDescription*.csv")
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
            buyerhtml = glob.glob(str(config.ARIBA_PO_DIR / "Purchase*.xls"))
            buyerdf = LoadFilesFromFolder(buyerhtml, "html")

            buyercsv = glob.glob(str(config.ARIBA_PO_DIR / "Purchase*.csv"))
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

            run.output += "AribaInvoices written to SQL | "
    except:
        run.output += "AribaInvoices failed to write to SQL" + error_function() + "|"
        run.failure = 1
    try:
        supplierdetailsxlsx = str(config.SUPPLIER_DIR)
        try:
            supplierdetailscreatedtoday = find_files_created_today(supplierdetailsxlsx)
        except:
            supplierdetailscreatedtoday = pd.DataFrame()
        if supplierdetailscreatedtoday.empty or len(supplierdetailscreatedtoday) == 0:
            run.output += "No New Supplier Files|"
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
            run.output += "Suppliers written to SQL | "
    except:
        run.output += "Suppliers failed to write to SQL" + error_function() + "|"
        run.failure = 1
    try:
        clf = load(config.ML_MODEL_FILE)
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
            run.output += "No new predictions"
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
            run.output += "Entered Predictions"
        run.result = "Success"
    except:
        run.output += "Failed at predictions" + error_function() + "|"
        run.failure = 1
        run.result = "Failure"


def main():
    with monitored_run(JOB_NAME, scriptinput="Scheduled Monthly") as run:
        run_load(run)
    print(run.output)


if __name__ == "__main__":
    main()
