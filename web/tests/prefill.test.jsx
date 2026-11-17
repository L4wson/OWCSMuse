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
    // the service resolved nobody by that id in this answer, so there is no name to show: the box stays empty
    expect(screen.getByRole("textbox").value).toBe("");
  });

  it("shows a question asked by id under the player's name, as the service resolved it", async () => {
    // the link OWCS Grid puts on an answer: nobody typed it, so without this the box above the answer is empty
    const id = VERSUS.entities.subject.entity_id;
    const question = `player:${id} record`;
    const { fetchMock } = mountAt(`/?q=${encodeURIComponent(question)}`, [["/ask", ok({ ...VERSUS, question })]]);
    await screen.findByTestId("answer");
    expect(asks(fetchMock)[0].body.question).toBe(question); // what was asked is still the id
    const box = screen.getByRole("textbox");
    expect(box.value).toBe(`${VERSUS.entities.subject.current_name} record`);
    expect(box.value).not.toContain(id);
    expect(document.body.textContent).not.toContain(`player:${id}`);
  });

  it("names every id or none: a question with one unresolved id is not half translated", async () => {
    const id = VERSUS.entities.subject.entity_id;
    const question = `player:${id} record against player:00000000-0000-4000-8000-000000000000`;
    mountAt(`/?q=${encodeURIComponent(question)}`, [["/ask", ok({ ...VERSUS, question })]]);
    await screen.findByTestId("answer");
    expect(screen.getByRole("textbox").value).toBe("");
  });

  it("shows a shared link to a question asked by id under the player's name too", async () => {
    const question = `player:${VERSUS.entities.subject.entity_id} record`;
    mountAt(`/q/${VERSUS.slug}`, [[`/query/${VERSUS.slug}`, ok({ ...VERSUS, question })]]);
    await screen.findByTestId("answer");
    await waitFor(() => expect(screen.getByRole("textbox").value).toBe(`${VERSUS.entities.subject.current_name} record`));
  });

  it("leaves a typed question alone when the service echoes ids back", async () => {
    // only a prefilled question is renamed: what someone typed stays what they typed
    const question = `player:${VERSUS.entities.subject.entity_id} record`;
    mountAt("/", [["/ask", ok({ ...VERSUS, question })]]);
    await userEvent.type(await screen.findByRole("textbox"), "sugarfree record{Enter}");
    await screen.findByTestId("answer");
    expect(screen.getByRole("textbox").value).toBe("sugarfree record");
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
