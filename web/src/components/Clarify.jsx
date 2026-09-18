import { activeRange } from "../format.js";

/**
 * "Which one did you mean?" - the state a resolver reaches honestly rather than
 * guessing.
 *
 * Two candidates can carry the same name, which is the whole reason this screen
 * exists, so each option shows what actually separates them: what kind of entity
 * it is, how many matches it has in scope, and the id itself. Two identical rows
 * would make the choice meaningless.
 */
export default function Clarify({ answer, onAsk }) {
  const roles = Object.entries(answer?.candidates ?? {});
  if (!roles.length) return null;

  return (
    <section className="clarify" data-testid="clarify">
      <h2 className="clarify-question">{answer.reason}</h2>
      {roles.map(([role, candidates]) => {
        const typed = answer.query?.filters?.[role] ?? null;
        const counts = new Map();
        for (const candidate of candidates) {
          const key = (candidate.current_name ?? "").toLowerCase();
          counts.set(key, (counts.get(key) ?? 0) + 1);
        }

        return (
          <div key={role} className="clarify-role">
            {typed ? (
              <p className="muted">
                You typed <b>{typed}</b>
                {roles.length > 1 ? ` for the ${role}` : null}.
              </p>
            ) : null}
            <ul className="candidates">
              {candidates.map((candidate) => {
                const shared = (counts.get((candidate.current_name ?? "").toLowerCase()) ?? 0) > 1;
                const active = activeRange(candidate);
                // The service ships a question per candidate that resolves to
                // exactly this entity; substituting a name is what fails when two
                // of them share one.
                return (
                  <li key={`${candidate.entity_type}:${candidate.entity_id}`}>
                    <button
                      type="button"
                      className="candidate"
                      onClick={() => onAsk(candidate.question)}
                      data-entity-id={candidate.entity_id}
                      data-question={candidate.question}
                    >
                      <span className="candidate-name">{candidate.current_name ?? candidate.matched_name}</span>
                      <span className="candidate-facts">
                        <span className={`badge badge--${candidate.entity_type}`}>{candidate.entity_type}</span>
                        <span>
                          {candidate.matches > 0
                            ? `${candidate.matches.toLocaleString("en-GB")} matches in scope`
                            : "no matches in scope"}
                        </span>
                        {active ? <span className="candidate-active">{active}</span> : null}
                        {candidate.matched_name && candidate.matched_name !== candidate.current_name ? (
                          <span>matched &ldquo;{candidate.matched_name}&rdquo;</span>
                        ) : null}
                        {shared ? <span className="candidate-id">id {candidate.entity_id}</span> : null}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </section>
  );
}
