import { useEffect, useState } from "react";
import { api } from "../api/client";

function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

export default function FileBrowser({ creds, onSelect, onBack }) {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const res = await api.listFiles(creds);
        if (active) setFiles(res.files);
      } catch (err) {
        if (active) setError(err.message);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [creds]);

  return (
    <div className="card">
      <h2>2 · Choose a file</h2>
      <p className="muted">
        Connected to <strong>{creds.bucket}</strong>.
        <button className="link" onClick={onBack}>change</button>
      </p>
      {loading && <div className="muted">Loading files…</div>}
      {error && <div className="error">{error}</div>}
      {!loading && !error && files.length === 0 && (
        <div className="muted">No CSV or Excel files found in this bucket.</div>
      )}
      {files.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>File</th>
              <th>Type</th>
              <th>Size</th>
              <th>Modified</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {files.map((f) => (
              <tr key={f.key}>
                <td className="mono">{f.key}</td>
                <td>{f.type}</td>
                <td>{fmtSize(f.size)}</td>
                <td className="muted">{new Date(f.last_modified).toLocaleString()}</td>
                <td>
                  <button onClick={() => onSelect(f)}>Select</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
