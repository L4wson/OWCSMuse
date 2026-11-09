/**
 * The names the service read by a partial match: "'any' was read as Anyones Legend".
 *
 * A question answered about someone the asker never named is the worst kind of wrong answer, because it looks right.
 * The service resolves a strong partial match without asking (a name typed short), so whenever it did, it says so
 * here: next to the answer, before the numbers, not in the notes below them (2026-11-05: "highest kd of any player"
 * ranked Anyones Legend's players without a word about it).
 */
export default function ReadAs({ readAs = [] }) {
  if (!readAs?.length) return null;
  return (
    <div className="read-as" data-testid="read-as" role="status">
      {readAs.map((r) => (
        <p key={`${r.role}:${r.entity_id}`}>
          <b>Read “{r.typed}” as {r.name}</b> ({r.how}). If you meant someone else, ask with their exact name.
        </p>
      ))}
    </div>
  );
}

/** The notes without the read-as sentences, which ReadAs already shows. */
export function otherNotes(notes = [], readAs = []) {
  const shown = new Set((readAs ?? []).map((r) => r.text));
  return (notes ?? []).filter((n) => !shown.has(n));
}
