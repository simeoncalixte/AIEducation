import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import {
  ApiError,
  api,
  type AssignmentOptions,
  type AssignmentRow,
} from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorPage } from "../components/ErrorPage";
import { useSession } from "../session";

/** Assignment list with assign form (mirrors assignments.html + POST). */
export function AssignmentsPage() {
  const { user, loading } = useSession();
  const [assignments, setAssignments] = useState<AssignmentRow[] | null>(
    null,
  );
  const [options, setOptions] = useState<AssignmentOptions | null>(null);
  const [lessonId, setLessonId] = useState("");
  const [classroomId, setClassroomId] = useState("");
  const [studentId, setStudentId] = useState("");
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    document.title = "Assignments · EvolvingClass";
  }, []);

  useEffect(() => {
    if (user === null) {
      return;
    }
    api
      .assignments()
      .then((payload) => {
        setAssignments(payload.assignments);
        setOptions(payload.options);
        setError(null);
        if (payload.options.lessons.length > 0) {
          setLessonId((current) =>
            current === ""
              ? String(payload.options.lessons[0].id)
              : current,
          );
        }
      })
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
  if (user === null || assignments === null || options === null) {
    return (
      <>
        {error !== null && <p className="flash">{error.message}</p>}
        <p className="loading">Loading…</p>
      </>
    );
  }

  return (
    <>
      <h1>Assignments</h1>
      {flash !== null && <p className="flash">{flash}</p>}
      {assignments.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>Lesson</th>
              <th>Target</th>
              <th>Assigned by</th>
              <th>Attempts</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {assignments.map((assignment) => (
              <tr key={assignment.id}>
                <td>{assignment.lesson}</td>
                <td>{assignment.target}</td>
                <td>{assignment.by}</td>
                <td>{assignment.attempts}</td>
                <td>
                  <Link to={`/assignments/${assignment.id}`}>
                    Progress…
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <EmptyState>No assignments yet. Assign a lesson below.</EmptyState>
      )}

      <h2>New assignment</h2>
      <p className="muted">
        Pick exactly one target: a classroom or one student.
      </p>
      <form
        className="block"
        onSubmit={(event) => {
          event.preventDefault();
          setBusy(true);
          api
            .assign({
              lesson_id: lessonId,
              classroom_id: classroomId,
              student_id: studentId,
            })
            .then((result) => {
              setAssignments(result.assignments);
              setOptions(result.options);
              setFlash(result.message);
              setClassroomId("");
              setStudentId("");
              setBusy(false);
            })
            .catch((exc: unknown) => {
              setFlash(
                exc instanceof Error ? exc.message : "Submit failed.",
              );
              setBusy(false);
            });
        }}
      >
        <label htmlFor="lesson_id">Lesson</label>
        <select
          id="lesson_id"
          value={lessonId}
          onChange={(event) => setLessonId(event.target.value)}
        >
          {options.lessons.map((lesson) => (
            <option key={lesson.id} value={lesson.id}>
              {lesson.title} ({lesson.classroom})
            </option>
          ))}
        </select>
        <label htmlFor="classroom_id">Classroom</label>
        <select
          id="classroom_id"
          value={classroomId}
          onChange={(event) => setClassroomId(event.target.value)}
        >
          <option value="">—</option>
          {options.classrooms.map((room) => (
            <option key={room.id} value={room.id}>
              {room.name}
            </option>
          ))}
        </select>
        <label htmlFor="student_id">Student</label>
        <select
          id="student_id"
          value={studentId}
          onChange={(event) => setStudentId(event.target.value)}
        >
          <option value="">—</option>
          {options.students.map((student) => (
            <option key={student.id} value={student.id}>
              {student.name}
            </option>
          ))}
        </select>
        <div>
          <button type="submit" disabled={busy}>
            Assign lesson
          </button>
        </div>
      </form>
    </>
  );
}
