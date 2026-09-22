import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import PageHeader from "../components/PageHeader";
import Pager from "../components/Pager";

const PER_PAGE = 8;

const FREQUENCIES = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "biweekly", label: "Every two weeks" },
  { value: "monthly", label: "Monthly" },
  { value: "custom", label: "Every N days" },
];

function describe(group) {
  const at = group.run_at.slice(0, 5);
  switch (group.frequency) {
    case "daily":
      return `Every day at ${at}`;
    case "weekly":
      return `Every week at ${at}`;
    case "biweekly":
      return `Every two weeks at ${at}`;
    case "monthly":
      return `Every month at ${at}`;
    case "custom":
      return `Every ${group.interval_days} days at ${at}`;
    default:
      return at;
  }
}

function whenNext(iso) {
  if (!iso) return "not scheduled";
  const target = new Date(iso);
  const hours = Math.round((target - new Date()) / 3600000);
  const stamp = target.toLocaleString([], {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
  if (hours < 0) return `${stamp} (due)`;
  if (hours < 1) return `${stamp} (within the hour)`;
  if (hours < 24) return `${stamp} (in ${hours}h)`;
  return `${stamp} (in ${Math.round(hours / 24)}d)`;
}

export default function Scheduling() {
  const { can } = useAuth();
  const canManage = can("manage_schedules");

  const [groups, setGroups] = useState([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(null); // null | "new" | group
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    try {
      setGroups(await api.listSchedules());
      setStatus("ready");
    } catch (err) {
      setError(err.message);
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const pages = Math.max(1, Math.ceil(groups.length / PER_PAGE));
  const visible = groups.slice((page - 1) * PER_PAGE, page * PER_PAGE);

  async function remove(group) {
    const label = group.name || `Schedule ${group.id}`;
    if (!window.confirm(`Delete ${label}? Its sites become available again.`)) return;
    try {
      await api.deleteSchedule(group.id);
      setGroups((prev) => prev.filter((g) => g.id !== group.id));
    } catch (err) {
      setError(err.message);
    }
  }

  if (status === "loading") return <p className="state">Loading…</p>;
  if (status === "error") return <p className="notice notice-error">{error}</p>;

  if (editing) {
    return (
      <ScheduleWizard
        group={editing === "new" ? null : editing}
        onCancel={() => setEditing(null)}
        onSaved={(saved) => {
          setGroups((prev) => {
            const exists = prev.some((g) => g.id === saved.id);
            return exists
              ? prev.map((g) => (g.id === saved.id ? saved : g))
              : [saved, ...prev];
          });
          setEditing(null);
        }}
      />
    );
  }

  return (
    <>
      <PageHeader title="Scheduling" count={groups.length}>
        {canManage && (
          <button className="btn btn-primary" onClick={() => setEditing("new")}>
            Create new schedule
          </button>
        )}
      </PageHeader>

      {error && <p className="notice notice-error">{error}</p>}

      {groups.length === 0 && (
        <p className="state">
          No schedules yet.
          {canManage
            ? " Create one to have a set of sites scraped automatically."
            : " Someone with scheduling permission can create one."}
        </p>
      )}

      <div className="rows">
        {visible.map((group) => (
          <article className="row-item" key={group.id}>
            <div className="row-main">
              <div className="row-text">
                <h2>
                  <span className={`dot ${group.enabled ? "dot-on" : "dot-off"}`} />
                  {group.name || `Schedule ${group.id}`}
                </h2>

                <p className="row-sub">
                  {describe(group)}
                  {!group.enabled && " · turned off"}
                </p>

                <p className="row-sub mono">
                  Next: {group.enabled ? whenNext(group.next_run_at) : "—"}
                  {group.last_run_at &&
                    ` · last ran ${new Date(group.last_run_at).toLocaleDateString()}`}
                  {group.last_status === "failed" && " · failed"}
                  {group.last_status === "skipped" && " · skipped"}
                </p>

                <ul className="chips chips-tight">
                  {group.sites.map((site) => (
                    <li
                      className={`chip mono ${site.active ? "" : "chip-empty"}`}
                      key={site.id}
                    >
                      {site.name}
                      {!site.active && " (paused)"}
                    </li>
                  ))}
                </ul>

                {group.last_error && <p className="row-error">{group.last_error}</p>}
              </div>

              {canManage && (
                <div className="cell-actions">
                  <button className="btn btn-quiet" onClick={() => setEditing(group)}>
                    Edit
                  </button>
                  <button className="btn btn-danger" onClick={() => remove(group)}>
                    Delete
                  </button>
                </div>
              )}
            </div>
          </article>
        ))}
      </div>

      <Pager page={page} pages={pages} onChange={setPage} />
    </>
  );
}

/** Step one, then step two. Sites first, timing second. */
function ScheduleWizard({ group, onCancel, onSaved }) {
  const isNew = !group;
  const [step, setStep] = useState("sites");
  const [availability, setAvailability] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [selected, setSelected] = useState(group ? group.sites.map((s) => s.id) : []);
  const [form, setForm] = useState({
    name: group?.name || "",
    frequency: group?.frequency || "weekly",
    run_at: (group?.run_at || "08:00:00").slice(0, 5),
    interval_days: group?.interval_days || 3,
    enabled: group?.enabled ?? true,
  });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .siteAvailability()
      .then(setAvailability)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  function update(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function save() {
    setError("");
    setBusy(true);
    const payload = {
      name: form.name.trim() || null,
      site_ids: selected,
      frequency: form.frequency,
      run_at: `${form.run_at}:00`,
      interval_days: form.frequency === "custom" ? Number(form.interval_days) : null,
      enabled: form.enabled,
    };
    try {
      onSaved(
        isNew
          ? await api.createSchedule(payload)
          : await api.updateSchedule(group.id, payload)
      );
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  if (loading) return <p className="state">Loading sites…</p>;

  return (
    <>
      <PageHeader title={isNew ? "New schedule" : `Edit ${group.name || "schedule"}`}>
        <button className="btn btn-quiet" onClick={onCancel}>
          Cancel
        </button>
      </PageHeader>

      <ol className="steps" aria-label="Schedule steps">
        {[
          { key: "sites", label: "Sites" },
          { key: "timing", label: "Frequency and time" },
        ].map((stage, index) => {
          const done = step === "timing" && index === 0;
          const active = step === stage.key;
          return (
            <li
              key={stage.key}
              className={`step ${done ? "step-done" : ""} ${active ? "step-active" : ""}`}
            >
              {index > 0 && <span className="step-line" aria-hidden="true" />}
              <button
                type="button"
                className="step-dot"
                disabled={!done}
                onClick={done ? () => setStep("sites") : undefined}
              >
                {done ? "✓" : index + 1}
              </button>
              <span className="step-label">{stage.label}</span>
            </li>
          );
        })}
      </ol>

      {error && <p className="notice notice-error">{error}</p>}

      {step === "sites" ? (
        <SitePicker
          availability={availability}
          selected={selected}
          onChange={setSelected}
          currentGroupId={group?.id ?? null}
          onNext={() => setStep("timing")}
        />
      ) : (
        <section className="panel">
          <div className="panel-head">
            <h2>How often should these sites be scraped?</h2>
            <span className="mono">
              {selected.length} site{selected.length === 1 ? "" : "s"}
            </span>
          </div>

          <label className="field">
            <span>Name (optional)</span>
            <input
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
              placeholder="Morning banks"
              maxLength={80}
            />
            <small>Helps tell schedules apart in the list.</small>
          </label>

          <label className="field">
            <span>How often</span>
            <select
              value={form.frequency}
              onChange={(e) => update("frequency", e.target.value)}
            >
              {FREQUENCIES.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>

          {form.frequency === "custom" && (
            <label className="field">
              <span>Every how many days</span>
              <input
                type="number"
                min="1"
                max="365"
                value={form.interval_days}
                onChange={(e) => update("interval_days", e.target.value)}
                required
              />
            </label>
          )}

          <label className="field">
            <span>At what time</span>
            <input
              type="time"
              className="mono"
              value={form.run_at}
              onChange={(e) => update("run_at", e.target.value)}
              required
            />
            <small>
              Local time. A schedule set for 08:00 stays at 08:00 through the year.
            </small>
          </label>

          <label className="check panel-extra">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => update("enabled", e.target.checked)}
            />
            <span>
              Run this schedule
              <small>
                Turn it off to keep the settings without scraping. A paused site
                is never scraped, whatever its schedule says.
              </small>
            </span>
          </label>

          <div className="panel-foot">
            <button className="btn btn-quiet" onClick={() => setStep("sites")}>
              Back
            </button>
            <button
              className="btn btn-primary"
              disabled={busy || selected.length === 0}
              onClick={save}
            >
              {busy ? "Saving…" : "Save schedule"}
            </button>
          </div>
        </section>
      )}
    </>
  );
}

function SitePicker({ availability, selected, onChange, currentGroupId, onNext }) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return availability.filter(
      (row) => !needle || row.site_name.toLowerCase().includes(needle)
    );
  }, [availability, query]);

  // A site held by another schedule cannot be chosen. When editing, this
  // group's own sites are of course still available to it.
  const isBlocked = (row) => row.group_id !== null && row.group_id !== currentGroupId;

  const selectable = rows.filter((row) => !isBlocked(row));
  const pages = Math.max(1, Math.ceil(rows.length / PER_PAGE));
  useEffect(() => {
    if (page > pages) setPage(1);
  }, [page, pages]);
  const visible = rows.slice((page - 1) * PER_PAGE, page * PER_PAGE);

  const allSelected =
    selectable.length > 0 && selectable.every((r) => selected.includes(r.site_id));

  function toggle(id) {
    onChange(
      selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]
    );
  }

  function toggleAll() {
    const ids = selectable.map((r) => r.site_id);
    onChange(
      allSelected
        ? selected.filter((id) => !ids.includes(id))
        : [...new Set([...selected, ...ids])]
    );
  }

  const blockedCount = rows.filter(isBlocked).length;

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Which sites should this schedule cover?</h2>
        <span className="mono">
          {selected.length} selected
          {blockedCount > 0 && ` · ${blockedCount} unavailable`}
        </span>
      </div>

      <div className="picker">
        <div className="picker-head">
          <label className="check picker-all">
            <input type="checkbox" checked={allSelected} onChange={toggleAll} />
            <span>
              {query ? `Select all ${selectable.length} available` : "Select all"}
            </span>
          </label>
          <input
            className="search"
            placeholder="Filter sites…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
          />
        </div>

        <ul className="picker-list">
          {visible.map((row) => {
            const blocked = isBlocked(row);
            return (
              <li key={row.site_id}>
                <div
                  className={`picker-row ${
                    selected.includes(row.site_id) ? "picked" : ""
                  } ${blocked ? "picker-blocked" : ""}`}
                >
                  <label>
                    <input
                      type="checkbox"
                      checked={selected.includes(row.site_id)}
                      disabled={blocked}
                      onChange={() => toggle(row.site_id)}
                    />
                    <span className="picker-label">
                      {row.site_name}
                      {blocked ? (
                        <small>
                          Already in “{row.group_name}”. Remove it from that
                          schedule before adding it here.
                        </small>
                      ) : (
                        <small className="mono">
                          {row.site_url.replace(/^https?:\/\//, "").slice(0, 44)}
                          {!row.site_active && " · paused"}
                        </small>
                      )}
                    </span>
                  </label>
                </div>
              </li>
            );
          })}
        </ul>

        {rows.length === 0 && <p className="state">No sites match that filter.</p>}

        {pages > 1 && (
          <div className="picker-foot">
            <button
              type="button"
              className="btn btn-quiet btn-tiny"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </button>
            <span className="mono">
              {page} / {pages}
            </span>
            <button
              type="button"
              className="btn btn-quiet btn-tiny"
              disabled={page >= pages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        )}
      </div>

      <div className="panel-foot">
        <span className="mono hint">
          {selected.length === 0 ? "Select at least one site to continue." : "\u00a0"}
        </span>
        <button
          className="btn btn-primary"
          disabled={selected.length === 0}
          onClick={onNext}
        >
          Done
        </button>
      </div>
    </section>
  );
}
