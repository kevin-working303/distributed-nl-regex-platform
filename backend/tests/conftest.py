"""Test configuration.

Force SQLite and an isolated results dir so the task/Spark layer can be tested
without Postgres/Redis/S3. Env vars are set before Django is configured.
"""
import os
import tempfile

os.environ.setdefault("USE_SQLITE", "1")
os.environ.setdefault("DJANGO_DEBUG", "1")
os.environ.setdefault("ANTHROPIC_API_KEY", "")  # force heuristic fallback in tests
os.environ.setdefault("RESULTS_DIR", os.path.join(tempfile.gettempdir(), "regex_test_results"))

os.makedirs(os.environ["RESULTS_DIR"], exist_ok=True)
