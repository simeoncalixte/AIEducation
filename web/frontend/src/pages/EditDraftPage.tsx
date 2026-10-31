import { useEffect, useState } from "react";
import {
  Link,
  Navigate,
  useNavigate,
  useParams,
} from "react-router-dom";
import { ApiError, api, type Dossier } from "../api";
import { ErrorPage } from "../components/ErrorPage";
import { useSession } from "../session";

/** Edit-draft form (mirrors edit.html + /review edit POST). */
export function EditDraftPage() {
  const { kind, versionId } = useParams();
  const { user, loading } = useSession();
  const navigate = useNavigate();
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [rationale, setRationale] = useState("");
  const [contentRef, setContentRef] = useState("");
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  const id = Number(versionId);

  useEffect(() => {
    if (dossier !== null) {
      document.title = `Edit ${dossier.title} v${dossier.version_no} · EvolvingClass`;
    }
  }, [dossier]);

  useEffect(() => {
    if (user === null || kind === undefined || !Number.isInteger(id)) {
      return;
    }
    api
      .dossier(kind, id)
      .then((payload) => {
        setDossier(payload.dossier);
        setRationale(payload.dossier.rationale);
        setContentRef(payload.dossier.content_ref ?? "");
        setError(null);
      })
      .catch((exc: unknown) =>
        setError(
          exc instanceof ApiError
            ? exc
            : new ApiError(500, "Could not load."),
        ),
      );
  }, [user, kind, id]);

  if (!loading && user === null) {
    return <Navigate to="/login" replace />;
  }
  if (error !== null && (error.status === 403 || error.status === 404)) {
    return <ErrorPage code={error.status} message={error.message} />;
  }
  if (user === null || dossier === null || kind === undefined) {
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
        <Link to={`/review/${dossier.kind}/${dossier.id}`}>
          Back to proposal
        </Link>
      </p>
      <h1>
        Edit draft: {dossier.title} · v{dossier.version_no}
      </h1>
      {flash !== null && <p className="flash">{flash}</p>}
      <form
        className="block"
        onSubmit={(event) => {
          event.preventDefault();
          setBusy(true);
          api
            .editDraft(dossier.kind, dossier.id, {
              rationale,
              ...(dossier.kind === "asset"
                ? { content_ref: contentRef }
                : {}),
            })
            .then((result) =>
              navigate(`/review/${dossier.kind}/${dossier.id}`, {
                state: { flash: result.message },
              }),
            )
            .catch((exc: unknown) => {
              setFlash(exc instanceof Error ? exc.message : "Save failed.");
              setBusy(false);
            });
        }}
      >
        <label htmlFor="rationale">Rationale</label>
        <textarea
          id="rationale"
          rows={4}
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
        />
        {dossier.kind === "asset" && (
          <>
            <label htmlFor="content_ref">Content ref</label>
            <input
              type="text"
              id="content_ref"
              value={contentRef}
              onChange={(event) => setContentRef(event.target.value)}
            />
          </>
        )}
        <p>
          <button type="submit" disabled={busy}>
            Save draft
          </button>
        </p>
      </form>
    </>
  );
}
