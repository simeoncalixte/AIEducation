import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import {
  ApiError,
  api,
  type AssignmentProgress,
  type MisconceptionOption,
  type ProgressVerdict,
} from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorPage } from "../components/ErrorPage";
import { useSession } from "../session";

/** Inline verdict-override form for one goal verdict. */
function OverrideForm({
  verdict,
  onDone,
  onError,
}: {
  verdict: ProgressVerdict;
  onDone: (progress: AssignmentProgress, message: string) => void;
  onError: (message: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [corrected, setCorrected] = useState("pass");
  const [score, setScore] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <form
      className="inline"
      onSubmit={(event) => {
        event.preventDefault();
        setBusy(true);
        api
          .overrideVerdict(verdict.event_id, { reason, corrected, score })
          .then((result) => {
            onDone(result.progress, result.message);
            setReason("");
            setScore("");
            setBusy(false);
          })
          .catch((exc: unknown) => {
            onError(exc instanceof Error ? exc.message : "Submit failed.");
            setBusy(false);
          });
      }}
    >
      <input
        type="text"
        size={18}
        placeholder="Reason"
        aria-label={`Override reason for ${verdict.goal}`}
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        required
      />
      <select
        value={corrected}
        aria-label={`Corrected result for ${verdict.goal}`}
        onChange={(event) => setCorrected(event.target.value)}
      >
        <option value="pass">Pass</option>
        <option value="fail">Fail</option>
      </select>
      <input
        type="text"
        size={4}
        placeholder="0–1"
        aria-label={`Corrected score for ${verdict.goal}`}
        value={score}
        onChange={(event) => setScore(event.target.value)}
      />
      <button type="submit" disabled={busy}>
        Override
      </button>
    </form>
  );
}

/** Misconception-flag form for one attempt. */
function FlagForm({
  attemptId,
  misconceptions,
  onDone,
  onError,
}: {
  attemptId: number;
  misconceptions: MisconceptionOption[];
  onDone: (progress: AssignmentProgress, message: string) => void;
  onError: (message: string) => void;
}) {
  const [misconceptionId, setMisconceptionId] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <form
      className="block"
      onSubmit={(event) => {
        event.preventDefault();
        setBusy(true);
        api
          .flagAttempt(attemptId, {
            misconception_id: misconceptionId,
            note,
          })
          .then((result) => {
            onDone(result.progress, result.message);
            setMisconceptionId("");
            setNote("");
            setBusy(false);
          })
          .catch((exc: unknown) => {
            onError(exc instanceof Error ? exc.message : "Submit failed.");
            setBusy(false);
          });
      }}
    >
      <label>
        Misconception
        <select
          value={misconceptionId}
          onChange={(event) => setMisconceptionId(event.target.value)}
        >
          <option value="">General note</option>
          {misconceptions.map((misc) => (
            <option key={misc.id} value={misc.id}>
              {misc.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Note{" "}
        <input
          type="text"
          size={40}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      <button type="submit" disabled={busy}>
        Flag misconception
      </button>
    </form>
  );
}

/** Assignment progress detail (mirrors assignment_detail.html). */
export function AssignmentProgressPage() {
  const { assignmentId } = useParams();
  const { user, loading } = useSession();
  const [progress, setProgress] = useState<AssignmentProgress | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const id = Number(assignmentId);

  useEffect(() => {
    if (progress !== null) {
      document.title = `Progress · ${progress.lesson} · EvolvingClass`;
    }
  }, [progress]);

  useEffect(() => {
    if (user === null || !Number.isInteger(id)) {
      return;
    }
    api
      .assignmentProgress(id)
      .then((payload) => {
        setProgress(payload.progress);
        setError(null);
      })
      .catch((exc: unknown) =>
        setError(
          exc instanceof ApiError
            ? exc
            : new ApiError(500, "Could not load."),
        ),
      );
  }, [user, id]);

  if (!loading && user === null) {
    return <Navigate to="/login" replace />;
  }
  if (!Number.isInteger(id)) {
    return <ErrorPage code={404} message="Unknown assignment" />;
  }
  if (error !== null && (error.status === 403 || error.status === 404)) {
    return <ErrorPage code={error.status} message={error.message} />;
  }
  if (user === null || progress === null) {
    return (
      <>
        {error !== null && <p className="flash">{error.message}</p>}
        <p className="loading">Loading…</p>
      </>
    );
  }

  function refresh(result: AssignmentProgress, message: string) {
    setProgress(result);
    setFlash(message);
  }

  return (
    <>
      <p className="muted">
        <Link to="/assignments">Assignments</Link> / {progress.lesson} →{" "}
        {progress.target}
      </p>
      <h1>
        {progress.lesson} → {progress.target}
      </h1>
      {flash !== null && <p className="flash">{flash}</p>}

      {progress.students.length > 0 ? (
        progress.students.map((student) => (
          <section key={student.id}>
            <h2>{student.name}</h2>
            <p className="muted">
              Enjoyment rating:{" "}
              <strong>{student.rating ?? "—"}</strong> ·{" "}
              {student.attempts.length} attempt(s)
            </p>
            {student.attempts.length > 0 ? (
              student.attempts.map((attempt) => (
                <section key={attempt.id}>
                  <h3>
                    Attempt #{attempt.id}
                    {attempt.retry_of !== null &&
                      ` (retry of #${attempt.retry_of})`}{" "}
                    ·{" "}
                    {attempt.finished !== null
                      ? `finished ${attempt.finished}`
                      : "in progress"}
                  </h3>
                  <h4>Goal verdicts</h4>
                  {attempt.verdicts.length > 0 ? (
                    <table>
                      <thead>
                        <tr>
                          <th>Goal</th>
                          <th>Result</th>
                          <th>Override</th>
                        </tr>
                      </thead>
                      <tbody>
                        {attempt.verdicts.map((verdict) => (
                          <tr key={verdict.event_id}>
                            <td>{verdict.goal}</td>
                            <td>
                              <span
                                className={`pill ${verdict.passed ? "approved" : "rejected"}`}
                              >
                                {verdict.passed ? "pass" : "fail"}
                              </span>{" "}
                              {verdict.source === "teacher" &&
                                "(teacher graded)"}
                              {verdict.overridden &&
                                `(overridden: ${verdict.override_reason})`}
                            </td>
                            <td>
                              {verdict.source === "teacher" ? (
                                <Link
                                  to={`/attempts/${attempt.id}/grading`}
                                >
                                  Re-grade
                                </Link>
                              ) : (
                                <OverrideForm
                                  verdict={verdict}
                                  onDone={refresh}
                                  onError={setFlash}
                                />
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <p className="muted">
                      No verdicts yet for this attempt.
                    </p>
                  )}
                  <h4>Misconception flags</h4>
                  {attempt.flags.length > 0 ? (
                    <ul>
                      {attempt.flags.map((flag) => (
                        <li key={flag.id}>
                          #{flag.id} · {flag.ref} — {flag.note}{" "}
                          <span className="muted">({flag.at})</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="muted">No flags on this attempt.</p>
                  )}
                  <FlagForm
                    attemptId={attempt.id}
                    misconceptions={progress.misconceptions}
                    onDone={refresh}
                    onError={setFlash}
                  />
                </section>
              ))
            ) : (
              <EmptyState>No attempts yet.</EmptyState>
            )}
          </section>
        ))
      ) : (
        <EmptyState>No students in scope.</EmptyState>
      )}
    </>
  );
}
