import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { ApiError, api, type LessonRow } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorPage } from "../components/ErrorPage";
import { useSession } from "../session";

/** Teacher lesson list (mirrors lessons.html + /lessons). */
export function LessonsPage() {
  const { user, loading } = useSession();
  const [lessons, setLessons] = useState<LessonRow[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    document.title = "Lessons · EvolvingClass";
  }, []);

  useEffect(() => {
    if (user === null) {
      return;
    }
    api
      .lessons()
      .then((payload) => setLessons(payload.lessons))
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
  if (user === null || lessons === null) {
    return (
      <>
        {error !== null && <p className="flash">{error.message}</p>}
        <p className="loading">Loading…</p>
      </>
    );
  }
  return (
    <>
      <h1>Lessons</h1>
      <p className="muted">
        Pick a lesson to brief it: your focus and constraints become a
        brief directive, and agents draft a lesson proposal for review.
      </p>
      {lessons.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>Lesson</th>
              <th>Subject</th>
              <th>Classroom</th>
              <th>Drafts</th>
              <th>Published</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {lessons.map((lesson) => (
              <tr key={lesson.id}>
                <td>{lesson.title}</td>
                <td>{lesson.subject}</td>
                <td>{lesson.classroom}</td>
                <td>{lesson.drafts}</td>
                <td>{lesson.published}</td>
                <td>
                  <Link to={`/lessons/${lesson.id}/brief`}>Brief…</Link>{" "}
                  <Link to={`/lessons/${lesson.id}/directives`}>
                    Directives
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <EmptyState>No lessons yet.</EmptyState>
      )}
    </>
  );
}
