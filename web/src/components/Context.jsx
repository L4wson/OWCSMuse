/**
 * Coverage, notes and known limitations: where the reader is already looking.
 *
 * A leaderboard that covers 2025 and 2026 but not 2024 is not wrong, it is
 * partial, and the difference only matters if it is said next to the number. So
 * this sits between the sentence and the table, and the coverage line and the
 * notes (each a sentence about this answer: "results only for ...: that part is
 * not in this answer") are always shown.
 *
 * The known limitations are the long explanations behind them - why offline and
 * LAN days carry no map stats, why a slice is results only. Shown in full they
 * dominated the answer (owner, 2026-10-25), so they sit behind a small "why?"
 * that expands to the same text. A native <details>: keyboard and screen readers
 * work, and it needs no state.
 */
export default function Context({ coverage, notes = [], limitations = [] }) {
  const hasCoverage = coverage && coverage.stat_key && (coverage.maps_total ?? 0) > 0;
  if (!hasCoverage && !notes?.length && !limitations?.length) return null;

  return (
    <section className="context" data-testid="context">
      {hasCoverage ? <CoverageLine coverage={coverage} /> : null}

      {notes?.map((note) => (
        <p className="note" data-testid="note" key={note}>
          {note}
        </p>
      ))}

      {limitations?.length ? (
        <details className="limitations" data-testid="limitations">
          <summary aria-label={`Why: ${limitations.length} known limitation${limitations.length === 1 ? "" : "s"} of this data`}>
            <span aria-hidden="true" className="info-icon">
              i
            </span>{" "}
            why?
          </summary>
          {limitations.map((limitation) => (
            <p className="limitation" data-testid={`limitation-${limitation.id}`} key={limitation.id}>
              <b>{limitation.title}.</b> {limitation.note}
            </p>
          ))}
        </details>
      ) : null}
    </section>
  );
}

function CoverageLine({ coverage }) {
  const pct = coverage.coverage_pct ?? 0;
  const partial = pct < 100;
  const withStat = coverage.seasons_with_stat ?? [];
  const without = coverage.seasons_without_stat ?? [];

  return (
    <p className={partial ? "coverage coverage--partial" : "coverage"} data-testid="coverage">
      <b>{coverage.stat_key}</b> is recorded on {Number(coverage.maps_with_stat ?? 0).toLocaleString("en-GB")} of{" "}
      {Number(coverage.maps_total ?? 0).toLocaleString("en-GB")} maps in this slice ({pct}%)
      {withStat.length ? <> · seasons with it: {withStat.join(", ")}</> : null}
      {without.length ? (
        <>
          {" "}
          · <span className="coverage-missing">missing in {without.join(", ")}</span>
        </>
      ) : null}
      {partial ? <> · the ranking covers only the maps that have it</> : null}
    </p>
  );
}
