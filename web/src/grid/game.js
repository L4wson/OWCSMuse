// OWCS Grid's game state: everything about a visitor's play lives here and in this browser's localStorage.
// The server keeps nothing about who is playing, so the nine-guess budget and the one-cell-per-player rule are
// enforced in this file and nowhere else.

const PREFIX = "owcs-grid:v1";
const puzzleKey = (number) => `${PREFIX}:puzzle:${number}`;
const STATS_KEY = `${PREFIX}:stats`;

// localStorage can be missing, full, or blocked (private windows, embedded browsers such as the Reddit app's).
// Every read and write is guarded: a game that cannot be saved still plays, it just does not survive a reload.
function read(key) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function newGame() {
  return { filled: {}, used: 0, misses: [], over: false };
}

/** A saved game, or a fresh one. Anything that does not look like a game is ignored rather than trusted. */
export function loadGame(number) {
  const saved = read(puzzleKey(number));
  if (!saved || typeof saved !== "object" || typeof saved.filled !== "object" || !Array.isArray(saved.misses)) {
    return newGame();
  }
  return { ...newGame(), ...saved, used: Number.isInteger(saved.used) ? saved.used : 0 };
}

export function saveGame(number, game) {
  return write(puzzleKey(number), game);
}

export const score = (game) => Object.keys(game.filled).length;

export const guessesLeft = (game, budget) => Math.max(0, budget - game.used);

export const isOver = (game, budget) => game.over || game.used >= budget || score(game) >= 9;

/** The cell a player already fills, or null: a player can fill only one cell per puzzle. */
export function cellOf(game, playerId) {
  const hit = Object.entries(game.filled).find(([, answer]) => answer.id === playerId);
  return hit ? Number(hit[0]) : null;
}

/** Has this player already been tried, and missed, in this cell? Trying again would only burn a guess. */
export const alreadyMissed = (game, cell, playerId) =>
  game.misses.some((miss) => miss.cell === cell && miss.id === playerId && miss.result === "wrong");

/**
 * The game after the server's verdict on one guess. A correct or wrong guess costs one of the budget; a
 * "can't verify" costs nothing and leaves the cell open.
 */
export function applyGuess(game, budget, verdict) {
  if (isOver(game, budget)) return game;
  const { cell, player, result } = verdict;
  if (result === "cannot_verify") {
    return { ...game, misses: [...game.misses, { cell, id: player.id, name: player.name, result }] };
  }
  const used = game.used + 1;
  const next =
    result === "correct"
      ? {
          ...game,
          used,
          filled: { ...game.filled, [cell]: { id: player.id, name: player.name, explanation: verdict.explanation } },
        }
      : { ...game, used, misses: [...game.misses, { cell, id: player.id, name: player.name, result: "wrong" }] };
  return { ...next, over: used >= budget || score(next) >= 9 };
}

export const giveUp = (game) => ({ ...game, over: true });

/** "OWCS Grid #12  7/9", three rows of squares and the link. Never a name: sharing must not spoil the puzzle. */
export function shareText(number, game, url) {
  const rows = [0, 1, 2].map((row) =>
    [0, 1, 2].map((col) => (game.filled[row * 3 + col] ? "\u{1F7E9}" : "⬜")).join(""),
  );
  return [`OWCS Grid #${number}  ${score(game)}/9`, ...rows, url].join("\n");
}

export function loadStats() {
  const saved = read(STATS_KEY);
  const base = { streak: 0, best: 0, played: 0, last: null };
  return saved && typeof saved === "object" ? { ...base, ...saved } : base;
}

/**
 * Count a finished daily puzzle towards the streak: consecutive puzzle numbers finished on their own day.
 * Finishing the same puzzle twice changes nothing, and an archive puzzle never counts.
 */
export function recordFinish(number, isToday) {
  const stats = loadStats();
  if (!isToday || stats.last === number) return stats;
  const streak = stats.last === number - 1 ? stats.streak + 1 : 1;
  const next = { streak, best: Math.max(stats.best, streak), played: stats.played + 1, last: number };
  write(STATS_KEY, next);
  return next;
}
