import { useEffect, useState } from "react";
import {
  Link,
  Navigate,
  useNavigate,
  useParams,
} from "react-router-dom";
import { ApiError, api, type BriefContext } from "../api";
import { ErrorPage } from "../components/ErrorPage";
import { useSession } from "../session";

/** Brief composer (mirrors brief.html + /lessons brief POST). */
export function BriefComposerPage() {
  const { lessonId } = useParams();
  const { user, loading } = useSession();
  const navigate = useNavigate();
  const [brief, setBrief] = useState<BriefContext | null>(null);
  const [focus, setFocus] = useState("");
  const [studentId, setStudentId] = useState("");
  const [objectives, setObjectives] = useState("");
  const [mentalModels, setMentalModels] = useState("");
  const [mustInclude, setMustInclude] = useState("");
  const [mustAvoid, setMustAvoid] = useState("");
  const [priority, setPriority] = useState("1");
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  const id = Number(lessonId);

  useEffect(() => {
    if (brief !== null) {
      document.title = `Brief ${brief.title} · EvolvingClass`;
    }
  }, [brief]);

  useEffect(() => {
    if (user === null || !Number.isInteger(id)) {
      return;
    }
    api
      .brief(id)
      .then((payload) => {
        setBrief(payload.brief);
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
  if (user === null || brief === null) {
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
        <Link to="/lessons">Lessons</Link> / brief {brief.title}
      </p>
      <h1>Brief: {brief.title}</h1>
      <p className="muted">
        {brief.subject} · {brief.classroom}
      </p>

      <h2>Active directives</h2>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Kind</th>
            <th>Scope</th>
            <th>Active</th>
            <th>Focus</th>
          </tr>
        </thead>
        <tbody>
          {brief.directives.length > 0 ? (
            brief.directives.map((directive) => (
              <tr key={directive.id}>
                <td>#{directive.id}</td>
                <td>{directive.kind}</td>
                <td>{directive.scope}</td>
                <td>{directive.active ? "yes" : "no"}</td>
                <td>{directive.focus}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={5} className="muted">
                No directives yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <p>
        <Link to={`/lessons/${brief.id}/directives`}>
          Manage all directives…
        </Link>
      </p>

      <h2>New brief</h2>
      {flash !== null && <p className="flash">{flash}</p>}
      <form
        className="block"
        onSubmit={(event) => {
          event.preventDefault();
          setBusy(true);
          api
            .submitBrief(brief.id, {
              focus,
              objectives,
              mental_models: mentalModels,
              must_include: mustInclude,
              must_avoid: mustAvoid,
              priority,
              student_id: studentId,
            })
            .then((result) =>
              navigate(
                `/review/${result.dossier.kind}/${result.dossier.id}`,
                { state: { flash: result.message } },
              ),
            )
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
          placeholder="What should agents draft toward?"
        />
        <label htmlFor="student_id">Scope</label>
        <select
          id="student_id"
          value={studentId}
          onChange={(event) => setStudentId(event.target.value)}
        >
          <option value="">Class-wide</option>
          {brief.roster.map((student) => (
            <option key={student.id} value={student.id}>
              {student.name}
            </option>
          ))}
        </select>
        <label htmlFor="objectives">Objectives (one per line)</label>
        <textarea
          id="objectives"
          rows={3}
          value={objectives}
          onChange={(event) => setObjectives(event.target.value)}
        />
        <label htmlFor="mental_models">Mental models (one per line)</label>
        <textarea
          id="mental_models"
          rows={3}
          value={mentalModels}
          onChange={(event) => setMentalModels(event.target.value)}
        />
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
            Submit brief
          </button>
        </div>
      </form>
    </>
  );
}
