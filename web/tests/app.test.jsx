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

  it("shows a spinner in the ask box while a clicked example is in flight", async () => {
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    mount([["/ask", async () => { await gate; return ok(LEADERBOARD); }]]);
    const example = (await screen.findAllByRole("button", { name: SUGGESTIONS.suggestions[0].question }))[0];
    await userEvent.click(example);

    // the click submits at once: the box holds the question, the button says it is working
    expect(screen.getByRole("textbox", { name: /ask about owcs/i })).toHaveValue(SUGGESTIONS.suggestions[0].question);
    const button = screen.getByRole("button", { name: /asking/i });
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(within(button).getByTestId("ask-spinner")).toBeInTheDocument();

    release();
    await screen.findByTestId("answer");
    expect(screen.queryByTestId("ask-spinner")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask" })).toBeInTheDocument();
  });

  it("marks the last answer out of date while the next question is in flight", async () => {
    let release;
    let gate = Promise.resolve();
    mount([["/ask", async ({ body }) => {
      await gate;
      return ok(body.question.startsWith("who") ? LEADERBOARD : VERSUS);
    }]]);
    const box = await screen.findByRole("textbox");
    await userEvent.type(box, "Sugarfree map record against Zeruhh{Enter}");
    await screen.findByTestId("answer");

    gate = new Promise((resolve) => {
      release = resolve;
    });
    await userEvent.clear(screen.getByRole("textbox"));
    await userEvent.type(screen.getByRole("textbox"), "who had the most eliminations{Enter}");

    expect(await screen.findByTestId("loading-line")).toHaveTextContent("Looking up: who had the most eliminations");
    expect(screen.getByTestId("answer").closest(".result-stale")).not.toBeNull();
    expect(screen.getByTestId("ask-spinner")).toBeInTheDocument();

    release();
    await waitFor(() => expect(screen.queryByTestId("loading-line")).not.toBeInTheDocument());
    expect(screen.getByTestId("answer").closest(".result-stale")).toBeNull();
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

  it("offers 25, 50 and 100 rows per page, and refetches page 1 at the chosen size", async () => {
    window.history.replaceState({}, "", `/q/${VERSUS.slug}`);
    const { fetchMock } = mount([[`/query/${VERSUS.slug}`, ok(VERSUS)]]);

    await screen.findByTestId("evidence");
    const select = screen.getByTestId("page-size");
    expect([...select.options].map((option) => option.value)).toEqual(["25", "50", "100"]);
    expect(select).toHaveValue("25");

    await userEvent.selectOptions(select, "50");
    await waitFor(() => expect(fetchMock.calls.some((call) => call.url.includes("page_size=50"))).toBe(true));
    const refetch = fetchMock.calls.filter((call) => call.url.includes("page_size=50")).at(-1);
    expect(refetch.url).toContain("page=1"); // a new size restarts at the newest rows
    await waitFor(() => expect(screen.getByTestId("page-size")).toHaveValue("50"));
    expect(screen.getByTestId("answer-sentence")).toBeInTheDocument(); // the answer stays on screen
  });

  it("keeps the chosen page size for the next question", async () => {
    window.history.replaceState({}, "", "/");
    const { fetchMock } = mount([["/ask", ok(VERSUS)], [`/query/${VERSUS.slug}`, ok(VERSUS)]]);
    await userEvent.type(await screen.findByRole("textbox"), "Sugarfree map record against Zeruhh{Enter}");
    await userEvent.selectOptions(await screen.findByTestId("page-size"), "100");
    await waitFor(() => expect(screen.getByTestId("page-size")).toHaveValue("100"));

    const box = screen.getByRole("textbox");
    await userEvent.clear(box);
    await userEvent.type(box, "Twisted Minds record{Enter}");
    await waitFor(() => expect(fetchMock.calls.filter((c) => c.url.includes("/ask")).length).toBe(2));
    expect(fetchMock.calls.filter((c) => c.url.includes("/ask")).at(-1).body.page_size).toBe(100);
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

  it("never shows the id it just submitted after picking a clarify candidate", async () => {
    mount([["/ask", ({ body }) => (body.question === "tea record" ? ok(CLARIFY) : ok(VERSUS))]]);
    await userEvent.type(await screen.findByRole("textbox"), "tea record{Enter}");

    const clarify = await screen.findByTestId("clarify");
    const candidate = CLARIFY.candidates.subject.find((c) => c.current_name === "Team Liquid");
    expect(candidate.question).toMatch(/^team:/); // the id-bearing question that gets submitted
    await userEvent.click(within(clarify).getByRole("button", { name: /Team Liquid/ }));

    await screen.findByTestId("answer");
    const box = screen.getByRole("textbox");
    expect(box.value).not.toContain("team:");
    expect(box.value).not.toContain(candidate.entity_id);
    // the id never appears anywhere else on the page either
    expect(screen.queryByText(candidate.entity_id, { exact: false })).not.toBeInTheDocument();
  });

  it("never shows an id echoed back by the API as the question", async () => {
    // whatever was actually submitted (e.g. a chained clarify re-ask), the
    // service's own echo of it must not overwrite the search box either
    mount([["/ask", ok({ ...VERSUS, question: "player:0a7555bc-8cd2-44bd-b1d5-df0c528dddea record" })]]);
    await userEvent.type(await screen.findByRole("textbox"), "sugarfree record vs zeruhh{Enter}");

    await screen.findByTestId("answer");
    const box = screen.getByRole("textbox");
    expect(box.value).toBe("sugarfree record vs zeruhh");
    expect(box.value).not.toContain("player:");
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

  it("says how long to wait when this connection asked too fast, not that the service failed", async () => {
    const detail = "You are asking faster than OWCS Muse answers one person: wait 7 seconds and ask again.";
    mount([["/ask", fail(429, detail)]]);
    await userEvent.type(await screen.findByRole("textbox"), "who had the most eliminations{Enter}");

    const error = await screen.findByTestId("error");
    expect(error).toHaveAttribute("data-kind", "rate_limited");
    expect(error).toHaveTextContent("Too many questions at once");
    expect(error).toHaveTextContent("wait 7 seconds and ask again");
    expect(error).not.toHaveTextContent("HTTP 429");
    expect(error).not.toHaveTextContent("Wait a few seconds and ask again."); // the specific message, not both
  });

  it("says the service is busy, not that its database is down, when every connection is in use", async () => {
    const detail = "OWCS Muse is busy answering other questions right now. Try again in a few seconds.";
    mount([["/ask", { status: 503, payload: { detail, reason: "busy", retry_after: 5 } }]]);
    await userEvent.type(await screen.findByRole("textbox"), "who had the most eliminations{Enter}");

    const error = await screen.findByTestId("error");
    expect(error).toHaveAttribute("data-kind", "busy");
    expect(error).toHaveTextContent("OWCS Muse is busy");
    expect(error).not.toHaveTextContent("database is not answering");
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

describe("the footer", () => {
  it("says what is logged and that a shared link is public", async () => {
    mount([]);
    const privacy = await screen.findByTestId("privacy");
    expect(privacy).toHaveTextContent("Questions are logged as text");
    expect(privacy).toHaveTextContent("no account, cookie or IP address is stored");
    expect(privacy).toHaveTextContent("A shared link is public");
  });
});
