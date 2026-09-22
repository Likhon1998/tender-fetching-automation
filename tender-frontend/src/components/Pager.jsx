/** Shared previous/next control for the paginated list pages. */
export default function Pager({ page, pages, onChange }) {
  if (pages <= 1) return null;

  return (
    <nav className="pager">
      <button
        className="btn btn-quiet"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >
        Previous
      </button>
      <span className="mono">
        Page {page} of {pages}
      </span>
      <button
        className="btn btn-quiet"
        disabled={page >= pages}
        onClick={() => onChange(page + 1)}
      >
        Next
      </button>
    </nav>
  );
}
