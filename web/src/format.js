// Turning API rows into something readable, without deciding what they mean.
//
// The API sends snake_case keys and raw values; every client would otherwise
// reinvent these labels. Anything not listed here is title-cased, so a new
// column appears in the table rather than disappearing from it.

const LABELS = {
  played_at: "Date",
  round_number: "Map #",
  map_name: "Map",
  game_mode: "Mode",
  competition: "Competition",
  championship_id: "Competition id",
  opponent: "Opponent",
  opponent_score: "Opp",
  best_of: "Best of",
  map_stats_recorded: "Map stats",
  match_url: "Source",
  damage_dealt: "Damage",
  healing_done: "Healing",
  damage_mitigated: "Mitigated",
  kd_ratio: "K/D",
  map_win_pct: "Map win %",
  win_pct: "Win %",
  coverage_pct: "Coverage %",
  maps_with_stat: "Maps with stat",
  maps_played: "Maps played",
  avg_per_map: "Per map",
  first_map_at: "First",
  last_map_at: "Last",
  first_match_at: "First",
  last_match_at: "Last",
  org_key: "Entity id",
  player_id: "Player id",
  nickname: "Player",
  stat_value: "Value",
  stat_key: "Stat",
  total_rows: "Rows",
};

// Never shown as a column: identifiers a reader cannot use, and the link that
// gets its own cell.
export const HIDDEN_COLUMNS = new Set(["match_id", "championship_id", "player_id", "org_key", "org_id", "total_rows"]);

export function labelFor(key) {
  if (LABELS[key]) return LABELS[key];
  return key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

export function formatDate(value) {
  if (!value) return "";
  const text = String(value);
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(text);
  return match ? `${match[1]}-${match[2]}-${match[3]}` : text;
}

export function formatValue(key, value) {
  if (value === null || value === undefined || value === "") return "-";
  if (key === "played_at" || key.endsWith("_at")) return formatDate(value);
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "number") {
    if (key.endsWith("_pct")) return `${Number.isInteger(value) ? value : value.toFixed(1)}%`;
    if (!Number.isInteger(value)) return value.toFixed(2);
    return value.toLocaleString("en-GB");
  }
  return String(value);
}

/**
 * Columns for a set of rows, in the order the API sent them.
 *
 * The evidence shape follows the grain of the answer - a map row and a series
 * row do not carry the same keys - so columns are derived per response rather
 * than hardcoded. A column whose every value on this page is null is dropped:
 * a series row has no map number, and an empty column is noise.
 */
export function deriveColumns(rows, { hidden = HIDDEN_COLUMNS } = {}) {
  if (!rows?.length) return [];
  const keys = [];
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!keys.includes(key) && !hidden.has(key)) keys.push(key);
    }
  }
  const kept = keys.filter((key) => rows.some((row) => row[key] !== null && row[key] !== undefined && row[key] !== ""));

  // A score and its opposite number are one fact, and read as one: "3-1".
  if (kept.includes("score") && kept.includes("opponent_score")) {
    const at = kept.indexOf("score");
    kept.splice(at, 1, "score_pair");
    kept.splice(kept.indexOf("opponent_score"), 1);
  }
  // The source link always goes last, whatever order the keys arrived in.
  if (kept.includes("match_url")) {
    kept.splice(kept.indexOf("match_url"), 1);
    kept.push("match_url");
  }
  return kept;
}

export function cellValue(row, key) {
  if (key === "score_pair") {
    const ours = row.score ?? null;
    const theirs = row.opponent_score ?? null;
    if (ours === null && theirs === null) return "-";
    return `${ours ?? "-"}-${theirs ?? "-"}`;
  }
  return formatValue(key, row[key]);
}

/** The name a ranked row should be labelled with, and the id that expands it. */
export function rowLabel(row) {
  return row.nickname ?? row.team ?? row.display_name ?? row.map_name ?? row.game_mode ?? row.entity ?? null;
}

export function rowId(row, idKey) {
  if (idKey && row[idKey] !== undefined) return row[idKey];
  return row.player_id ?? row.org_key ?? row.map_name ?? row.game_mode ?? null;
}

/**
 * The question to ask about an entity mentioned in an answer sentence.
 *
 * The API marks who an entity is but not what to ask about them, so the client
 * picks: a record is the one question that works for a player, a team and an org
 * alike.
 */
export function entityQuestion(name, kind) {
  if (!name) return null;
  if (kind === "player" || kind === "team" || kind === "org") return `${name} record`;
  if (kind === "map" || kind === "mode") return `most played ${kind === "map" ? "maps" : "modes"}`;
  if (kind === "stat") return `which seasons have ${String(name).toLowerCase()}`;
  return null;
}

export const LINKABLE_SPAN_KINDS = new Set(["player", "team", "org", "map", "mode", "stat"]);

// A FACEIT player or team id. The question parser accepts one of these in place
// of a name, which is how an identical-name tie is broken; an org id is a slug
// and the parser does not accept it (see the report), so an org candidate is
// selected by its exact name instead.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function selectorFor(candidate) {
  const id = candidate?.entity_id ?? "";
  if (UUID.test(id)) return { token: id, exact: true };
  return { token: candidate?.current_name ?? candidate?.matched_name ?? id, exact: false };
}

/**
 * The question to run when someone picks one of several candidates.
 *
 * The typed name is replaced in place, so the rest of the question - season,
 * map, opponent - survives. If the name cannot be found in the text (the parser
 * may have read it from a different wording) the question falls back to a record
 * for that entity, which is never a dead end.
 */
export function disambiguatedQuestion(question, typedName, candidate) {
  const { token } = selectorFor(candidate);
  const haystack = String(question ?? "");
  for (const name of [typedName, candidate?.matched_name, candidate?.current_name]) {
    if (!name) continue;
    const at = haystack.toLowerCase().indexOf(String(name).toLowerCase());
    if (at >= 0) return haystack.slice(0, at) + token + haystack.slice(at + String(name).length);
  }
  return `${token} record`;
}

export function deepEqual(a, b) {
  if (a === b) return true;
  if (typeof a !== typeof b || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (typeof a !== "object") return false;
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  if (keysA.length !== keysB.length) return false;
  return keysA.every((key) => deepEqual(a[key], b[key]));
}

/**
 * What changed between the parse stored with a shared link and today's parse.
 *
 * A shared link re-runs against current data on purpose, so the parser may have
 * learned something since. That is worth saying out loud rather than quietly
 * answering a different question than the one that was shared.
 */
export function describeParseChange(before, after) {
  if (!before || !after || deepEqual(before, after)) return [];
  const changes = [];
  for (const key of ["intent", "entity", "metric", "aggregation", "sort", "limit", "min_maps"]) {
    if (!deepEqual(before[key], after[key])) {
      changes.push(`${labelFor(key).toLowerCase()}: ${before[key] ?? "none"} -> ${after[key] ?? "none"}`);
    }
  }
  const filtersBefore = before.filters ?? {};
  const filtersAfter = after.filters ?? {};
  for (const key of new Set([...Object.keys(filtersBefore), ...Object.keys(filtersAfter)])) {
    if (!deepEqual(filtersBefore[key], filtersAfter[key])) {
      changes.push(`${key}: ${filtersBefore[key] ?? "none"} -> ${filtersAfter[key] ?? "none"}`);
    }
  }
  return changes;
}
