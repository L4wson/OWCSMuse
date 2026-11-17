import { useEffect, useState } from "react";

import { getPuzzle } from "./api.js";

/**
 * The way into OWCS Grid from Muse's landing page: one compact line under the question box.
 *
 * It renders at once as a plain link and never waits on anything. Today's puzzle number is fetched afterwards, from
 * a route that reads no database, and is added when it arrives; if it never does (no puzzle today, the service
 * unreachable), the link stays as it is and still goes to /grid, which says what it found.
 */
export default function GridEntry({ navigate }) {
  const [today, setToday] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    getPuzzle(null, { signal: controller.signal })
      .then(setToday)
      .catch(() => setToday(null)); // the number is a nicety, never an error on the landing page
    return () => controller.abort();
  }, []);

  return (
    <a
      className="grid-entry"
      href="/grid"
      data-testid="grid-entry"
      onClick={(event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return; // a new tab is a new tab
        event.preventDefault();
        navigate("/grid");
      }}
    >
      <span className="grid-entry-mark" aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
        <i />
        <i />
        <i />
        <i />
        <i />
      </span>
      <span className="grid-entry-text">
        <strong>
          Daily Grid{today?.number ? ` · Puzzle #${today.number}` : ""}
          {today?.difficulty ? <span className="grid-entry-level"> · {today.difficulty}</span> : null}
        </strong>
        <span className="muted">Nine cells, nine guesses: today's OWCS trivia puzzle</span>
      </span>
      <span className="grid-entry-go" aria-hidden="true">
        →
      </span>
    </a>
  );
}
