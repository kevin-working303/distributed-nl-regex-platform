import { useEffect, useState } from "react";
import { api } from "../api/client";

const OPERATIONS = [
  {
    value: "replace",
    label: "Replace",
    hint: "Find matches and replace them with a value (e.g. redact emails).",
  },
  {
    value: "extract",
    label: "Extract",
    hint: "Pull matched text into a new column (e.g. extract the domain).",
  },
  {
    value: "standardize",
    label: "Standardize",
    hint: "Normalize a column using LLM-derived rules (e.g. unify date formats).",
  },
];

export default function JobConfig({ creds, file, onSubmitted, onBack }) {
  const [columns, setColumns] = useState([]);
  const [loadingCols, setLoadingCols] = useState(true);
  const [operation, setOperation] = useState("replace");
  const [description, setDescription] = useState("");
  const [replacement, setReplacement] = useState("REDACTED");
  const [selectedCols, setSelectedCols] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      setLoadingCols(true);
      setError("");
      try {
        const res = await api.getColumns(creds, file.key);
        if (active) setColumns(res.columns);
      } catch (err) {
        if (active) setError(err.message);
      } finally {
        if (active) setLoadingCols(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [creds, file]);

  const toggleCol = (c) =>
    setSelectedCols((prev) =>
      prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]
    );

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (selectedCols.length === 0) {
      setError("Select at least one target column.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.submitJob({
        ...creds,
        file_key: file.key,
        operation,
        description,
        replacement: operation === "replace" ? replacement : "",
        target_columns: selectedCols,
      });
      onSubmitted(res.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const op = OPERATIONS.find((o) => o.value === operation);

  return (
    <form className="card" onSubmit={submit}>
      <h2>3 · Describe the transformation</h2>
      <p className="muted">
        File: <span className="mono">{file.key}</span>
        <button className="link" type="button" onClick={onBack}>change</button>
      </p>

      <label>
        Operation
        <select value={operation} onChange={(e) => setOperation(e.target.value)}>
          {OPERATIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </label>
      <p className="muted small">{op.hint}</p>

      <label>
        Describe the pattern in natural language
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="e.g. Find email addresses"
          required
          rows={2}
        />
      </label>

      {operation === "replace" && (
        <label>
          Replacement value
          <input value={replacement} onChange={(e) => setReplacement(e.target.value)} />
        </label>
      )}

      <div className="field">
        <span className="field-label">Target column(s)</span>
        {loadingCols && <div className="muted">Reading columns…</div>}
        {!loadingCols && columns.length === 0 && (
          <div className="muted">No columns detected.</div>
        )}
        <div className="chips">
          {columns.map((c) => (
            <button
              type="button"
              key={c}
              className={`chip ${selectedCols.includes(c) ? "chip-on" : ""}`}
              onClick={() => toggleCol(c)}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      <button type="submit" disabled={busy || loadingCols}>
        {busy ? "Submitting…" : "Run job"}
      </button>
    </form>
  );
}
