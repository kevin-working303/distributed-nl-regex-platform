"""Pagination reads a precise row window out of a multi-batch Parquet dataset
without loading the whole thing."""
import os

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from django.conf import settings

from apps.processing import results as rr


@pytest.fixture
def written_result():
    job_id = "test-job-pagination"
    out = os.path.join(settings.RESULTS_DIR, job_id)
    os.makedirs(out, exist_ok=True)
    # 250 rows split across two parquet files.
    for part in range(2):
        start = part * 125
        table = pa.table(
            {
                "id": list(range(start, start + 125)),
                "value": [f"v{i}" for i in range(start, start + 125)],
            }
        )
        pq.write_table(table, os.path.join(out, f"part-{part}.parquet"))
    yield job_id


def test_result_exists(written_result):
    assert rr.result_exists(written_result)


def test_total_and_columns(written_result):
    page = rr.read_page(written_result, offset=0, limit=10)
    assert page["total"] == 250
    assert set(page["columns"]) == {"id", "value"}


def test_first_page(written_result):
    page = rr.read_page(written_result, offset=0, limit=10)
    assert len(page["rows"]) == 10
    assert page["rows"][0]["id"] == 0


def test_offset_page(written_result):
    page = rr.read_page(written_result, offset=200, limit=10)
    assert len(page["rows"]) == 10
    assert page["rows"][0]["id"] == 200


def test_page_size_capped(written_result):
    page = rr.read_page(written_result, offset=0, limit=99999)
    assert page["limit"] <= rr.MAX_PAGE_SIZE
