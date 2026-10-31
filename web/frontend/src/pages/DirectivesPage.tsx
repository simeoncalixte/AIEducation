import { useEffect, useState } from "react";
import { Link, Navigate, useLocation, useParams } from "react-router-dom";
import { ApiError, api, type DirectivesPanel } from "../api";
import { ErrorPage } from "../components/ErrorPage";
import { useSession } from "../session";

/** Directives panel (mirrors directives.html + steer/deactivate POSTs). */
export function DirectivesPage() {
  const { lessonId } = useParams();
  const { user, loading } = useSession();
  const location = useLocation();
  const [panel, setPanel] = useState<DirectivesPanel | null>(null);
  const [focus, setFocus] = useState("");
  const [studentId, setStudentId] = useState("");
  const [mustInclude, setMustInclude] = useState("");
  const [mustAvoid, setMustAvoid] = useState("");
  const [priority, setPriority] = useState("1");
  const [flash, setFlash] = useState<string | null>(
    (location.state as { flash?: string } | null)?.flash ?? null,
  );
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [deactivating, setDeactivating] = useState<number | null>(null);

  const id = Number(lessonId);

  useEffect(() => {
    if (panel !== null) {
      document.title = `Directives ${panel.title} · EvolvingClass`;
    }
  }, [panel]);

  useEffect(() => {
    if (user === null || !Number.isInteger(id)) {
      return;
    }
    api
      .directivesPanel(id)
      .then((payload) => {
        setPanel(payload.panel);
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
    return <ErrorPage code={404} message="Unknown lesson" />;
  }
  if (error !== null && (error.status === 403 || error.status === 404)) {
    return <ErrorPage code={error.status} message={error.message} />;
  }
  if (user === null || panel === null) {
    return (
      <>
        {error !== null && <p className="flash">{error.message}</p>}
        <p className="loading">Loading…</p>
      </>
    );
  }

  function resetForm() {
    setFocus("");
    setStudentId("");
    setMustInclude("");
    setMustAvoid("");
    setPriority("1");
  }

  return (
    <>
      <p className="muted">
        <Link to="/lessons">Lessons</Link> / directives for {panel.title}
      </p>
      <h1>Directives: {panel.title}</h1>
      <p className="muted">
        {panel.subject} · {panel.classroom}
      </p>
      {flash !== null && <p className="flash">{flash}</p>}

      <h2>Active and past directives</h2>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Kind</th>
            <th>Scope</th>
            <th>Focus</th>
            <th>Priority</th>
            <th>Active</th>
            <th></th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {panel.directives.length > 0 ? (
            panel.directives.map((directive) => (
              <tr key={directive.id}>
                <td>#{directive.id}</td>
                <td>{directive.kind}</td>
                <td>{directive.scope}</td>
                <td>{directive.focus}</td>
                <td>{directive.priority}</td>
                <td>{directive.active ? "yes" : "no"}</td>
                <td>
                  <Link to={`/directives/${directive.id}/edit`}>Edit…</Link>
                </td>
                <td>
                  {directive.active && (
                    <button
                      type="button"
                      disabled={deactivating !== null}
                      onClick={() => {
                        setDeactivating(directive.id);
                        api
                          .deactivateDirective(directive.id)
                          .then((result) => {
                            setPanel(result.panel);
                            setFlash(result.message);
                            setDeactivating(null);
                          })
                          .catch((exc: unknown) => {
                            setFlash(
                              exc instanceof Error
                                ? exc.message
                                : "Deactivation failed.",
                            );
                            setDeactivating(null);
                          });
                      }}
                    >
                      {deactivating === directive.id
                        ? "Deactivating…"
                        : "Deactivate"}
                    </button>
                  )}
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={8} className="muted">
                No directives yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h2>New steer directive</h2>
      <form
        className="block"
        onSubmit={(event) => {
          event.preventDefault();
          setBusy(true);
          api
            .createDirective(panel.id, {
              focus,
              must_include: mustInclude,
              must_avoid: mustAvoid,
              priority,
              student_id: studentId,
            })
            .then((result) => {
              setPanel(result.panel);
              setFlash(result.message);
              resetForm();
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
        <label htmlFor="focus">Focus</label>
        <input
          type="text"
          id="focus"
          value={focus}
          onChange={(event) => setFocus(event.target.value)}
          placeholder="What should agents steer toward?"
        />
        <label htmlFor="student_id">Scope</label>
        <select
          id="student_id"
          value={studentId}
          onChange={(event) => setStudentId(event.target.value)}
        >
          <option value="">Class-wide</option>
          {panel.roster.map((student) => (
            <option key={student.id} value={student.id}>
              {student.name}
            </option>
          ))}
        </select>
        <label htmlFor="must_include">Must-include (comma-separated)</label>
        <input
          type="text"
          id="must_include"
          value={mustInclude}
          onChange={(event) => setMustInclude(event.target.value)}
        />
        <label htmlFor="must_avoid">Must-avoid (comma-separated)</label>
        <input
          type="text"
          id="must_avoid"
          value={mustAvoid}
          onChange={(event) => setMustAvoid(event.target.value)}
        />
        <label htmlFor="priority">Priority</label>
        <input
          type="text"
          id="priority"
          size={4}
          value={priority}
          onChange={(event) => setPriority(event.target.value)}
        />
        <div>
          <button type="submit" disabled={busy}>
            Record directive
          </button>
        </div>
      </form>
    </>
  );
}
