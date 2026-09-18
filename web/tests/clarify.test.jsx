import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Clarify from "../src/components/Clarify.jsx";
import { CLARIFY } from "./fixtures.js";

const TWO_OF_THE_SAME = {
  status: "clarify",
  code: "ambiguous_entity",
  reason: "'Team Falcons' could be several player/teams; which one?",
  query: { intent: "team_record", filters: { subject: "team falcons" } },
  candidates: {
    subject: [
      {
        entity_type: "team",
        entity_id: "2ab92d33-4c33-46e1-a13f-743a95291d0e",
        current_name: "Team Falcons",
        matched_name: "Team Falcons",
        name_kind: "current_name",
        score: 1,
        matches: 4,
        seasons: [2024],
        first_at: "2024-05-31T00:00:00Z",
        last_at: "2024-06-02T00:00:00Z",
        question: "team:2ab92d33-4c33-46e1-a13f-743a95291d0e record in 2024",
      },
      {
        entity_type: "team",
        entity_id: "9e21c0c1-1111-2222-3333-444455556666",
        current_name: "Team Falcons",
        matched_name: "Team Falcons",
        name_kind: "current_name",
        score: 1,
        matches: 0,
        seasons: [],
        first_at: null,
        last_at: null,
        question: "team:9e21c0c1-1111-2222-3333-444455556666 record in 2024",
      },
    ],
  },
};

describe("clarify", () => {
  it("asks the question the API asked, and offers every candidate", () => {
    render(<Clarify answer={CLARIFY} onAsk={() => {}} />);
    expect(screen.getByTestId("clarify")).toHaveTextContent("which one?");
    expect(screen.getByText("Team Peps")).toBeInTheDocument();
    expect(screen.getByText("Team Liquid")).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(CLARIFY.candidates.subject.length);
  });

  it("shows what was typed and what each candidate is", () => {
    render(<Clarify answer={CLARIFY} onAsk={() => {}} />);
    expect(screen.getByTestId("clarify")).toHaveTextContent("You typed tea");
    const peps = screen.getByRole("button", { name: /Team Peps/ });
    expect(peps).toHaveTextContent("org");
    expect(peps).toHaveTextContent("55 matches in scope");
  });

  it("separates two candidates that share a name, instead of showing two identical rows", () => {
    render(<Clarify answer={TWO_OF_THE_SAME} onAsk={() => {}} />);
    const [first, second] = screen.getAllByRole("button");

    expect(within(first).getByText("4 matches in scope")).toBeInTheDocument();
    expect(within(second).getByText("no matches in scope")).toBeInTheDocument();
    expect(first).toHaveTextContent("id 2ab92d33-4c33-46e1-a13f-743a95291d0e");
    expect(second).toHaveTextContent("id 9e21c0c1-1111-2222-3333-444455556666");
    expect(first).toHaveTextContent("season 2024");           // one has an era, the other never played
    expect(first.textContent).not.toBe(second.textContent);
  });

  it("asks the question the service shipped with the candidate, verbatim", async () => {
    const onAsk = vi.fn();
    render(<Clarify answer={TWO_OF_THE_SAME} onAsk={onAsk} />);
    await userEvent.click(screen.getAllByRole("button")[1]);
    expect(onAsk).toHaveBeenCalledWith(TWO_OF_THE_SAME.candidates.subject[1].question);
  });

  it("selects an org by its id, which the service guarantees resolves", async () => {
    const onAsk = vi.fn();
    const org = CLARIFY.candidates.subject.find((c) => c.entity_type === "org");
    expect(org.question).toMatch(/^org:/); // not a name, which is what fails on a tie

    render(<Clarify answer={CLARIFY} onAsk={onAsk} />);
    await userEvent.click(screen.getByRole("button", { name: new RegExp(org.current_name) }));
    expect(onAsk).toHaveBeenCalledWith(org.question);
  });

  it("shows when each candidate was active, which is what tells two eras apart", () => {
    render(<Clarify answer={CLARIFY} onAsk={() => {}} />);
    for (const candidate of CLARIFY.candidates.subject) {
      const option = screen.getByRole("button", { name: new RegExp(candidate.current_name) });
      expect(option).toHaveTextContent(`seasons ${candidate.seasons.join(", ")}`);
    }
  });

  it("constructs no question of its own", () => {
    render(<Clarify answer={CLARIFY} onAsk={() => {}} />);
    for (const [index, option] of screen.getAllByRole("button").entries()) {
      expect(option).toHaveAttribute("data-question", CLARIFY.candidates.subject[index].question);
    }
  });
});
