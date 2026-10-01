import { LINKABLE_SPAN_KINDS, entityQuestion } from "../format.js";
import DataTable from "./DataTable.jsx";

/**
 * The rows behind the claim, with their paging state.
 *
 * `grain` decides nothing about the columns - those come from the rows - but it
 * is what the header says, so a reader knows whether they are looking at maps or
 * series before they read the table.
 */
export const PAGE_SIZE_OPTIONS = [25, 50, 100];

export default function Evidence({ evidence, busy = false, onPage = null, onAsk = null, pageSize = null, onPageSize = null }) {
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
  // The id is the right thing to ask about, never the right thing to show -
  // same rule as the search box (App.jsx's displayable()). Only ever fall
  // back to it when a name never arrived.
  const label = expanded?.name ?? expanded?.id;
  const question = expanded?.name && LINKABLE_SPAN_KINDS.has(expanded.type) ? entityQuestion(expanded.name, expanded.type) : null;

  return (
    <section className="evidence" data-testid="evidence" aria-busy={busy ? "true" : "false"}>
      <header className="evidence-head">
        <h2>
          {totalRows.toLocaleString("en-GB")} {grain === "series" ? "series" : "maps"}
          {label ? (
            <>
              {" "}
              behind{" "}
              {question && onAsk ? (
                <button
                  type="button"
                  className={`entity entity--link entity--${expanded.type} evidence-subject`}
                  data-testid="evidence-subject"
                  data-kind={expanded.type}
                  data-entity-id={expanded.id ?? ""}
                  title={`Ask: ${question}`}
                  onClick={() => onAsk(question)}
                >
                  {label}
                </button>
              ) : (
                <span className="evidence-subject" data-testid="evidence-subject">
                  {label}
                </span>
              )}
            </>
          ) : null}
        </h2>
        {description ? <p className="muted">{description}, newest first.</p> : null}
      </header>

      <DataTable rows={rows} columns={evidence.columns ?? []} emptyText="No rows on this page." />

      {totalRows > 0 && (totalPages > 1 || onPageSize) ? (
        <nav className="pager" aria-label="Evidence pages">
          {onPageSize ? (
            <label className="page-size">
              Rows per page{" "}
              <select
                data-testid="page-size"
                value={pageSize ?? evidence.page_size ?? PAGE_SIZE_OPTIONS[0]}
                disabled={busy}
                onChange={(event) => onPageSize(Number(event.target.value))}
              >
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {totalPages > 1 ? (
            <>
              <button type="button" onClick={() => onPage?.(page - 1)} disabled={busy || page <= 1}>
                Newer
              </button>
              <span data-testid="pager-state">
                Page {page} of {totalPages}
              </span>
              <button type="button" onClick={() => onPage?.(page + 1)} disabled={busy || !evidence.has_more}>
                Older
              </button>
            </>
          ) : null}
        </nav>
      ) : null}
    </section>
  );
}
