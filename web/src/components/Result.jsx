import AnswerSentence from "./AnswerSentence.jsx";
import Attribution from "./Attribution.jsx";
import Clarify from "./Clarify.jsx";
import Context from "./Context.jsx";
import DataTable from "./DataTable.jsx";
import Evidence from "./Evidence.jsx";
import GrainToggle from "./GrainToggle.jsx";
import Refusal from "./Refusal.jsx";

/** An answer, whichever of the three kinds it turned out to be. */
export default function Result({ answer, suggestions, busy, onAsk, onPage, onExpand, pageSize, onPageSize }) {
  if (!answer) return null;

  // The service decides whether a shared link now reads differently; the client
  // used to diff two parse objects to find out.
  const parseChanged = answer.shared?.parse_changed ? (answer.shared.parse_change ?? []) : [];

  if (answer.status === "clarify") {
    return (
      <>
        <ParseChange changes={parseChanged} />
        <Clarify answer={answer} onAsk={onAsk} />
      </>
    );
  }

  if (answer.status === "cannot_answer") {
    return (
      <>
        <ParseChange changes={parseChanged} />
        <Refusal answer={answer} suggestions={suggestions} onAsk={onAsk} onPage={onPage} busy={busy} pageSize={pageSize} onPageSize={onPageSize} />
      </>
    );
  }

  const evidence = answer.evidence;
  const ranked = Boolean(evidence?.expandable_by);
  const aggregate = answer.aggregate ?? {};
  const rows = aggregate.rows ?? [];

  return (
    <article className="answer" data-testid="answer">
      <AnswerSentence sentence={answer.sentence} onAsk={onAsk} />
      <GrainToggle answer={answer} onAsk={onAsk} busy={busy} />
      <ParseChange changes={parseChanged} />
      <Context coverage={answer.coverage} notes={answer.notes} limitations={answer.limitations} />

      {rows.length ? (
        <section className="aggregate" data-testid="aggregate">
          <DataTable
            rows={rows}
            columns={aggregate.columns ?? []}
            caption={aggregate.description}
            expandedId={evidence?.expanded_for?.id}
            onExpand={ranked ? onExpand : null}
          />
          {ranked ? (
            <p className="muted" data-testid="expand-hint">
              Showing the rows behind{" "}
              <b>{evidence?.expanded_for?.name ?? evidence?.expanded_for?.id}</b>. Pick another row to see its rows.
            </p>
          ) : null}
        </section>
      ) : null}

      <Evidence evidence={evidence} busy={busy} onPage={onPage} onAsk={onAsk} pageSize={pageSize} onPageSize={onPageSize} />
      <Attribution attribution={answer.attribution} />
    </article>
  );
}

/**
 * A shared link re-runs against current data, so the question can be read
 * differently today than it was when the link was made. Saying so is the point:
 * silently answering something else is the failure mode.
 */
function ParseChange({ changes }) {
  if (!changes?.length) return null;
  return (
    <p className="parse-change" data-testid="parse-change" role="status">
      <b>This link is being read differently than when it was shared.</b> {changes.join("; ")}. The answer below is the
      current reading, against current data.
    </p>
  );
}
