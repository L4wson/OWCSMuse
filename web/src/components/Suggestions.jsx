/**
 * Examples, taken live from the service.
 *
 * They are not hardcoded because the warehouse changes: /suggestions builds them
 * from the entities with the most data, so a suggestion always has an answer
 * behind it. One per group, so four examples show four different shapes of
 * question rather than four leaderboards.
 */
export default function Suggestions({ suggestions, onAsk, limit = 4 }) {
  const picked = pickAcrossGroups(suggestions?.suggestions ?? [], limit);
  if (!picked.length) return null;

  return (
    <div className="suggestions" data-testid="suggestions">
      <p className="muted">For example</p>
      <ul>
        {picked.map((suggestion) => (
          <li key={suggestion.slug ?? suggestion.question}>
            <button type="button" className="chip" onClick={() => onAsk(suggestion.question)}>
              {suggestion.question}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function pickAcrossGroups(suggestions, limit) {
  const seen = new Set();
  const picked = [];
  for (const suggestion of suggestions) {
    if (picked.length >= limit) break;
    if (seen.has(suggestion.group)) continue;
    seen.add(suggestion.group);
    picked.push(suggestion);
  }
  for (const suggestion of suggestions) {
    if (picked.length >= limit) break;
    if (!picked.includes(suggestion)) picked.push(suggestion);
  }
  return picked;
}
