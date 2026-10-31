import { useCallback, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { ApiError, api, type AuditPayload } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorPage } from "../components/ErrorPage";
import { useSession } from "../session";

function toError(exc: unknown): ApiError {
  return exc instanceof ApiError
    ? exc
    : new ApiError(500, "Could not load.");
}

/** School audit: lesson status plus filterable history (mirrors audit.html). */
export function AuditPage() {
  const { user, loading } = useSession();
  const [payload, setPayload] = useState<AuditPayload | null>(null);
  const [actor, setActor] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [filtering, setFiltering] = useState(false);

  useEffect(() => {
    document.title = "Audit · EvolvingClass";
  }, []);

  const load = useCallback(
    (query?: { actor?: string; since?: string; until?: string }) => {
      setFiltering(true);
      api
        .audit(query)
        .then((next) => {
          setPayload(next);
          setError(null);
          setFiltering(false);
        })
        .catch((exc: unknown) => {
          setError(toError(exc));
          setFiltering(false);
        });
    },
    [],
  );

  useEffect(() => {
    if (user === null) {
      return;
    }
    load();
  }, [user, load]);

  if (!loading && user === null) {
    return <Navigate to="/login" replace />;
  }
  if (error !== null && error.status === 403) {
    return <ErrorPage code={403} message={error.message} />;
  }
  if (user === null || payload === null) {
    return (
      <>
        {error !== null && <p className="flash">{error.message}</p>}
        <p className="loading">Loading…</p>
      </>
    );
  }
  return (
    <>
      <h1>School audit</h1>

      <h2>Lesson status by classroom</h2>
      {payload.status.length > 0 ? (
        payload.status.map((room) => (
          <section key={room.name} aria-label={room.name}>
            <h3>{room.name}</h3>
            {room.lessons.length > 0 ? (
              <table>
                <thead>
                  <tr>
                    <th>Lesson</th>
                    <th>Subject</th>
                    <th>Drafts</th>
                    <th>Published</th>
                    <th>Retired</th>
                    <th>Assignments</th>
                    <th>Attempts</th>
                  </tr>
                </thead>
                <tbody>
                  {room.lessons.map((lesson) => (
                    <tr key={lesson.id}>
                      <td>{lesson.title}</td>
                      <td>{lesson.subject}</td>
                      <td>{lesson.drafts}</td>
                      <td>{lesson.published}</td>
                      <td>{lesson.retired}</td>
                      <td>{lesson.assignments}</td>
                      <td>{lesson.attempts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState>No lessons in this classroom.</EmptyState>
            )}
          </section>
        ))
      ) : (
        <EmptyState>No classrooms yet.</EmptyState>
      )}

      <h2>Approvals and publish history</h2>
      <form
        className="block"
        onSubmit={(event) => {
          event.preventDefault();
          load({ actor, since, until });
        }}
      >
        <label htmlFor="actor">Actor</label>
        <select
          id="actor"
          value={actor}
          onChange={(event) => setActor(event.target.value)}
        >
          <option value="">Everyone</option>
          {payload.actors.map((entry) => (
            <option key={entry.id} value={entry.id}>
              {`${entry.name} (${entry.role})`}
            </option>
          ))}
        </select>
        <label htmlFor="since">Since</label>
        <input
          type="date"
          id="since"
          value={since}
          onChange={(event) => setSince(event.target.value)}
        />
        <label htmlFor="until">Until</label>
        <input
          type="date"
          id="until"
          value={until}
          onChange={(event) => setUntil(event.target.value)}
        />
        <div>
          <button type="submit" disabled={filtering}>
            Filter
          </button>
        </div>
      </form>
      {payload.trail.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>At</th>
              <th>Actor</th>
              <th>Kind</th>
              <th>Result</th>
              <th>Target</th>
              <th>Rationale</th>
            </tr>
          </thead>
          <tbody>
            {payload.trail.map((row, index) => (
              <tr key={`${row.at_text}-${row.actor_id}-${index}`}>
                <td>{row.at_text}</td>
                <td>{row.actor}</td>
                <td>{row.kind}</td>
                <td>{row.result}</td>
                <td>{row.target}</td>
                <td>{row.rationale}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <EmptyState>No history matches these filters.</EmptyState>
      )}
    </>
  );
}
