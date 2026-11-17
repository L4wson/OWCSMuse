import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { GridError, getArchive, getPuzzle, getReveal, postGuess, searchPlayers } from "./api.js";
import {
  alreadyMissed,
  applyGuess,
  cellOf,
  giveUp,
  guessesLeft,
  isOver,
  loadGame,
  loadStats,
  recordFinish,
  saveGame,
  score,
  shareText,
} from "./game.js";
import "./grid.css";

/**
 * OWCS Grid: a daily 3x3. Rows are roles, columns are a season, a region or "all three seasons"; a cell takes one
 * player who fits both. Nine guesses, one cell per player.
 *
 * The page asks the service three things only: the clues, whether one guess is right, and (after the game) a few
 * example answers. It never holds an answer it was not told one guess at a time.
 */
export default function GridPage({ route, navigate }) {
  const go = useCallback(
    (path) => (event) => {
      event?.preventDefault();
      navigate(path);
    },
    [navigate],
  );
  return (
    <div className="grid-page" data-testid="grid-page">
      <nav className="grid-tabs" aria-label="OWCS Grid">
        <a href="/grid" onClick={go("/grid")} aria-current={route.view === "today" ? "page" : undefined}>
          Today
        </a>
        <a href="/grid/archive" onClick={go("/grid/archive")} aria-current={route.view === "archive" ? "page" : undefined}>
          Archive
        </a>
        <a href="/" onClick={go("/")} className="grid-tabs-back" data-testid="grid-back">
          Ask Muse a question
        </a>
      </nav>
      {route.view === "archive" ? (
        <Archive go={go} />
      ) : (
        // keyed: another puzzle is another game, with its own saved state
        <Game key={route.number ?? "today"} number={route.number ?? null} go={go} />
      )}
    </div>
  );
}

