import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api, type HomePayload } from "../api";
import { EmptyState } from "../components/EmptyState";
import { useSession } from "../session";

/** Role-based home (mirrors home.html + /home). */
export function HomePage() {
  const { user, loading } = useSession();
  const [payload, setPayload] = useState<HomePayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.title = "Home · EvolvingClass";
  }, []);

  useEffect(() => {
    if (user === null) {
      return;
    }
    api
      .home()
      .then(setPayload)
      .catch((exc: unknown) =>
        setError(exc instanceof Error ? exc.message : "Could not load."),
      );
  }, [user]);

  if (!loading && user === null) {
    return <Navigate to="/login" replace />;
  }
  if (user === null || payload === null) {
    return (
      <>
        {error !== null && <p className="flash">{error}</p>}
        <p className="loading">Loading…</p>
      </>
    );
  }
  if (payload.links !== undefined) {
    return (
      <>
        <h1>{`Welcome, ${user.name}`}</h1>
        <ul>
          {payload.links.map((link) => (
            <li key={link.href}>
              <Link to={link.href}>{link.label}</Link>{" "}
              <span className="muted">— {link.blurb}</span>
            </li>
          ))}
        </ul>
      </>
    );
  }
  return (
    <>
      <h1>{`Welcome, ${user.name}`}</h1>
      <h2>My assignments</h2>
      {payload.assignments.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>Lesson</th>
              <th>Status</th>
              <th>Attempts</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {payload.assignments.map((assignment) => (
              <tr key={assignment.id}>
                <td>{assignment.lesson}</td>
                <td>{assignment.status}</td>
                <td>{assignment.attempts}</td>
                <td>
                  <Link to={`/play/${assignment.id}`}>Open…</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <EmptyState>
          No assignments yet. Your teacher&apos;s assignments will appear
          here.
        </EmptyState>
      )}
    </>
  );
}
