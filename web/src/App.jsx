import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, ask as askApi, askSlug, getSuggestions } from "./api.js";
import { useRoute } from "./router.js";
import QuestionBar from "./components/QuestionBar.jsx";
import Result from "./components/Result.jsx";
import Suggestions from "./components/Suggestions.jsx";
import { ErrorState, Loading } from "./components/States.jsx";

const DEFAULT_PAGE_SIZE = 25;

// A clarify pick, or a re-ask built from one, sends the API a question with a
// player:/team:/org: id spliced into it - that is the right thing to submit
// (it is what resolves a name that was ambiguous by name alone) and the wrong
// thing to ever show: nobody typed it, and it means nothing to read. The
// submitted text and the displayed text diverge exactly here, so this is the
// one place that decides which text the search box is allowed to show.
const ID_TOKEN = /\b(?:player|team|org):[A-Za-z0-9._-]+/;
const displayable = (text) => (typeof text === "string" && !ID_TOKEN.test(text) ? text : undefined);

export default function App() {
  const [route, navigate] = useRoute();
  const [phase, setPhase] = useState("idle"); // idle | loading | ready | error
  const [answer, setAnswer] = useState(null);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState(null);
  const [suggestions, setSuggestions] = useState(null);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const sizeRef = useRef(DEFAULT_PAGE_SIZE); // read inside callbacks that must not re-create on a change
  const inFlight = useRef(null);

  // Examples come from the service so they always have data behind them.
  useEffect(() => {
    const controller = new AbortController();
    getSuggestions({ signal: controller.signal })
      .then(setSuggestions)
      .catch(() => setSuggestions(null)); // examples are a nicety, never an error state
    return () => controller.abort();
  }, []);

  const load = useCallback(
    async (run, { question: asked, keepPhase = false } = {}) => {
      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;
      if (!keepPhase) setPhase("loading");
      setError(null);
      const shown = displayable(asked);
      if (shown !== undefined) setQuestion(shown);
      try {
        const payload = await run(controller.signal);
        if (controller.signal.aborted) return null;
        setAnswer(payload);
        // The API echoes back exactly what was submitted, ids included, so it
        // is not a display source either - only update the box when what came
        // back is itself human-readable; otherwise leave whatever is showing.
        const echoed = displayable(payload.question);
        if (echoed !== undefined) setQuestion(echoed);
        setPhase("ready");
        return payload;
      } catch (thrown) {
        if (thrown instanceof ApiError && thrown.kind === "aborted") return null;
        setError(thrown instanceof ApiError ? thrown : new ApiError("server", String(thrown?.message ?? thrown)));
        setPhase("error");
        return null;
      }
    },
    [],
  );

  const runQuestion = useCallback(
    async (text) => {
      const payload = await load((signal) => askApi({ question: text, pageSize: sizeRef.current, signal }), {
        question: text,
      });
      if (payload?.slug) navigate(`/q/${payload.slug}`);
    },
    [load, navigate],
  );

  // A slug in the URL is the question; the answer is always recomputed.
  useEffect(() => {
    if (route.name !== "query") return;
    if (answer?.slug === route.slug && phase === "ready") return;
    load((signal) => askSlug(route.slug, { pageSize: sizeRef.current, signal }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route.name, route.slug]);

  const reload = useCallback(
    ({ page = 1, evidenceFor = null, size = sizeRef.current } = {}) => {
      const slug = answer?.slug ?? (route.name === "query" ? route.slug : null);
      const options = { page, pageSize: size, evidenceFor };
      // Paging keeps the current answer on screen; only the rows change.
      return load(
        (signal) =>
          slug
            ? askSlug(slug, { ...options, signal })
            : askApi({ question: answer?.question ?? question, ...options, signal }),
        { keepPhase: true },
      );
    },
    [answer, question, route, load],
  );

  const onPage = useCallback(
    (page) => reload({ page, evidenceFor: answer?.evidence?.expanded_for?.id ?? null }),
    [reload, answer],
  );
  // A different page size restarts at page 1: "page 3 of 25" has no meaning at another size.
  const onPageSize = useCallback(
    (size) => {
      sizeRef.current = size;
      setPageSize(size);
      return reload({ page: 1, evidenceFor: answer?.evidence?.expanded_for?.id ?? null, size });
    },
    [reload, answer],
  );
  const onExpand = useCallback((id) => reload({ page: 1, evidenceFor: id }), [reload]);

  const goHome = useCallback(() => {
    setAnswer(null);
    setQuestion("");
    setError(null);
    setPhase("idle");
    navigate("/");
  }, [navigate]);

  const showLanding = route.name === "home" && phase === "idle";

  return (
    <div className={showLanding ? "app app--landing" : "app"}>
      <header className="masthead">
        <button type="button" className="wordmark" onClick={goHome}>
          OWCS Muse
        </button>
        <span className="beta-tag">beta</span>
      </header>

      <main>
        {showLanding ? (
          <div className="landing">
            <QuestionBar onSubmit={runQuestion} autoFocus busy={phase === "loading"} />
            <Suggestions suggestions={suggestions} onAsk={runQuestion} />
          </div>
        ) : (
          <>
            <QuestionBar value={question} onSubmit={runQuestion} busy={phase === "loading"} compact />
            {phase === "loading" && !answer ? <Loading question={question} /> : null}
            {phase === "loading" && answer ? (
              // a new question while the last answer is still on screen: say so, and dim what is now out of date
              <p className="loading-line" role="status" data-testid="loading-line">
                <span className="spinner spinner--inline" aria-hidden="true" />
                Looking up{question ? `: ${question}` : "..."}
              </p>
            ) : null}
            {phase === "error" ? (
              <ErrorState error={error} onRetry={() => (question ? runQuestion(question) : goHome())} onHome={goHome} />
            ) : null}
            {answer && phase !== "error" ? (
              <div className={phase === "loading" ? "result-stale" : undefined} aria-busy={phase === "loading" || undefined}>
                <Result
                  answer={answer}
                  suggestions={suggestions?.suggestions ?? []}
                  busy={phase === "loading"}
                  onAsk={runQuestion}
                  onPage={onPage}
                  pageSize={pageSize}
                  onPageSize={onPageSize}
                  onExpand={onExpand}
                />
                <ShareLine slug={answer.slug} />
              </div>
            ) : null}
          </>
        )}
      </main>

      <footer className="footer">
        <span>OWCS NA + EMEA main competition and the international events, 2024-2026. Every row links to its source.</span>
        <span>
          Data from the{" "}
          <a href="https://developers.faceit.com" target="_blank" rel="noreferrer noopener">
            FACEIT Data API
          </a>{" "}
          and{" "}
          <a href="https://liquipedia.net/overwatch/" target="_blank" rel="noreferrer noopener">
            Liquipedia
          </a>{" "}
          (
          <a href="https://creativecommons.org/licenses/by-sa/3.0/" target="_blank" rel="noreferrer noopener license">
            CC-BY-SA 3.0
          </a>
          ). Not affiliated with FACEIT, Liquipedia or Blizzard Entertainment.
        </span>
      </footer>
    </div>
  );
}

function ShareLine({ slug }) {
  const [copied, setCopied] = useState(false);
  if (!slug) return null;
  const url = `${window.location.origin}/q/${slug}`;
  return (
    <p className="share" data-testid="share">
      <span className="share-url">{url}</span>
      <button
        type="button"
        className="chip"
        onClick={async () => {
          try {
            await navigator.clipboard?.writeText(url);
            setCopied(true);
          } catch {
            setCopied(false); // no clipboard permission: the URL is on screen to copy by hand
          }
        }}
      >
        {copied ? "copied" : "copy link"}
      </button>
      <span className="muted">re-runs against current data</span>
    </p>
  );
}
