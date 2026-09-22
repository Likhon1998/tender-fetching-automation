export default function PageHeader({ title, count, children }) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {count !== undefined && (
          <p className="page-count mono">
            {count} {count === 1 ? "record" : "records"}
          </p>
        )}
      </div>
      <div className="page-actions">{children}</div>
    </header>
  );
}
