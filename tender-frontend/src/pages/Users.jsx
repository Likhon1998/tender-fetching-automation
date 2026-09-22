import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Modal from "../components/Modal";
import PageHeader from "../components/PageHeader";
import Pager from "../components/Pager";

const PER_PAGE = 10;
const BLANK = {
  username: "",
  full_name: "",
  email: "",
  password: "",
  confirm_password: "",
  capabilities: [],
};

export default function Users() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [catalogue, setCatalogue] = useState([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(null);
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    try {
      const [rows, caps] = await Promise.all([
        api.listUsers(),
        api.listCapabilities(),
      ]);
      setUsers(rows);
      setCatalogue(caps);
      setStatus("ready");
    } catch (err) {
      setError(err.message);
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const pages = Math.max(1, Math.ceil(users.length / PER_PAGE));
  const visible = users.slice((page - 1) * PER_PAGE, page * PER_PAGE);

  async function remove(target) {
    if (!window.confirm(`Delete ${target.username}? This cannot be undone.`)) return;
    try {
      await api.deleteUser(target.id);
      setUsers((prev) => prev.filter((u) => u.id !== target.id));
    } catch (err) {
      setError(err.message);
    }
  }

  async function toggleStatus(target) {
    const next = target.status === "active" ? "disabled" : "active";
    try {
      const updated = await api.updateUser(target.id, { status: next });
      setUsers((prev) => prev.map((u) => (u.id === target.id ? updated : u)));
    } catch (err) {
      setError(err.message);
    }
  }

  if (status === "loading") return <p className="state">Loading users…</p>;
  if (status === "error") return <p className="notice notice-error">{error}</p>;

  return (
    <>
      <PageHeader title="Users" count={users.length}>
        <button className="btn btn-primary" onClick={() => setEditing(BLANK)}>
          Add user
        </button>
      </PageHeader>

      {error && <p className="notice notice-error">{error}</p>}

      <div className="rows">
        {visible.map((row) => (
          <article
            className={`row-item ${row.status === "active" ? "" : "row-paused"}`}
            key={row.id}
          >
            <div className="row-main">
              <div className="row-text">
                <h2>
                  <span
                    className={`dot ${row.status === "active" ? "dot-on" : "dot-off"}`}
                  />
                  {row.full_name}
                  {row.id === me?.id && <span className="tag tag-you">you</span>}
                </h2>
                <p className="row-sub mono">
                  {row.username} · {row.email}
                </p>
                <ul className="chips chips-tight">
                  {row.capabilities.length === 0 && (
                    <li className="chip chip-empty">No permissions</li>
                  )}
                  {row.capabilities.map((c) => (
                    <li className="chip mono" key={c}>
                      {c.replace(/_/g, " ")}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="cell-actions">
                <button className="btn btn-quiet" onClick={() => toggleStatus(row)}>
                  {row.status === "active" ? "Disable" : "Enable"}
                </button>
                <button className="btn btn-quiet" onClick={() => setEditing(row)}>
                  Edit
                </button>
                {row.id !== me?.id && (
                  <button className="btn btn-danger" onClick={() => remove(row)}>
                    Delete
                  </button>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>

      <Pager page={page} pages={pages} onChange={setPage} />

      {editing && (
        <UserForm
          user={editing}
          catalogue={catalogue}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setUsers((prev) => {
              const exists = prev.some((u) => u.id === saved.id);
              return exists
                ? prev.map((u) => (u.id === saved.id ? saved : u))
                : [saved, ...prev];
            });
            setEditing(null);
          }}
        />
      )}
    </>
  );
}

function UserForm({ user, catalogue, onClose, onSaved }) {
  const isNew = !user.id;
  const [form, setForm] = useState({
    username: user.username || "",
    full_name: user.full_name || "",
    email: user.email || "",
    password: "",
    confirm_password: "",
    capabilities: user.capabilities || [],
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function update(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function toggleCapability(key) {
    setForm((prev) => ({
      ...prev,
      capabilities: prev.capabilities.includes(key)
        ? prev.capabilities.filter((c) => c !== key)
        : [...prev.capabilities, key],
    }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    if (form.password !== form.confirm_password) {
      setError("The two passwords do not match.");
      return;
    }
    if (isNew && !form.password) {
      setError("Set a password for the new account.");
      return;
    }

    setBusy(true);
    try {
      let saved;
      if (isNew) {
        saved = await api.createUser(form);
      } else {
        // Only send what changed; an empty password field means "leave it".
        const payload = {
          full_name: form.full_name,
          email: form.email,
          capabilities: form.capabilities,
        };
        if (form.password) payload.password = form.password;
        saved = await api.updateUser(user.id, payload);
      }
      onSaved(saved);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Modal
      title={isNew ? "Add user" : `Edit ${user.username}`}
      onClose={onClose}
    >
      <form onSubmit={handleSubmit}>
        {error && <p className="notice notice-error">{error}</p>}

        {isNew && (
          <label className="field">
            <span>Username</span>
            <input
              className="mono"
              value={form.username}
              onChange={(e) => update("username", e.target.value)}
              required
            />
          </label>
        )}

        <label className="field">
          <span>Full name</span>
          <input
            value={form.full_name}
            onChange={(e) => update("full_name", e.target.value)}
            required
          />
        </label>

        <label className="field">
          <span>Email</span>
          <input
            className="mono"
            type="email"
            value={form.email}
            onChange={(e) => update("email", e.target.value)}
            required
          />
        </label>

        <label className="field">
          <span>{isNew ? "Password" : "New password"}</span>
          <input
            type="password"
            value={form.password}
            onChange={(e) => update("password", e.target.value)}
            required={isNew}
          />
          <small>
            {isNew
              ? "At least 12 characters, with a letter and a number."
              : "Leave blank to keep the current password."}
          </small>
        </label>

        <label className="field">
          <span>Confirm password</span>
          <input
            type="password"
            value={form.confirm_password}
            onChange={(e) => update("confirm_password", e.target.value)}
            required={isNew}
          />
        </label>

        <fieldset className="caps">
          <legend>What this account can do</legend>
          {catalogue.map((cap) => (
            <label className="check cap-row" key={cap.key}>
              <input
                type="checkbox"
                checked={form.capabilities.includes(cap.key)}
                onChange={() => toggleCapability(cap.key)}
              />
              <span>
                {cap.key.replace(/_/g, " ")}
                <small>{cap.description}</small>
              </span>
            </label>
          ))}
        </fieldset>

        <div className="dialog-foot">
          <button type="button" className="btn btn-quiet" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={busy}>
            {busy ? "Saving…" : isNew ? "Create user" : "Save changes"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
