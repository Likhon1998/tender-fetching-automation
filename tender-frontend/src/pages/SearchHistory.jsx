import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";

export default function SearchHistory() {
  const [searches, setSearches] = useState([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");

  async function remove(search) {
    if (!window.confirm(`Delete search #${search.id}? The tenders it found stay in the registry.`)) return;
    try {
      await api.deleteSearch(search.id);
      setSearches((prev) => prev.filter((s) => s.id !== search.id));
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    api.listSearches()
      .then((rows) => { setSearches(rows); setStatus("ready"); })
      .catch((err) => { setError(err.message); setStatus("error"); });
  }, []);

  if (status === "loading") return <p className="state">Loading…</p>;
  if (status === "error") return <p className="notice notice-error">{error}</p>;

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Saved lists</h1>
          <p className="page-count mono">
            {searches.length} saved {searches.length === 1 ? "list" : "lists"}
          </p>
        </div>
        <div className="page-actions">
          <Link className="btn btn-primary" to="/search">New search</Link>
        </div>
      </header>

      {searches.length === 0 && (
        <p className="state">
          No saved lists yet. Run a search, tick the tenders worth keeping,
          and they will appear here.
        </p>
      )}

      <div className="tender-list">
        {searches.map((s) => (
          <article className="tender-row history-row" key={s.id}>
            <span className="tender-id mono">#{s.id}</span>
            <div className="tender-body">
              <h2 className="tender-title">
                <Link to={`/searches/${s.id}`}>
                  {s.tender_count} tender{s.tender_count === 1 ? "" : "s"}
                </Link>
              </h2>
              <div className="tender-meta">
                <span className="mono">{new Date(s.created_at).toLocaleString()}</span>
                <span className="mono">{s.created_by_username || "unknown"}</span>
              </div>
              <p className="history-detail">
                <span className="recap-key mono">Sites</span>{" "}
                {s.site_names.length > 4
                  ? `${s.site_names.slice(0, 4).join(", ")} and ${s.site_names.length - 4} more`
                  : s.site_names.join(", ")}
              </p>
              <p className="history-detail">
                <span className="recap-key mono">Categories</span>{" "}
                {s.category_names.join(", ") || "none"}
                {s.include_uncategorised && " · uncategorised"}
              </p>
            </div>
            <div className="cell-actions tender-action">
              <Link className="btn btn-quiet" to={`/searches/${s.id}`}>
                Show tenders
              </Link>
              <button className="btn btn-danger" onClick={() => remove(s)}>
                Delete
              </button>
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
