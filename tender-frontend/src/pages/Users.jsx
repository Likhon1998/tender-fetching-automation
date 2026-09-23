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
  capabilities: ["search_tenders", "save_lists", "triage_tenders"],
};

const PRESETS = [
  {
    id: "staff",
    label: "Staff",
    hint: "Search, save lists, triage tenders",
    capabilities: ["search_tenders", "save_lists", "triage_tenders"],
  },
  {
    id: "manager",
    label: "Manager",
    hint: "Staff plus sites, categories, schedules",
    capabilities: [
      "search_tenders",
      "save_lists",
      "triage_tenders",
      "manage_sites",
      "manage_categories",
      "manage_schedules",
    ],
  },
  {
    id: "admin",
    label: "Admin",
    hint: "Full access, including creating accounts",
    capabilities: [
      "search_tenders",
      "save_lists",
      "triage_tenders",
      "manage_sites",
      "manage_categories",
      "manage_schedules",
      "manage_users",
      "run_admin_tasks",
    ],
  },
];

function generatePassword() {
  const letters = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ";
  const digits = "23456789";
  let out = "";
  for (let i = 0; i < 6; i += 1) {
    out += letters[Math.floor(Math.random() * letters.length)];
  }
  out += digits[Math.floor(Math.random() * digits.length)];
  out += letters[Math.floor(Math.random() * letters.length)];
  return out;
}

export default function Users() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [catalogue, setCatalogue] = useState([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(null);
  const [createdCreds, setCreatedCreds] = useState(null);
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
        <button
          className="btn btn-primary"
          onClick={() => setEditing({ ...BLANK, password: "", confirm_password: "" })}
        >
          Create account
        </button>
      </PageHeader>

      <p className="page-lead">
        Create an account for someone, choose what they can do, then share the
        username and password so they can sign in. There is no self-registration.
      </p>

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
          onSaved={(saved, plainPassword) => {
            setUsers((prev) => {
              const exists = prev.some((u) => u.id === saved.id);
              return exists
                ? prev.map((u) => (u.id === saved.id ? saved : u))
                : [saved, ...prev];
            });
            setEditing(null);
            if (plainPassword) {
              setCreatedCreds({
                username: saved.username,
                email: saved.email,
                password: plainPassword,
                full_name: saved.full_name,
              });
            }
          }}
        />
      )}

      {createdCreds && (
        <CredentialsShare
          creds={createdCreds}
          onClose={() => setCreatedCreds(null)}
        />
      )}
    </>
  );
}

function CredentialsShare({ creds, onClose }) {
  const [copied, setCopied] = useState(false);
  const shareText = [
    `Sign in to Tender Registry`,
    `Name: ${creds.full_name}`,
    `Username: ${creds.username}`,
    `Email: ${creds.email}`,
    `Password: ${creds.password}`,
    ``,
    `Open the app and sign in with the username (or email) and this password.`,
  ].join("\n");

  async function copyAll() {
    try {
      await navigator.clipboard.writeText(shareText);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <Modal title="Account ready — share these details" onClose={onClose}>
      <p className="notice notice-ok">
        {creds.full_name} can now sign in. Copy the details below and send them
        privately. The password is shown only once here.
      </p>

      <dl className="cred-box">
        <div>
          <dt>Username</dt>
          <dd className="mono">{creds.username}</dd>
        </div>
        <div>
          <dt>Email</dt>
          <dd className="mono">{creds.email}</dd>
        </div>
        <div>
          <dt>Password</dt>
          <dd className="mono">{creds.password}</dd>
        </div>
      </dl>

      <div className="dialog-foot">
        <button type="button" className="btn btn-quiet" onClick={onClose}>
          Done
        </button>
        <button type="button" className="btn btn-primary" onClick={copyAll}>
          {copied ? "Copied" : "Copy login details"}
        </button>
      </div>
    </Modal>
  );
}

function UserForm({ user, catalogue, onClose, onSaved }) {
  const isNew = !user.id;
  const [form, setForm] = useState({
    username: user.username || "",
    full_name: user.full_name || "",
    email: user.email || "",
    password: user.password || "",
    confirm_password: user.confirm_password || "",
    capabilities: user.capabilities || [],
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function update(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function applyPreset(capabilities) {
    setForm((prev) => ({ ...prev, capabilities: [...capabilities] }));
  }

  function toggleCapability(key) {
    setForm((prev) => ({
      ...prev,
      capabilities: prev.capabilities.includes(key)
        ? prev.capabilities.filter((c) => c !== key)
        : [...prev.capabilities, key],
    }));
  }

  function fillGeneratedPassword() {
    const password = generatePassword();
    setForm((prev) => ({ ...prev, password, confirm_password: password }));
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
        onSaved(saved, form.password);
      } else {
        const payload = {
          full_name: form.full_name,
          email: form.email,
          capabilities: form.capabilities,
        };
        if (form.password) payload.password = form.password;
        saved = await api.updateUser(user.id, payload);
        onSaved(saved, null);
      }
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Modal
      title={isNew ? "Create account for someone" : `Edit ${user.username}`}
      onClose={onClose}
    >
      <form onSubmit={handleSubmit}>
        {error && <p className="notice notice-error">{error}</p>}

        {isNew && (
          <p className="form-intro">
            Fill in their details and choose access. After you create the
            account, you will get a password to share so they can sign in.
          </p>
        )}

        {isNew && (
          <label className="field">
            <span>Username</span>
            <input
              className="mono"
              value={form.username}
              onChange={(e) => update("username", e.target.value)}
              placeholder="e.g. rifat"
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
          <div className="field-row">
            <input
              type="text"
              className="mono"
              value={form.password}
              onChange={(e) => update("password", e.target.value)}
              required={isNew}
              autoComplete="new-password"
            />
            {isNew && (
              <button
                type="button"
                className="btn btn-quiet"
                onClick={fillGeneratedPassword}
              >
                Generate
              </button>
            )}
          </div>
          <small>
            {isNew
              ? "At least 8 characters. Share this with them."
              : "Leave blank to keep the current password."}
          </small>
        </label>

        <label className="field">
          <span>Confirm password</span>
          <input
            type="text"
            className="mono"
            value={form.confirm_password}
            onChange={(e) => update("confirm_password", e.target.value)}
            required={isNew}
            autoComplete="new-password"
          />
        </label>

        <fieldset className="caps">
          <legend>What this account can do</legend>
          {isNew && (
            <div className="preset-row">
              {PRESETS.map((preset) => (
                <button
                  type="button"
                  key={preset.id}
                  className={`btn btn-tiny ${
                    JSON.stringify(form.capabilities) ===
                    JSON.stringify(preset.capabilities)
                      ? "btn-primary"
                      : "btn-quiet"
                  }`}
                  title={preset.hint}
                  onClick={() => applyPreset(preset.capabilities)}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          )}
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
            {busy ? "Saving…" : isNew ? "Create account" : "Save changes"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
