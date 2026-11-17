import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "../src/App.jsx";
import { SUGGESTIONS, VERSUS, mockFetch, ok, fail } from "./fixtures.js";

// How a visitor to Muse finds OWCS Grid: the masthead link and the line under the question box, both on by default.

const TODAY = {
  number: 12,
  date: "2026-11-28",
  is_today: true,
  kind: "mixed",
  difficulty: "Hard",
  rows: [
    { key: "row0", family: "org", label: "Played for Team Peps", help: "h." },
    { key: "row1", family: "teammate", label: "Teammate of Seicoe", help: "h." },
    { key: "row2", family: "stage", label: "Stage finalist in 2026", help: "h." },
  ],
  cols: [
    { key: "col0", family: "teammate", label: "Teammate of eisgnom", help: "h." },
    { key: "col1", family: "lan", label: "Rostered at 2025 World Finals", help: "h." },
    { key: "col2", family: "stats", label: "Top 25% fewest deaths/10, 2025 NA/EMEA", help: "h." },
  ],
  guesses: 9,
  min_maps: null,
  coverage: "Unless a clue says otherwise, answers come from FACEIT map stats.",
};

function mountHome(routes = [["/api/grid/today", ok(TODAY)]], path = "/") {
  window.history.replaceState({}, "", path);
  const fetchMock = mockFetch([...routes, ["/suggestions", ok(SUGGESTIONS)], ["/ask", ok(VERSUS)]]);
  vi.stubGlobal("fetch", fetchMock);
  return { ...render(<App />), fetchMock };
}

describe("finding Grid from Muse", () => {
  it("shows the Daily Grid link in the masthead by default, and it goes to /grid", async () => {
    mountHome();
    await userEvent.click(await screen.findByTestId("grid-nav"));
    expect(window.location.pathname).toBe("/grid");
    expect(await screen.findByTestId("grid-board")).toBeInTheDocument();
    expect(screen.queryByTestId("grid-nav")).not.toBeInTheDocument(); // already there: the link steps aside
  });

  it("puts one entry under the question box, with today's puzzle number, linking to /grid", async () => {
    mountHome();
    const entry = await screen.findByTestId("grid-entry");
    expect(entry).toHaveAttribute("href", "/grid");
    await waitFor(() => expect(entry).toHaveTextContent("Daily Grid · Puzzle #12 · Hard"));
    // under the box, above the examples: the question box is still the first thing on the page
    const box = screen.getByRole("textbox", { name: /ask about owcs/i });
    expect(box.compareDocumentPosition(entry) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(entry.compareDocumentPosition(await screen.findByTestId("suggestions")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    await userEvent.click(entry);
    expect(window.location.pathname).toBe("/grid");
    expect(await screen.findByTestId("grid-board")).toBeInTheDocument();
  });

  it("never holds the landing page up: the box is ready while the puzzle number is still on its way", async () => {
    let release;
    const waiting = new Promise((resolve) => {
      release = resolve;
    });
    mountHome([["/api/grid/today", () => waiting.then(() => ok(TODAY))]]);
    const box = await screen.findByRole("textbox", { name: /ask about owcs/i });
    expect(box).toHaveFocus();
    const entry = screen.getByTestId("grid-entry");
    expect(entry).toHaveTextContent("Daily Grid");
    expect(entry).not.toHaveTextContent("Puzzle #");
    expect(await screen.findByTestId("suggestions")).toBeInTheDocument();
    release();
    await waitFor(() => expect(entry).toHaveTextContent("Puzzle #12"));
  });

  it("stays a plain link when there is no puzzle today or the service cannot be reached", async () => {
    for (const today of [fail(404, "no puzzle is published for 2027-01-01"), new TypeError("Failed to fetch")]) {
      const { unmount } = mountHome([["/api/grid/today", today]]);
      const entry = await screen.findByTestId("grid-entry");
      await screen.findByTestId("suggestions");
      expect(entry).toHaveTextContent("Daily Grid");
      expect(entry).not.toHaveTextContent("Puzzle #");
      expect(entry).toHaveAttribute("href", "/grid");
      expect(screen.queryByTestId("error")).not.toBeInTheDocument();
      unmount();
    }
  });

  it("leaves the search box working exactly as before", async () => {
    const { fetchMock } = mountHome();
    await screen.findByTestId("grid-entry");
    await userEvent.type(screen.getByRole("textbox", { name: /ask about owcs/i }), "Sugarfree map record against Zeruhh{Enter}");
    expect(await screen.findByTestId("answer-sentence")).toHaveTextContent("sug2rfree is 22-20 in maps");
    expect(window.location.pathname).toBe(`/q/${VERSUS.slug}`);
    const asked = fetchMock.calls.filter((call) => call.url.endsWith("/ask"));
    expect(asked).toHaveLength(1);
    expect(asked[0].body.question).toBe("Sugarfree map record against Zeruhh");
    expect(screen.queryByTestId("grid-entry")).not.toBeInTheDocument(); // the entry belongs to the landing page only
    expect(screen.getByTestId("grid-nav")).toBeInTheDocument(); // the masthead link stays
  });

  it("has a way back from Grid to Muse's search", async () => {
    mountHome([["/api/grid/today", ok(TODAY)]], "/grid");
    const back = await screen.findByTestId("grid-back");
    expect(back).toHaveTextContent("Ask Muse a question");
    expect(back).toHaveAttribute("href", "/");
    await userEvent.click(back);
    expect(window.location.pathname).toBe("/");
    expect(await screen.findByRole("textbox", { name: /ask about owcs/i })).toBeInTheDocument();
    expect(screen.queryByTestId("grid-board")).not.toBeInTheDocument();
  });

  it("hides both the masthead link and the entry when VITE_GRID_NAV is false, and /grid still works", async () => {
    vi.stubEnv("VITE_GRID_NAV", "false");
    vi.resetModules();
    const { default: HiddenApp } = await import("../src/App.jsx");
    window.history.replaceState({}, "", "/");
    const fetchMock = mockFetch([["/suggestions", ok(SUGGESTIONS)], ["/api/grid/today", ok(TODAY)]]);
    vi.stubGlobal("fetch", fetchMock);
    const first = render(<HiddenApp />);
    await screen.findByTestId("suggestions");
    expect(screen.queryByTestId("grid-nav")).not.toBeInTheDocument();
    expect(screen.queryByTestId("grid-entry")).not.toBeInTheDocument();
    expect(fetchMock.calls.some((call) => call.url.includes("/api/grid"))).toBe(false); // nor a request for it
    first.unmount();

    window.history.replaceState({}, "", "/grid");
    render(<HiddenApp />);
    expect(await screen.findByTestId("grid-board")).toBeInTheDocument();
    vi.unstubAllEnvs();
  });

  it("shows them for any other value of the flag, as when it is unset", async () => {
    vi.stubEnv("VITE_GRID_NAV", "true");
    vi.resetModules();
    const { default: ShownApp } = await import("../src/App.jsx");
    window.history.replaceState({}, "", "/");
    vi.stubGlobal("fetch", mockFetch([["/suggestions", ok(SUGGESTIONS)], ["/api/grid/today", ok(TODAY)]]));
    render(<ShownApp />);
    expect(await screen.findByTestId("grid-nav")).toBeInTheDocument();
    expect(screen.getByTestId("grid-entry")).toBeInTheDocument();
    vi.unstubAllEnvs();
  });
});
