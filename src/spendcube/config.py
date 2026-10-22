"""Central place for reading configuration from environment variables.

Read settings only through this module. Never print or log values; they may be secrets.
Real values live in `.env` (gitignored). Add every new variable to `.env.example` too.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Loads `.env` if present. Variables already set in the real environment win.
load_dotenv()


def get(name: str, default: str | None = None) -> str | None:
    """Return an optional setting, or `default` if it is unset or blank."""
    value = os.getenv(name)
    return value if value else default


def require(name: str) -> str:
    """Return a required setting, failing early with a clear message if missing."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name} (see .env.example)")
    return value


# --- Settings -------------------------------------------------------------
DATA_DIR = Path(get("DATA_DIR", "data"))
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
SAMPLE_DIR = DATA_DIR / "sample"
OUTPUTS_DIR = Path(get("OUTPUTS_DIR", "outputs"))

# Shared SharePoint libraries, synced locally. The roots are machine-specific (.env); the specific
# subfolders this project reads are listed below. Never scan a whole library: files are synced on
# demand, so listing or searching it downloads them.
_SHAREPOINT = Path.home() / "Boston University" / "Continuous Improvement & Data Analytics - Documents"
AUTOMATION_DIR = Path(get("CIDA_AUTOMATION_DIR", str(_SHAREPOINT / "Automation and Data")))
CIDA_PROJECTS_DIR = Path(get("CIDA_PROJECTS_DIR", str(_SHAREPOINT / "CIDA Projects")))

# Data can live anywhere (the DATA_DIR folders above, the libraries here, SQL Server, an API...).
# List every source folder this project reads, one line each, and document each in
# docs/data_dictionary.md. Name the specific folder; never point at a whole library. Examples:
#   SAP_PA0001_DIR = AUTOMATION_DIR / "SAP-PA0001"
#   PROJECT_DATA_DIR = CIDA_PROJECTS_DIR / "<area>" / "<project folder>" / "Data"

# SQL Server: one server and one login, shared with cida_toolkit monitoring (which reads the same
# CIDA_SQL_* variables itself). Optional here so modules that don't touch SQL still import; code
# that connects should call require() for what it needs.
SQL_SERVER = get("CIDA_SQL_SERVER")
SQL_USERNAME = get("CIDA_SQL_USERNAME")
SQL_PASSWORD = get("CIDA_SQL_PASSWORD")
SPENDCUBE_SQL_DATABASE = get("SPENDCUBE_SQL_DATABASE")

# One Asana token for monitoring and project use
ASANA_ACCESS_TOKEN = get("CIDA_ASANA_ACCESS_TOKEN")

# Uncomment what the project uses (and keep .env.example in sync):
# AWS_PROFILE = get("AWS_PROFILE")
# AWS_REGION = get("AWS_REGION")
