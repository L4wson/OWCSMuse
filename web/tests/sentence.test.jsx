import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AnswerSentence, { segments } from "../src/components/AnswerSentence.jsx";
import { VERSUS } from "./fixtures.js";

describe("answer sentence", () => {
  it("renders the whole sentence exactly as the API wrote it", () => {
    render(<AnswerSentence sentence={VERSUS.sentence} />);
    expect(screen.getByTestId("answer-sentence")).toHaveTextContent(
      "sug2rfree is 22-20 in maps against zeruhh across 2024-2026.",
    );
  });

  it("links the entities the API marked, carrying their resolved ids", async () => {
    const onAsk = vi.fn();
    render(<AnswerSentence sentence={VERSUS.sentence} onAsk={onAsk} />);

    const sugarfree = screen.getByRole("button", { name: "sug2rfree" });
    const zeruhh = screen.getByRole("button", { name: "zeruhh" });
    expect(sugarfree).toHaveAttribute("data-entity-id", "58239fd5-cf2f-4894-a2ec-30fd026c262a");
    expect(zeruhh).toHaveAttribute("data-entity-id", "58faa695-b501-4642-a4d9-0e4c2ed8526d");

    await userEvent.click(zeruhh);
    expect(onAsk).toHaveBeenCalledWith("zeruhh record");
  });

  it("uses the offsets, not the words: the same name is linked only where the span says", () => {
    // "Ilios" appears twice; only the second one is an entity span.
    const sentence = {
      text: "Ilios is not Ilios.",
      spans: [{ start: 13, end: 18, kind: "map", text: "Ilios", entity_id: null }],
    };
    render(<AnswerSentence sentence={sentence} onAsk={() => {}} />);
    const links = screen.getAllByRole("button", { name: "Ilios" });
    expect(links).toHaveLength(1);
    expect(screen.getByTestId("answer-sentence")).toHaveTextContent("Ilios is not Ilios.");
  });

  it("marks non-entity spans without making them links", () => {
    const sentence = {
      text: "Twisted Minds went 30-12 in maps in 2024 and 31-10 in 2026.",
      spans: [
        { start: 0, end: 13, kind: "org", text: "Twisted Minds", entity_id: "twisted-minds" },
        { start: 36, end: 40, kind: "season", text: "2024", entity_id: null },
        { start: 53, end: 57, kind: "season", text: "2026", entity_id: null },
      ],
    };
    render(<AnswerSentence sentence={sentence} onAsk={() => {}} />);
    expect(screen.getAllByRole("button")).toHaveLength(1); // the org only
    expect(screen.getByText("2024")).toHaveAttribute("data-kind", "season");
  });

  it("drops spans that do not fit the text rather than trusting them", () => {
    const parts = segments("short", [
      { start: 0, end: 99, kind: "player" },
      { start: -3, end: 2, kind: "player" },
      { start: 2, end: 2, kind: "player" },
    ]);
    expect(parts).toEqual([{ text: "short" }]);
  });

  it("keeps the first of two overlapping spans", () => {
    const parts = segments("abcdef", [
      { start: 0, end: 3, kind: "player" },
      { start: 2, end: 5, kind: "team" },
    ]);
    expect(parts.map((p) => p.text)).toEqual(["abc", "def"]);
    expect(parts[0].span.kind).toBe("player");
  });

  it("renders nothing when there is no sentence", () => {
    const { container } = render(<AnswerSentence sentence={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
