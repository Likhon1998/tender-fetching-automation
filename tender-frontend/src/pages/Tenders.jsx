import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import TenderDates from "../components/TenderDates";
import { useAuth } from "../auth/AuthContext";

const PAGE_SIZE = 25;

// Each option maps to a sort column and direction the API understands.
const SORT_OPTIONS = [
  { value: "date:desc", label: "Newest first" },
  { value: "submission_date:asc", label: "Deadline soonest" },
  { value: "date:asc", label: "Oldest first" },
  { value: "title:asc", label: "Title A–Z" },
  { value: "confidence:desc", label: "Best match first" },
  { value: "created_at:desc", label: "Recently added" },
];

export default function Tenders() {
  const { can } = useAuth();
  const canTriage = can("triage_tenders");
  const [tenders, setTenders] = useState([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [summary, setSummary] = useState(null);

  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [undo, setUndo] = useState(null); // { id, title } after dismissing

  const [categories, setCategories] = useState([]);
  const [sites, setSites] = useState([]);

  // Filter state
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  // "" = every category, "__uncategorised__" = only the ones with none,
  // "__all__" = both. Anything else is a real category id.
  const [categoryId, setCategoryId] = useState("");
  const [siteId, setSiteId] = useState("");
  const [sort, setSort] = useState("date:desc");
  const [view, setView] = useState("new"); // "new" | "not_interested"
  // The registry shows tenders kept in a list. Everything scraped is still
  // stored, and "scope=all" reveals it, which is how you check what the
  // classifier is rejecting.
  const [scope, setScope] = useState("saved");
  // Empty means no deadline filter at all. Selecting a window also hides
  // notices whose deadline is unknown, since they cannot be placed in one.
  const [submissionWithin, setSubmissionWithin] = useState("");
  const [page, setPage] = useState(1);

  const firstLoad = useRef(true);

  // Debounce the search box so we do not fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Filter dropdown contents only need fetching once.
  useEffect(() => {
    Promise.all([api.listCategories(), api.listSites()])
      .then(([c, s]) => {
        setCategories(c);
        setSites(s);
      })
      .catch(() => {
        /* filters stay empty; the list itself still works */
      });
  }, []);

  const load = useCallback(async () => {
    if (!firstLoad.current) setStatus("refreshing");
    setError("");

    const [sortField, sortOrder] = sort.split(":");
    try {
      const [data, counts] = await Promise.all([
        api.listTenders({
          search,
          category_id: /^\d+$/.test(categoryId) ? categoryId : "",
          uncategorised:
            categoryId === "__uncategorised__"
              ? "only"
              : categoryId === "__all__"
                ? "include"
                : "exclude",
          site_id: siteId,
          status: view,
          scope,
          submission_within: submissionWithin,
          sort: sortField,
          order: sortOrder,
          page,
          page_size: PAGE_SIZE,
        }),
        api.tenderSummary(scope),
      ]);
      setTenders(data.items);
      setTotal(data.total);
      setPages(data.pages);
      setSummary(counts);
      setStatus("ready");
    } catch (err) {
      setError(err.message);
      setStatus("error");
    } finally {
      firstLoad.current = false;
    }
  }, [search, categoryId, siteId, sort, view, scope, submissionWithin, page]);

  useEffect(() => {
    load();
  }, [load]);

  async function dismiss(tender) {
    // Remove it straight away; the request is small and the row reappearing
    // on failure is clearer than a spinner on every button.
    setTenders((prev) => prev.filter((t) => t.id !== tender.id));
    setTotal((n) => n - 1);
    try {
      await api.setTenderStatus(tender.id, "not_interested");
      setUndo({ id: tender.id, title: tender.title });
    } catch (err) {
      setError(err.message);
      load();
    }
  }

  async function restore(tender) {
    setTenders((prev) => prev.filter((t) => t.id !== tender.id));
    setTotal((n) => n - 1);
    try {
      await api.setTenderStatus(tender.id, "new");
    } catch (err) {
      setError(err.message);
      load();
    }
  }

  async function undoDismiss() {
    if (!undo) return;
    try {
      await api.setTenderStatus(undo.id, "new");
      setUndo(null);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  function resetFilters() {
    setSearchInput("");
    setCategoryId("");
    setSiteId("");
    setSubmissionWithin("");
    setSort("date:desc");
    setPage(1);
  }

  const filtersActive = search || categoryId || siteId || submissionWithin;

  if (status === "loading") return <p className="state">Loading tenders…</p>;

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Saved tenders</h1>
          {summary && (
            <p className="page-count mono">
              {summary.by_status?.new ?? 0} active
              {summary.by_status?.not_interested
                ? ` · ${summary.by_status.not_interested} dismissed`
                : ""}
              {summary.unclassified
                ? ` · ${summary.unclassified} unclassified`
                : ""}
            </p>
          )}
        </div>

        <div className="page-actions">
          <div className="switch" role="group" aria-label="View">
            <button
              className={view === "new" ? "on" : ""}
              onClick={() => {
                setView("new");
                setPage(1);
              }}
            >
              Active
            </button>
            <button
              className={view === "not_interested" ? "on" : ""}
              onClick={() => {
                setView("not_interested");
                setPage(1);
              }}
            >
              Dismissed
            </button>
          </div>
        </div>
      </header>

      <div className="filters">
        <input
          className="search"
          placeholder="Search titles…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />

        <select
          value={categoryId}
          onChange={(e) => {
            setCategoryId(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All categories</option>
          <option value="__all__">All, including uncategorised</option>
          <option value="__uncategorised__">Uncategorised only</option>
          <optgroup label="Categories">
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </optgroup>
        </select>

        <select
          value={siteId}
          onChange={(e) => {
            setSiteId(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All sources</option>
          {sites.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>

        <select
          value={submissionWithin}
          onChange={(e) => {
            setSubmissionWithin(e.target.value);
            setPage(1);
          }}
          aria-label="Submission within"
        >
          <option value="">Any deadline</option>
          <option value="1">Submission within 1 week</option>
          <option value="2">Submission within 2 weeks</option>
          <option value="3">Submission within 3 weeks</option>
          <option value="4">Submission within 4 weeks</option>
          <option value="4plus">Submission in 4 weeks+</option>
        </select>

        <select
          value={scope}
          onChange={(e) => {
            setScope(e.target.value);
            setPage(1);
          }}
        >
          <option value="saved">Saved lists only</option>
          <option value="all">Everything scraped</option>
        </select>

        <select
          value={sort}
          onChange={(e) => {
            setSort(e.target.value);
            setPage(1);
          }}
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        {filtersActive && (
          <button className="btn btn-quiet" onClick={resetFilters}>
            Clear
          </button>
        )}
      </div>

      {error && <p className="notice notice-error">{error}</p>}

      {undo && view === "new" && (
        <p className="notice notice-undo">
          <span>Dismissed “{undo.title.slice(0, 60)}…”</span>
          <button className="btn btn-quiet" onClick={undoDismiss}>
            Undo
          </button>
        </p>
      )}

      <p className="result-count mono">
        {total} {total === 1 ? "entry" : "entries"} shown
        {status === "refreshing" && " · updating…"}
      </p>

      <div className="tender-list">
        {tenders.map((tender) => (
          <article className="tender-row" key={tender.id}>
            <span className="tender-id mono">
              №&nbsp;{String(tender.id).padStart(4, "0")}
            </span>

            <div className="tender-body">
              <h2 className="tender-title">
                {tender.pdf_link ? (
                  <a href={tender.pdf_link} target="_blank" rel="noreferrer">
                    {tender.title}
                  </a>
                ) : (
                  tender.title
                )}
              </h2>

              <div className="tender-meta">
                {tender.category ? (
                  <span className="badge">{tender.category}</span>
                ) : (
                  <span className="badge badge-none">Unclassified</span>
                )}
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

            {canTriage &&
              (view === "new" ? (
                <button className="btn btn-quiet tender-action" onClick={() => dismiss(tender)}>
                  Not interested
                </button>
              ) : (
                <button className="btn btn-quiet tender-action" onClick={() => restore(tender)}>
                  Restore
                </button>
              ))}
          </article>
        ))}
      </div>

      {tenders.length === 0 && (
        <p className="state">
          {submissionWithin
            ? "No saved tenders have a deadline in that window. Many notices do not state one."
            : filtersActive
            ? "No tenders match those filters."
            : view === "new"
              ? scope === "saved"
                ? "Nothing saved yet. Run a search and save the tenders worth keeping."
                : "No tenders yet. Run a search to fetch some."
              : "Nothing has been dismissed."}
        </p>
      )}

      {pages > 1 && (
        <nav className="pager">
          <button
            className="btn btn-quiet"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </button>
          <span className="mono">
            Page {page} of {pages}
          </span>
          <button
            className="btn btn-quiet"
            disabled={page >= pages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
        </nav>
      )}
    </>
  );
}
