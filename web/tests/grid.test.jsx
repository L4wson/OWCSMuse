import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "../src/App.jsx";
import { pathToRoute } from "../src/router.js";
import {
  applyGuess,
  cellOf,
  guessesLeft,
  isOver,
  loadGame,
  loadStats,
  newGame,
  recordFinish,
  saveGame,
  score,
  shareText,
} from "../src/grid/game.js";
import { SUGGESTIONS, mockFetch, ok, fail } from "./fixtures.js";

// Payloads in the shape /api/grid returns (captured from the running service, 2026-11-17, and cut down).
const PUZZLE = {
  number: 4,
  date: "2026-11-21",
  is_today: true,
  rows: [
    { key: "tank", label: "Tank" },
    { key: "dps", label: "DPS" },
    { key: "support", label: "Support" },
  ],
  cols: [
    { key: "2026", label: "2026", help: "10+ maps in the role in the 2026 season" },
    { key: "2025", label: "2025", help: "10+ maps in the role in the 2025 season" },
    { key: "emea", label: "EMEA", help: "10+ maps in the role in OWCS EMEA" },
  ],
  guesses: 9,
  min_maps: 10,
  coverage: "Answers are players with 10 or more maps in the role inside the column, from FACEIT map stats.",
};
const HAWK = { id: "a940981f", name: "Hawk", detail: "SpaceStation Gaming, 2024-2026", matched: "TheeHawk" };
const DANNY_A = { id: "16e56097", name: "Danny", detail: "Shikigami, 2024-2025", matched: null };
const DANNY_B = { id: "2d211a8f", name: "Danny", detail: "Team Liquid, 2024-2025", matched: null };
const LATE = { id: "lp:player:Late", name: "Late", detail: "Tanuki, 2024", matched: null };
const REVEAL = {
  puzzle: 4,
  per_cell: 5,
  cells: Array.from({ length: 9 }, (_, cell) => ({ cell, examples: [{ id: `x${cell}`, name: `Example${cell}`, maps: 40 + cell }] })),
};

const verdict = (cell, player, result, extra = {}) => ({
  puzzle: 4,
  cell,
  player: { id: player.id, name: player.name },
  result,
  uses_guess: result !== "cannot_verify",
  ...extra,
});

function guessResponder({ body }) {
  if (body.player_id === HAWK.id && body.cell === 0) {
    return ok(verdict(0, HAWK, "correct", { maps: 41, explanation: "41 Tank maps in 2026 (FACEIT map stats)", link: null }));
  }
  if (body.player_id === LATE.id) {
    return ok(verdict(body.cell, LATE, "cannot_verify", { explanation: "There is no role data for Late in this column (2026), so the guess can't be checked. It didn't use a guess." }));
  }
  const player = [HAWK, DANNY_A, DANNY_B].find((p) => p.id === body.player_id);
  return ok(verdict(body.cell, player, "wrong"));
}

function mountGrid(path = "/grid", routes = []) {
  window.history.replaceState({}, "", path);
  const fetchMock = mockFetch([
    ...routes,
    ["/api/grid/today", ok(PUZZLE)],
    ["/api/grid/archive", ok({ puzzles: [{ number: 4, date: "2026-11-21", is_today: true, cols: ["2026", "2025", "EMEA"] }, { number: 3, date: "2026-11-20", is_today: false, cols: ["Played all 3 seasons", "2026", "NA"] }] })],
    ["/api/grid/players?q=haw", ok({ query: "haw", players: [HAWK] })],
    ["/api/grid/players?q=dan", ok({ query: "dan", players: [DANNY_A, DANNY_B] })],
    ["/api/grid/players?q=late", ok({ query: "late", players: [LATE] })],
    ["/api/grid/players", ok({ query: "", players: [] })],
    [/\/api\/grid\/4\/guess$/, guessResponder],
    [/\/api\/grid\/4\/reveal$/, ok(REVEAL)],
    [/\/api\/grid\/3$/, ok({ ...PUZZLE, number: 3, date: "2026-11-20", is_today: false })],
    ["/suggestions", ok(SUGGESTIONS)],
  ]);
  vi.stubGlobal("fetch", fetchMock);
  return { ...render(<App />), fetchMock };
}

