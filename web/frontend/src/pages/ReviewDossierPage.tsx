import { useEffect, useState } from "react";
import {
  Link,
  Navigate,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { ApiError, api, type Dossier } from "../api";
import { ErrorPage } from "../components/ErrorPage";
import { useSession } from "../session";

/** One rationale-taking review action (mirrors the Flask action forms). */
function ActionForm({
  label,
  button,
  danger,
  onSubmit,
}: {
  label: string;
  button: string;
  danger?: boolean;
  onSubmit: (rationale: string) => Promise<void>;
}) {
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        setBusy(true);
        onSubmit(rationale).finally(() => setBusy(false));
      }}
    >
      <label>
        Rationale{" "}
        <input
          type="text"
          size={30}
          aria-label={label}
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
        />
      </label>
      <button type="submit" className={danger ? "danger" : undefined} disabled={busy}>
        {button}
      </button>
    </form>
  );
}

/** Proposal dossier with review actions (mirrors detail.html + /review). */
export function ReviewDossierPage() {
  const { kind, versionId } = useParams();
  const { user, loading } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [flash, setFlash] = useState<string | null>(
    (location.state as { flash?: string } | null)?.flash ?? null,
  );
  const [error, setError] = useState<ApiError | null>(null);

  const id = Number(versionId);

  useEffect(() => {
    if (dossier !== null) {
      document.title = `${dossier.title} v${dossier.version_no} · EvolvingClass`;
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
        {flash !== null && <p className="flash">{flash}</p>}
        {error !== null && <p className="flash">{error.message}</p>}
        <p className="loading">Loading…</p>
      </>
    );
  }

  const run = async (
    action: (rationale: string) => Promise<{ message: string; dossier: Dossier }>,
    rationale: string,
  ) => {
    try {
      const result = await action(rationale);
      setDossier(result.dossier);
      setFlash(result.message);
    } catch (exc: unknown) {
      setFlash(exc instanceof Error ? exc.message : "Action failed.");
    }
  };

  const revise = async (rationale: string) => {
    try {
      const result = await api.revise(dossier.id, rationale);
      navigate(`/review/asset/${result.version_id}`, {
        state: { flash: result.message },
      });
    } catch (exc: unknown) {
      setFlash(exc instanceof Error ? exc.message : "Action failed.");
    }
  };

  const changedHeading =
    dossier.prior_version_no !== null
      ? `What changed (vs v${dossier.prior_version_no})`
      : "What changed (first version)";
  const coverage = dossier.coverage;

  return (
    <>
      <p className="muted">
        <Link to="/review">Queues</Link> / {dossier.kind} proposal
      </p>
      <h1>
        {dossier.title} · v{dossier.version_no}
      </h1>
      {flash !== null && <p className="flash">{flash}</p>}
      <p>
        <span className={`pill ${dossier.status}`}>{dossier.status}</span>{" "}
        <span className={`pill ${dossier.decision}`}>{dossier.decision}</span>
      </p>

      <h2>Rationale</h2>
      <p>{dossier.rationale}</p>
      {dossier.content_ref !== undefined && (
        <p className="muted">content: {dossier.content_ref}</p>
      )}

      <h2>{changedHeading}</h2>
      <table>
        <thead>
          <tr>
            <th>Field</th>
            <th>Before</th>
            <th>After</th>
          </tr>
        </thead>
        <tbody>
          {dossier.diff.map((row) => (
            <tr key={row.field} className={row.changed ? "changed" : undefined}>
              <td>{row.field}</td>
              <td>
                <pre>{row.old}</pre>
              </td>
              <td>
                <pre>{row.new}</pre>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Directive coverage</h2>
      {coverage.generation_run !== null ? (
        <p className="muted">
          Generated by {coverage.generation_run.agent} (
          {coverage.generation_run.model}), run #
          {coverage.generation_run.id} · {coverage.generation_run.status}.
        </p>
      ) : (
        <p className="muted">No generation run linked.</p>
      )}
      {coverage.brief !== "" && <p>Brief: {coverage.brief}</p>}
      {coverage.snapshot_directives.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>Snapshot directive</th>
              <th>Focus</th>
            </tr>
          </thead>
          <tbody>
            {coverage.snapshot_directives.map((s) => (
              <tr key={s.id}>
                <td>#{s.id}</td>
                <td>{s.focus}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        !coverage.snapshot_present && (
          <p className="muted">
            No directive snapshot recorded for this proposal.
          </p>
        )
      )}
      {coverage.lesson_directives.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Lesson directive</th>
              <th>Kind</th>
              <th>Active</th>
              <th>Covered</th>
              <th>Focus</th>
            </tr>
          </thead>
          <tbody>
            {coverage.lesson_directives.map((ld) => (
              <tr key={ld.id}>
                <td>#{ld.id}</td>
                <td>{ld.kind}</td>
                <td>{ld.active ? "yes" : "no"}</td>
                <td>{ld.covered ? "yes" : "no"}</td>
                <td>{ld.focus}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {(dossier.kind === "asset" || dossier.kind === "stage") && (
        <>
          <h2>Previews</h2>
          {dossier.previews.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Kind</th>
                  <th>Storage ref</th>
                  <th>Rendered</th>
                </tr>
              </thead>
              <tbody>
                {dossier.previews.map((p) => (
                  <tr key={p.storage_ref}>
                    <td>{p.kind}</td>
                    <td>{p.storage_ref}</td>
                    <td>{p.rendered_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">
              No previews rendered for this version yet.
            </p>
          )}
        </>
      )}

      {dossier.kind === "asset" && (
        <>
          <h2>Reuse matches</h2>
          {dossier.reuse.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Published alternative</th>
                  <th>Ver</th>
                  <th>Mastery</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {dossier.reuse.map((r) => (
                  <tr key={r.id}>
                    <td>{r.title}</td>
                    <td>v{r.version_no}</td>
                    <td>{r.mastery}</td>
                    <td>
                      <Link to={`/review/asset/${r.id}`}>Open</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">
              No published same-kind alternatives in scope.
            </p>
          )}

          <h2>Impact scores</h2>
          {dossier.low_impact && (
            <p>
              <span className="pill draft">Low impact</span>{" "}
              <span className="muted">
                Latest mastery below 0.5 — revise or retire with the actions
                below; evidence is in the table.
              </span>
            </p>
          )}
          {dossier.impact.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Ver</th>
                  <th>Window</th>
                  <th>Mastery</th>
                  <th>Completion</th>
                  <th>Enjoyment</th>
                  <th>n</th>
                  <th>Formula</th>
                  <th>Cohort</th>
                  <th>Unc</th>
                  <th>Flag</th>
                </tr>
              </thead>
              <tbody>
                {dossier.impact.map((row, index) => (
                  <tr key={`${row.version_no}-${row.window}-${index}`}>
                    <td>v{row.version_no}</td>
                    <td>{row.window}</td>
                    <td>{row.mastery}</td>
                    <td>{row.completion}</td>
                    <td>{row.enjoyment}</td>
                    <td>{row.sample_size}</td>
                    <td>{row.formula}</td>
                    <td>{row.cohort}</td>
                    <td>{row.uncertainty}</td>
                    <td>{row.low ? "low" : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">
              No impact rollups recorded for this asset yet.
            </p>
          )}

          <h2>Used in</h2>
          {dossier.usage.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Consumer</th>
                  <th>Kind</th>
                  <th>Ver</th>
                  <th>Status</th>
                  <th>Role</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {dossier.usage.map((u) => (
                  <tr key={`${u.link_kind}-${u.version_id}-${u.role}`}>
                    <td>{u.consumer}</td>
                    <td>{u.kind}</td>
                    <td>v{u.version_no}</td>
                    <td>
                      <span className={`pill ${u.status}`}>{u.status}</span>
                    </td>
                    <td>{u.role}</td>
                    <td>
                      <Link
                        to={`/review/${u.link_kind}/${u.version_id}`}
                      >
                        Open
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">
              No stage, lesson, or challenge uses this version yet.
            </p>
          )}
        </>
      )}

      {dossier.kind === "stage" && (
        <>
          <h2>Asset uses (library reuse)</h2>
          <table>
            <thead>
              <tr>
                <th>Asset</th>
                <th>Kind</th>
                <th>Ver</th>
                <th>Status</th>
                <th>Role</th>
                <th>Mastery</th>
              </tr>
            </thead>
            <tbody>
              {dossier.uses.length > 0 ? (
                dossier.uses.map((u, index) => (
                  <tr key={`${u.asset}-${u.role}-${index}`}>
                    <td>{u.asset}</td>
                    <td>{u.kind}</td>
                    <td>v{u.version_no}</td>
                    <td>
                      <span className={`pill ${u.status}`}>{u.status}</span>
                    </td>
                    <td>{u.role}</td>
                    <td>{u.mastery}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="muted">
                    This stage uses no assets.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}

      {dossier.kind === "lesson" && (
        <>
          <h2>Stage composition</h2>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Stage</th>
                <th>Ver</th>
                <th>Status</th>
                <th>Required</th>
                <th>Uses</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {dossier.composition.length > 0 ? (
                dossier.composition.map((c) => (
                  <tr key={c.stage_version_id}>
                    <td>{c.position}</td>
                    <td>{c.stage}</td>
                    <td>v{c.version_no}</td>
                    <td>
                      <span className={`pill ${c.status}`}>{c.status}</span>
                    </td>
                    <td>{c.required ? "yes" : "no"}</td>
                    <td>{c.uses}</td>
                    <td>
                      <Link
                        to={`/review/stage/${c.stage_version_id}`}
                      >
                        Open
                      </Link>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="muted">
                    No stages pinned.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}

      <h2>Review actions</h2>
      <div className="actions">
        {dossier.status === "draft" && (
          <>
            <ActionForm
              label="Approve rationale"
              button="Approve"
              onSubmit={(rationale) =>
                run(
                  (r) => api.approve(dossier.kind, dossier.id, r),
                  rationale,
                )
              }
            />
            <ActionForm
              label="Reject rationale"
              button="Reject"
              danger
              onSubmit={(rationale) =>
                run(
                  (r) => api.reject(dossier.kind, dossier.id, r),
                  rationale,
                )
              }
            />
            <form
              onSubmit={(event) => {
                event.preventDefault();
                navigate(`/review/${dossier.kind}/${dossier.id}/edit`);
              }}
            >
              <button type="submit">Edit draft</button>
            </form>
            <ActionForm
              label="Publish rationale"
              button="Publish"
              onSubmit={(rationale) =>
                run(
                  (r) => api.publish(dossier.kind, dossier.id, r),
                  rationale,
                )
              }
            />
          </>
        )}
        {dossier.status === "retired" && (
          <ActionForm
            label="Rollback rationale"
            button="Roll back to this version"
            onSubmit={(rationale) =>
              run(
                (r) => api.rollback(dossier.kind, dossier.id, r),
                rationale,
              )
            }
          />
        )}
        {dossier.status === "published" && (
          <ActionForm
            label="Retire rationale"
            button="Retire"
            danger
            onSubmit={(rationale) =>
              run(
                (r) => api.retire(dossier.kind, dossier.id, r),
                rationale,
              )
            }
          />
        )}
        {dossier.kind === "asset" &&
          (dossier.status === "published" ||
            dossier.status === "retired") && (
            <ActionForm
              label="Revise rationale"
              button="Revise"
              onSubmit={revise}
            />
          )}
      </div>

      <h2>Audit trail</h2>
      <h3>Decisions</h3>
      <table>
        <thead>
          <tr>
            <th>Reviewer</th>
            <th>Decision</th>
            <th>Rationale</th>
            <th>At</th>
          </tr>
        </thead>
        <tbody>
          {dossier.audit.approvals.length > 0 ? (
            dossier.audit.approvals.map((a, index) => (
              <tr key={`${a.actor}-${a.at}-${index}`}>
                <td>{a.actor}</td>
                <td>
                  <span className={`pill ${a.decision}`}>{a.decision}</span>
                </td>
                <td>{a.rationale}</td>
                <td>{a.at}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={4} className="muted">
                No decisions recorded.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <h3>Publication events</h3>
      <table>
        <thead>
          <tr>
            <th>Action</th>
            <th>Actor</th>
            <th>Rationale</th>
            <th>At</th>
          </tr>
        </thead>
        <tbody>
          {dossier.audit.events.length > 0 ? (
            dossier.audit.events.map((e, index) => (
              <tr key={`${e.action}-${e.at}-${index}`}>
                <td>{e.action}</td>
                <td>{e.actor}</td>
                <td>{e.rationale}</td>
                <td>{e.at}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={4} className="muted">
                No publication events recorded.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}
