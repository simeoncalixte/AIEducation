import { useEffect, useState } from "react";
import {
  Link,
  Navigate,
  useNavigate,
  useParams,
} from "react-router-dom";
import {
  ApiError,
  api,
  type EditPinInput,
  type EditUseInput,
  type Dossier,
  type ReviewQueues,
} from "../api";
import { ErrorPage } from "../components/ErrorPage";
import { useSession } from "../session";

interface UseRow extends EditUseInput {
  label: string;
  param_overrides: Record<string, unknown>;
}

interface PinRow extends EditPinInput {
  label: string;
}

function move<T>(rows: T[], index: number, delta: number): T[] {
  const next = [...rows];
  const target = index + delta;
  if (target < 0 || target >= next.length) {
    return next;
  }
  const [row] = next.splice(index, 1);
  next.splice(target, 0, row);
  return next;
}

/** Edit-draft form (mirrors edit.html + /review edit POST). */
export function EditDraftPage() {
  const { kind, versionId } = useParams();
  const { user, loading } = useSession();
  const navigate = useNavigate();
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [rationale, setRationale] = useState("");
  const [contentRef, setContentRef] = useState("");
  const [uses, setUses] = useState<UseRow[]>([]);
  const [pins, setPins] = useState<PinRow[]>([]);
  const [queues, setQueues] = useState<ReviewQueues | null>(null);
  const [addUseId, setAddUseId] = useState("");
  const [addUseRole, setAddUseRole] = useState("prop");
  const [addPinId, setAddPinId] = useState("");
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
        setUses(
          payload.dossier.uses.map((u) => ({
            asset_version_id: u.asset_version_id,
            role: u.role,
            param_overrides: u.param_overrides,
            label: `${u.asset} · v${u.version_no} (${u.status})`,
          })),
        );
        setPins(
          payload.dossier.composition.map((c) => ({
            stage_version_id: c.stage_version_id,
            required: c.required,
            label: `${c.stage} · v${c.version_no} (${c.status})`,
          })),
        );
        setError(null);
      })
      .catch((exc: unknown) =>
        setError(
          exc instanceof ApiError
            ? exc
            : new ApiError(500, "Could not load."),
        ),
      );
    if (kind === "stage" || kind === "lesson") {
      api
        .review()
        .then((payload) => setQueues(payload.queues))
        .catch(() => setQueues({ asset: [], stage: [], lesson: [] }));
    }
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
              ...(dossier.kind === "stage"
                ? {
                    uses: uses.map((u) => ({
                      asset_version_id: u.asset_version_id,
                      role: u.role,
                      param_overrides: u.param_overrides,
                    })),
                  }
                : {}),
              ...(dossier.kind === "lesson"
                ? {
                    pins: pins.map((p) => ({
                      stage_version_id: p.stage_version_id,
                      required: p.required,
                    })),
                  }
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
        {dossier.kind === "stage" && (
          <>
            <h2>Asset uses</h2>
            {uses.length === 0 && (
              <p className="muted">This stage uses no assets.</p>
            )}
            {uses.map((u, index) => (
              <div key={`${u.asset_version_id}-${index}`} className="row">
                <span>{u.label}</span>
                <label>
                  Role{" "}
                  <input
                    type="text"
                    aria-label={`Role for ${u.label}`}
                    value={u.role}
                    onChange={(event) => {
                      const next = [...uses];
                      next[index] = { ...u, role: event.target.value };
                      setUses(next);
                    }}
                  />
                </label>
                <button
                  type="button"
                  aria-label={`Move ${u.label} up`}
                  disabled={index === 0}
                  onClick={() => setUses(move(uses, index, -1))}
                >
                  ↑
                </button>
                <button
                  type="button"
                  aria-label={`Move ${u.label} down`}
                  disabled={index === uses.length - 1}
                  onClick={() => setUses(move(uses, index, 1))}
                >
                  ↓
                </button>
                <button
                  type="button"
                  aria-label={`Remove ${u.label}`}
                  onClick={() =>
                    setUses(uses.filter((_, i) => i !== index))
                  }
                >
                  Remove
                </button>
              </div>
            ))}
            <div className="row">
              <label>
                Add asset{" "}
                <select
                  aria-label="Add asset version"
                  value={addUseId}
                  onChange={(event) => setAddUseId(event.target.value)}
                >
                  <option value="">Choose…</option>
                  {(queues?.asset ?? []).map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.title} · v{row.version_no} ({row.status})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Role{" "}
                <input
                  type="text"
                  aria-label="Role for new asset"
                  value={addUseRole}
                  onChange={(event) => setAddUseRole(event.target.value)}
                />
              </label>
              <button
                type="button"
                disabled={addUseId === ""}
                onClick={() => {
                  const row = (queues?.asset ?? []).find(
                    (candidate) => candidate.id === Number(addUseId),
                  );
                  if (row === undefined) {
                    return;
                  }
                  setUses([
                    ...uses,
                    {
                      asset_version_id: row.id,
                      role: addUseRole.trim() || "prop",
                      param_overrides: {},
                      label:
                        `${row.title} · v${row.version_no} ` +
                        `(${row.status})`,
                    },
                  ]);
                  setAddUseId("");
                }}
              >
                Add use
              </button>
            </div>
          </>
        )}
        {dossier.kind === "lesson" && (
          <>
            <h2>Stage composition</h2>
            {pins.length === 0 && (
              <p className="muted">No stages pinned.</p>
            )}
            {pins.map((p, index) => (
              <div key={`${p.stage_version_id}-${index}`} className="row">
                <span>{p.label}</span>
                <label>
                  <input
                    type="checkbox"
                    aria-label={`Required: ${p.label}`}
                    checked={p.required}
                    onChange={(event) => {
                      const next = [...pins];
                      next[index] = {
                        ...p,
                        required: event.target.checked,
                      };
                      setPins(next);
                    }}
                  />{" "}
                  Required
                </label>
                <button
                  type="button"
                  aria-label={`Move ${p.label} up`}
                  disabled={index === 0}
                  onClick={() => setPins(move(pins, index, -1))}
                >
                  ↑
                </button>
                <button
                  type="button"
                  aria-label={`Move ${p.label} down`}
                  disabled={index === pins.length - 1}
                  onClick={() => setPins(move(pins, index, 1))}
                >
                  ↓
                </button>
                <button
                  type="button"
                  aria-label={`Remove ${p.label}`}
                  onClick={() =>
                    setPins(pins.filter((_, i) => i !== index))
                  }
                >
                  Remove
                </button>
              </div>
            ))}
            <div className="row">
              <label>
                Add stage{" "}
                <select
                  aria-label="Add stage version"
                  value={addPinId}
                  onChange={(event) => setAddPinId(event.target.value)}
                >
                  <option value="">Choose…</option>
                  {(queues?.stage ?? [])
                    .filter(
                      (row) =>
                        !pins.some(
                          (p) => p.stage_version_id === row.id,
                        ),
                    )
                    .map((row) => (
                      <option key={row.id} value={row.id}>
                        {row.title} · v{row.version_no} ({row.status})
                      </option>
                    ))}
                </select>
              </label>
              <button
                type="button"
                disabled={addPinId === ""}
                onClick={() => {
                  const row = (queues?.stage ?? []).find(
                    (candidate) => candidate.id === Number(addPinId),
                  );
                  if (row === undefined) {
                    return;
                  }
                  setPins([
                    ...pins,
                    {
                      stage_version_id: row.id,
                      required: true,
                      label:
                        `${row.title} · v${row.version_no} ` +
                        `(${row.status})`,
                    },
                  ]);
                  setAddPinId("");
                }}
              >
                Add pin
              </button>
            </div>
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
