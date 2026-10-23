import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import Attribution, { pageTitle } from "../src/components/Attribution.jsx";
import Refusal from "../src/components/Refusal.jsx";
import Result from "../src/components/Result.jsx";
import { REFUSAL_WITH_EVIDENCE, VERSUS } from "./fixtures.js";

// the block the API returns (owcsmuse/liquipedia/attribution.py, attribution_block)
const BLOCK = {
  source: "Liquipedia",
  license: "CC-BY-SA 3.0",
  license_url: "https://creativecommons.org/licenses/by-sa/3.0/",
  pages: [
    "https://liquipedia.net/overwatch/Overwatch_Champions_Series/2024/North_America/Stage_1",
    "https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_3/Regular_Season",
  ],
};

describe("Liquipedia attribution", () => {
  it("credits the source and the licence, and links every page", () => {
    render(<Attribution attribution={BLOCK} />);
    const block = screen.getByTestId("attribution");
    expect(within(block).getByRole("link", { name: "Liquipedia" })).toHaveAttribute("href", "https://liquipedia.net/overwatch/");
    expect(within(block).getByRole("link", { name: "CC-BY-SA 3.0" })).toHaveAttribute("href", BLOCK.license_url);
    const pages = within(block).getAllByRole("listitem").map((li) => within(li).getByRole("link"));
    expect(pages.map((a) => a.getAttribute("href"))).toEqual(BLOCK.pages);
    expect(pages[1]).toHaveTextContent("Overwatch Champions Series/2026/NA/Stage 3/Regular Season");
  });

  it("renders nothing for an answer that used no Liquipedia value", () => {
    const { container } = render(<Attribution attribution={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("is shown with an answer that carries it", () => {
    render(<Result answer={{ ...VERSUS, attribution: BLOCK }} onAsk={() => {}} />);
    expect(within(screen.getByTestId("answer")).getByTestId("attribution")).toBeInTheDocument();
  });

  it("is not shown with an answer that does not", () => {
    render(<Result answer={{ ...VERSUS, attribution: null }} onAsk={() => {}} />);
    expect(screen.queryByTestId("attribution")).not.toBeInTheDocument();
  });

  it("is shown with a refusal that carries it: its rows can be Liquipedia's", () => {
    render(<Refusal answer={{ ...REFUSAL_WITH_EVIDENCE, attribution: BLOCK }} suggestions={[]} onAsk={() => {}} />);
    expect(within(screen.getByTestId("refusal")).getByTestId("attribution")).toBeInTheDocument();
  });

  it("reads a page's title off its URL", () => {
    expect(pageTitle("https://liquipedia.net/overwatch/Team_CC_%28Chinese_orgless_team%29")).toBe("Team CC (Chinese orgless team)");
    expect(pageTitle("https://liquipedia.net/overwatch/Bad_%E0%A4%A")).toBe("Bad %E0%A4%A");
  });
});
