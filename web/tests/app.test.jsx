import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "../src/App.jsx";
import { CLARIFY, LEADERBOARD, SUGGESTIONS, VERSUS, mockFetch, ok, fail, pageOf } from "./fixtures.js";

function mount(routes) {
  const fetchMock = mockFetch([["/suggestions", ok(SUGGESTIONS)], ...routes]);
  vi.stubGlobal("fetch", fetchMock);
  return { ...render(<App />), fetchMock };
}

describe("landing", () => {
  it("is a question box and examples from the service, nothing else", async () => {
    mount([]);
    expect(await screen.findByTestId("suggestions")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /ask about owcs/i })).toHaveFocus();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    const examples = within(screen.getByTestId("suggestions")).getAllByRole("button");
    expect(examples.length).toBeGreaterThanOrEqual(3);
    expect(examples.length).toBeLessThanOrEqual(4);
  });

  it("runs an example when it is clicked", async () => {
    const { fetchMock } = mount([["/ask", ok(LEADERBOARD)]]);
    const example = (await screen.findAllByRole("button", { name: SUGGESTIONS.suggestions[0].question }))[0];
    await userEvent.click(example);

    await screen.findByTestId("answer");
    const asked = fetchMock.calls.find((call) => call.url.includes("/ask"));
    expect(asked.body.question).toBe(SUGGESTIONS.suggestions[0].question);
  });

  it("still works when the suggestions call fails", async () => {
    mount([["/suggestions", fail(503)], ["/ask", ok(VERSUS)]]);
    expect(await screen.findByRole("textbox", { name: /ask about owcs/i })).toBeInTheDocument();
    expect(screen.queryByTestId("error")).not.toBeInTheDocument();
  });
});

describe("asking", () => {
  it("shows a loading state, then the answer", async () => {
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    mount([["/ask", async () => { await gate; return ok(VERSUS); }]]);

    await userEvent.type(await screen.findByRole("textbox"), "Sugarfree map record against Zeruhh{Enter}");
    expect(await screen.findByTestId("loading")).toBeInTheDocument();

    release();
    expect(await screen.findByTestId("answer-sentence")).toHaveTextContent("sug2rfree is 22-20 in maps");
    expect(screen.queryByTestId("loading")).not.toBeInTheDocument();
  });

  it("puts the answer on its own URL", async () => {
    mount([["/ask", ok(VERSUS)]]);
    await userEvent.type(await screen.findByRole("textbox"), "Sugarfree map record against Zeruhh{Enter}");
    await screen.findByTestId("answer");
    expect(window.location.pathname).toBe(`/q/${VERSUS.slug}`);
    expect(screen.getByTestId("share")).toHaveTextContent(`/q/${VERSUS.slug}`);
  });

  it("loads a shared link by running the question again", async () => {
    window.history.replaceState({}, "", `/q/${VERSUS.slug}`);
    const { fetchMock } = mount([[`/query/${VERSUS.slug}`, ok(VERSUS)]]);

    expect(await screen.findByTestId("answer-sentence")).toHaveTextContent("sug2rfree is 22-20 in maps");
    expect(fetchMock.calls.some((call) => call.url.includes(`/query/${VERSUS.slug}`))).toBe(true);
  });

  it("says when a shared link is being read differently than when it was shared", async () => {
    // The service decides this and describes it; the client does not diff parses.
    const drifted = {
      ...VERSUS,
      shared: {
        times_asked: 3,
        parsed_when_saved: { ...VERSUS.query, intent: "head_to_head" },
        parse_changed: true,
        parse_change: ["intent: head_to_head -> versus"],
      },
    };
    window.history.replaceState({}, "", `/q/${VERSUS.slug}`);
    mount([[`/query/${VERSUS.slug}`, ok(drifted)]]);

    const notice = await screen.findByTestId("parse-change");
    expect(notice).toHaveTextContent("read differently than when it was shared");
    expect(notice).toHaveTextContent("intent: head_to_head -> versus");
    expect(screen.getByTestId("answer-sentence")).toBeInTheDocument(); // the answer is still shown
  });

  it("says nothing about a shared link that still reads the same way", async () => {
    window.history.replaceState({}, "", `/q/${VERSUS.slug}`);
    mount([[`/query/${VERSUS.slug}`, ok({ ...VERSUS, shared: { times_asked: 2, parse_changed: false, parse_change: [] } })]]);
    await screen.findByTestId("answer");
    expect(screen.queryByTestId("parse-change")).not.toBeInTheDocument();
  });

  it("pages the evidence through the API, keeping the answer on screen", async () => {
    window.history.replaceState({}, "", `/q/${VERSUS.slug}`);
    const secondPage = pageOf(VERSUS, 2, [{ ...VERSUS.evidence.rows[0], map_name: "Busan", played_at: "2026-04-10" }]);
    const { fetchMock } = mount([
      [
        `/query/${VERSUS.slug}`,
        ({ path }) => (path.includes("page=2") ? ok(secondPage) : ok(VERSUS)),
      ],
    ]);

    await screen.findByTestId("evidence");
    await userEvent.click(screen.getByRole("button", { name: "Older" }));

    await waitFor(() => expect(screen.getByTestId("pager-state")).toHaveTextContent("Page 2 of 14"));
    expect(screen.getByTestId("evidence")).toHaveTextContent("Busan");
    expect(screen.getByTestId("answer-sentence")).toBeInTheDocument();
    expect(fetchMock.calls.some((call) => call.url.includes("page=2"))).toBe(true);
  });

  it("expands a different ranked row through the API", async () => {
    window.history.replaceState({}, "", `/q/${LEADERBOARD.slug}`);
    const second = LEADERBOARD.aggregate.rows[1];
    const expanded = {
      ...LEADERBOARD,
      evidence: {
        ...LEADERBOARD.evidence,
        expanded_for: { id: second.player_id, type: "player", name: second.nickname, column: "player_id" },
      },
    };
    const { fetchMock } = mount([
      [
        `/query/${LEADERBOARD.slug}`,
        ({ path }) => (path.includes("evidence_for") ? ok(expanded) : ok(LEADERBOARD)),
      ],
    ]);

    await screen.findByTestId("aggregate");
    const rows = within(screen.getByTestId("aggregate")).getAllByRole("row").slice(1);
    await userEvent.click(within(rows[1]).getByRole("button"));

    await waitFor(() => expect(screen.getByTestId("evidence-subject")).toHaveTextContent(second.nickname));
    expect(fetchMock.calls.some((call) => call.url.includes(`evidence_for=${second.player_id}`))).toBe(true);
  });

  it("asks about an entity when its name in the sentence is clicked", async () => {
    const { fetchMock } = mount([["/ask", ok(VERSUS)]]);
    await userEvent.type(await screen.findByRole("textbox"), "Sugarfree map record against Zeruhh{Enter}");
    await screen.findByTestId("answer");

    await userEvent.click(screen.getByRole("button", { name: "zeruhh" }));
    await waitFor(() => expect(fetchMock.calls.some((call) => call.body?.question === "zeruhh record")).toBe(true));
  });

  it("offers the candidates when the service needs a clarification", async () => {
    const { fetchMock } = mount([["/ask", ({ body }) => (body.question === "tea record" ? ok(CLARIFY) : ok(VERSUS))]]);
    await userEvent.type(await screen.findByRole("textbox"), "tea record{Enter}");

    const clarify = await screen.findByTestId("clarify");
    const candidate = CLARIFY.candidates.subject.find((c) => c.current_name === "Team Liquid");
    await userEvent.click(within(clarify).getByRole("button", { name: /Team Liquid/ }));

    // verbatim: the service guarantees this question resolves to that entity
    await waitFor(() =>
      expect(fetchMock.calls.some((call) => call.body?.question === candidate.question)).toBe(true),
    );
  });
});