async function guess(cell, typed, pickName, pickDetail) {
  await userEvent.click(await screen.findByTestId(`cell-${cell}`));
  await userEvent.type(screen.getByRole("textbox"), typed);
  const options = await screen.findAllByRole("button", { name: new RegExp(pickName) });
  const option = pickDetail ? options.find((o) => o.textContent.includes(pickDetail)) : options[0];
  await userEvent.click(option);
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("grid routes", () => {
  it("reads /grid, a numbered puzzle and the archive, and leaves the question routes alone", () => {
    expect(pathToRoute("/grid")).toEqual({ name: "grid", view: "today" });
    expect(pathToRoute("/grid/")).toEqual({ name: "grid", view: "today" });
    expect(pathToRoute("/grid/12")).toEqual({ name: "grid", view: "puzzle", number: 12 });
    expect(pathToRoute("/grid/archive")).toEqual({ name: "grid", view: "archive" });
    expect(pathToRoute("/grid/0")).toEqual({ name: "home" });
    expect(pathToRoute("/gridiron")).toEqual({ name: "home" });
    expect(pathToRoute("/q/V5iNpKcbhata")).toEqual({ name: "query", slug: "V5iNpKcbhata" });
    expect(pathToRoute("/")).toEqual({ name: "home" });
  });
});

describe("game rules", () => {
  it("spends a guess on a right or wrong answer and none on a can't-verify", () => {
    let game = newGame();
    game = applyGuess(game, 9, verdict(0, HAWK, "correct", { explanation: "41 Tank maps" }));
    expect([score(game), guessesLeft(game, 9)]).toEqual([1, 8]);
    game = applyGuess(game, 9, verdict(1, DANNY_A, "wrong"));
    expect([score(game), guessesLeft(game, 9)]).toEqual([1, 7]);
    game = applyGuess(game, 9, verdict(1, LATE, "cannot_verify"));
    expect([score(game), guessesLeft(game, 9)]).toEqual([1, 7]);
    expect(game.filled[1]).toBeUndefined();
    expect(cellOf(game, HAWK.id)).toBe(0);
    expect(cellOf(game, DANNY_A.id)).toBeNull();
  });

  it("ends after nine guesses and takes no more", () => {
    let game = newGame();
    for (let i = 0; i < 9; i += 1) game = applyGuess(game, 9, verdict(0, DANNY_A, "wrong"));
    expect(isOver(game, 9)).toBe(true);
    const after = applyGuess(game, 9, verdict(0, HAWK, "correct", { explanation: "x" }));
    expect(score(after)).toBe(0);
  });

  it("shares the number, the score, squares and the link, and never a name", () => {
    let game = newGame();
    game = applyGuess(game, 9, verdict(0, HAWK, "correct", { explanation: "41 Tank maps" }));
    game = applyGuess(game, 9, verdict(4, DANNY_A, "correct", { explanation: "20 DPS maps" }));
    const text = shareText(12, game, "https://owcsmuse.vercel.app/grid/12");
    expect(text).toBe("OWCS Grid #12  2/9\n🟩⬜⬜\n⬜🟩⬜\n⬜⬜⬜\nhttps://owcsmuse.vercel.app/grid/12");
    expect(text).not.toMatch(/Hawk|Danny/);
  });

  it("keeps a game across a reload, and plays on when storage refuses", () => {
    const game = applyGuess(newGame(), 9, verdict(0, HAWK, "correct", { explanation: "41 Tank maps" }));
    expect(saveGame(4, game)).toBe(true);
    expect(loadGame(4)).toEqual(game);
    expect(loadGame(5)).toEqual(newGame());

    window.localStorage.setItem("owcs-grid:v1:puzzle:6", "{not json");
    expect(loadGame(6)).toEqual(newGame());
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    expect(saveGame(4, game)).toBe(false);
    expect(loadGame(4)).toEqual(newGame());
    expect(loadStats().streak).toBe(0);
    expect(recordFinish(4, true).streak).toBe(1);
  });

  it("counts a streak over consecutive daily puzzles only", () => {
    expect(recordFinish(4, true).streak).toBe(1);
    expect(recordFinish(4, true).streak).toBe(1); // the same puzzle again
    expect(recordFinish(3, false).streak).toBe(1); // an archive puzzle
    expect(recordFinish(5, true).streak).toBe(2);
    expect(recordFinish(7, true)).toMatchObject({ streak: 1, best: 2, played: 3 }); // a day missed
  });
});

describe("the grid page", () => {
  it("shows the board, the rules and the coverage note, and asks for no suggestions or answers", async () => {
    const { fetchMock } = mountGrid();
    const board = await screen.findByTestId("grid-board");
    expect(within(board).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["2026", "2025", "EMEA"]);
    expect(within(board).getAllByRole("rowheader").map((h) => h.textContent)).toEqual(["Tank", "DPS", "Support"]);
    expect(screen.getByTestId("grid-status")).toHaveTextContent("9 guesses left · 0/9 filled");
    expect(screen.getByTestId("grid-coverage")).toHaveTextContent("FACEIT map stats");
    expect(screen.getByText("How to play")).toBeInTheDocument();
    expect(screen.getByTestId("privacy")).toBeInTheDocument(); // Muse's own footer, with its attribution
    expect(screen.getByRole("link", { name: "Liquipedia" })).toBeInTheDocument();
    expect(screen.queryByTestId("grid-nav")).not.toBeInTheDocument();
    const asked = fetchMock.calls.map((call) => call.url);
    expect(asked.some((url) => url.includes("/suggestions"))).toBe(false);
    expect(asked.some((url) => url.includes("/reveal"))).toBe(false);
  });

  it("fills a cell with a player picked from the list, by id, and shows why", async () => {
    const { fetchMock } = mountGrid();
    await guess(0, "haw", "Hawk");
    const cell = await screen.findByTestId("cell-0");
    await waitFor(() => expect(cell).toHaveTextContent("Hawk"));
    expect(cell).toHaveTextContent("41 Tank maps in 2026 (FACEIT map stats)");
    expect(screen.getByTestId("grid-status")).toHaveTextContent("8 guesses left · 1/9 filled");
    const sent = fetchMock.calls.find((call) => call.url.endsWith("/api/grid/4/guess"));
    expect(sent).toMatchObject({ method: "POST", body: { cell: 0, player_id: HAWK.id } });
    expect(loadGame(4).filled[0]).toMatchObject({ id: HAWK.id, name: "Hawk" });
  });

  it("tells two players with one name apart, and sends the one that was picked", async () => {
    const { fetchMock } = mountGrid();
    await userEvent.click(await screen.findByTestId("cell-3"));
    await userEvent.type(screen.getByRole("textbox"), "dan");
    const options = await screen.findAllByRole("button", { name: /Danny/ });
    expect(options.map((o) => o.textContent)).toEqual(["DannyShikigami, 2024-2025", "DannyTeam Liquid, 2024-2025"]);
    await userEvent.click(options[1]);
    await screen.findByTestId("grid-notice");
    const sent = fetchMock.calls.find((call) => call.url.endsWith("/guess"));
    expect(sent.body).toEqual({ cell: 3, player_id: DANNY_B.id });
    expect(screen.getByTestId("grid-notice")).toHaveTextContent("Danny is not a DPS × 2026 answer.");
    expect(screen.getByTestId("grid-status")).toHaveTextContent("8 guesses left · 0/9 filled");
  });

  it("spends no guess on a can't-verify and leaves the cell open", async () => {
    mountGrid();
    await guess(0, "late", "Late");
    expect(await screen.findByTestId("grid-notice")).toHaveTextContent("no role data for Late");
    expect(screen.getByTestId("grid-status")).toHaveTextContent("9 guesses left · 0/9 filled");
    expect(screen.getByTestId("cell-0")).toHaveAttribute("aria-pressed", "true");
  });

  it("will not let one player fill two cells", async () => {
    mountGrid();
    await guess(0, "haw", "Hawk");
    await waitFor(() => expect(screen.getByTestId("cell-0")).toHaveTextContent("Hawk"));
    await userEvent.click(screen.getByTestId("cell-1"));
    await userEvent.type(screen.getByRole("textbox"), "haw");
    const option = await screen.findByRole("button", { name: /Hawk/ });
    expect(option).toBeDisabled();
    expect(option).toHaveTextContent("already used in this grid");
  });

  it("ends with the score, a share text with no names, and example answers fetched only then", async () => {
    const { fetchMock } = mountGrid();
    await guess(0, "haw", "Hawk");
    await waitFor(() => expect(screen.getByTestId("cell-0")).toHaveTextContent("Hawk"));
    expect(fetchMock.calls.some((call) => call.url.includes("/reveal"))).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: /end game/i }));
    const end = await screen.findByTestId("grid-end");
    expect(end).toHaveTextContent("1/9");
    const shared = screen.getByTestId("grid-share-text").textContent;
    expect(shared).toBe(`OWCS Grid #4  1/9\n🟩⬜⬜\n⬜⬜⬜\n⬜⬜⬜\n${window.location.origin}/grid/4`);
    expect(shared).not.toContain("Hawk");
    expect(await screen.findByTestId("grid-reveal")).toHaveTextContent("Example0 (40)");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(loadStats()).toMatchObject({ streak: 1, last: 4 });
  });

  it("copies the share text when there is no share sheet", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...window.navigator, share: undefined, clipboard: { writeText } });
    saveGame(4, { ...newGame(), over: true });
    mountGrid();
    await userEvent.click(await screen.findByRole("button", { name: "Share result" }));
    expect(writeText).toHaveBeenCalledWith(`OWCS Grid #4  0/9\n⬜⬜⬜\n⬜⬜⬜\n⬜⬜⬜\n${window.location.origin}/grid/4`);
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("picks a saved game back up", async () => {
    saveGame(4, applyGuess(newGame(), 9, verdict(0, HAWK, "correct", { explanation: "41 Tank maps in 2026 (FACEIT map stats)" })));
    mountGrid();
    await waitFor(() => expect(screen.getByTestId("cell-0")).toHaveTextContent("Hawk"));
    expect(screen.getByTestId("grid-status")).toHaveTextContent("8 guesses left · 1/9 filled");
  });

  it("lists the archive with this browser's scores, and opens an earlier puzzle", async () => {
    saveGame(3, { ...applyGuess(newGame(), 9, verdict(0, HAWK, "correct", { explanation: "x" })), over: true });
    mountGrid("/grid/archive");
    const list = await screen.findByTestId("grid-archive");
    const rows = within(list).getAllByRole("link");
    expect(rows.map((row) => row.textContent)).toEqual(["#42026 · 2025 · EMEA2026-11-21 · todayplay", "#3Played all 3 seasons · 2026 · NA2026-11-201/9"]);
    await userEvent.click(rows[1]);
    expect(window.location.pathname).toBe("/grid/3");
    expect(await screen.findByText(/from the archive/)).toBeInTheDocument();
  });

  it("says so when there is no puzzle today, and is not an error page for the rest of the site", async () => {
    mountGrid("/grid", [["/api/grid/today", fail(404, "no puzzle is published for 2026-12-02")]]);
    expect(await screen.findByTestId("grid-error")).toHaveTextContent("There is no puzzle for today yet.");
    expect(screen.getByRole("link", { name: "See the archive" })).toBeInTheDocument();
  });
});

