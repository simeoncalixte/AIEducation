import { useEffect, useState } from "react";
import {
  Link,
  Navigate,
  useNavigate,
  useParams,
} from "react-router-dom";
import { ApiError, api, type DirectiveDetail } from "../api";
import { ErrorPage } from "../components/ErrorPage";
import { useSession } from "../session";

/** Edit-directive form (mirrors directive_edit.html + edit POST). */
export function EditDirectivePage() {
  const { directiveId } = useParams();
  const { user, loading } = useSession();
  const navigate = useNavigate();
  const [directive, setDirective] = useState<DirectiveDetail | null>(null);
  const [focus, setFocus] = useState("");
  const [mustInclude, setMustInclude] = useState("");
  const [mustAvoid, setMustAvoid] = useState("");
  const [priority, setPriority] = useState("1");
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  const id = Number(directiveId);

  useEffect(() => {
    if (directive !== null) {
      document.title = `Edit directive #${directive.id} · EvolvingClass`;
    }
  }, [directive]);

  useEffect(() => {
    if (user === null || !Number.isInteger(id)) {
      return;
    }
    api
      .directive(id)
      .then((payload) => {
        setDirective(payload.directive);
        setFocus(payload.directive.focus);
        setMustInclude(payload.directive.must_include);
        setMustAvoid(payload.directive.must_avoid);
        setPriority(String(payload.directive.priority));
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
    return <ErrorPage code={404} message="Unknown directive" />;
  }
  if (error !== null && (error.status === 403 || error.status === 404)) {
    return <ErrorPage code={error.status} message={error.message} />;
  }
  if (user === null || directive === null) {
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
        <Link to={`/lessons/${directive.lesson_id}/directives`}>
          Back to directives
        </Link>
      </p>
      <h1>Edit directive #{directive.id}</h1>
      <p className="muted">
        {directive.kind} · {directive.scope} ·{" "}
        {directive.active ? "active" : "inactive"}
      </p>
      {flash !== null && <p className="flash">{flash}</p>}
      <form
        className="block"
        onSubmit={(event) => {
          event.preventDefault();
          setBusy(true);
          api
            .updateDirective(directive.id, {
              focus,
              must_include: mustInclude,
              must_avoid: mustAvoid,
              priority,
            })
            .then((result) =>
              navigate(`/lessons/${directive.lesson_id}/directives`, {
                state: { flash: result.message },
              }),
            )
            .catch((exc: unknown) => {
              setFlash(exc instanceof Error ? exc.message : "Save failed.");
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
            Save directive
          </button>
        </div>
      </form>
    </>
  );
}
