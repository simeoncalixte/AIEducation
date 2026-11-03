import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { ApiError, api, type Debrief } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorPage } from "../components/ErrorPage";
import { useSession } from "../session";

/** Debrief page (mirrors debrief.html + rate/finish/retry POSTs). */
export function DebriefPage() {
  const { attemptId } = useParams();
  const { user, loading } = useSession();
  const navigate = useNavigate();
  const [debrief, setDebrief] = useState<Debrief | null>(null);
  const [score, setScore] = useState("5");
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const attempt = Number(attemptId);

  useEffect(() => {
    if (debrief !== null) {
      document.title = `${debrief.lesson} — results · EvolvingClass`;
    }
  }, [debrief]);

  useEffect(() => {
    if (user === null || !Number.isInteger(attempt)) {
      return;
    }
    api
      .debrief(attempt)
      .then((payload) => {
        setDebrief(payload.debrief);
        setError(null);
      })
      .catch((exc: unknown) =>
        setError(
          exc instanceof ApiError
            ? exc
            : new ApiError(500, "Could not load."),
        ),
      );
  }, [user, attempt]);

  if (!loading && user === null) {
    return <Navigate to="/login" replace />;
  }
  if (!Number.isInteger(attempt)) {
    return <ErrorPage code={404} message="Unknown attempt" />;
  }
  if (error !== null && (error.status === 404 || error.status === 403)) {
    return <ErrorPage code={error.status} message={error.message} />;
  }
  if (user === null || debrief === null) {
    return (
      <>
        {error !== null && <p className="flash">{error.message}</p>}
        <p className="loading">Loading…</p>
      </>
    );
  }

  const fail = (exc: unknown, action: string) => {
    setFlash(exc instanceof Error ? exc.message : `${action} failed.`);
    setBusy(null);
  };

  return (
    <>
      <p className="muted">
        <Link to="/home">Home</Link> / results
      </p>
      <h1>{`${debrief.lesson} — results`}</h1>
      <p className="muted">{debrief.finished ? "Finished" : "In progress"}</p>
      {flash !== null && <p className="flash">{flash}</p>}
      {debrief.preview && (
        <p className="muted">
          Previewing as staff — rating, finishing, and retrying are disabled.
        </p>
      )}

      <h2>Goal verdicts</h2>
      {debrief.verdicts.length > 0 ? (
        <table>
          <tbody>
            <tr>
              <th>Goal</th>
              <th>Result</th>
            </tr>
            {debrief.verdicts.map((verdict) => (
              <tr key={verdict.event_id}>
                <td>{verdict.goal}</td>
                <td>
                  <span
                    className={`pill ${verdict.passed ? "approved" : "rejected"}`}
                  >
                    {verdict.passed ? "pass" : "fail"}
                  </span>{" "}
                  {verdict.source === "teacher" && "(teacher graded)"}
                  {verdict.overridden && "(teacher corrected)"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <EmptyState>No verdicts yet.</EmptyState>
      )}

      <h2>Next steps</h2>
      {debrief.next_steps.length > 0 ? (
        <ul>
          {debrief.next_steps.map((step, position) => (
            <li key={`${step.kind}-${step.goal ?? position}`}>{step.text}</li>
          ))}
        </ul>
      ) : (
        <EmptyState>No follow-ups.</EmptyState>
      )}

      <h2>Enjoyment</h2>
      <p className="muted">
        Your rating: <strong>{debrief.rating ?? "—"}</strong> / 5
      </p>
      {!debrief.preview && (
        <form
          className="block"
          onSubmit={(event) => {
            event.preventDefault();
            setBusy("rate");
            api
              .rateAttempt(attempt, Number(score))
              .then((result) => {
                setDebrief(result.debrief);
                setFlash(result.message);
                setBusy(null);
              })
              .catch((exc: unknown) => fail(exc, "Rating"));
          }}
        >
          <label htmlFor="score">Rate this lesson</label>
          <select
            id="score"
            name="score"
            value={score}
            onChange={(event) => setScore(event.target.value)}
          >
            <option value="5">5 — loved it</option>
            <option value="4">4</option>
            <option value="3">3</option>
            <option value="2">2</option>
            <option value="1">1 — not for me</option>
          </select>
          <div>
            <button type="submit" disabled={busy !== null}>
              Save rating
            </button>
          </div>
        </form>
      )}

      {!debrief.preview && (
        <div className="actions">
          {!debrief.finished && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                setBusy("finish");
                api
                  .finishAttempt(attempt)
                  .then((result) => {
                    setDebrief(result.debrief);
                    setFlash(result.message);
                    setBusy(null);
                  })
                  .catch((exc: unknown) => fail(exc, "Finish"));
              }}
            >
              <button type="submit" disabled={busy !== null}>
                Finish lesson
              </button>
            </form>
          )}
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setBusy("retry");
              api
                .retryAttempt(attempt)
                .then((result) => navigate(result.next))
                .catch((exc: unknown) => fail(exc, "Retry"));
            }}
          >
            <button type="submit" disabled={busy !== null}>
              Retry lesson
            </button>
          </form>
        </div>
      )}
    </>
  );
}