function Game({ number, go }) {
  const [puzzle, setPuzzle] = useState(null);
  const [error, setError] = useState(null);
  const [game, setGame] = useState(null);
  const [selected, setSelected] = useState(null);
  const [notice, setNotice] = useState(null); // {kind: "wrong" | "cannot_verify" | "error", text}
  const [reveal, setReveal] = useState(null);
  const [stats, setStats] = useState(() => loadStats());
  const [info, setInfo] = useState(null); // the clue whose definition is open: "row0", "col2", ...

  useEffect(() => {
    const controller = new AbortController();
    getPuzzle(number, { signal: controller.signal })
      .then((loaded) => {
        setPuzzle(loaded);
        setGame(loadGame(loaded.number));
      })
      .catch((thrown) => {
        if (thrown?.kind !== "aborted") setError(thrown instanceof GridError ? thrown : new GridError("server", String(thrown)));
      });
    return () => controller.abort();
  }, [number]);

  const over = puzzle && game ? isOver(game, puzzle.guesses) : false;

  useEffect(() => {
    if (puzzle && game) saveGame(puzzle.number, game);
  }, [puzzle, game]);

  // The game has ended: count it towards the streak, and only now ask for example answers.
  useEffect(() => {
    if (!over || !puzzle) return undefined;
    setStats(recordFinish(puzzle.number, puzzle.is_today));
    const controller = new AbortController();
    getReveal(puzzle.number, { signal: controller.signal })
      .then(setReveal)
      .catch(() => setReveal(null)); // the examples are a nicety: the score stands without them
    return () => controller.abort();
  }, [over, puzzle]);

  const onVerdict = useCallback(
    (verdict) => {
      const label = `${puzzle.rows[Math.floor(verdict.cell / 3)].label} × ${puzzle.cols[verdict.cell % 3].label}`;
      setGame((current) => applyGuess(current, puzzle.guesses, verdict));
      if (verdict.result === "correct") {
        setNotice(null);
        setSelected(null);
      } else if (verdict.result === "cannot_verify") {
        setNotice({ kind: "cannot_verify", text: verdict.explanation });
      } else {
        setNotice({ kind: "wrong", text: `${verdict.player.name} is not a ${label} answer.` });
      }
    },
    [puzzle],
  );

  if (error) {
    return (
      <div className="grid-empty" role="alert" data-testid="grid-error">
        <p>{error.kind === "not_found" ? (number ? `There is no puzzle #${number}.` : "There is no puzzle for today yet.") : error.message}</p>
        <p>
          <a href="/grid/archive" onClick={go("/grid/archive")}>
            See the archive
          </a>
        </p>
      </div>
    );
  }
  if (!puzzle || !game) {
    return (
      <p className="grid-empty" role="status">
        Loading the puzzle...
      </p>
    );
  }

  const left = guessesLeft(game, puzzle.guesses);
  return (
    <>
      <header className="grid-head">
        <h1>
          OWCS Grid <span className="grid-number">#{puzzle.number}</span>
          {puzzle.difficulty ? (
            <span className={`grid-difficulty grid-difficulty--${puzzle.difficulty.toLowerCase()}`} data-testid="grid-difficulty">
              {puzzle.difficulty}
            </span>
          ) : null}
        </h1>
        <p className="muted">
          {puzzle.date}
          {puzzle.is_today ? "" : " · from the archive"}
        </p>
      </header>

      <Board
        puzzle={puzzle}
        game={game}
        selected={over ? null : selected}
        onSelect={over ? null : setSelected}
        info={info}
        onInfo={(place) => setInfo((open) => (open === place ? null : place))}
        counts={over && reveal ? Object.fromEntries(reveal.cells.map((entry) => [entry.cell, entry.count])) : null}
      />
      <ClueInfo puzzle={puzzle} info={info} onClose={() => setInfo(null)} />
      <YourAnswers puzzle={puzzle} game={game} />

      {over ? (
        <EndScreen puzzle={puzzle} game={game} reveal={reveal} stats={stats} go={go} />
      ) : (
        <>
          <p className="grid-status" role="status" data-testid="grid-status">
            <strong>{left}</strong> {left === 1 ? "guess" : "guesses"} left · <strong>{score(game)}</strong>/9 filled
          </p>
          {notice ? (
            <p className={`grid-notice grid-notice--${notice.kind}`} role="status" data-testid="grid-notice">
              {notice.text}
            </p>
          ) : null}
          {selected === null ? (
            <p className="grid-hint">Tap an empty cell, then name a player who fits its row and column.</p>
          ) : (
            <GuessBox
              key={selected}
              puzzle={puzzle}
              game={game}
              cell={selected}
              onVerdict={onVerdict}
              onError={(text) => setNotice({ kind: "error", text })}
              onCancel={() => setSelected(null)}
            />
          )}
          <button type="button" className="grid-giveup" onClick={() => setGame((current) => giveUp(current))}>
            End game and see answers
          </button>
        </>
      )}

      <HowToPlay puzzle={puzzle} />
      <p className="grid-coverage" data-testid="grid-coverage">
        {puzzle.coverage}
      </p>
      <p className="grid-coverage">
        Your guesses, score and streak are stored only in this browser. Nothing about you is sent to or kept by the
        server.
      </p>
    </>
  );
}

// A header is a button: tapping it opens the clue's exact definition under the board. A hover title cannot be
// reached on a phone, so the definition is never only a tooltip.
function Header({ clue, place, role, className, info, onInfo }) {
  const long = clue.label.length > 16;
  return (
    <button
      type="button"
      role={role}
      className={`${className}${long ? " grid-head-long" : ""}${info === place ? " grid-head-open" : ""}`}
      title={clue.help || undefined}
      aria-expanded={info === place}
      data-testid={`head-${place}`}
      onClick={() => onInfo(place)}
    >
      <span className="grid-head-label">{clue.label}</span>
      <span className="grid-head-i" aria-hidden="true" />
    </button>
  );
}

