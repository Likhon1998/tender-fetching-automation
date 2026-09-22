import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import PageHeader from "../components/PageHeader";

/** Shows the signed-in user what their account is allowed to do. */
export default function Profile() {
  const { user, capabilities } = useAuth();
  const [catalogue, setCatalogue] = useState([]);

  useEffect(() => {
    api.listCapabilities().then(setCatalogue).catch(() => setCatalogue([]));
  }, []);

  return (
    <>
      <PageHeader title="Your account" />

      <div className="panel">
        <div className="panel-head">
          <h2>{user?.full_name}</h2>
          <span className="mono">{user?.username}</span>
        </div>
        <p className="row-sub mono">{user?.email}</p>
      </div>

      <ChangePassword />

      <div className="panel" style={{ marginTop: "12px" }}>
        <div className="panel-head">
          <h2>What you can do</h2>
          <span className="mono">
            {capabilities.length} of {catalogue.length}
          </span>
        </div>

        <ul className="caps-list">
          {catalogue.map((cap) => {
            const held = capabilities.includes(cap.key);
            return (
              <li key={cap.key} className={held ? "held" : "not-held"}>
                <span className="caps-mark" aria-hidden="true">
                  {held ? "✓" : "—"}
                </span>
                <span>
                  <strong>{cap.key.replace(/_/g, " ")}</strong>
                  <small>{cap.description}</small>
                </span>
              </li>
            );
          })}
        </ul>

        <p className="hint">
          Permissions are set by an administrator. Ask them if you need
          something you do not have.
        </p>
      </div>
    </>
  );
}

function ChangePassword() {
  const [form, setForm] = useState({
    current_password: "",
    new_password: "",
    confirm_password: "",
  });
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  function update(field) {
    return (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    setDone(false);

    if (form.new_password !== form.confirm_password) {
      setError("The two new passwords do not match.");
      return;
    }

    setBusy(true);
    try {
      await api.changePassword(form);
      setForm({ current_password: "", new_password: "", confirm_password: "" });
      setDone(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel" style={{ marginTop: "12px" }}>
      <div className="panel-head">
        <h2>Change your password</h2>
      </div>

      <form onSubmit={submit}>
        {error && <p className="notice notice-error">{error}</p>}
        {done && <p className="notice notice-undo">Your password has been changed.</p>}

        <label className="field">
          <span>Current password</span>
          <input
            type="password"
            value={form.current_password}
            onChange={update("current_password")}
            autoComplete="current-password"
            required
          />
        </label>

        <label className="field">
          <span>New password</span>
          <input
            type="password"
            value={form.new_password}
            onChange={update("new_password")}
            autoComplete="new-password"
            required
          />
          <small>At least 12 characters, with a letter and a number.</small>
        </label>

        <label className="field">
          <span>Confirm new password</span>
          <input
            type="password"
            value={form.confirm_password}
            onChange={update("confirm_password")}
            autoComplete="new-password"
            required
          />
        </label>

        <div className="dialog-foot">
          <button className="btn btn-primary" disabled={busy}>
            {busy ? "Saving…" : "Change password"}
          </button>
        </div>
      </form>
    </div>
  );
}
