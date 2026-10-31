import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { ApiError, api, type Briefing } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorPage } from "../components/ErrorPage";
import { useSession } from "../session";

/** Lesson briefing (mirrors briefing.html + /play start POST). */
export function BriefingPage() {
  const { assignmentId } = useParams();
  const { user, loading } = useSession();
  const navigate = useNavigate();
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  const id = Number(assignmentId);

  useEffect(() => {
    if (briefing !== null) {
      document.title = `Briefing · ${briefing.lesson} · EvolvingClass`;
    }
  }, [briefing]);

  useEffect(() => {
    if (user === null || !Number.isInteger(id)) {
      return;
    }
    api
      .briefing(id)
      .then((payload) => {
        setBriefing(payload.briefing);
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
  if (error !== null && error.status === 404) {
    return <ErrorPage code={error.status} message={error.message} />;
  }
  if (user === null || briefing === null) {
    return (
      <>
        {error !== null && <p className="flash">{error.message}</p>}
        <p className="loading">Loading…</p>
      </>
    );
  }

  const objectives = briefing.objectives ?? [];
  const models = briefing.models ?? [];
  const stages = briefing.stages ?? [];

  return (
    <>
      <p className="muted">
        <Link to="/home">Home</Link> / briefing
      </p>
      <h1>{briefing.lesson}</h1>
      {flash !== null && <p className="flash">{flash}</p>}
      {!briefing.published ? (
        <EmptyState>
          This lesson is not published yet. Check back after your teacher
          publishes it.
        </EmptyState>
      ) : (
        <>
          <h2>Objectives</h2>
          {objectives.length > 0 ? (
            <ul>
              {objectives.map((objective) => (
                <li key={objective}>{objective}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">No objectives listed.</p>
          )}
          <h2>Ideas you will build</h2>
          {models.length > 0 ? (
            <ul>
              {models.map((model) => (
                <li key={model}>{model}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">No mental models listed.</p>
          )}
          <h2>{`Stages (${stages.length})`}</h2>
          {stages.length > 0 ? (
            <ol>
              {stages.map((stage) => (
                <li key={stage}>{stage}</li>
              ))}
            </ol>
          ) : (
            <p className="muted">No stages pinned yet.</p>
          )}
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setBusy(true);
              api
                .startAttempt(id)
                .then((result) => navigate(result.next))
                .catch((exc: unknown) => {
                  setFlash(
                    exc instanceof Error ? exc.message : "Submit failed.",
                  );
                  setBusy(false);
                });
            }}
          >
            <button type="submit" disabled={busy}>
              {briefing.open_attempt_id ? "Continue lesson" : "Start lesson"}
            </button>
          </form>
        </>
      )}
    </>
  );
}
