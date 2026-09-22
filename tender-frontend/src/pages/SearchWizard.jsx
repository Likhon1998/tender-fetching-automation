import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import SelectionList from "../components/SelectionList";
import TenderDates from "../components/TenderDates";
import WizardProgress from "../components/WizardProgress";

const POLL_MS = 1500;
const PAGE_SIZE = 25;

export default function SearchWizard() {
  const navigate = useNavigate();

  const [stage, setStage] = useState("sites");
  const [sites, setSites] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [selectedSites, setSelectedSites] = useState([]);
  const [selectedCategories, setSelectedCategories] = useState([]);
  const [includeUncategorised, setIncludeUncategorised] = useState(false);

  const [search, setSearch] = useState(null);
  const pollTimer = useRef(null);

  useEffect(() => {
    Promise.all([api.listSites(), api.listCategories()])
      .then(([s, c]) => {
        // Paused sites are never scraped, so offering them would mislead.
        setSites(s.filter((site) => site.active));
        setCategories(c);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => () => clearTimeout(pollTimer.current), []);

  const poll = useCallback(async (id) => {
    try {
      const current = await api.getSearch(id);
      setSearch(current);
      if (current.status === "pending" || current.status === "running") {
        pollTimer.current = setTimeout(() => poll(id), POLL_MS);
      }
    } catch (err) {
      setError(err.message);
    }
  }, []);

  async function startSearch() {
    setError("");
    try {
      const created = await api.createSearch({
        site_ids: selectedSites,
        category_ids: selectedCategories,
        include_uncategorised: includeUncategorised,
      });
      setSearch(created);
      setStage("fetch");
      poll(created.id);
    } catch (err) {
      setError(err.message);
    }
  }

  function restart() {
    clearTimeout(pollTimer.current);
    setSearch(null);
    setSelectedSites([]);
    setSelectedCategories([]);
    setIncludeUncategorised(false);
    setStage("sites");
  }

  if (loading) return <p className="state">Loading…</p>;

  return (
    <>
      <header className="page-head">
        <div>
          <h1>New search</h1>
          <p className="page-count mono">
            Choose sites, then categories, then fetch.
          </p>
        </div>
        <div className="page-actions">
          <button className="btn btn-quiet" onClick={() => navigate("/searches")}>
            Saved lists
          </button>
        </div>
      </header>

      <WizardProgress
        current={stage}
        onJumpTo={search ? undefined : (key) => setStage(key)}
      />

      {error && <p className="notice notice-error">{error}</p>}

      {stage === "sites" && (
        <section className="panel">
          <div className="panel-head">
            <h2>Which sites should we search?</h2>
            <span className="mono">
              {selectedSites.length} of {sites.length} selected
            </span>
          </div>

          <SelectionList
            items={sites}
            selected={selectedSites}
            onChange={setSelectedSites}
            getLabel={(s) => s.name}
            getSubLabel={(s) => s.url.replace(/^https?:\/\//, "").slice(0, 44)}
            searchPlaceholder="Filter sites…"
            emptyMessage="No sites match that filter."
          />

          <div className="panel-foot">
            <span className="mono hint">
              {selectedSites.length === 0
                ? "Select at least one site to continue."
                : "\u00a0"}
            </span>
            <button
              className="btn btn-primary"
              disabled={selectedSites.length === 0}
              onClick={() => setStage("categories")}
            >
              Next
            </button>
          </div>
        </section>
      )}

      {stage === "categories" && (
        <section className="panel">
          <div className="panel-head">
            <h2>Which categories are you interested in?</h2>
            <span className="mono">
              {selectedCategories.length} of {categories.length} selected
            </span>
          </div>

          <SelectionList
            items={categories}
            selected={selectedCategories}
            onChange={setSelectedCategories}
            getLabel={(c) => c.name}
            getSubLabel={(c) => `${c.keywords.length} keywords`}
            renderDetail={(c) => (
              <ul className="chips">
                {c.keywords.slice(0, 60).map((k) => (
                  <li className="chip mono" key={k}>{k}</li>
                ))}
                {c.keywords.length > 60 && (
                  <li className="chip chip-empty">
                    and {c.keywords.length - 60} more
                  </li>
                )}
              </ul>
            )}
            searchPlaceholder="Filter categories…"
            emptyMessage="No categories match that filter."
          />

          <label className="check panel-extra">
            <input
              type="checkbox"
              checked={includeUncategorised}
              onChange={(e) => setIncludeUncategorised(e.target.checked)}
            />
            <span>
              Also include uncategorised notices
              <small>
                Notices the classifier could not place, often ones titled only
                with a reference number.
              </small>
            </span>
          </label>

          <div className="panel-foot">
            <button className="btn btn-quiet" onClick={() => setStage("sites")}>
              Back
            </button>
            <button
              className="btn btn-primary"
              disabled={selectedCategories.length === 0 && !includeUncategorised}
              onClick={startSearch}
            >
              Fetch tenders
            </button>
          </div>
        </section>
      )}

      {stage === "fetch" && search && (
        <FetchStage search={search} onRestart={restart} navigate={navigate} />
      )}
    </>
  );
}

function FetchStage({ search, onRestart, navigate }) {
  const running = search.status === "pending" || search.status === "running";
  const pct = search.sites_total
    ? Math.round((search.sites_done / search.sites_total) * 100)
    : 0;

  if (running) {
    return (
      <section className="panel">
        <div className="panel-head">
          <h2>Fetching tenders…</h2>
          <span className="mono">
            {search.sites_done} of {search.sites_total} sites
          </span>
        </div>

        <div className="bar" role="progressbar" aria-valuenow={pct}>
          <div className="bar-fill" style={{ width: `${Math.max(pct, 3)}%` }} />
        </div>

        <p className="mono hint">
          {search.current_site
            ? `Last finished: ${search.current_site}`
            : "Starting…"}
        </p>
        <p className="hint">
          Each site is fetched now, so this takes a few minutes. You can leave
          this page, but the results are only kept once you save them.
        </p>

        <div className="panel-foot">
          <button className="btn btn-quiet" onClick={onRestart}>
            Cancel
          </button>
        </div>
      </section>
    );
  }

  if (search.status === "failed") {
    return (
      <section className="panel">
        <div className="panel-head">
          <h2>Search failed</h2>
        </div>
        <p className="notice notice-error">{search.error}</p>
        <div className="panel-foot">
          <button className="btn btn-quiet" onClick={onRestart}>
            Start over
          </button>
        </div>
      </section>
    );
  }

  return <ResultsStage search={search} onRestart={onRestart} navigate={navigate} />;
}

function ResultsStage({ search, onRestart, navigate }) {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [picked, setPicked] = useState([]);
  // Tenders already kept in another list. They are shown, but cannot be
  // saved again: the same notice in two lists carries no new information.
  const [alreadySaved, setAlreadySaved] = useState([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .searchResults(search.id, { page, page_size: PAGE_SIZE, status: "all" })
      .then((body) => {
        setData(body);
        setAlreadySaved(body.already_saved || []);
      })
      .catch((err) => setError(err.message));
  }, [search.id, page]);

  async function selectAll() {
    try {
      // Results are paginated, so "select all" has to mean the whole set.
      // The endpoint leaves out anything already saved elsewhere.
      const { tender_ids } = await api.searchTenderIds(search.id);
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

  async function save() {
    setSaving(true);
    setError("");
    try {
      const saved = await api.saveSelection(search.id, picked);
      navigate(`/searches/${saved.id}`);
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  if (error) return <p className="notice notice-error">{error}</p>;
  if (!data) return <p className="state">Loading results…</p>;

  const selectableOnPage = data.items.filter((t) => !alreadySaved.includes(t.id));
  const allPicked = selectableOnPage.length > 0 &&
    selectableOnPage.every((t) => picked.includes(t.id));

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>{data.total} tender{data.total === 1 ? "" : "s"} found</h2>
        <label className="check picker-all">
          <input
            type="checkbox"
            checked={allPicked}
            onChange={() => (allPicked ? setPicked([]) : selectAll())}
          />
          <span>Select all</span>
        </label>
      </div>

      {data.total === 0 && (
        <p className="hint">
          Nothing matched. Those sites may have published no notices in the
          chosen categories.
        </p>
      )}

      <div className="tender-list">
        {data.items.map((tender) => {
          const saved = alreadySaved.includes(tender.id);
          return (
            <article
              className={`tender-row selectable ${saved ? "row-saved" : ""}`}
              key={tender.id}
            >
              <label className="tender-pick">
                <input
                  type="checkbox"
                  checked={picked.includes(tender.id)}
                  disabled={saved}
                  onChange={() => toggle(tender.id)}
                  aria-label={`Select ${tender.title.slice(0, 40)}`}
                />
              </label>

              <div className="tender-body">
                <h3 className="tender-title">
                  {tender.pdf_link ? (
                    <a href={tender.pdf_link} target="_blank" rel="noreferrer">
                      {tender.title}
                    </a>
                  ) : (
                    tender.title
                  )}
                </h3>
                <div className="tender-meta">
                  {saved && <span className="badge badge-saved">Already saved</span>}
                  {tender.category ? (
                    <span className="badge">{tender.category}</span>
                  ) : (
                    <span className="badge badge-none">Uncategorised</span>
                  )}
                  <span className="mono">{tender.source_name}</span>
                  <TenderDates tender={tender} />
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
          );
        })}
      </div>

      {data.pages > 1 && (
        <nav className="pager">
          <button
            className="btn btn-quiet"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </button>
          <span className="mono">
            Page {page} of {data.pages}
          </span>
          <button
            className="btn btn-quiet"
            disabled={page >= data.pages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
        </nav>
      )}

      <div className="panel-foot">
        <button className="btn btn-quiet" onClick={onRestart}>
          Start over
        </button>
        <button
          className="btn btn-primary"
          disabled={saving || picked.length === 0}
          onClick={save}
        >
          {saving
            ? "Saving…"
            : `Save (${picked.length}) selected tender${picked.length === 1 ? "" : "s"}`}
        </button>
      </div>
    </section>
  );
}
