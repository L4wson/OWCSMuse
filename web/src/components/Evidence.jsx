import DataTable from "./DataTable.jsx";

/**
 * The rows behind the claim, with their paging state.
 *
 * `grain` decides nothing about the columns - those come from the rows - but it
 * is what the header says, so a reader knows whether they are looking at maps or
 * series before they read the table.
 */
export default function Evidence({ evidence, busy = false, onPage = null }) {
  if (!evidence) return null;

  if (!evidence.available) {
    return evidence.reason ? (
      <p className="muted evidence-empty" data-testid="evidence-none">
        No rows behind this answer: {evidence.reason}.
      </p>
    ) : null;
  }

  const { page = 1, total_pages: totalPages = 1, total_rows: totalRows = 0, rows = [], grain, description } = evidence;
  const expanded = evidence.expanded_for;

  return (
    <section className="evidence" data-testid="evidence" aria-busy={busy ? "true" : "false"}>
      <header className="evidence-head">
        <h2>
          {totalRows.toLocaleString("en-GB")} {grain === "series" ? "series" : "maps"}
          {expanded?.name || expanded?.id ? (
            <>
              {" "}
              behind{" "}
              <span className="evidence-subject" data-testid="evidence-subject">
                {expanded.name ?? expanded.id}
              </span>
            </>
          ) : null}
        </h2>
        {description ? <p className="muted">{description}, newest first.</p> : null}
      </header>

      <DataTable rows={rows} columns={evidence.columns ?? []} emptyText="No rows on this page." />

      {totalPages > 1 ? (
        <nav className="pager" aria-label="Evidence pages">
          <button type="button" onClick={() => onPage?.(page - 1)} disabled={busy || page <= 1}>
            Newer
          </button>
          <span data-testid="pager-state">
            Page {page} of {totalPages}
          </span>
          <button type="button" onClick={() => onPage?.(page + 1)} disabled={busy || !evidence.has_more}>
            Older
          </button>
        </nav>
      ) : null}
    </section>
  );
}
