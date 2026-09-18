import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Evidence from "../src/components/Evidence.jsx";
import Result from "../src/components/Result.jsx";
import { deriveColumns } from "../src/format.js";
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

  it("drops a column that is empty on this page instead of showing a blank one", () => {
    const seriesColumns = deriveColumns(REFUSAL_WITH_EVIDENCE.evidence.rows);
    expect(seriesColumns).not.toContain("round_number"); // always null on a series row
    expect(deriveColumns(VERSUS.evidence.rows)).toContain("round_number");
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
