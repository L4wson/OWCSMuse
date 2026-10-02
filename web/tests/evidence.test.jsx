import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Evidence from "../src/components/Evidence.jsx";
import Result from "../src/components/Result.jsx";
import { LEADERBOARD, LEADERBOARD_PARTIAL, REFUSAL_WITH_EVIDENCE, VERSUS, pageOf } from "./fixtures.js";

describe("evidence table", () => {
  it("shows map columns for a map-grain answer", () => {
    render(<Evidence evidence={VERSUS.evidence} />);
    const table = screen.getByRole("table");
    for (const header of ["Date", "Competition", "Map", "Mode", "Result", "Source"]) {
      expect(within(table).getByRole("columnheader", { name: header })).toBeInTheDocument();
    }
    expect(within(table).queryByRole("columnheader", { name: "Best of" })).not.toBeInTheDocument();
    expect(screen.getByTestId("evidence")).toHaveTextContent("42 maps");
  });

  it("shows series columns for a series-grain answer, from the same component", () => {
    render(<Evidence evidence={REFUSAL_WITH_EVIDENCE.evidence} />);
    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Best of" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Map stats" })).toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "Map" })).not.toBeInTheDocument();
    expect(screen.getByTestId("evidence")).toHaveTextContent("2 series");
  });

  it("renders exactly the columns the service described, in that order", () => {
    render(<Evidence evidence={VERSUS.evidence} />);
    const headers = screen.getAllByRole("columnheader").map((th) => th.textContent);
    expect(headers).toEqual(VERSUS.evidence.columns.map((column) => column.label));
    // the service already dropped what is empty at this grain
    expect(REFUSAL_WITH_EVIDENCE.evidence.columns.map((c) => c.key)).not.toContain("round_number");
  });

  it("formats by the declared type, not by the name of a key", () => {
    render(<Evidence evidence={VERSUS.evidence} />);
    const row = VERSUS.evidence.rows[0];
    const cells = screen.getAllByRole("row")[1];
    expect(cells).toHaveTextContent(row.played_at.slice(0, 10)); // a date, not a timestamp
    expect(cells).toHaveTextContent(`${row.score}-${row.opponent_score}`); // a score, one fact
    expect(within(cells).getByRole("link", { name: "FACEIT" })).toBeInTheDocument();
  });

  it("merges a score and its opposite number into one cell", () => {
    render(<Evidence evidence={VERSUS.evidence} />);
    const first = VERSUS.evidence.rows[0];
    expect(screen.getAllByRole("row")[1]).toHaveTextContent(`${first.score}-${first.opponent_score}`);
  });

  it("links every row to its FACEIT match", () => {
    render(<Evidence evidence={VERSUS.evidence} />);
    const links = screen.getAllByRole("link", { name: "FACEIT" });
    expect(links).toHaveLength(VERSUS.evidence.rows.length);
    expect(links[0]).toHaveAttribute("href", VERSUS.evidence.rows[0].match_url);
    expect(links[0]).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
  });

  it("labels every cell so the table can become cards on a phone", () => {
    render(<Evidence evidence={VERSUS.evidence} />);
    const cells = screen.getAllByRole("cell");
    expect(cells.every((cell) => cell.getAttribute("data-label"))).toBe(true);
  });
});

