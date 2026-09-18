import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, ask as askApi, askSlug, getSuggestions } from "./api.js";
import { useRoute } from "./router.js";
import QuestionBar from "./components/QuestionBar.jsx";
import Result from "./components/Result.jsx";
import Suggestions from "./components/Suggestions.jsx";
import { ErrorState, Loading } from "./components/States.jsx";

const PAGE_SIZE = 25;

export default function App() {
  const [route, navigate] = useRoute();
  const [phase, setPhase] = useState("idle"); // idle | loading | ready | error
  const [answer, setAnswer] = useState(null);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState(null);
  const [suggestions, setSuggestions] = useState(null);
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
      if (asked !== undefined) setQuestion(asked);
      try {
        const payload = await run(controller.signal);
        if (controller.signal.aborted) return null;
        setAnswer(payload);
        setQuestion(payload.question ?? asked ?? "");
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
      const payload = await load((signal) => askApi({ question: text, pageSize: PAGE_SIZE, signal }), {
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
    load((signal) => askSlug(route.slug, { pageSize: PAGE_SIZE, signal }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route.name, route.slug]);

  const reload = useCallback(
    ({ page = 1, evidenceFor = null } = {}) => {
      const slug = answer?.slug ?? (route.name === "query" ? route.slug : null);
      const options = { page, pageSize: PAGE_SIZE, evidenceFor };
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
            {phase === "error" ? (
              <ErrorState error={error} onRetry={() => (question ? runQuestion(question) : goHome())} onHome={goHome} />
            ) : null}
            {answer && phase !== "error" ? (
              <>
                <Result
                  answer={answer}
                  suggestions={suggestions?.suggestions ?? []}
                  busy={phase === "loading"}
                  onAsk={runQuestion}
                  onPage={onPage}
                  onExpand={onExpand}
                />
                <ShareLine slug={answer.slug} />
              </>
            ) : null}
          </>
        )}
      </main>

      <footer className="footer">
        <span>OWCS NA + EMEA main competition, 2024-2026. Every row links to its FACEIT match.</span>
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
