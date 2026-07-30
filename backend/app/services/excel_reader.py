"""
excel_reader.py
----------------
Reads an uploaded Excel/CSV file and produces a small SCHEMA SUMMARY (column names +
a few representative sample values per column) - this summary, not the raw file, is
what gets sent to the LLM. Full row data is parsed separately and stored as-is in
Postgres (master_rows), but the LLM never sees more than a handful of sample rows -
much cheaper and faster than sending every row, and plenty for it to infer meaning,
data type, and typical value shape from.
"""
import pandas as pd


def list_sheet_names(file_obj_or_path, filename: str) -> list:
    if not filename.lower().endswith((".xlsx", ".xls")):
        return []
    if hasattr(file_obj_or_path, "seek"):
        file_obj_or_path.seek(0)
    return pd.ExcelFile(file_obj_or_path).sheet_names


def _detect_header_row(raw: pd.DataFrame, max_rows_to_check: int = 10) -> int:
    """Finds which of the first few rows is the real header row, vs. a title/caption
    row above it (e.g. a sheet title or table name sitting alone in row 1, with the
    real headers a row or two below - exactly what a raw SAP table export looks like:
    a table-name row, then the real column headers). Ported from the sibling
    Header_Mapping project's schema_loader.py, which hit this same problem.

    Fill-count heuristic: the header row is the first row whose filled-cell count
    matches the max seen in the checked rows - a sparse title row above a full header
    row has fewer filled cells, so it's correctly skipped."""
    check_rows = min(max_rows_to_check, len(raw))
    if check_rows == 0:
        return 0
    fill_counts = [int(raw.iloc[i].notna().sum()) for i in range(check_rows)]
    max_fill = max(fill_counts)
    if max_fill <= 1:
        return 0  # every row has at most one filled cell - no reliable signal, just use row 0
    for i, count in enumerate(fill_counts):
        if count == max_fill:
            return i
    return 0


def read_file(file_obj_or_path, filename: str, sheet_name=0) -> pd.DataFrame:
    """Detects the real header row (see _detect_header_row) rather than always
    assuming row 0 - a raw SAP/ERP export commonly has a title/table-name row above
    the actual column headers, which would otherwise land every header as a blank
    'Unnamed: N' and silently corrupt every downstream column name."""
    if hasattr(file_obj_or_path, "seek"):
        file_obj_or_path.seek(0)
    lower = filename.lower()
    if lower.endswith(".csv"):
        # utf-8-sig strips a leading BOM from CSVs exported by Excel/Windows tools.
        raw = pd.read_csv(file_obj_or_path, header=None, encoding="utf-8-sig")
    else:
        raw = pd.read_excel(file_obj_or_path, sheet_name=sheet_name, header=None)
    header_row = _detect_header_row(raw)
    df = raw.iloc[header_row + 1:].reset_index(drop=True)
    df.columns = raw.iloc[header_row]
    df.columns = [str(c).strip() for c in df.columns]
    return df


def build_schema_summary(df: pd.DataFrame, n_samples: int = 5, max_sample_len: int = 60) -> dict:
    """The ONLY thing that gets sent to the LLM for classification/metadata generation -
    never the full dataframe. For each column: its name, up to n_samples distinct
    non-null example values (truncated), and a null-count ratio (a cheap, useful signal
    for "mandatory vs optional" that doesn't need the LLM to guess)."""
    columns = []
    for col in df.columns:
        series = df[col]
        non_null = series.dropna()
        samples = []
        seen = set()
        for v in non_null.tolist():
            sv = str(v).strip()
            if not sv or sv in seen:
                continue
            samples.append(sv[:max_sample_len])
            seen.add(sv)
            if len(samples) >= n_samples:
                break
        columns.append({
            "column_name": col,
            "sample_values": samples,
            "null_ratio": round(1 - (len(non_null) / len(series)), 3) if len(series) else 0.0,
            "distinct_count": int(series.nunique(dropna=True)),
        })
    return {
        "columns": columns,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
    }