describe("evidence paging", () => {
  it("reports where it is in the whole set", () => {
    render(<Evidence evidence={VERSUS.evidence} />);
    expect(screen.getByTestId("pager-state")).toHaveTextContent("Page 1 of 14");
    expect(screen.getByTestId("evidence")).toHaveTextContent("42 maps");
  });

  it("cannot go newer than the first page", () => {
    render(<Evidence evidence={VERSUS.evidence} onPage={() => {}} />);
    expect(screen.getByRole("button", { name: "Newer" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Older" })).toBeEnabled();
  });

  it("asks for the next page, newest first", async () => {
    const onPage = vi.fn();
    render(<Evidence evidence={VERSUS.evidence} onPage={onPage} />);
    await userEvent.click(screen.getByRole("button", { name: "Older" }));
    expect(onPage).toHaveBeenCalledWith(2);
  });

  it("stops at the last page, following has_more rather than guessing", async () => {
    const last = pageOf(VERSUS, 14);
    expect(last.evidence.has_more).toBe(false);
    render(<Evidence evidence={last.evidence} onPage={() => {}} />);
    expect(screen.getByRole("button", { name: "Older" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Newer" })).toBeEnabled();
  });

  it("hides the pager when everything fits on one page", () => {
    const single = { ...VERSUS.evidence, total_pages: 1, total_rows: 3, has_more: false };
    render(<Evidence evidence={single} onPage={() => {}} />);
    expect(screen.queryByTestId("pager-state")).not.toBeInTheDocument();
  });

  it("disables paging while a page is loading", () => {
    render(<Evidence evidence={VERSUS.evidence} onPage={() => {}} busy />);
    expect(screen.getByRole("button", { name: "Older" })).toBeDisabled();
    expect(screen.getByTestId("evidence")).toHaveAttribute("aria-busy", "true");
  });

  it("explains an answer that has no rows behind it", () => {
    render(<Evidence evidence={{ available: false, reason: "stat availability is already a per-season listing" }} />);
    expect(screen.getByTestId("evidence-none")).toHaveTextContent("per-season listing");
  });
});

describe("a ranked answer", () => {
  const props = { question: "who had the most eliminations in 2024", suggestions: [], onAsk: () => {} };

  it("says whose rows these are", () => {
    render(<Result answer={LEADERBOARD} {...props} />);
    expect(screen.getByTestId("evidence-subject")).toHaveTextContent("kevsteer");
    expect(screen.getByTestId("expand-hint")).toHaveTextContent("Showing the rows behind kevsteer");
    expect(screen.getByTestId("evidence")).toHaveTextContent("49 maps");
  });

  it("links the subject's name to asking about that entity, the same as the answer sentence", async () => {
    const onAsk = vi.fn();
    render(<Result answer={LEADERBOARD} {...props} onAsk={onAsk} />);
    const subject = screen.getByTestId("evidence-subject");
    expect(subject.tagName).toBe("BUTTON");
    expect(subject).toHaveAttribute("data-kind", "player");
    expect(subject).toHaveAttribute("data-entity-id", LEADERBOARD.evidence.expanded_for.id);

    await userEvent.click(subject);
    expect(onAsk).toHaveBeenCalledWith("kevsteer record");
  });

  it("marks the expanded row in the ranking itself", () => {
    render(<Result answer={LEADERBOARD} {...props} onExpand={() => {}} />);
    const aggregate = within(screen.getByTestId("aggregate"));
    const rows = aggregate.getAllByRole("row").slice(1); // drop the header
    expect(rows[0]).toHaveAttribute("aria-current", "true");
    expect(rows[1]).not.toHaveAttribute("aria-current");
    expect(within(rows[0]).getByRole("button")).toHaveAttribute("aria-pressed", "true");
  });

  it("expands another row by the id the API said to use", async () => {
    const onExpand = vi.fn();
    render(<Result answer={LEADERBOARD} {...props} onExpand={onExpand} />);
    const second = LEADERBOARD.aggregate.rows[1];
    const rows = within(screen.getByTestId("aggregate")).getAllByRole("row").slice(1);

    await userEvent.click(within(rows[1]).getByRole("button"));
    expect(LEADERBOARD.evidence.expandable_by).toBe("player_id");
    expect(onExpand).toHaveBeenCalledWith(second.player_id, second);
  });

  it("offers no expansion on an answer that is a single row", () => {
    render(<Result answer={VERSUS} {...props} onExpand={() => {}} />);
    expect(screen.queryByTestId("expand-hint")).not.toBeInTheDocument();
    expect(within(screen.getByTestId("aggregate")).queryByRole("columnheader", { name: "Evidence" })).toBeNull();
  });
});

describe("coverage and limitations", () => {
  const props = { question: "who had the most final blows", suggestions: [], onAsk: () => {} };

  it("says which seasons a partial stat is missing from, next to the answer", () => {
    render(<Result answer={LEADERBOARD_PARTIAL} {...props} />);
    const context = screen.getByTestId("context");
    expect(context).toHaveTextContent("Final Blows");
    expect(context).toHaveTextContent("missing in 2024");
    expect(context).toHaveTextContent("seasons with it: 2025, 2026");
    expect(screen.getByTestId("coverage")).toHaveClass("coverage--partial");
  });

  it("puts the caveats above the table, not below it", () => {
    render(<Result answer={LEADERBOARD_PARTIAL} {...props} />);
    const context = screen.getByTestId("context");
    const aggregate = screen.getByTestId("aggregate");
    expect(context.compareDocumentPosition(aggregate) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows the known limitations in full, not behind a control", () => {
    render(<Result answer={LEADERBOARD_PARTIAL} {...props} />);
    for (const limitation of LEADERBOARD_PARTIAL.limitations) {
      expect(screen.getByTestId(`limitation-${limitation.id}`)).toHaveTextContent(limitation.title);
    }
    expect(screen.getByTestId("limitation-stats_2024")).toHaveTextContent("9-key stat set");
  });

  it("shows the excluded-series note on a versus answer", () => {
    render(<Result answer={VERSUS} question="Sugarfree map record against Zeruhh" suggestions={[]} onAsk={() => {}} />);
    expect(screen.getByTestId("note")).toHaveTextContent("carry no map stats on FACEIT");
  });
});

describe("rows from one answer never survive into the next", () => {
  // Map-grain evidence has several rows per match (one per map), so `match_id` alone is not a row identity.
  const mapRow = (team, matchId, round) => ({
    match_id: matchId, round_number: round, played_at: "2026-05-01T20:00:00Z", competition: "Comp",
    team, opponent: "Opp", map_name: `Map ${round}`, game_mode: "Control", score: 1, opponent_score: 0, result: "won",
  });
  const evidenceOf = (rows) => ({
    available: true, grain: "map", description: "every map", page: 1, page_size: 25, total_rows: rows.length,
    total_pages: 1, has_more: false, rows,
    columns: [
      { key: "team", label: "Team", type: "text" },
      { key: "map_name", label: "Map", type: "text" },
    ],
  });

  it("replaces the previous answer's rows when the same component renders a different answer", () => {
    const cjay = evidenceOf([mapRow("Dallas Fuel", "m1", 1), mapRow("Dallas Fuel", "m1", 2), mapRow("Dallas Fuel", "m1", 3), mapRow("Dallas Fuel", "m2", 1)]);
    const sugarfree = evidenceOf([mapRow("SpaceStation Gaming", "m9", 1), mapRow("SpaceStation Gaming", "m9", 2)]);
    const { rerender } = render(<Evidence evidence={cjay} />);
    expect(screen.getAllByRole("row")).toHaveLength(1 + 4);

    rerender(<Evidence evidence={sugarfree} />);
    const body = screen.getAllByRole("row").slice(1);
    expect(body).toHaveLength(2);
    for (const row of body) {
      expect(row).toHaveTextContent("SpaceStation Gaming");
      expect(row).not.toHaveTextContent("Dallas Fuel");
    }
  });

  it("gives every row a distinct key, whatever the grain", () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<Evidence evidence={evidenceOf([mapRow("A", "m1", 1), mapRow("A", "m1", 2)])} />);
    const duplicateKeyWarnings = errors.mock.calls.filter((call) => String(call[0]).includes("same key"));
    errors.mockRestore();
    expect(duplicateKeyWarnings).toEqual([]);
  });
});

describe("identifiers are not quantities", () => {
  it("prints a season as 2026, and a count with its separator", async () => {
    const { formatCell } = await import("../src/format.js");
    expect(formatCell({ season: 2026 }, { key: "season", type: "identifier" })).toBe("2026");
    expect(formatCell({ season: "2024" }, { key: "season", type: "identifier" })).toBe("2024");
    expect(formatCell({ maps: 1482 }, { key: "maps", type: "integer" })).toBe("1,482");
  });

  it("renders the season column of a real answer without a separator", () => {
    const evidence = {
      available: true, grain: "map", page: 1, total_pages: 1, total_rows: 1, rows: [{ match_id: "m", season: 2026 }],
      columns: [{ key: "season", label: "Season", type: "identifier" }],
    };
    render(<Evidence evidence={evidence} />);
    expect(screen.getByRole("table")).toHaveTextContent("2026");
    expect(screen.getByRole("table")).not.toHaveTextContent("2,026");
  });
});


describe("the source link names its source", () => {
  it("labels a FACEIT room FACEIT and a Liquipedia page Liquipedia", () => {
    const evidence = {
      available: true, grain: "series", page: 1, total_pages: 1, total_rows: 2,
      rows: [
        { match_id: "1-abc", team: "A", match_url: "https://www.faceit.com/en/ow2/room/1-abc" },
        { match_id: "lp:1_B1_0001", team: "B", match_url: "https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/Major" },
      ],
      columns: [{ key: "team", label: "Team", type: "text" }, { key: "match_url", label: "Source", type: "link" }],
    };
    render(<Evidence evidence={evidence} />);
    const links = screen.getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(["FACEIT", "Liquipedia"]);
  });
});
