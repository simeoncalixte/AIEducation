import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import {
  ApiError,
  api,
  type Grading,
  type GradingGoal,
} from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorPage } from "../components/ErrorPage";
import { useSession } from "../session";

/** Rubric criteria as a list, falling back to raw JSON. */
function Rubric({ rubric }: { rubric: Record<string, unknown> }) {
  const criteria = rubric.criteria;
  if (Array.isArray(criteria) && criteria.length > 0) {
    return (
      <ul>
        {criteria.map((item, position) => (
          <li key={position}>{String(item)}</li>
        ))}
      </ul>
    );
  }
  return <pre>{JSON.stringify(rubric)}</pre>;
}

/** Pass/fail + rationale form for one teacher-graded goal. */
function GradeForm({
  goal,
  attemptId,
  onDone,
  onError,
}: {
  goal: GradingGoal;
  attemptId: number;
  onDone: (message: string) => void;
  onError: (message: string) => void;
}) {
  const [passed, setPassed] = useState("pass");
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <form
      className="block"
      onSubmit={(event) => {
        event.preventDefault();
        setBusy(true);
        api
          .gradeGoal(attemptId, {
            goal_id: goal.goal_id,
            passed: passed === "pass",
            rationale,
          })
          .then((result) => {
            onDone(result.message);
            setRationale("");
            setBusy(false);
          })
          .catch((exc: unknown) => {
            onError(exc instanceof Error ? exc.message : "Submit failed.");
            setBusy(false);
          });
      }}
    >
      <label>
        Result for {goal.key}
        <select
          value={passed}
          aria-label={`Result for ${goal.key}`}
          onChange={(event) => setPassed(event.target.value)}
        >
          <option value="pass">Pass</option>
          <option value="fail">Fail</option>
        </select>
      </label>
      <label>
        Rationale
        <input
          type="text"
          size={40}
          aria-label={`Rationale for ${goal.key}`}
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
        />
      </label>
      <div>
        <button type="submit" disabled={busy}>
          Record grade
        </button>
      </div>
    </form>
  );
}

/** Rubric grading view: recorded evidence beside rubric criteria (SCRUM-129). */
export function GradingPage() {
  const { attemptId } = useParams();
  const { user, loading } = useSession();
  const [grading, setGrading] = useState<Grading | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const attempt = Number(attemptId);

  const reload = (id: number) => {
    api
      .grading(id)
      .then((payload) => {
        setGrading(payload.grading);
        setError(null);
      })
      .catch((exc: unknown) =>
        setError(
          exc instanceof ApiError
            ? exc
            : new ApiError(500, "Could not load."),
        ),
      );
  };

  useEffect(() => {
    if (grading !== null) {
      document.title = `${grading.lesson} — grading · EvolvingClass`;
    }
  }, [grading]);

  useEffect(() => {
    if (user === null || !Number.isInteger(attempt)) {
      return;
    }
    reload(attempt);
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
  if (user === null || grading === null) {
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
        <Link to="/home">Home</Link> /{" "}
        <Link to={`/play/attempt/${grading.attempt_id}/debrief`}>
          results
        </Link>{" "}
        / grading
      </p>
      <h1>{`${grading.lesson} — grading ${grading.student}`}</h1>
      <p className="muted">
        {grading.finished ? "Finished" : "In progress"}
      </p>
      {flash !== null && <p className="flash">{flash}</p>}

      <h2>Recorded evidence</h2>
      {grading.evidence.length > 0 ? (
        <table>
          <tbody>
            <tr>
              <th>#</th>
              <th>Event</th>
              <th>Note</th>
            </tr>
            {grading.evidence.map((item) => (
              <tr key={item.id}>
                <td>{item.sequence_no}</td>
                <td>
                  {item.verb} · {item.object_ref}
                </td>
                <td>{item.note === "" ? "—" : item.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <EmptyState>No recorded evidence yet.</EmptyState>
      )}

      <h2>Rubric goals</h2>
      {grading.goals.length > 0 ? (
        grading.goals.map((goal) => (
          <section key={goal.goal_id} aria-label={`Grade ${goal.key}`}>
            <h3>
              {goal.key} <span className="muted">· {goal.challenge}</span>
            </h3>
            <Rubric rubric={goal.rubric} />
            {goal.evaluation === null ? (
              <p className="muted">Not graded yet.</p>
            ) : (
              <p>
                <span
                  className={`pill ${goal.evaluation.passed ? "approved" : "rejected"}`}
                >
                  {goal.evaluation.passed ? "pass" : "fail"}
                </span>{" "}
                <span className="muted">
                  by {goal.evaluation.by}
                  {goal.evaluation.rationale !== "" &&
                    ` — ${goal.evaluation.rationale}`}
                </span>
              </p>
            )}
            <GradeForm
              goal={goal}
              attemptId={grading.attempt_id}
              onDone={(message) => {
                setFlash(message);
                reload(grading.attempt_id);
              }}
              onError={setFlash}
            />
          </section>
        ))
      ) : (
        <EmptyState>No teacher-graded goals in this lesson.</EmptyState>
      )}
    </>
  );
}
