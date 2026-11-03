import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { ApiError, api, type Challenge } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorPage } from "../components/ErrorPage";
import { useSession } from "../session";

/** Challenge page (mirrors challenge.html + answer POST). */
export function ChallengePage() {
  const { attemptId, index } = useParams();
  const { user, loading } = useSession();
  const navigate = useNavigate();
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  const attempt = Number(attemptId);
  const position = Number(index);

  useEffect(() => {
    if (challenge !== null) {
      document.title =
        `Challenge ${challenge.index} of ${challenge.total} · ` +
        `${challenge.title} · EvolvingClass`;
    }
  }, [challenge]);

  useEffect(() => {
    if (
      user === null ||
      !Number.isInteger(attempt) ||
      !Number.isInteger(position)
    ) {
      return;
    }
    api
      .challenge(attempt, position)
      .then((payload) => {
        setChallenge(payload.challenge);
        setSelected(
          payload.challenge.goals
            .filter((goal) => goal.answered)
            .map((goal) => goal.key),
        );
        setError(null);
      })
      .catch((exc: unknown) =>
        setError(
          exc instanceof ApiError
            ? exc
            : new ApiError(500, "Could not load."),
        ),
      );
  }, [user, attempt, position]);

  if (!loading && user === null) {
    return <Navigate to="/login" replace />;
  }
  if (!Number.isInteger(attempt) || !Number.isInteger(position)) {
    return <ErrorPage code={404} message="Unknown challenge" />;
  }
  if (error !== null && (error.status === 404 || error.status === 403)) {
    return <ErrorPage code={error.status} message={error.message} />;
  }
  if (user === null || challenge === null) {
    return (
      <>
        {error !== null && <p className="flash">{error.message}</p>}
        <p className="loading">Loading…</p>
      </>
    );
  }

  return (
    <>
      <p className="muted">
        <Link to={`/play/${challenge.assignment_id}`}>Briefing</Link> /{" "}
        {challenge.stage}
      </p>
      <h1>{challenge.title}</h1>
      <p>
        <strong>
          {`Challenge ${challenge.index} of ${challenge.total}`}
        </strong>
      </p>
      {challenge.guides.length > 0 && (
        <p className="muted">
          Guide: {challenge.guides.map((guide) => guide.name).join(", ")}
        </p>
      )}
      {flash !== null && <p className="flash">{flash}</p>}
      {challenge.finished ? (
        <EmptyState>
          <>
            This attempt is finished.{" "}
            <Link to={`/play/attempt/${challenge.attempt_id}/debrief`}>
              See results…
            </Link>
          </>
        </EmptyState>
      ) : challenge.preview ? (
        <>
          <p className="muted">
            Previewing as staff — submitting answers is disabled.
          </p>
          <ul>
            {challenge.goals.map((goal) => (
              <li key={goal.key}>
                <label>
                  <input
                    type="checkbox"
                    checked={goal.answered}
                    disabled
                    readOnly
                  />{" "}
                  {goal.key}
                </label>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            setBusy(true);
            api
              .answerChallenge(attempt, position, { goals: selected, note })
              .then((result) => navigate(result.next))
              .catch((exc: unknown) => {
                setFlash(
                  exc instanceof Error ? exc.message : "Submit failed.",
                );
                setBusy(false);
              });
          }}
        >
          <p>Check off each goal you completed in the scene:</p>
          {challenge.goals.map((goal) => (
            <label key={goal.key}>
              <input
                type="checkbox"
                name="goals"
                value={goal.key}
                checked={selected.includes(goal.key)}
                onChange={(event) => {
                  const checked = event.target.checked;
                  setSelected((current) =>
                    checked
                      ? [...current, goal.key]
                      : current.filter((key) => key !== goal.key),
                  );
                }}
              />{" "}
              {goal.key}
            </label>
          ))}
          <label htmlFor="note">Note (optional)</label>
          <input
            type="text"
            id="note"
            name="note"
            size={40}
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
          <div>
            <button type="submit" disabled={busy}>
              {challenge.index < challenge.total
                ? "Next challenge"
                : "See results"}
            </button>
          </div>
        </form>
      )}
    </>
  );
}