// A mixed-clue puzzle, in the shape /api/grid returns for one (captured 2026-11-17, cut down).
const MIXED = {
  number: 4,
  date: "2026-11-21",
  is_today: true,
  kind: "mixed",
  difficulty: "Hard",
  rows: [
    { key: "row0", family: "stats", label: "Top 25% fewest deaths/10, 2025 NA/EMEA", help: "In the lowest 25% for deaths per 10 minutes among players of the same role, 2025 season, OWCS NA/EMEA main series." },
    { key: "row1", family: "lan", label: "Rostered at 2026 Champions Clash", help: "On a team's roster at 2026 Champions Clash, per Liquipedia's line-ups. Rostered, not necessarily played." },
    { key: "row2", family: "stage", label: "Won an OWCS stage", help: "Played 1+ playoff map for the team that won an OWCS NA or EMEA stage's playoffs (FACEIT map stats)." },
  ],
  cols: [
    { key: "col0", family: "teammate", label: "Teammate of kevster", help: "Played 1+ map on the same team as kevster in OWCS NA/EMEA main series (FACEIT map stats). kevster is not an answer." },
    { key: "col1", family: "org", label: "Played for NTMR", help: "Played 1+ map for NTMR in OWCS NA/EMEA main series (FACEIT map stats)." },
    { key: "col2", family: "teammate", label: "Teammate of Admiral", help: "Played 1+ map on the same team as Admiral in OWCS NA/EMEA main series (FACEIT map stats). Admiral is not an answer." },
  ],
  guesses: 9,
  min_maps: null,
  coverage: "Unless a clue says otherwise, answers come from FACEIT map stats. Tap a clue to see exactly what it means.",
};
const MIXED_REVEAL = {
  puzzle: 4,
  per_cell: 5,
  cells: [8, 4, 5, 5, 5, 6, 9, 7, 10].map((count, cell) => ({
    cell,
    count,
    examples: [{ id: `x${cell}`, name: `Example${cell}`, why: "a reason" }],
  })),
};
const CHASE_WHY = "4.3 deaths/10 as Tank in 2025, #3 of 28. 21 maps together, most on The Ultimates in 2025 EMEA Stage 1";

