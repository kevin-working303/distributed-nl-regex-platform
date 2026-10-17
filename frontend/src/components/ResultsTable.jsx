import { useEffect, useState } from "react";
import { api } from "../api/client";

const PAGE_SIZE = 25;

export default function ResultsTable({ jobId }) {
  const [page, setPage] = useState({ rows: [], columns: [], total: 0, offset: 0 });
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const res = await api.getResults(jobId, offset, PAGE_SIZE);
        if (active) setPage(res);
      } catch (err) {
        if (active) setError(err.message);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [jobId, offset]);

  const total = page.total || 0;
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + PAGE_SIZE, total);
  const hasPrev = offset > 0;
  const hasNext = end < total;

  return (
    <div className="card">
      <h2>Processed data</h2>
      {error && <div className="error">{error}</div>}
      {loading && <div className="muted">Loading page…</div>}
      {!loading && total === 0 && <div className="muted">No rows to display.</div>}
      {!loading && page.rows.length > 0 && (
        <>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>{page.columns.map((c) => <th key={c}>{c}</th>)}</tr>
              </thead>
              <tbody>
                {page.rows.map((row, i) => (
                  <tr key={i}>
                    {page.columns.map((c) => (
                      <td key={c} className="mono">{String(row[c] ?? "")}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pager">
            <button disabled={!hasPrev} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              ← Prev
            </button>
            <span className="muted">
              {start.toLocaleString()}–{end.toLocaleString()} of {total.toLocaleString()}
            </span>
            <button disabled={!hasNext} onClick={() => setOffset(offset + PAGE_SIZE)}>
              Next →
            </button>
          </div>
        </>
      )}
    </div>
  );
}
