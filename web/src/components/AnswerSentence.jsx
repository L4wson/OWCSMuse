import { LINKABLE_SPAN_KINDS, entityQuestion } from "../format.js";

/**
 * Split a sentence at the API's character offsets.
 *
 * The spans are authoritative: the text is sliced at start/end and never
 * searched for the entity's name. A nickname that also appears as an ordinary
 * word - or twice, once as each of two different entities - stays correct.
 * Spans that overlap or fall outside the text are dropped rather than trusted.
 */
export function segments(text, spans = []) {
  const usable = (spans ?? [])
    .filter(
      (span) =>
        Number.isInteger(span?.start) &&
        Number.isInteger(span?.end) &&
        span.start >= 0 &&
        span.end <= text.length &&
        span.end > span.start,
    )
    .sort((a, b) => a.start - b.start);

  const parts = [];
  let at = 0;
  for (const span of usable) {
    if (span.start < at) continue; // overlapping: the first one wins
    if (span.start > at) parts.push({ text: text.slice(at, span.start) });
    parts.push({ text: text.slice(span.start, span.end), span });
    at = span.end;
  }
  if (at < text.length) parts.push({ text: text.slice(at) });
  return parts;
}

export default function AnswerSentence({ sentence, onAsk }) {
  if (!sentence?.text) return null;
  return (
    <p className="sentence" data-testid="answer-sentence">
      {segments(sentence.text, sentence.spans).map((part, index) => {
        const span = part.span;
        if (!span) return <span key={index}>{part.text}</span>;

        const question = LINKABLE_SPAN_KINDS.has(span.kind) ? entityQuestion(part.text, span.kind) : null;
        if (!question || !onAsk) {
          return (
            <span key={index} className={`entity entity--${span.kind}`} data-kind={span.kind}>
              {part.text}
            </span>
          );
        }
        return (
          <button
            key={index}
            type="button"
            className={`entity entity--link entity--${span.kind}`}
            data-kind={span.kind}
            data-entity-id={span.entity_id ?? ""}
            title={`Ask: ${question}`}
            onClick={() => onAsk(question)}
          >
            {part.text}
          </button>
        );
      })}
    </p>
  );
}