function mountMixed() {
  window.history.replaceState({}, "", "/grid");
  const fetchMock = mockFetch([
    ["/api/grid/today", ok(MIXED)],
    ["/api/grid/players?q=haw", ok({ query: "haw", players: [HAWK] })],
    ["/api/grid/players?q=late", ok({ query: "late", players: [LATE] })],
    [
      /\/api\/grid\/4\/guess$/,
      ({ body }) =>
        body.player_id === HAWK.id
          ? ok(verdict(body.cell, HAWK, "correct", { explanation: CHASE_WHY, link: null }))
          : ok(verdict(body.cell, LATE, "cannot_verify", { clue: "Teammate of kevster", explanation: "They were rostered with kevster only in series we have no map data for, so we can't tell whether they played together. It didn't use a guess." })),
    ],
    [/\/api\/grid\/4\/reveal$/, ok(MIXED_REVEAL)],
  ]);
  vi.stubGlobal("fetch", fetchMock);
  return { ...render(<App />), fetchMock };
}

describe("a mixed-clue puzzle", () => {
  it("shows its difficulty and every clue as a header, long ones included", async () => {
    mountMixed();
    const board = await screen.findByTestId("grid-board");
    expect(screen.getByTestId("grid-difficulty")).toHaveTextContent("Hard");
    expect(within(board).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Teammate of kevster", "Played for NTMR", "Teammate of Admiral"]);
    expect(within(board).getAllByRole("rowheader").map((h) => h.textContent)).toEqual([
      "Top 25% fewest deaths/10, 2025 NA/EMEA",
      "Rostered at 2026 Champions Clash",
      "Won an OWCS stage",
    ]);
    expect(board.className).toContain("grid-board--wide");
    expect(screen.getByTestId("grid-coverage")).toHaveTextContent("Tap a clue");
  });

  it("opens a clue's definition when its header is tapped, and closes it again", async () => {
    mountMixed();
    const header = await screen.findByTestId("head-row1");
    expect(header).toHaveAttribute("title", expect.stringContaining("Rostered, not necessarily played"));
    expect(screen.queryByTestId("grid-info")).not.toBeInTheDocument();
    await userEvent.click(header);
    expect(screen.getByTestId("grid-info")).toHaveTextContent("Rostered at 2026 Champions Clash");
    expect(screen.getByTestId("grid-info")).toHaveTextContent("per Liquipedia's line-ups");
    expect(header).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(screen.getByTestId("head-col0")); // another clue replaces it
    expect(screen.getByTestId("grid-info")).toHaveTextContent("kevster is not an answer");
    await userEvent.click(screen.getByTestId("head-col0"));
    expect(screen.queryByTestId("grid-info")).not.toBeInTheDocument();
  });

  it("writes out the reason the service gave, in the cell and in full under the board", async () => {
    mountMixed();
    await guess(0, "haw", "Hawk");
    await waitFor(() => expect(screen.getByTestId("cell-0")).toHaveTextContent("Hawk"));
    expect(screen.getByTestId("grid-yours")).toHaveTextContent(CHASE_WHY);
    expect(screen.getByTestId("grid-yours")).toHaveTextContent("Top 25% fewest deaths/10, 2025 NA/EMEA × Teammate of kevster");
  });

  it("shows the clue's own can't-verify sentence and spends no guess", async () => {
    mountMixed();
    await guess(0, "late", "Late");
    expect(await screen.findByTestId("grid-notice")).toHaveTextContent("rostered with kevster only in series we have no map data for");
    expect(screen.getByTestId("grid-status")).toHaveTextContent("9 guesses left · 0/9 filled");
  });

  it("shows how many answers each cell had only once the game is over", async () => {
    mountMixed();
    await screen.findByTestId("grid-board");
    expect(screen.queryByTestId("count-0")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /end game/i }));
    expect(await screen.findByTestId("count-0")).toHaveTextContent("8 possible");
    expect(screen.getByTestId("count-8")).toHaveTextContent("10 possible");
    const reveal = screen.getByTestId("grid-reveal");
    expect(reveal).toHaveTextContent("4 possible answers");
    expect(reveal).toHaveTextContent("Example1");
    expect(reveal).not.toHaveTextContent("undefined");
  });
});

