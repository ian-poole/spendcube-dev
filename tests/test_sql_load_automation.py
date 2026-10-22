import pandas as pd
import pytest

from cida_toolkit import run as toolkit_run
from spendcube import config, sql_load_automation as job


def test_assign_values_prefers_first_classified_value():
    row = {"a": "Unclassified", "b": "WBS-1", "c": "CC-9"}
    assert job.assign_values(row, "a", "b", "c") == "WBS-1"
    assert job.assign_values({"a": "IO-1", "b": "x", "c": "y"}, "a", "b", "c") == "IO-1"
    assert job.assign_values({"a": "Unclassified", "b": "Unclassified", "c": "CC-9"}, "a", "b", "c") == "CC-9"


def test_column_cleaning_keeps_pre_0_3_names():
    cleaned = job.columnreplaceforsqlload(pd.DataFrame(columns=["G/L Account", "G/L Acct Long Text"]))
    assert list(cleaned.columns) == ["g/l_account", "g/l_acct_long_text"]


def test_main_logs_one_monitored_run(tmp_path, monkeypatch):
    # An automation library with no new files: every source reports "No New ..." and the run is logged.
    gl = pd.DataFrame(
        {"G/L Account": ["1"], "G/L Acct Long Text": ["x"], "Chart of Accounts": ["0010"]}
    )
    gl_file = tmp_path / "GL_EXPORT.XLSX"
    gl.to_excel(gl_file, index=False)
    supplier_dir = tmp_path / "suppliers"
    supplier_dir.mkdir()
    pd.DataFrame({"Supplier ID": ["1"], "Line of Business": ["x"]}).to_excel(
        supplier_dir / "Suppliers SandP test.xlsx", index=False
    )
    monkeypatch.setattr(config, "GL_EXPORT_FILE", gl_file)
    monkeypatch.setattr(config, "SUPPLIER_DIR", supplier_dir)
    for name in ("DISBURSEMENT_DIR", "BOA_PCARD_DIR", "CONCUR_ENTRIES_DIR", "ARIBA_INVOICE_DIR"):
        monkeypatch.setattr(config, name, tmp_path / "missing" / name)
    for var in ("CIDA_SQL_SERVER", "SPENDCUBE_SQL_DATABASE", "CIDA_SQL_USERNAME", "CIDA_SQL_PASSWORD"):
        monkeypatch.setenv(var, "test")
    monkeypatch.setattr(config, "ML_MODEL_FILE", tmp_path / "missing" / "model.joblib")
    monkeypatch.setattr(job, "make_engine", lambda *a, **k: object())

    logged = []
    monkeypatch.setattr(toolkit_run, "scriptmonitoring", lambda **kw: logged.append(kw))

    job.main()

    assert len(logged) == 1
    assert logged[0]["script"] == job.JOB_NAME
    assert "No New Disbursement Files" in logged[0]["scriptoutput"]
