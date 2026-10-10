import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "../src/App.jsx";
import { SUGGESTIONS, VERSUS, mockFetch, ok } from "./fixtures.js";

const SERIES_Q = "sug2rfree series record against Zeruhh";
const MAP_ANSWER = { ...VERSUS, other_grain: { grain: "series", label: "Series record", question: SERIES_Q } };
const SERIES_ANSWER = {
  ...VERSUS,
  question: SERIES_Q,
  slug: "series-slug",
  query: { ...VERSUS.query, intent: "head_to_head" },
  other_grain: { grain: "map", label: "Map record", question: VERSUS.question },
};

function mount() {
  const fetchMock = mockFetch([
    ["/suggestions", ok(SUGGESTIONS)],
    ["/ask", async ({ body }) => ok(body.question === SERIES_Q ? SERIES_ANSWER : MAP_ANSWER)],
  ]);
  vi.stubGlobal("fetch", fetchMock);
  return { ...render(<App />), fetchMock };
}

describe("grain toggle on a versus answer", () => {
  it("shows the grain on screen and asks the other one", async () => {
    const { fetchMock } = mount();
    await userEvent.type(await screen.findByRole("textbox"), `${VERSUS.question}{Enter}`);
    const toggle = await screen.findByTestId("grain-toggle");
    expect(within(toggle).getByRole("button", { name: "Map record" })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(within(toggle).getByRole("button", { name: "Series record" }));
    const asked = fetchMock.calls.filter((call) => call.url.includes("/ask")).at(-1);
    expect(asked.body.question).toBe(SERIES_Q);

    // and back: the series answer offers the map record
    const back = await screen.findByRole("button", { name: "Map record", pressed: false });
    expect(within(screen.getByTestId("grain-toggle")).getByRole("button", { name: "Series record" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await userEvent.click(back);
    expect(fetchMock.calls.filter((call) => call.url.includes("/ask")).at(-1).body.question).toBe(VERSUS.question);
  });

  it("is absent where there is no other grain", async () => {
    vi.stubGlobal("fetch", mockFetch([["/suggestions", ok(SUGGESTIONS)], ["/ask", ok({ ...VERSUS, other_grain: null })]]));
    render(<App />);
    await userEvent.type(await screen.findByRole("textbox"), `${VERSUS.question}{Enter}`);
    await screen.findByTestId("answer");
    expect(screen.queryByTestId("grain-toggle")).not.toBeInTheDocument();
  });
});