describe("links from an answer to Muse", () => {
  const LINK = "/?q=player%3Aa940981f-c750-40b9-bb55-bd3e8e6ef986%20record";

  function mountLinked() {
    window.history.replaceState({}, "", "/grid");
    const fetchMock = mockFetch([
      ["/api/grid/today", ok(MIXED)],
      ["/api/grid/players?q=haw", ok({ query: "haw", players: [HAWK] })],
      [/\/api\/grid\/4\/guess$/, ({ body }) => ok(verdict(body.cell, HAWK, "correct", { explanation: CHASE_WHY, link: LINK }))],
      [
        /\/api\/grid\/4\/reveal$/,
        ok({
          ...MIXED_REVEAL,
          cells: MIXED_REVEAL.cells.map((entry) => ({
            ...entry,
            examples: [
              { id: "g", name: "Linked", why: "a reason", link: LINK },
              { id: "lp:player:Shu", name: "Unlinked", why: "a reason", link: null },
            ],
          })),
        }),
      ],
    ]);
    vi.stubGlobal("fetch", fetchMock);
    return { ...render(<App />), fetchMock };
  }

  it("links a filled answer to the question the service named, and keeps it across a reload", async () => {
    const first = mountLinked();
    await guess(0, "haw", "Hawk");
    const link = await screen.findByTestId("grid-muse-link");
    expect(link).toHaveTextContent("Ask Muse about Hawk");
    expect(link).toHaveAttribute("href", LINK);
    expect(loadGame(4).filled[0].link).toBe(LINK);
    first.unmount();
    mountLinked();
    expect(await screen.findByTestId("grid-muse-link")).toHaveAttribute("href", LINK);
  });

  it("links each revealed example that has a link, and leaves the others as plain names", async () => {
    mountLinked();
    await screen.findByTestId("grid-board");
    await userEvent.click(screen.getByRole("button", { name: /end game/i }));
    const reveal = await screen.findByTestId("grid-reveal");
    const linked = within(reveal).getAllByRole("link", { name: "Linked" });
    expect(linked).toHaveLength(9);
    expect(linked[0]).toHaveAttribute("href", LINK);
    expect(within(reveal).queryByRole("link", { name: "Unlinked" })).not.toBeInTheDocument();
    expect(reveal).toHaveTextContent("Linked, Unlinked");
  });

  it("shows no link when the service sent none", async () => {
    mountMixed(); // its correct verdict carries link: null
    await guess(0, "haw", "Hawk");
    await waitFor(() => expect(screen.getByTestId("cell-0")).toHaveTextContent("Hawk"));
    expect(screen.queryByTestId("grid-muse-link")).not.toBeInTheDocument();
  });
});