function Board({ puzzle, game, selected, onSelect, info, onInfo, counts }) {
  // a role grid's row labels are one short word; a mixed grid's can be "Teammate of sHockWave" and need the room
  const wide = puzzle.rows.some((row) => row.label.length > 8);
  return (
    <div
      className={`grid-board${wide ? " grid-board--wide" : ""}`}
      role="grid"
      aria-label={`OWCS Grid ${puzzle.number}`}
      data-testid="grid-board"
    >
      <div className="grid-corner" aria-hidden="true" />
      {puzzle.cols.map((col, c) => (
        <Header key={col.key} clue={col} place={`col${c}`} role="columnheader" className="grid-colhead" info={info} onInfo={onInfo} />
      ))}
      {puzzle.rows.map((row, r) => (
        <Row key={row.key} row={row} r={r} puzzle={puzzle} game={game} selected={selected} onSelect={onSelect} info={info} onInfo={onInfo} counts={counts} />
      ))}
    </div>
  );
}

function Row({ row, r, puzzle, game, selected, onSelect, info, onInfo, counts }) {
  return (
    <>
      <Header clue={row} place={`row${r}`} role="rowheader" className="grid-rowhead" info={info} onInfo={onInfo} />
      {puzzle.cols.map((col, c) => {
        const cell = r * 3 + c;
        const answer = game.filled[cell];
        const label = `${row.label} × ${col.label}`;
        const possible =
          counts && counts[cell] !== undefined ? (
            <span className="grid-cell-count" data-testid={`count-${cell}`}>
              {counts[cell]} possible
            </span>
          ) : null;
        if (answer) {
          return (
            <div key={col.key} className="grid-cell grid-cell--filled" role="gridcell" data-testid={`cell-${cell}`}>
              <span className="grid-cell-name">{answer.name}</span>
              <span className="grid-cell-why">{answer.explanation}</span>
              {possible}
            </div>
          );
        }
        return (
          <button
            key={col.key}
            type="button"
            role="gridcell"
            className={`grid-cell${selected === cell ? " grid-cell--selected" : ""}`}
            data-testid={`cell-${cell}`}
            aria-label={`${label}, empty`}
            aria-pressed={selected === cell}
            disabled={!onSelect}
            onClick={() => onSelect?.(selected === cell ? null : cell)}
          >
            <span aria-hidden="true">{onSelect ? "+" : ""}</span>
            {possible}
          </button>
        );
      })}
    </>
  );
}

// A cell is small and a mixed clue's reason can be two sentences, so each answer's reason is also written out in full.
function YourAnswers({ puzzle, game }) {
  const filled = Object.keys(game.filled)
    .map(Number)
    .sort((x, y) => x - y);
  if (!filled.length) return null;
  return (
    <ul className="grid-yours" data-testid="grid-yours" aria-label="Your answers">
      {filled.map((cell) => (
        <li key={cell}>
          <strong>{game.filled[cell].name}</strong>{" "}
          <span className="muted">
            {puzzle.rows[Math.floor(cell / 3)].label} × {puzzle.cols[cell % 3].label}
          </span>
          <span>{game.filled[cell].explanation}</span>
          <MuseLink link={game.filled[cell].link} name={game.filled[cell].name} />
        </li>
      ))}
    </ul>
  );
}

// The service says where an answer's Muse page is (a question about that player, by id). It sends none for a
// player Muse cannot be asked about by id, and then there is no link: never one that might not resolve.
function MuseLink({ link, name }) {
  if (!link) return null;
  return (
    <a className="grid-muse" href={link} data-testid="grid-muse-link">
      Ask Muse about {name}
    </a>
  );
}

function ClueInfo({ puzzle, info, onClose }) {
  if (!info) return null;
  const index = Number(info.slice(3));
  const clue = info.startsWith("row") ? puzzle.rows[index] : puzzle.cols[index];
  if (!clue) return null;
  return (
    <section className="grid-info" role="note" data-testid="grid-info">
      <div className="grid-guess-head">
        <strong>{clue.label}</strong>
        <button type="button" className="grid-link" onClick={onClose}>
          close
        </button>
      </div>
      <p>{clue.help || "No definition for this clue."}</p>
    </section>
  );
}

