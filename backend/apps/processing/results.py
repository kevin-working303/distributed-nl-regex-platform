"""Read processed results back in pages.

Results are written to ``RESULTS_DIR/<job_id>/`` as Parquet by the Spark job.
This module reads a specific row range out of that dataset using pyarrow, so the
web process can serve pagination WITHOUT importing Spark and WITHOUT loading
millions of rows into memory — it streams record batches and stops once the
requested window is filled.
"""
from __future__ import annotations

import os

from django.conf import settings

MAX_PAGE_SIZE = 500


def result_dir(job_id: str) -> str:
    return os.path.join(settings.RESULTS_DIR, str(job_id))


def result_exists(job_id: str) -> bool:
    d = result_dir(job_id)
    return os.path.isdir(d) and any(f.endswith(".parquet") for f in os.listdir(d))


def read_page(job_id: str, offset: int = 0, limit: int = 50) -> dict:
    """Return a page of rows: {rows, columns, offset, limit, total}."""
    import pyarrow.dataset as ds

    limit = max(1, min(limit, MAX_PAGE_SIZE))
    offset = max(0, offset)

    dataset = ds.dataset(result_dir(job_id), format="parquet")
    columns = [f.name for f in dataset.schema]
    total = dataset.count_rows()

    rows: list[dict] = []
    seen = 0
    # Stream batches; skip until we reach `offset`, then collect `limit` rows.
    for batch in dataset.to_batches(batch_size=max(limit, 1024)):
        n = batch.num_rows
        if seen + n <= offset:
            seen += n
            continue
        start = max(0, offset - seen)
        pydict = batch.slice(start).to_pylist()
        for row in pydict:
            rows.append(row)
            if len(rows) >= limit:
                break
        seen += n
        if len(rows) >= limit:
            break

    return {
        "rows": rows,
        "columns": columns,
        "offset": offset,
        "limit": limit,
        "total": total,
    }
