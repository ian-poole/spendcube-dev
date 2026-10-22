# Data dictionary

_Keep this current. It is the main file to upload to a Claude Project._

Record each data source once, then its columns. Sources can be files (Excel/CSV), databases,
APIs, Power BI connections, or anything else; delete what doesn't apply.

**Naming:** `source_name` is the column exactly as it appears in the source.
`snake_case_name` is the cleaned version used when working with the data; use snake_case
when possible.

## Source: <name>
- **Type:** file | database | API | Power BI connection | other
- **Location:** path, host/schema, or connection name (never credentials or secrets)
- **Access:** how it is read, and whether read-only
- **Owner / contact:**
- **Grain:** one row per ...
- **Primary key:**
- **Notes:** refresh cadence, known quirks

| source_name | snake_case_name | type | description | notes |
|-------------|-----------------|------|-------------|-------|
|             |                 |      |             |       |

## Business definitions
- **Term:** definition used in this project
