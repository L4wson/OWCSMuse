/** Loading, and the failures that are not answers at all. */

export function Loading({ question }) {
  return (
    <section className="loading" data-testid="loading" aria-live="polite">
      <p className="muted">Looking up{question ? `: ${question}` : "..."}</p>
      <div className="skeleton skeleton--sentence" />
      <div className="skeleton skeleton--row" />
      <div className="skeleton skeleton--row" />
      <div className="skeleton skeleton--row" />
    </section>
  );
}

const HEADINGS = {
  unavailable: "OWCS Muse is unavailable",
  busy: "OWCS Muse is busy",
  rate_limited: "Too many questions at once",
  offline: "Could not reach OWCS Muse",
  not_found: "That link has nothing behind it",
  invalid: "That question could not be sent",
  server: "OWCS Muse hit an error",
};

const EXPLANATIONS = {
  // A service that is up but cannot read its warehouse has not refused the
  // question, and must not look like it did.
  unavailable: "The service is running but its database is not answering, so no question can be answered right now.",
  offline: "The service did not respond. It may not be running, or the network dropped.",
  not_found: "No question is saved under that link. It may be from another deployment, or it may have been mistyped.",
  invalid: "The service rejected the request itself rather than the question.",
  server: "Something failed inside the service. This is not a refusal of the question.",
  busy: "Other questions are being answered right now. Try again in a few seconds.",
  rate_limited: "Wait a few seconds and ask again.",
};

// The service's own message says exactly how long to wait: it replaces the general explanation rather than repeating it.
const DETAIL_IS_THE_EXPLANATION = new Set(["busy", "rate_limited"]);

export function ErrorState({ error, onRetry, onHome }) {
  const kind = error?.kind ?? "server";
  return (
    <section className="error" data-testid="error" data-kind={kind} role="alert">
      <h2>{HEADINGS[kind] ?? HEADINGS.server}</h2>
      {DETAIL_IS_THE_EXPLANATION.has(kind) && error?.detail ? (
        <p>{error.detail}</p>
      ) : (
        <>
          <p>{EXPLANATIONS[kind] ?? EXPLANATIONS.server}</p>
          {error?.detail ? <p className="muted error-detail">{error.detail}</p> : null}
        </>
      )}
      <p className="error-actions">
        {onRetry && kind !== "not_found" ? (
          <button type="button" className="chip" onClick={onRetry}>
            Try again
          </button>
        ) : null}
        {onHome ? (
          <button type="button" className="chip" onClick={onHome}>
            Ask something else
          </button>
        ) : null}
      </p>
    </section>
  );
}
