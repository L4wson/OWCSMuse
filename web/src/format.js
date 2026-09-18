// Formatting, driven by the column descriptors the API sends.
//
// There used to be a label table and a key-name formatter here, both of them
// guessing at things the schema already knew. The API now returns
// {key, label, type} per column, so this file only has to render a value of a
// given type - and when a new column appears, it appears correctly without a
// change here.

const NUMBER = new Intl.NumberFormat("en-GB");

export function formatDate(value) {
  if (!value) return "";
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value));
  return match ? `${match[1]}-${match[2]}-${match[3]}` : String(value);
}

/** A cell's text, from its column's declared type. */
export function formatCell(row, column) {
  const value = row?.[column.key];
  if (column.type === "score") {
    const ours = value ?? null;
    const theirs = column.pair_key ? (row?.[column.pair_key] ?? null) : null;
    if (ours === null && theirs === null) return "-";
    return `${ours ?? "-"}-${theirs ?? "-"}`;
  }
  if (value === null || value === undefined || value === "") return "-";

  switch (column.type) {
    case "date":
      return formatDate(value);
    case "percent":
      return `${Number.isInteger(value) ? value : Number(value).toFixed(1)}%`;
    case "integer":
      return typeof value === "number" ? NUMBER.format(value) : String(value);
    case "decimal":
      return typeof value === "number" ? NUMBER.format(Number(value.toFixed(2))) : String(value);
    case "flag":
      return value ? "yes" : "no";
    case "list":
      return Array.isArray(value) ? value.join(", ") : String(value);
    default:
      return String(value);
  }
}

/**
 * The question to ask about an entity mentioned in an answer sentence.
 *
 * Still the client's guess: a span says who an entity is, not what to ask about
 * them. A record is the one question that works for a player, a team and an org.
 */
export function entityQuestion(name, kind) {
  if (!name) return null;
  if (kind === "player" || kind === "team" || kind === "org") return `${name} record`;
  if (kind === "map" || kind === "mode") return `most played ${kind === "map" ? "maps" : "modes"}`;
  if (kind === "stat") return `which seasons have ${String(name).toLowerCase()}`;
  return null;
}

export const LINKABLE_SPAN_KINDS = new Set(["player", "team", "org", "map", "mode", "stat"]);

/** How a candidate's era reads in a list of otherwise identical names. */
export function activeRange(candidate) {
  const seasons = candidate?.seasons ?? [];
  const first = formatDate(candidate?.first_at);
  const last = formatDate(candidate?.last_at);
  if (!seasons.length && !first) return null;
  const era = seasons.length ? `season${seasons.length === 1 ? "" : "s"} ${seasons.join(", ")}` : null;
  const dates = first && last ? (first === last ? first : `${first} to ${last}`) : null;
  return [era, dates].filter(Boolean).join(", ");
}