describe("a beta puzzle after the change", () => {
  it("has no difficulty badge, keeps its short headers, and still explains them", async () => {
    mountGrid();
    const board = await screen.findByTestId("grid-board");
    expect(screen.queryByTestId("grid-difficulty")).not.toBeInTheDocument();
    expect(board.className).not.toContain("grid-board--wide");
    await userEvent.click(screen.getByTestId("head-col1"));
    expect(screen.getByTestId("grid-info")).toHaveTextContent("10+ maps in the role in the 2025 season");
  });
});

describe("the nav link", () => {
  it("is hidden unless VITE_GRID_NAV is true, and /grid works either way", async () => {
    vi.stubEnv("VITE_GRID_NAV", "true");
    vi.resetModules();
    const { default: FlaggedApp } = await import("../src/App.jsx");
    window.history.replaceState({}, "", "/");
    vi.stubGlobal("fetch", mockFetch([["/suggestions", ok(SUGGESTIONS)], ["/api/grid/today", ok(PUZZLE)]]));
    render(<FlaggedApp />);
    await userEvent.click(await screen.findByTestId("grid-nav"));
    expect(window.location.pathname).toBe("/grid");
    expect(await screen.findByTestId("grid-board")).toBeInTheDocument();
    vi.unstubAllEnvs();
  });
});
