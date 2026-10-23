/**
 * The credit an answer owes Liquipedia (CC-BY-SA 3.0): the source, the licence and
 * every page a value in the answer came from.
 *
 * The API decides what is owed (`attribution`, null when the answer used no
 * Liquipedia value) and this renders all of it, every time: no page is left out
 * and nothing is behind a disclosure, because the credit is a licence condition.
 */
export default function Attribution({ attribution }) {
  const pages = attribution?.pages ?? [];
  if (!pages.length) return null;

  return (
    <section className="attribution" data-testid="attribution">
      <p>
        Includes data from{" "}
        <a href="https://liquipedia.net/overwatch/" target="_blank" rel="noreferrer noopener">
          {attribution.source ?? "Liquipedia"}
        </a>
        , licensed under{" "}
        <a href={attribution.license_url} target="_blank" rel="noreferrer noopener license">
          {attribution.license}
        </a>
        . {pages.length === 1 ? "Page" : "Pages"} used:
      </p>
      <ul>
        {pages.map((url) => (
          <li key={url}>
            <a href={url} target="_blank" rel="noreferrer noopener">
              {pageTitle(url)}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** "https://liquipedia.net/overwatch/Overwatch_Champions_Series/2026/NA/Stage_3" -> "Overwatch Champions Series/2026/NA/Stage 3" */
export function pageTitle(url) {
  const path = String(url).replace(/^https?:\/\/liquipedia\.net\/[^/]+\//, "");
  let title = path;
  try {
    title = decodeURIComponent(path);
  } catch {
    // a malformed escape: show the path as it is
  }
  return title.replace(/_/g, " ");
}
