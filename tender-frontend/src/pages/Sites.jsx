import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Modal from "../components/Modal";
import PageHeader from "../components/PageHeader";
import Pager from "../components/Pager";

const BLANK = { name: "", url: "", strategy: "", active: true };
const PER_PAGE = 10;

export default function Sites() {
  const { can } = useAuth();
  const canManage = can("manage_sites");
  const [sites, setSites] = useState([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(null);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      setSites(await api.listSites());
      setStatus("ready");
    } catch (err) {
      setError(err.message);
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const matching = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return sites;
    return sites.filter(
      (s) =>
        s.name.toLowerCase().includes(needle) ||
        s.url.toLowerCase().includes(needle) ||
        (s.strategy || "").toLowerCase().includes(needle)
    );
  }, [sites, query]);

  const pages = Math.max(1, Math.ceil(matching.length / PER_PAGE));
  useEffect(() => {
    if (page > pages) setPage(1);
  }, [page, pages]);
  const visible = matching.slice((page - 1) * PER_PAGE, page * PER_PAGE);

  async function handleDelete(site) {
    if (!window.confirm(`Delete ${site.name}? This cannot be undone.`)) return;
    try {
      await api.deleteSite(site.id);
      setSites((prev) => prev.filter((s) => s.id !== site.id));
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleToggle(site) {
    try {
      const updated = await api.updateSite(site.id, { active: !site.active });
      setSites((prev) => prev.map((s) => (s.id === site.id ? updated : s)));
    } catch (err) {
      setError(err.message);
    }
  }

  if (status === "loading") return <p className="state">Loading sites…</p>;
  if (status === "error") return <p className="notice notice-error">{error}</p>;

  return (
    <>
      <PageHeader title="Sites" count={sites.length}>
        <input
          className="search mono"
          placeholder="Filter by name, URL or strategy"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(1);
          }}
        />
        {canManage && (
          <button className="btn btn-primary" onClick={() => setEditing(BLANK)}>
            Add site
          </button>
        )}
      </PageHeader>

      {error && <p className="notice notice-error">{error}</p>}

      <div className="rows">
        {visible.map((site) => (
          <article
            className={`row-item ${site.active ? "" : "row-paused"}`}
            key={site.id}
          >
            <div className="row-main">
              <div className="row-text">
                <h2>
                  <span className={`dot ${site.active ? "dot-on" : "dot-off"}`} />
                  {site.name}
                </h2>
                <p className="row-sub mono">
                  <a href={site.url} target="_blank" rel="noreferrer">
                    {site.url.replace(/^https?:\/\//, "")}
                  </a>
                </p>
                <p className="row-sub mono">
                  {site.strategy || "no strategy"} ·{" "}
                  {site.last_scraped_at
                    ? `scraped ${new Date(site.last_scraped_at).toLocaleDateString()}`
                    : "never scraped"}
                </p>
                {site.last_scrape_error && (
                  <p className="row-error">{site.last_scrape_error}</p>
                )}
              </div>

              {canManage && (
                <div className="cell-actions">
                  <button className="btn btn-quiet" onClick={() => handleToggle(site)}>
                    {site.active ? "Pause" : "Resume"}
                  </button>
                  <button className="btn btn-quiet" onClick={() => setEditing(site)}>
                    Edit
                  </button>
                  <button className="btn btn-danger" onClick={() => handleDelete(site)}>
                    Delete
                  </button>
                </div>
              )}
            </div>
          </article>
        ))}
      </div>

      {matching.length === 0 && <p className="state">No sites match that filter.</p>}

      <Pager page={page} pages={pages} onChange={setPage} />

      {editing && (
        <SiteForm
          site={editing}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setSites((prev) => {
              const exists = prev.some((s) => s.id === saved.id);
              return exists
                ? prev.map((s) => (s.id === saved.id ? saved : s))
                : [...prev, saved].sort((a, b) => a.name.localeCompare(b.name));
            });
            setEditing(null);
          }}
        />
      )}
    </>
  );
}

function SiteForm({ site, onClose, onSaved }) {
  const isNew = !site.id;
  const [form, setForm] = useState({
    name: site.name || "",
    url: site.url || "",
    strategy: site.strategy || "",
    active: site.active ?? true,
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function update(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setBusy(true);

    const payload = {
      name: form.name.trim(),
      url: form.url.trim(),
      strategy: form.strategy.trim() || null,
      active: form.active,
    };

    try {
      const saved = isNew
        ? await api.createSite(payload)
        : await api.updateSite(site.id, payload);
      onSaved(saved);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Modal title={isNew ? "Add site" : `Edit ${site.name}`} onClose={onClose}>
      <form onSubmit={handleSubmit}>
        {error && <p className="notice notice-error">{error}</p>}

        <label className="field">
          <span>Name</span>
          <input value={form.name} onChange={(e) => update("name", e.target.value)} required />
        </label>

        <label className="field">
          <span>URL</span>
          <input
            className="mono"
            type="url"
            value={form.url}
            onChange={(e) => update("url", e.target.value)}
            required
          />
        </label>

        <label className="field">
          <span>Parsing strategy</span>
          <input
            className="mono"
            value={form.strategy}
            onChange={(e) => update("strategy", e.target.value)}
            placeholder="data-column, positional, gp-cards…"
          />
          <small>Which parser handles this site's HTML. Leave blank if unknown.</small>
        </label>

        <label className="check">
          <input
            type="checkbox"
            checked={form.active}
            onChange={(e) => update("active", e.target.checked)}
          />
          <span>Include this site when scraping</span>
        </label>

        <div className="dialog-foot">
          <button type="button" className="btn btn-quiet" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={busy}>
            {busy ? "Saving…" : isNew ? "Add site" : "Save changes"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
