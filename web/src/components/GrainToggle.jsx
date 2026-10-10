/**
 * A versus answer is a map record and a series record is the other grain of the same pairing: both are reachable from
 * either. The service builds the other grain's question (same two sides, season and event) as `other_grain`; this only
 * shows which grain is on screen and asks the other.
 */
const LABELS = { map: "Map record", series: "Series record" };

export default function GrainToggle({ answer, onAsk, busy = false }) {
  const other = answer?.other_grain;
  if (!other?.question) return null;
  const current = other.grain === "series" ? "map" : "series";
  return (
    <div className="grain-toggle" role="group" aria-label="Record grain" data-testid="grain-toggle">
      <button type="button" className="grain-toggle__option" aria-pressed="true" disabled>
        {LABELS[current]}
      </button>
      <button
        type="button"
        className="grain-toggle__option"
        aria-pressed="false"
        disabled={busy}
        onClick={() => onAsk(other.question)}
        title={other.question}
      >
        {other.label ?? LABELS[other.grain]}
      </button>
    </div>
  );
}
