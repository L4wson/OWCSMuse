import { cellValue, deriveColumns, labelFor, rowId, rowLabel } from "../format.js";

/**
 * One table for every shape the API returns.
 *
 * Columns come from the rows, so a map-grain answer shows maps and a series-grain
 * answer shows series without the client knowing which it asked for. Each cell
 * carries its column label, which is what turns the table into cards on a narrow
 * screen (see styles.css) - one DOM, two layouts.
 */
export default function DataTable({
  rows,
  columns,
  caption,
  idKey = null,
  expandedId = null,
  onExpand = null,
  className = "",
  emptyText = "No rows.",
}) {
  if (!rows?.length) return <p className="muted">{emptyText}</p>;
  const cols = columns ?? deriveColumns(rows);

  return (
    <div className={`table-wrap ${className}`}>
      <table className="data">
        {caption ? <caption>{caption}</caption> : null}
        <thead>
          <tr>
            {onExpand ? <th scope="col">Evidence</th> : null}
            {cols.map((key) => (
              <th key={key} scope="col">
                {labelFor(key)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const id = rowId(row, idKey);
            // Which row the evidence belongs to is a fact about the answer, not
            // about whether this table happens to be interactive.
            const isExpanded = id !== null && expandedId !== null && String(id) === String(expandedId);
            return (
              <tr
                key={`${id ?? index}`}
                className={isExpanded ? "row row--expanded" : "row"}
                aria-current={isExpanded ? "true" : undefined}
              >
                {onExpand ? (
                  <td data-label="Evidence" className="cell-expand">
                    <button
                      type="button"
                      className={isExpanded ? "expand expand--on" : "expand"}
                      aria-pressed={isExpanded ? "true" : "false"}
                      disabled={id === null}
                      onClick={() => onExpand(id, row)}
                    >
                      {isExpanded ? "showing" : "show"}
                      <span className="visually-hidden"> the rows behind {rowLabel(row) ?? "this row"}</span>
                    </button>
                  </td>
                ) : null}
                {cols.map((key) => (
                  <td key={key} data-label={labelFor(key)} className={`cell cell--${key}`}>
                    <Cell row={row} column={key} />
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
  const raw = row[column];

  if (column === "match_url" && raw) {
    return (
      <a href={raw} target="_blank" rel="noreferrer noopener" className="source-link">
        FACEIT
      </a>
    );
  }
  if (column === "result" && raw) {
    return <span className={`result result--${String(raw)}`}>{raw}</span>;
  }
  if (column === "map_stats_recorded") {
    return raw === false ? (
      <span className="flag flag--missing" title="FACEIT recorded no per-map stats for this series">
        none
      </span>
    ) : (
      <span className="flag">yes</span>
    );
  }
  return <>{cellValue(row, column)}</>;
}
