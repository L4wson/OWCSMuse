import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import Result from "../src/components/Result.jsx";
import { LEADERBOARD, REFUSAL } from "./fixtures.js";

const READ = {
  role: "team",
  typed: "any",
  entity_type: "org",
  entity_id: "anyones-legend",
  name: "Anyones Legend",
  how: "the start of the name",
  text: "'any' was read as Anyones Legend (the start of the name). If you meant someone else, ask with their exact name.",
};

describe("a name read by a partial match", () => {
  it("is said next to the answer, before the numbers, and not repeated in the notes", () => {
    const answer = { ...LEADERBOARD, read_as: [READ], notes: [READ.text, ...(LEADERBOARD.notes ?? [])] };
    render(<Result answer={answer} onAsk={() => {}} />);

    const notice = screen.getByTestId("read-as");
    expect(notice).toHaveAttribute("role", "status");
    expect(notice).toHaveTextContent("Read “any” as Anyones Legend");
    // before the table: a reader sees how the question was read before reading the ranking
    const aggregate = screen.queryByTestId("aggregate");
    if (aggregate) {
      expect(notice.compareDocumentPosition(aggregate) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
    const context = screen.queryByTestId("context");
    if (context) {
      expect(within(context).queryByText(READ.text)).toBeNull();
    }
  });

  it("is said on a refusal too", () => {
    const answer = { ...REFUSAL, read_as: [READ], notes: [READ.text] };
    render(<Result answer={answer} onAsk={() => {}} />);
    expect(screen.getByTestId("read-as")).toHaveTextContent("Anyones Legend");
  });

  it("is absent when every name was read exactly", () => {
    render(<Result answer={{ ...LEADERBOARD, read_as: [] }} onAsk={() => {}} />);
    expect(screen.queryByTestId("read-as")).toBeNull();
  });
});
