import { useState } from "react";
import ConnectForm from "./components/ConnectForm";
import FileBrowser from "./components/FileBrowser";
import JobConfig from "./components/JobConfig";
import JobProgress from "./components/JobProgress";

// Simple step machine: connect → browse → configure → monitor.
export default function App() {
  const [creds, setCreds] = useState(null);
  const [file, setFile] = useState(null);
  const [jobId, setJobId] = useState(null);

  const reset = () => {
    setFile(null);
    setJobId(null);
  };

  return (
    <div className="app">
      <header>
        <h1>Distributed NL-to-Regex Data Processor</h1>
        <p className="muted">
          Connect to your S3 bucket, describe a pattern in plain English, and
          transform millions of rows with Spark — asynchronously.
        </p>
      </header>

      {!creds && <ConnectForm onConnected={setCreds} />}

      {creds && !file && (
        <FileBrowser
          creds={creds}
          onSelect={setFile}
          onBack={() => {
            setCreds(null);
            reset();
          }}
        />
      )}

      {creds && file && !jobId && (
        <JobConfig
          creds={creds}
          file={file}
          onSubmitted={setJobId}
          onBack={() => setFile(null)}
        />
      )}

      {jobId && <JobProgress jobId={jobId} onReset={reset} />}

      <footer className="muted small">
        Django · Celery · Redis · PySpark · React — credentials are never stored
        in plaintext.
      </footer>
    </div>
  );
}
