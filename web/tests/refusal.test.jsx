import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Refusal, { nearbyQuestions } from "../src/components/Refusal.jsx";
import { REFUSAL, REFUSAL_WITH_EVIDENCE, SUGGESTIONS } from "./fixtures.js";

describe("refusal", () => {
  it("says plainly what it could not answer", () => {
    render(<Refusal answer={REFUSAL} suggestions={SUGGESTIONS.suggestions} onAsk={() => {}} />);
    expect(screen.getByTestId("refusal-reason")).toHaveTextContent("hero picks are not in the FACEIT payloads");
    expect(screen.getByText("unsupported metric")).toBeInTheDocument();
    expect(screen.getByText(/what stats are available/)).toBeInTheDocument();
  });

  it("is never a dead end: it offers questions that do work", async () => {
    const onAsk = vi.fn();
    render(<Refusal answer={REFUSAL} suggestions={SUGGESTIONS.suggestions} onAsk={onAsk} />);

    const alternatives = screen.getByTestId("alternatives");
    const options = within(alternatives).getAllByRole("button");
    expect(options.length).toBeGreaterThan(0);

    await userEvent.click(options[0]);
    expect(onAsk).toHaveBeenCalledWith(options[0].textContent);
  });

  it("offers the service's own alternatives before generic examples", () => {
    const nearby = nearbyQuestions(REFUSAL_WITH_EVIDENCE, SUGGESTIONS.suggestions);
    expect(nearby.slice(0, REFUSAL_WITH_EVIDENCE.alternatives.length)).toEqual(REFUSAL_WITH_EVIDENCE.alternatives);
    // the first one is the question that actually answers this pairing
    expect(nearby[0]).toBe("Team Falcons series record against Crazy Raccoons");
  });

  it("falls back to live suggestions when the service has nothing specific", () => {
    expect(REFUSAL.alternatives).toEqual([]); // a typo has no better question to offer
    expect(nearbyQuestions(REFUSAL, SUGGESTIONS.suggestions)[0]).toBe(SUGGESTIONS.suggestions[0].question);
  });

  it("renders an informative refusal: no map record, but here are the series", () => {
    render(<Refusal answer={REFUSAL_WITH_EVIDENCE} suggestions={[]} onAsk={() => {}} />);

    expect(screen.getByTestId("refusal-reason")).toHaveTextContent(
      "Team Falcons and Crazy Raccoons met, but none of those series has map stats",
    );
    // the note that explains the gap, next to the answer
    expect(screen.getByTestId("context")).toHaveTextContent("They did meet: 2 series in season 2024");

    // and the series themselves, as rows
    const evidence = screen.getByTestId("evidence");
    expect(evidence).toHaveTextContent("2 series");
    expect(evidence).toHaveTextContent("Dreamhack Dallas");
    expect(evidence).toHaveTextContent("Crazy Raccoons");
    expect(screen.getAllByRole("link", { name: "FACEIT" }).length).toBe(2);
  });

  it("marks the series whose map stats are missing", () => {
    render(<Refusal answer={REFUSAL_WITH_EVIDENCE} suggestions={[]} onAsk={() => {}} />);
    const flags = screen.getAllByTitle("FACEIT recorded no per-map stats for this series");
    expect(flags).toHaveLength(2);
  });

  it("shows no evidence block when there is genuinely nothing behind it", () => {
    render(<Refusal answer={REFUSAL} suggestions={[]} onAsk={() => {}} />);
    expect(screen.queryByTestId("evidence")).not.toBeInTheDocument();
  });
});
