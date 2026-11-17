import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "../src/App.jsx";
import { SUGGESTIONS, VERSUS, mockFetch, ok, fail } from "./fixtures.js";

// A prefilled question, /?q=...: a link from elsewhere (OWCS Grid's "Ask Muse about ...") lands here.

function mountAt(path, routes) {
  window.history.replaceState({}, "", path);
  const fetchMock = mockFetch([["/suggestions", ok(SUGGESTIONS)], ...routes]);
  vi.stubGlobal("fetch", fetchMock);
  return { ...render(<App />), fetchMock };
}

const asks = (fetchMock) => fetchMock.calls.filter((call) => call.url.endsWith("/ask"));

describe("a prefilled question", () => {
  it("is asked exactly as if it had been typed and submitted", async () => {
    const { fetchMock } = mountAt("/?q=Sugarfree%20map%20record%20against%20Zeruhh", [["/ask", ok(VERSUS)]]);
    expect(await screen.findByTestId("answer-sentence")).toHaveTextContent("sug2rfree is 22-20 in maps");
    expect(asks(fetchMock)).toHaveLength(1);
    expect(asks(fetchMock)[0]).toMatchObject({ method: "POST", body: { question: "Sugarfree map record against Zeruhh", page: 1 } });
    // and it ends where a typed question ends: on the answer's own URL, with the question in the box
    expect(window.location.pathname).toBe(`/q/${VERSUS.slug}`);
    expect(window.location.search).toBe("");
    expect(screen.getByRole("textbox").value).toBe("Sugarfree map record against Zeruhh");
    expect(screen.getByTestId("share")).toHaveTextContent(`/q/${VERSUS.slug}`);
  });

  it("sends what a typed question sends", async () => {
    const prefilled = mountAt("/?q=Sugarfree%20map%20record%20against%20Zeruhh", [["/ask", ok(VERSUS)]]);
    await screen.findByTestId("answer");
    const fromLink = asks(prefilled.fetchMock)[0].body;
    prefilled.unmount();

    const typed = mountAt("/", [["/ask", ok(VERSUS)]]);
    await userEvent.type(await screen.findByRole("textbox"), "Sugarfree map record against Zeruhh{Enter}");
    await screen.findByTestId("answer");
    expect(asks(typed.fetchMock)[0].body).toEqual(fromLink);
  });

  it("replaces its own history entry, so Back does not ask again", async () => {
    const before = window.history.length;
    const { fetchMock } = mountAt("/?q=Toronto%20Defiant%20record", [["/ask", ok(VERSUS)]]);
    await screen.findByTestId("answer");
    expect(window.history.length).toBe(before); // /?q=... became /q/<slug>: nothing was pushed
    expect(asks(fetchMock)).toHaveLength(1);
  });

  it("asks an id-prefixed question as given and never shows the id", async () => {
    const question = "player:0a7555bc-8cd2-44bd-b1d5-df0c528dddea record";
    const { fetchMock } = mountAt(`/?q=${encodeURIComponent(question)}`, [["/ask", ok({ ...VERSUS, question })]]);
    await screen.findByTestId("answer");
    expect(asks(fetchMock)[0].body.question).toBe(question);
    expect(screen.getByRole("textbox").value).not.toContain("player:");
  });

  it("shows a failure the way a typed question's failure is shown", async () => {
    mountAt("/?q=who%20had%20the%20most%20eliminations", [["/ask", fail(503, "database unavailable: OperationalError")]]);
    expect(await screen.findByTestId("error")).toBeInTheDocument();
  });

  it("does nothing without a question: the landing page is the landing page", async () => {
    for (const path of ["/", "/?q=", "/?q=%20%20", "/?other=1"]) {
      const { fetchMock, unmount } = mountAt(path, [["/ask", ok(VERSUS)]]);
      expect(await screen.findByTestId("suggestions")).toBeInTheDocument();
      await waitFor(() => expect(asks(fetchMock)).toHaveLength(0));
      unmount();
    }
  });

  it("is ignored on a shared link, which already names its question", async () => {
    const { fetchMock } = mountAt(`/q/${VERSUS.slug}?q=something%20else`, [[`/query/${VERSUS.slug}`, ok(VERSUS)]]);
    await screen.findByTestId("answer");
    expect(asks(fetchMock)).toHaveLength(0);
  });
});
