import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import PageHeader from "../components/PageHeader";
import Pager from "../components/Pager";
import TenderDates from "../components/TenderDates";

const PAGE_SIZE = 25;

/**
 * Everything a scrape brought in that nobody has kept yet.
 *
 * Scheduled runs store tenders without anyone having asked for them, so they
 * would otherwise sit in the database unseen. This is where they surface, and
 * where the ones worth keeping become a saved list.
 */
export default function Review() {
  const { can } = useAuth();
  const canSave = can("save_lists");
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [lists, setLists] = useState([]);
  const [sites, setSites] = useState([]);
  const [categories, setCategories] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [siteId, setSiteId] = useState("");
  const [page, setPage] = useState(1);
  const [picked, setPicked] = useState([]);
  const [target, setTarget] = useState(""); // "" = a new list

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    Promise.all([api.listSites(), api.listCategories(), api.listSearches()])
      .then(([s, c, l]) => {
        setSites(s);
        setCategories(c);
        setLists(l);
      })
      .catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setError("");
    try {
      setData(
        await api.listTenders({
          search: query,
          category_id: /^\d+$/.test(categoryId) ? categoryId : "",
          uncategorised:
            categoryId === "__uncategorised__"
              ? "only"
              : categoryId === "__all__"
                ? "include"
                : "exclude",
          site_id: siteId,
          scope: "unsaved",
          status: "all",
          sort: "created_at",
          order: "desc",
          page,
          page_size: PAGE_SIZE,
        })
      );
    } catch (err) {
      setError(err.message);
    }
  }, [query, categoryId, siteId, page]);

  useEffect(() => {
    load();
  }, [load]);

  async function selectAll() {
    try {
      // The list is paginated, so select all must mean everything matching
      // the filters rather than just the page on screen.
      const { tender_ids } = await api.tenderIds({
        search: query,
        category_id: /^\d+$/.test(categoryId) ? categoryId : "",
        uncategorised:
          categoryId === "__uncategorised__"
            ? "only"
            : categoryId === "__all__"
              ? "include"
              : "exclude",
        site_id: siteId,
        scope: "unsaved",
        status: "all",
      });
      setPicked(tender_ids);
    } catch (err) {
      setError(err.message);
    }
  }

  function toggle(id) {
    setPicked((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function keep() {
    setBusy(true);
    setError("");
    try {
      const saved = await api.keepTenders({
        tender_ids: picked,
        search_id: target ? Number(target) : null,
      });
      navigate(`/searches/${saved.id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  if (!data) return <p className="state">Loading…</p>;

  const allOnPage =
    data.items.length > 0 && data.items.every((t) => picked.includes(t.id));

  return (
    <>
      <PageHeader title="Review" count={data.total}>
        <input
          className="search mono"
          placeholder="Search titles…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
      </PageHeader>

      <p className="page-count mono" style={{ marginTop: "-14px", marginBottom: "14px" }}>
        Tenders found by scrapes that nobody has kept yet
      </p>

      {error && <p className="notice notice-error">{error}</p>}

      <div className="filters">
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

        {canSave && (
          <label className="check picker-all">
            <input
              type="checkbox"
              checked={allOnPage}
              onChange={() => (allOnPage ? setPicked([]) : selectAll())}
            />
            <span>Select all</span>
          </label>
        )}
      </div>

      <p className="result-count mono">
        {data.total} waiting
        {picked.length > 0 && ` · ${picked.length} selected`}
      </p>

      {data.total === 0 && (
        <p className="state">
          Nothing waiting. Tenders appear here after a scheduled scrape, or any
          search that turns up something you have not kept.
        </p>
      )}

      <div className="tender-list">
        {data.items.map((tender) => (
          <article
            className={`tender-row ${canSave ? "selectable" : ""}`}
            key={tender.id}
          >
            {canSave && (
              <label className="tender-pick">
                <input
                  type="checkbox"
                  checked={picked.includes(tender.id)}
                  onChange={() => toggle(tender.id)}
                  aria-label={`Select ${tender.title.slice(0, 40)}`}
                />
              </label>
            )}

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
                  <span className="badge badge-none">Uncategorised</span>
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
          </article>
        ))}
      </div>

      <Pager page={page} pages={data.pages} onChange={setPage} />

      {canSave && picked.length > 0 && (
        <div className="keep-bar">
          <div className="keep-target">
            <label className="mono">Keep in</label>
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">A new list</option>
              {lists.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name || `Saved list ${l.id}`} ({l.tender_count})
                </option>
              ))}
            </select>
          </div>

          <div className="keep-actions">
            <button className="btn btn-quiet" onClick={() => setPicked([])}>
              Clear selection
            </button>
            <button className="btn btn-primary" disabled={busy} onClick={keep}>
              {busy
                ? "Saving…"
                : `Save (${picked.length}) selected tender${picked.length === 1 ? "" : "s"}`}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
