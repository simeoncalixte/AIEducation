import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { ApiError, api, type ReviewQueues } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorPage } from "../components/ErrorPage";
import { useSession } from "../session";

const LEVELS = [
  { kind: "asset", heading: "Asset proposals" },
  { kind: "stage", heading: "Stage proposals" },
  { kind: "lesson", heading: "Lesson proposals" },
] as const;

/** Teacher review queues (mirrors queues.html + /review). */
export function ReviewQueuesPage() {
  const { user, loading } = useSession();
  const [queues, setQueues] = useState<ReviewQueues | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    document.title = "Review queues · EvolvingClass";
  }, []);

  useEffect(() => {
    if (user === null) {
      return;
    }
    api
      .review()
      .then((payload) => setQueues(payload.queues))
      .catch((exc: unknown) =>
        setError(
          exc instanceof ApiError
            ? exc
            : new ApiError(500, "Could not load."),
        ),
      );
  }, [user]);

  if (!loading && user === null) {
    return <Navigate to="/login" replace />;
  }
  if (error !== null && error.status === 403) {
    return <ErrorPage code={403} message={error.message} />;
  }
  if (user === null || queues === null) {
    return (
      <>
        {error !== null && <p className="flash">{error.message}</p>}
        <p className="loading">Loading…</p>
      </>
    );
  }
  return (
    <>
      <h1>Review queues</h1>
      {LEVELS.map(({ kind, heading }) => (
        <section key={kind} aria-label={heading}>
          <h2>{heading}</h2>
          {queues[kind].length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Proposal</th>
                  <th>Ver</th>
                  <th>Status</th>
                  <th>Decision</th>
                  <th>Rationale</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {queues[kind].map((row) => (
                  <tr key={row.id}>
                    <td>
                      {row.title}{" "}
                      {row.low_impact && (
                        <span className="pill draft">Low impact</span>
                      )}
                    </td>
                    <td>{`v${row.version_no}`}</td>
                    <td>
                      <span className={`pill ${row.status}`}>
                        {row.status}
                      </span>
                    </td>
                    <td>
                      <span className={`pill ${row.decision}`}>
                        {row.decision}
                      </span>
                    </td>
                    <td>{row.rationale}</td>
                    <td>
                      <Link to={`/review/${kind}/${row.id}`}>Open</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState>Nothing here yet.</EmptyState>
          )}
        </section>
      ))}
    </>
  );
}
