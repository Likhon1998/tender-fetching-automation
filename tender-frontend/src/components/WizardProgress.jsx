/**
 * The three-stage progress bar that stays visible across the whole wizard.
 * A stage's circle fills once that stage is behind you.
 */
const STAGES = [
  { key: "sites", label: "Sites" },
  { key: "categories", label: "Categories" },
  { key: "fetch", label: "Fetch Tenders" },
];

export default function WizardProgress({ current, onJumpTo }) {
  const currentIndex = STAGES.findIndex((s) => s.key === current);

  return (
    <ol className="steps" aria-label="Search progress">
      {STAGES.map((stage, index) => {
        const done = index < currentIndex;
        const active = index === currentIndex;
        // Only completed stages are clickable: jumping ahead would skip a
        // choice the next stage depends on.
        const clickable = done && typeof onJumpTo === "function";

        return (
          <li
            key={stage.key}
            className={`step ${done ? "step-done" : ""} ${active ? "step-active" : ""}`}
          >
            {index > 0 && <span className="step-line" aria-hidden="true" />}
            <button
              type="button"
              className="step-dot"
              disabled={!clickable}
              onClick={clickable ? () => onJumpTo(stage.key) : undefined}
              aria-current={active ? "step" : undefined}
              aria-label={`${stage.label}${done ? " (complete)" : ""}`}
            >
              {done ? "✓" : index + 1}
            </button>
            <span className="step-label">{stage.label}</span>
          </li>
        );
      })}
    </ol>
  );
}
