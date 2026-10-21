"""Spark transform correctness on a small DataFrame.

Exercises the real ``apply_transform`` for all three operations, asserting both
the transformed values and the distributed match counts. Skipped automatically
if PySpark/Java aren't available in the environment."""
import pytest

pyspark = pytest.importorskip("pyspark")

from pyspark.sql import SparkSession  # noqa: E402

from apps.processing.spark_engine import apply_transform  # noqa: E402


@pytest.fixture(scope="module")
def spark():
    s = (
        SparkSession.builder.appName("test")
        .master("local[1]")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield s
    s.stop()


def _df(spark):
    return spark.createDataFrame(
        [
            ("1", "John Doe", "john.doe@example.com"),
            ("2", "Jane Smith", "jane_smith@domain.com"),
            ("3", "Alice Brown", "alice.brown@website.org"),
            ("4", "No Email", "n/a"),
        ],
        ["ID", "Name", "Email"],
    )


def test_replace_emails(spark):
    spec = {
        "operation": "replace",
        "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b",
    }
    out, matches, rows = apply_transform(spark, _df(spark), spec, ["Email"], "REDACTED")
    vals = {r["ID"]: r["Email"] for r in out.collect()}
    assert vals["1"] == "REDACTED"
    assert vals["4"] == "n/a"
    assert matches == 3
    assert rows == 4


def test_extract_creates_column(spark):
    spec = {
        "operation": "extract",
        "pattern": r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+)",
    }
    out, matches, rows = apply_transform(spark, _df(spark), spec, ["Email"], "")
    assert "Email_extracted" in out.columns
    extracted = {r["ID"]: r["Email_extracted"] for r in out.collect()}
    assert extracted["1"].startswith("john.doe@")  # group 0 = full match
    assert matches == 3


def test_standardize_rules(spark):
    spec = {
        "operation": "standardize",
        "rules": [{"pattern": r"_", "replacement": "."}],
    }
    out, matches, rows = apply_transform(spark, _df(spark), spec, ["Email"], "")
    vals = {r["ID"]: r["Email"] for r in out.collect()}
    assert vals["2"] == "jane.smith@domain.com"  # underscore -> dot
    assert matches == 1  # only row 2 changed


def test_excel_ingestion_through_pipeline(spark):
    """Mirrors spark_engine.load_dataframe's Excel branch: pandas reads the
    .xlsx (dtype=str, like a real upload) and the result is converted to a
    Spark DataFrame, then run through the same apply_transform used for CSV."""
    pd = pytest.importorskip("pandas")
    import io

    source = pd.DataFrame(
        {
            "ID": ["1", "2", "3"],
            "Name": ["John Doe", "Jane Smith", "Alice Brown"],
            "Email": [
                "john.doe@example.com",
                "jane_smith@domain.com",
                "alice.brown@website.org",
            ],
        }
    )
    buf = io.BytesIO()
    source.to_excel(buf, index=False)
    buf.seek(0)

    pdf = pd.read_excel(buf, dtype=str).fillna("")
    df = spark.createDataFrame(pdf)

    spec = {
        "operation": "replace",
        "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b",
    }
    out, matches, rows = apply_transform(spark, df, spec, ["Email"], "REDACTED")
    vals = {r["ID"]: r["Email"] for r in out.collect()}
    assert vals == {"1": "REDACTED", "2": "REDACTED", "3": "REDACTED"}
    assert matches == 3
    assert rows == 3


def test_missing_column_raises(spark):
    spec = {"operation": "replace", "pattern": r"x"}
    with pytest.raises(ValueError):
        apply_transform(spark, _df(spark), spec, ["Nonexistent"], "y")