describe("when the service itself is the problem", () => {
  it("says it is unavailable rather than looking like a refused question", async () => {
    mount([["/ask", fail(503, "database unavailable: OperationalError")]]);
    await userEvent.type(await screen.findByRole("textbox"), "who had the most eliminations{Enter}");

    const error = await screen.findByTestId("error");
    expect(error).toHaveAttribute("data-kind", "unavailable");
    expect(error).toHaveTextContent("OWCS Muse is unavailable");
    expect(error).toHaveTextContent("database is not answering");
    expect(screen.queryByTestId("refusal")).not.toBeInTheDocument();
    expect(screen.queryByTestId("answer")).not.toBeInTheDocument();
  });

  it("distinguishes an unreachable service from an unavailable one", async () => {
    mount([["/ask", () => new TypeError("Failed to fetch")]]);
    await userEvent.type(await screen.findByRole("textbox"), "who had the most eliminations{Enter}");

    const error = await screen.findByTestId("error");
    expect(error).toHaveAttribute("data-kind", "offline");
    expect(error).toHaveTextContent("Could not reach OWCS Muse");
  });

  it("explains a shared link that points at nothing", async () => {
    window.history.replaceState({}, "", "/q/deadlink1234");
    mount([["/query/deadlink1234", fail(404, "no question is saved under 'deadlink1234'")]]);

    const error = await screen.findByTestId("error");
    expect(error).toHaveAttribute("data-kind", "not_found");
    expect(screen.getByRole("button", { name: "Ask something else" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("lets a failed question be retried", async () => {
    let attempt = 0;
    const { fetchMock } = mount([
      [
        "/ask",
        () => {
          attempt += 1;
          return attempt === 1 ? fail(503) : ok(VERSUS);
        },
      ],
    ]);
    await userEvent.type(await screen.findByRole("textbox"), "Sugarfree map record against Zeruhh{Enter}");
    await screen.findByTestId("error");

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("answer")).toBeInTheDocument();
    expect(fetchMock.calls.filter((call) => call.url.includes("/ask"))).toHaveLength(2);
  });
});
