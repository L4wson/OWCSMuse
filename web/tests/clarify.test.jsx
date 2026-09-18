import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Clarify from "../src/components/Clarify.jsx";
import { disambiguatedQuestion } from "../src/format.js";
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
      },
      {
        entity_type: "team",
        entity_id: "9e21c0c1-1111-2222-3333-444455556666",
        current_name: "Team Falcons",
        matched_name: "Team Falcons",
        name_kind: "current_name",
        score: 1,
        matches: 0,
      },
    ],
  },
};

describe("clarify", () => {
  it("asks the question the API asked, and offers every candidate", () => {
    render(<Clarify answer={CLARIFY} question="tea record" onAsk={() => {}} />);
    expect(screen.getByTestId("clarify")).toHaveTextContent("which one?");
    expect(screen.getByText("Team Peps")).toBeInTheDocument();
    expect(screen.getByText("Team Liquid")).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(CLARIFY.candidates.subject.length);
  });

  it("shows what was typed and what each candidate is", () => {
    render(<Clarify answer={CLARIFY} question="tea record" onAsk={() => {}} />);
    expect(screen.getByTestId("clarify")).toHaveTextContent("You typed tea");
    const peps = screen.getByRole("button", { name: /Team Peps/ });
    expect(peps).toHaveTextContent("org");
    expect(peps).toHaveTextContent("55 matches in scope");
  });

  it("separates two candidates that share a name, instead of showing two identical rows", () => {
    render(<Clarify answer={TWO_OF_THE_SAME} question="Team Falcons record" onAsk={() => {}} />);
    const [first, second] = screen.getAllByRole("button");

    expect(within(first).getByText("4 matches in scope")).toBeInTheDocument();
    expect(within(second).getByText("no matches in scope")).toBeInTheDocument();
    expect(first).toHaveTextContent("id 2ab92d33-4c33-46e1-a13f-743a95291d0e");
    expect(second).toHaveTextContent("id 9e21c0c1-1111-2222-3333-444455556666");
    expect(first.textContent).not.toBe(second.textContent);
  });

  it("re-asks the original question with the chosen id in place of the name", async () => {
    const onAsk = vi.fn();
    render(<Clarify answer={TWO_OF_THE_SAME} question="Team Falcons record in 2024" onAsk={onAsk} />);
    await userEvent.click(screen.getAllByRole("button")[1]);
    expect(onAsk).toHaveBeenCalledWith("9e21c0c1-1111-2222-3333-444455556666 record in 2024");
  });

  it("selects an org by name, and says so, because its id is not a question the parser takes", async () => {
    const onAsk = vi.fn();
    const orgTie = {
      ...TWO_OF_THE_SAME,
      candidates: {
        subject: [
          { ...TWO_OF_THE_SAME.candidates.subject[0], entity_type: "org", entity_id: "team-falcons" },
          TWO_OF_THE_SAME.candidates.subject[1],
        ],
      },
    };
    render(<Clarify answer={orgTie} question="Team Falcons record" onAsk={onAsk} />);
    expect(screen.getAllByRole("button")[0]).toHaveTextContent("cannot be picked by id yet");

    await userEvent.click(screen.getAllByRole("button")[0]);
    expect(onAsk).toHaveBeenCalledWith("Team Falcons record");
  });

  it("falls back to a record rather than a dead end when the name is not in the question", () => {
    const candidate = CLARIFY.candidates.subject[1];
    expect(disambiguatedQuestion("who had the most eliminations", null, candidate)).toBe(
      `${candidate.entity_id} record`,
    );
  });
});
