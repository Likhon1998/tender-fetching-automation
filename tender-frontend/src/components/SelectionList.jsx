import { useEffect, useMemo, useState } from "react";

const PER_PAGE = 8;

/**
 * The paginated checkbox list used by both wizard stages.
 *
 * "Select all" applies to everything matching the current filter, not just the
 * visible page, otherwise the count would depend on where you happened to be.
 * `renderDetail` lets the categories stage expand a row to show its keywords
 * while the sites stage stays a plain list.
 */
export default function SelectionList({
  items,
  selected,
  onChange,
  getLabel,
  getSubLabel,
  renderDetail,
  searchPlaceholder,
  emptyMessage,
}) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState(null);

  const matching = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((item) =>
      `${getLabel(item)} ${getSubLabel?.(item) ?? ""}`.toLowerCase().includes(needle)
    );
  }, [items, query, getLabel, getSubLabel]);

  const pages = Math.max(1, Math.ceil(matching.length / PER_PAGE));

  // Filtering can leave you on a page that no longer exists.
  useEffect(() => {
    if (page > pages) setPage(1);
  }, [page, pages]);

  const visible = matching.slice((page - 1) * PER_PAGE, page * PER_PAGE);
  const matchingIds = matching.map((i) => i.id);
  const allSelected =
    matchingIds.length > 0 && matchingIds.every((id) => selected.includes(id));

  function toggle(id) {
    onChange(
      selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]
    );
  }

  function toggleAll() {
    if (allSelected) {
      onChange(selected.filter((id) => !matchingIds.includes(id)));
    } else {
      onChange([...new Set([...selected, ...matchingIds])]);
    }
  }

  return (
    <div className="picker">
      <div className="picker-head">
        <label className="check picker-all">
          <input
            type="checkbox"
            checked={allSelected}
            onChange={toggleAll}
            aria-label="Select all"
          />
          <span>
            {query ? `Select all ${matching.length} matching` : "Select all"}
          </span>
        </label>

        <input
          className="search"
          placeholder={searchPlaceholder}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(1);
          }}
        />
      </div>

      <ul className="picker-list">
        {visible.map((item) => (
          <li key={item.id}>
            <div className={`picker-row ${selected.includes(item.id) ? "picked" : ""}`}>
              <label>
                <input
                  type="checkbox"
                  checked={selected.includes(item.id)}
                  onChange={() => toggle(item.id)}
                />
                <span className="picker-label">
                  {getLabel(item)}
                  {getSubLabel && <small className="mono">{getSubLabel(item)}</small>}
                </span>
              </label>

              {renderDetail && (
                <button
                  type="button"
                  className="btn btn-quiet btn-tiny"
                  aria-expanded={expanded === item.id}
                  onClick={() =>
                    setExpanded(expanded === item.id ? null : item.id)
                  }
                >
                  {expanded === item.id ? "Hide" : "Keywords"}
                </button>
              )}
            </div>

            {renderDetail && expanded === item.id && (
              <div className="picker-detail">{renderDetail(item)}</div>
            )}
          </li>
        ))}
      </ul>

      {matching.length === 0 && <p className="state">{emptyMessage}</p>}

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
  );
}
