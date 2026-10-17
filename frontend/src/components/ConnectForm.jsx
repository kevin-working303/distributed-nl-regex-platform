import { useState } from "react";
import { api } from "../api/client";

export default function ConnectForm({ onConnected }) {
  const [form, setForm] = useState({
    access_key: "",
    secret_key: "",
    bucket: "",
    region: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api.connect(form);
      onConnected(form);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card" onSubmit={submit}>
      <h2>1 · Connect to your S3 bucket</h2>
      <p className="muted">
        Your credentials are sent securely for this session only. They are never
        logged, stored in plaintext, or returned by the API.
      </p>
      <label>
        AWS Access Key
        <input value={form.access_key} onChange={update("access_key")} required
          autoComplete="off" />
      </label>
      <label>
        AWS Secret Key
        <input type="password" value={form.secret_key} onChange={update("secret_key")}
          required autoComplete="off" />
      </label>
      <label>
        Bucket name
        <input value={form.bucket} onChange={update("bucket")} required />
      </label>
      <label>
        Region <span className="muted">(optional)</span>
        <input value={form.region} onChange={update("region")} placeholder="us-east-1" />
      </label>
      {error && <div className="error">{error}</div>}
      <button type="submit" disabled={busy}>
        {busy ? "Connecting…" : "Connect"}
      </button>
    </form>
  );
}
