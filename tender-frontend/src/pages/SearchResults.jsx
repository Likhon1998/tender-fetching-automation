import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import TenderDates from "../components/TenderDates";
import { useAuth } from "../auth/AuthContext";

const PAGE_SIZE = 25;

const SORT_OPTIONS = [
  { value: "date:desc", label: "Newest first" },
  { value: "date:asc", label: "Oldest first" },
  { value: "title:asc", label: "Title A–Z" },
  { value: "confidence:desc", label: "Best match first" },
];

export default function SearchResults() {
  const { can } = useAuth();
  const canTriage = can("triage_tenders");
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");

  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("date:desc");
  const [view, setView] = useState("new");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const t = setTimeout(() => { setQuery(searchInput); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  const load = useCallback(async () => {
    const [field, order] = sort.split(":");
    try {
      setData(await api.searchResults(id, {
        search: query, status: view, sort: field, order, page, page_size: PAGE_SIZE,
      }));
      setStatus("ready");
    } catch (err) {
      setError(err.message);
      setStatus("error");
    }
  }, [id, query, sort, view, page]);

  useEffect(() => { load(); }, [load]);

  async function setTenderStatus(tender, next) {
    setData((prev) => ({
      ...prev,
      items: prev.items.filter((t) => t.id !== tender.id),
      total: prev.total - 1,
    }));
    try {
      await api.setTenderStatus(tender.id, next);
    } catch (err) {
      setError(err.message);
      load();
    }
  }

  if (status === "loading") return <p className="state">Loading results…</p>;
  if (status === "error") return <p className="notice notice-error">{error}</p>;

  const { search } = data;

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Saved list #{search.id}</h1>
          <p className="page-count mono">
            {new Date(search.created_at).toLocaleString()} · {search.tender_count} tender
            {search.tender_count === 1 ? "" : "s"} · {search.site_names.length} site
            {search.site_names.length === 1 ? "" : "s"}
          </p>
        </div>
        <div className="page-actions">
          <div className="switch" role="group">
            <button className={view === "new" ? "on" : ""}
                    onClick={() => { setView("new"); setPage(1); }}>Active</button>
            <button className={view === "not_interested" ? "on" : ""}
                    onClick={() => { setView("not_interested"); setPage(1); }}>Dismissed</button>
          </div>
          <Link className="btn btn-quiet" to="/search">New search</Link>
        </div>
      </header>

      <div className="recap">
        <div>
          <span className="recap-key mono">Sites</span>
          <span>{search.site_names.join(", ")}</span>
        </div>
        <div>
          <span className="recap-key mono">Categories</span>
          <span>
            {search.category_names.join(", ") || "none"}
            {search.include_uncategorised && " · uncategorised included"}
          </span>
        </div>
      </div>

      <div className="filters">
        <input className="search" placeholder="Search titles…"
               value={searchInput} onChange={(e) => setSearchInput(e.target.value)} />
        <select value={sort} onChange={(e) => { setSort(e.target.value); setPage(1); }}>
          {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>

      {error && <p className="notice notice-error">{error}</p>}

      <p className="result-count mono">
        {data.total} {data.total === 1 ? "entry" : "entries"} shown
      </p>

      <div className="tender-list">
        {data.items.map((tender) => (
          <article className="tender-row" key={tender.id}>
            <span className="tender-id mono">№&nbsp;{String(tender.id).padStart(4, "0")}</span>
            <div className="tender-body">
              <h2 className="tender-title">
                {tender.pdf_link
                  ? <a href={tender.pdf_link} target="_blank" rel="noreferrer">{tender.title}</a>
                  : tender.title}
              </h2>
              <div className="tender-meta">
                {tender.category
                  ? <span className="badge">{tender.category}</span>
                  : <span className="badge badge-none">Uncategorised</span>}
                <span className="mono">{tender.source_name || "unknown source"}</span>
                <TenderDates tender={tender} />
                {tender.confidence !== null && (
                  <span className="mono tender-conf">
                    {Math.round(parseFloat(tender.confidence) * 100)}% match
                  </span>
                )}
                {tender.source_url && (
                  <a
                    className="mono tender-link"
                    href={tender.source_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View on site ↗
                  </a>
                )}
              </div>
            </div>
            {canTriage && (
              <button className="btn btn-quiet tender-action"
                      onClick={() => setTenderStatus(tender, view === "new" ? "not_interested" : "new")}>
                {view === "new" ? "Not interested" : "Restore"}
              </button>
            )}
          </article>
        ))}
      </div>

      {data.items.length === 0 && (
        <p className="state">
          {view === "new"
            ? "No tenders in this search match those filters."
            : "Nothing dismissed from this search."}
        </p>
      )}

      {data.pages > 1 && (
        <nav className="pager">
          <button className="btn btn-quiet" disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}>Previous</button>
          <span className="mono">Page {page} of {data.pages}</span>
          <button className="btn btn-quiet" disabled={page >= data.pages}
                  onClick={() => setPage((p) => p + 1)}>Next</button>
        </nav>
      )}
    </>
  );
}
