import { useEffect, useRef, useState } from "react";

/** The only thing on the landing page, and the thing that stays at the top after. */
export default function QuestionBar({ value = "", onSubmit, busy = false, autoFocus = false, compact = false }) {
  const [text, setText] = useState(value);
  const input = useRef(null);

  useEffect(() => {
    setText(value);
  }, [value]);

  useEffect(() => {
    if (autoFocus) input.current?.focus();
  }, [autoFocus]);

  return (
    <form
      className={compact ? "question-bar question-bar--compact" : "question-bar"}
      aria-busy={busy || undefined}
      onSubmit={(event) => {
        event.preventDefault();
        const question = text.trim();
        if (question) onSubmit(question);
      }}
    >
      <label className="visually-hidden" htmlFor="question">
        Ask about OWCS
      </label>
      <input
        id="question"
        ref={input}
        type="text"
        name="question"
        value={text}
        autoComplete="off"
        spellCheck="false"
        maxLength={500}
        placeholder="Ask about OWCS"
        onChange={(event) => setText(event.target.value)}
      />
      <button type="submit" disabled={busy || !text.trim()} aria-busy={busy || undefined}>
        {busy ? (
          <>
            <span className="spinner" aria-hidden="true" data-testid="ask-spinner" />
            <span>Asking</span>
          </>
        ) : (
          "Ask"
        )}
      </button>
    </form>
  );
}
