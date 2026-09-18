import Evidence from "./Evidence.jsx";
import Context from "./Context.jsx";

/**
 * A refusal, which is a kind of answer.
 *
 * Two things stop it being a dead end. It says what it could not do in plain
 * words, and it offers questions that do work - built from whatever the API
 * managed to resolve, then from live suggestions.
 *
 * It can also carry rows. A map-grain question about two teams whose maps FACEIT
 * never recorded is refused *and* evidenced: the series happened, the maps do not
 * exist, and both halves of that are true at once.
 */
export default function Refusal({ answer, suggestions = [], onAsk, onPage, busy }) {
  const alternatives = nearbyQuestions(answer, suggestions);
  const evidence = answer.evidence;

  return (
    <section className="refusal" data-testid="refusal">
      <p className="refusal-reason" data-testid="refusal-reason">
        {answer.reason}
      </p>
      {answer.code ? (
        <p className="muted refusal-code">
          <span className="badge">{answer.code.replace(/_/g, " ")}</span>
        </p>
      ) : null}

      {answer.suggestions?.length ? (
        <ul className="tips">
          {answer.suggestions.map((tip) => (
            <li key={tip}>{tip}</li>
          ))}
        </ul>
      ) : null}

      <Context coverage={answer.coverage} notes={answer.notes} limitations={answer.limitations} />

      {evidence?.available ? (
        <>
          <p className="muted">
            What is known, even though the answer above is not:
          </p>
          <Evidence evidence={evidence} busy={busy} onPage={onPage} />
        </>
      ) : null}

      {alternatives.length ? (
        <div className="alternatives" data-testid="alternatives">
          <h2>Try instead</h2>
          <ul>
            {alternatives.map((question) => (
              <li key={question}>
                <button type="button" className="chip" onClick={() => onAsk(question)}>
                  {question}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

/**
 * Questions worth offering after this particular failure.
 *
 * The service knows what would have worked - it resolved the entities and it
 * knows which seasons carry the stat - so `alternatives` comes from there. Live
 * suggestions only fill the gap when the failure was a typo and there is nothing
 * specific to offer.
 */
export function nearbyQuestions(answer, suggestions = []) {
  const out = [...(answer?.alternatives ?? [])];
  for (const suggestion of suggestions) {
    if (out.length >= 4) break;
    if (suggestion?.question && !out.includes(suggestion.question)) out.push(suggestion.question);
  }
  return out.slice(0, 4);
}