function GuessBox({ puzzle, game, cell, onVerdict, onError, onCancel }) {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState([]);
  const [busy, setBusy] = useState(false);
  const input = useRef(null);
  const box = useRef(null);
  const row = puzzle.rows[Math.floor(cell / 3)];
  const col = puzzle.cols[cell % 3];

  useEffect(() => {
    input.current?.focus();
    box.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, []);

  // Name search, a beat after typing stops. A slower earlier answer never overwrites a newer one.
  useEffect(() => {
    const text = query.trim();
    if (!text) {
      setOptions([]);
      return undefined;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchPlayers(text, { signal: controller.signal })
        .then((found) => setOptions(found.players ?? []))
        .catch((thrown) => {
          if (thrown?.kind !== "aborted") setOptions([]);
        });
    }, 160);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  const pick = async (player) => {
    if (busy) return;
    setBusy(true);
    try {
      onVerdict(await postGuess(puzzle.number, cell, player.id));
      setQuery("");
      setOptions([]);
    } catch (thrown) {
      onError(thrown instanceof GridError ? thrown.message : "That guess could not be sent. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="grid-guess" ref={box} data-testid="grid-guess">
      <div className="grid-guess-head">
        <strong>
          {row.label} × {col.label}
        </strong>
        <button type="button" className="grid-link" onClick={onCancel}>
          cancel
        </button>
      </div>
      <p className="muted grid-guess-help">{[row.help, col.help].filter(Boolean).join(" ")}</p>
      <input
        ref={input}
        type="text"
        inputMode="search"
        autoComplete="off"
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        enterKeyHint="search"
        placeholder="Type a player's name"
        aria-label={`Player for ${row.label} × ${col.label}`}
        value={query}
        maxLength={60}
        onChange={(event) => setQuery(event.target.value)}
      />
      {options.length ? (
        <ul className="grid-options" aria-label="Matching players">
          {options.map((player) => {
            const usedIn = cellOf(game, player.id);
            const missed = alreadyMissed(game, cell, player.id);
            const blocked = usedIn !== null || missed;
            return (
              <li key={player.id}>
                <button type="button" disabled={blocked || busy} onClick={() => pick(player)}>
                  <span className="grid-option-name">
                    {player.name}
                    {player.matched ? <span className="muted"> (also {player.matched})</span> : null}
                  </span>
                  <span className="grid-option-detail">
                    {usedIn !== null ? "already used in this grid" : missed ? "already tried here" : player.detail}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : query.trim() ? (
        <p className="muted grid-guess-help">No player by that name yet. Keep typing.</p>
      ) : null}
    </section>
  );
}

function EndScreen({ puzzle, game, reveal, stats, go }) {
  const [shared, setShared] = useState(null); // "copied" | "shared" | "manual"
  const url = `${window.location.origin}/grid/${puzzle.number}`;
  const text = useMemo(() => shareText(puzzle.number, game, url), [puzzle.number, game, url]);
  const filled = score(game);

  const share = async () => {
    try {
      if (navigator.share) {
        await navigator.share({ text });
        setShared("shared");
        return;
      }
      await navigator.clipboard.writeText(text);
      setShared("copied");
    } catch {
      setShared("manual"); // no share sheet and no clipboard permission: the text is on screen to copy by hand
    }
  };

  return (
    <section className="grid-end" data-testid="grid-end">
      <p className="grid-score">
        <strong>{filled}</strong>/9
      </p>
      <p className="muted">
        {filled === 9 ? "A perfect grid." : filled >= 6 ? "Nicely done." : "Tough one."}
        {puzzle.is_today && stats.streak > 1 ? ` ${stats.streak} days in a row.` : ""}
      </p>
      <pre className="grid-share-text" data-testid="grid-share-text">
        {text}
      </pre>
      <button type="button" className="grid-share" onClick={share}>
        {shared === "copied" ? "Copied" : shared === "shared" ? "Shared" : "Share result"}
      </button>
      {shared === "manual" ? <p className="muted">Copy the text above to share it.</p> : null}

      {reveal ? (
        <div className="grid-reveal" data-testid="grid-reveal">
          <h2>Some answers</h2>
          <p className="muted">Up to {reveal.per_cell} examples a cell. The count is every answer the cell had.</p>
          <ul>
            {reveal.cells.map((entry) => (
              <li key={entry.cell}>
                <strong>
                  {puzzle.rows[Math.floor(entry.cell / 3)].label} × {puzzle.cols[entry.cell % 3].label}
                </strong>
                {entry.count !== undefined ? (
                  <span className="grid-reveal-count">
                    {entry.count} possible {entry.count === 1 ? "answer" : "answers"}
                  </span>
                ) : null}
                <span>
                  {entry.examples.map((example, index) => {
                    const text = example.maps !== undefined ? `${example.name} (${example.maps})` : example.name;
                    return (
                      <span key={example.id}>
                        {index ? ", " : ""}
                        {example.link ? (
                          <a href={example.link} title={`Ask Muse about ${example.name}`}>
                            {text}
                          </a>
                        ) : (
                          text
                        )}
                      </span>
                    );
                  })}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="muted">
        A new puzzle arrives at 00:00 UTC.{" "}
        <a href="/grid/archive" onClick={go("/grid/archive")}>
          Play an earlier one
        </a>
        .
      </p>
    </section>
  );
}

function HowToPlay({ puzzle }) {
  return (
    <details className="grid-how">
      <summary>How to play</summary>
      <ul>
        <li>Each cell wants one player who fits both its row clue and its column clue.</li>
        <li>Tap a clue to see exactly what it means and what it counts.</li>
        {puzzle.min_maps ? (
          <li>
            A player fits a role if they have {puzzle.min_maps} or more maps in it inside the column: that season,
            that region, or their whole OWCS career for "Played all 3 seasons".
          </li>
        ) : (
          <li>
            The two clues are checked separately, except a role beside a season or region, which means that role in
            that season or region.
          </li>
        )}
        <li>
          You have {puzzle.guesses} guesses for the whole grid. Right or wrong, a guess is spent. A player can fill
          only one cell.
        </li>
        <li>
          If the data that would settle a guess is missing, the guess "can't be verified": the cell stays open and no
          guess is spent.
        </li>
        <li>Pick the player from the list: it shows their last team and seasons, to tell same-named players apart.</li>
      </ul>
    </details>
  );
}

function Archive({ go }) {
  const [puzzles, setPuzzles] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    getArchive({ signal: controller.signal })
      .then((loaded) => setPuzzles(loaded.puzzles ?? []))
      .catch((thrown) => {
        if (thrown?.kind !== "aborted") setError(thrown?.message ?? "The archive could not be loaded.");
      });
    return () => controller.abort();
  }, []);

  if (error) {
    return (
      <p className="grid-empty" role="alert">
        {error}
      </p>
    );
  }
  if (!puzzles) {
    return (
      <p className="grid-empty" role="status">
        Loading the archive...
      </p>
    );
  }
  if (!puzzles.length) return <p className="grid-empty">No puzzles have been published yet.</p>;

  return (
    <>
      <header className="grid-head">
        <h1>Archive</h1>
        <p className="muted">Every puzzle so far. Earlier ones do not count towards your streak.</p>
      </header>
      <ul className="grid-archive" data-testid="grid-archive">
        {puzzles.map((entry) => {
          const saved = loadGame(entry.number);
          const started = saved.used > 0 || saved.over;
          const path = entry.is_today ? "/grid" : `/grid/${entry.number}`;
          return (
            <li key={entry.number}>
              <a href={path} onClick={go(path)}>
                <span className="grid-archive-no">#{entry.number}</span>
                <span className="grid-archive-what">
                  {entry.kind === "mixed" ? [...entry.rows, ...entry.cols].join(" · ") : entry.cols.join(" · ")}
                  <span className="muted">
                    {entry.date}
                    {entry.difficulty ? ` · ${entry.difficulty}` : ""}
                    {entry.is_today ? " · today" : ""}
                  </span>
                </span>
                <span className="grid-archive-score">{started ? `${score(saved)}/9` : "play"}</span>
              </a>
            </li>
          );
        })}
      </ul>
    </>
  );
}
