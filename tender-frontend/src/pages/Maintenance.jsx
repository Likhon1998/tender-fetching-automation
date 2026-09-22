import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import PageHeader from "../components/PageHeader";

/**
 * Admin actions that had no home in the interface: re-running classification,
 * starting a scrape by hand, and clearing collected data.
 */
export default function Maintenance() {
  const [counts, setCounts] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");

  const loadCounts = useCallback(async () => {
    try {
      setCounts(await api.clearPreview());
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    loadCounts();
  }, [loadCounts]);

  async function run(key, action) {
    setBusy(key);
    setError("");
    setNotice("");
    try {
      setNotice(await action());
      await loadCounts();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  function reclassify() {
    return run("reclassify", async () => {
      const r = await api.reclassify();
      return (
        `Re-scored ${r.examined} tender${r.examined === 1 ? "" : "s"} against ` +
        `${r.keywords_in_use} keywords. ${r.newly_classified} newly matched, ` +
        `${r.newly_unclassified} no longer match, ${r.unclassified} still unmatched.`
      );
    });
  }

  function scrape() {
    return run("scrape", async () => {
      await api.startIngest();
      return (
        "Scrape started in the background. It visits every active site and " +
        "takes several minutes. Progress shows on the Sites page as each " +
        "site's last scraped time updates."
      );
    });
  }

  function clear(scope) {
    return run(`clear-${scope}`, async () => {
      const r = await api.clearData(scope);
      return scope === "everything"
        ? `Removed ${r.lists_removed} saved list(s) and ${r.tenders_removed} tender(s).`
        : `Removed ${r.lists_removed} saved list(s). ${r.tenders_kept} tender(s) kept.`;
    });
  }

  return (
    <>
      <PageHeader title="Maintenance" />

      {error && <p className="notice notice-error">{error}</p>}
      {notice && <p className="notice notice-undo">{notice}</p>}

      <section className="panel">
        <div className="panel-head">
          <h2>Re-run classification</h2>
        </div>
        <p className="hint">
          Applies the current category keywords to every stored tender. Use it
          after editing keywords: notices that previously matched nothing can
          be picked up without scraping the sites again.
        </p>
        <div className="panel-foot">
          <button
            className="btn btn-primary"
            disabled={Boolean(busy)}
            onClick={reclassify}
          >
            {busy === "reclassify" ? "Working…" : "Re-run classification"}
          </button>
        </div>
      </section>

      <section className="panel" style={{ marginTop: "12px" }}>
        <div className="panel-head">
          <h2>Scrape every site</h2>
        </div>
        <p className="hint">
          Fetches all active sites in the background. Searches already scrape
          the sites they cover, so this is mainly for filling the database
          ahead of time or checking that the parsers still work.
        </p>
        <div className="panel-foot">
          <button
            className="btn btn-primary"
            disabled={Boolean(busy)}
            onClick={scrape}
          >
            {busy === "scrape" ? "Starting…" : "Start scrape"}
          </button>
        </div>
      </section>

      <ClearPanel counts={counts} busy={busy} onClear={clear} />
    </>
  );
}

function ClearPanel({ counts, busy, onClear }) {
  const [scope, setScope] = useState("lists");
  const [typed, setTyped] = useState("");

  const confirmed = typed.trim().toUpperCase() === "CLEAR";

  return (
    <section className="panel panel-danger" style={{ marginTop: "12px" }}>
      <div className="panel-head">
        <h2>Clear collected data</h2>
        {counts && (
          <span className="mono">
            {counts.saved_lists} list{counts.saved_lists === 1 ? "" : "s"} ·{" "}
            {counts.stored_tenders} tender
            {counts.stored_tenders === 1 ? "" : "s"}
          </span>
        )}
      </div>

      <p className="hint">
        Users, sites and categories are never removed, so the tool keeps
        working afterwards. This cannot be undone.
      </p>

      <label className="check panel-extra">
        <input
          type="radio"
          name="clear-scope"
          checked={scope === "lists"}
          onChange={() => setScope("lists")}
        />
        <span>
          Saved lists only
          <small>
            Empties Saved tenders. The tenders stay in the database and remain
            visible under "Everything scraped", so nothing needs re-scraping.
          </small>
        </span>
      </label>

      <label className="check panel-extra">
        <input
          type="radio"
          name="clear-scope"
          checked={scope === "everything"}
          onChange={() => setScope("everything")}
        />
        <span>
          Saved lists and every stored tender
          <small>
            A clean slate. The next search scrapes from nothing, which takes
            several minutes across all sites.
          </small>
        </span>
      </label>

      <label className="field" style={{ marginTop: "16px" }}>
        <span>Type CLEAR to confirm</span>
        <input
          className="mono"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder="CLEAR"
          autoComplete="off"
        />
      </label>

      <div className="panel-foot">
        <button
          className="btn btn-danger-solid"
          disabled={!confirmed || Boolean(busy)}
          onClick={async () => {
            await onClear(scope);
            setTyped("");
          }}
        >
          {busy.startsWith("clear")
            ? "Clearing…"
            : scope === "everything"
              ? "Clear everything"
              : "Clear saved lists"}
        </button>
      </div>
    </section>
  );
}
