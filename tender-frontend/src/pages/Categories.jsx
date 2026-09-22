import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Modal from "../components/Modal";
import PageHeader from "../components/PageHeader";
import Pager from "../components/Pager";

const BLANK = { name: "", description: "", keywords: [] };
const PER_PAGE = 10;

export default function Categories() {
  const { can } = useAuth();
  const canManage = can("manage_categories");
  const [categories, setCategories] = useState([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(null);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  // Keywords are long lists, so a row shows them only when asked.
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      setCategories(await api.listCategories());
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
    if (!needle) return categories;
    return categories.filter(
      (c) =>
        c.name.toLowerCase().includes(needle) ||
        c.keywords.some((k) => k.includes(needle))
    );
  }, [categories, query]);

  const pages = Math.max(1, Math.ceil(matching.length / PER_PAGE));
  useEffect(() => {
    if (page > pages) setPage(1);
  }, [page, pages]);
  const visible = matching.slice((page - 1) * PER_PAGE, page * PER_PAGE);

  async function handleDelete(category) {
    if (!window.confirm(`Delete ${category.name}? This cannot be undone.`)) return;
    try {
      await api.deleteCategory(category.id);
      setCategories((prev) => prev.filter((c) => c.id !== category.id));
    } catch (err) {
      setError(err.message);
    }
  }

  if (status === "loading") return <p className="state">Loading categories…</p>;
  if (status === "error") return <p className="notice notice-error">{error}</p>;

  return (
    <>
      <PageHeader title="Categories" count={categories.length}>
        <input
          className="search mono"
          placeholder="Filter by name or keyword"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(1);
          }}
        />
        {canManage && (
          <button className="btn btn-primary" onClick={() => setEditing(BLANK)}>
            Add category
          </button>
        )}
      </PageHeader>

      {error && <p className="notice notice-error">{error}</p>}

      <div className="rows">
        {visible.map((category) => (
          <article className="row-item" key={category.id}>
            <div className="row-main">
              <div className="row-text">
                <h2>{category.name}</h2>
                <p className="row-sub mono">
                  {category.keywords.length} keyword
                  {category.keywords.length === 1 ? "" : "s"}
                  {category.description ? ` · ${category.description}` : ""}
                </p>
              </div>

              <div className="cell-actions">
                <button
                  className="btn btn-quiet"
                  aria-expanded={expanded === category.id}
                  onClick={() =>
                    setExpanded(expanded === category.id ? null : category.id)
                  }
                >
                  {expanded === category.id ? "Hide" : "Keywords"}
                </button>
                {canManage && (
                  <>
                    <button className="btn btn-quiet" onClick={() => setEditing(category)}>
                      Edit
                    </button>
                    <button className="btn btn-danger" onClick={() => handleDelete(category)}>
                      Delete
                    </button>
                  </>
                )}
              </div>
            </div>

            {expanded === category.id && (
              <div className="row-detail">
                <ul className="chips">
                  {category.keywords.length === 0 && (
                    <li className="chip chip-empty">No keywords yet</li>
                  )}
                  {category.keywords.map((keyword) => (
                    <li className="chip mono" key={keyword}>
                      {keyword}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </article>
        ))}
      </div>

      {matching.length === 0 && <p className="state">No categories match that filter.</p>}

      <Pager page={page} pages={pages} onChange={setPage} />

      {editing && (
        <CategoryForm
          category={editing}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setCategories((prev) => {
              const exists = prev.some((c) => c.id === saved.id);
              return exists
                ? prev.map((c) => (c.id === saved.id ? saved : c))
                : [...prev, saved].sort((a, b) => a.name.localeCompare(b.name));
            });
            setEditing(null);
          }}
        />
      )}
    </>
  );
}

function CategoryForm({ category, onClose, onSaved }) {
  const isNew = !category.id;
  const [form, setForm] = useState({
    name: category.name || "",
    description: category.description || "",
    keywords: (category.keywords || []).join(", "),
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
      description: form.description.trim() || null,
      keywords: form.keywords.split(",").map((k) => k.trim()).filter(Boolean),
    };

    try {
      const saved = isNew
        ? await api.createCategory(payload)
        : await api.updateCategory(category.id, payload);
      onSaved(saved);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  const keywordCount = form.keywords.split(",").filter((k) => k.trim()).length;

  return (
    <Modal title={isNew ? "Add category" : `Edit ${category.name}`} onClose={onClose}>
      <form onSubmit={handleSubmit}>
        {error && <p className="notice notice-error">{error}</p>}

        <label className="field">
          <span>Name</span>
          <input value={form.name} onChange={(e) => update("name", e.target.value)} required />
        </label>

        <label className="field">
          <span>Description</span>
          <textarea
            rows={2}
            value={form.description}
            onChange={(e) => update("description", e.target.value)}
          />
        </label>

        <label className="field">
          <span>Keywords</span>
          <textarea
            className="mono"
            rows={8}
            value={form.keywords}
            onChange={(e) => update("keywords", e.target.value)}
            placeholder="firewall, network security, ngfw"
          />
          <small>
            Separate with commas. {keywordCount} keyword{keywordCount === 1 ? "" : "s"}.
            Matching a tender title against these decides its category.
          </small>
        </label>

        <div className="dialog-foot">
          <button type="button" className="btn btn-quiet" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={busy}>
            {busy ? "Saving…" : isNew ? "Add category" : "Save changes"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
