/**
 * Tender dates, labelled.
 *
 * Sites are inconsistent: most list when a notice was published, a few list
 * the deadline instead, and many state the deadline only inside the title.
 * Showing an unlabelled date would leave the reader guessing which they are
 * looking at, and the difference matters when deciding whether to bid.
 */
function format(iso) {
  if (!iso) return null;
  const [year, month, day] = iso.split("-").map(Number);
  const name = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ][month - 1];
  return `${day} ${name} ${year}`;
}

function daysUntil(iso) {
  if (!iso) return null;
  const [y, m, d] = iso.split("-").map(Number);
  const target = new Date(y, m - 1, d);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target - today) / 86400000);
}

export default function TenderDates({ tender }) {
  const published =
    tender.date_type === "publish" && tender.date ? format(tender.date) : null;
  const submission = format(tender.submission_date);
  const left = daysUntil(tender.submission_date);

  // Deadlines inside a fortnight are worth flagging; passed ones are dead.
  const urgency =
    left === null ? "" : left < 0 ? "date-passed" : left <= 14 ? "date-soon" : "";

  return (
    <>
      {published && (
        <span className="mono date-tag">
          <span className="date-label">Published</span> {published}
        </span>
      )}

      {submission && (
        <span className={`mono date-tag ${urgency}`}>
          <span className="date-label">Submission</span> {submission}
          {left !== null && left >= 0 && left <= 14 && ` · ${left}d left`}
          {left !== null && left < 0 && " · closed"}
        </span>
      )}

      {!published && !submission && <span className="mono date-tag">no date</span>}
    </>
  );
}
