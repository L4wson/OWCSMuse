import { formatCell } from "../format.js";

// A row's identity. `match_id` alone is not one: map-grain evidence has a row per map, so a
// match repeats. Duplicate keys make React keep rows of the previous answer on screen, so the
// key is every field that distinguishes a row at any grain, plus its position as the last word.
const rowKey = (row, index) =>
  [row.entity?.id, row.match_id, row.round_number, row.team, index].map((part) => part ?? "").join("|");

/**
 * One table for every shape the API returns.
 *
 * Columns arrive described - key, label and type - so a map-grain answer shows
 * maps and a series-grain answer shows series without this component knowing
 * which was asked, and a new column renders correctly the day it appears. Each
 * cell carries its label, which is what turns the table into cards on a narrow
 * screen (see styles.css): one DOM, two layouts.
 */
export default function DataTable({
  rows,
  columns = [],
  caption,
  expandedId = null,
  onExpand = null,
  className = "",
  emptyText = "No rows.",
}) {
  if (!rows?.length || !columns.length) return <p className="muted">{emptyText}</p>;

  return (
    <div className={`table-wrap ${className}`}>
      <table className="data">
        {caption ? <caption>{caption}</caption> : null}
        <thead>
          <tr>
            {onExpand ? <th scope="col">Evidence</th> : null}
            {columns.map((column) => (
              <th key={column.key} scope="col">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const entity = row.entity ?? null;
            const isExpanded = entity?.id != null && expandedId != null && String(entity.id) === String(expandedId);
            return (
              <tr
                key={rowKey(row, index)}
                className={isExpanded ? "row row--expanded" : "row"}
                aria-current={isExpanded ? "true" : undefined}
              >
                {onExpand ? (
                  <td data-label="Evidence" className="cell-expand">
                    <button
                      type="button"
                      className={isExpanded ? "expand expand--on" : "expand"}
                      aria-pressed={isExpanded ? "true" : "false"}
                      disabled={!entity?.id}
                      onClick={() => onExpand(entity.id, row)}
                    >
                      {isExpanded ? "showing" : "show"}
                      <span className="visually-hidden"> the rows behind {entity?.name ?? "this row"}</span>
                    </button>
                  </td>
                ) : null}
                {columns.map((column) => (
                  <td key={column.key} data-label={column.label} className={`cell cell--${column.type}`}>
                    <Cell row={row} column={column} />
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Cell({ row, column }) {
  const raw = row[column.key];

  if (column.type === "link" && raw) {
    return (
      <a href={raw} target="_blank" rel="noreferrer noopener" className="source-link">
        FACEIT
      </a>
    );
  }
  if (column.type === "result" && raw) {
    return <span className={`result result--${String(raw)}`}>{raw}</span>;
  }
  if (column.type === "flag") {
    return raw === false ? (
      <span className="flag flag--missing" title="FACEIT recorded no per-map stats for this series">
        none
      </span>
    ) : (
      <span className="flag">yes</span>
    );
  }
  return <>{formatCell(row, column)}</>;
}
