import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { ApiError, api, type LoginChoice } from "../api";
import { useSession } from "../session";

/** Pilot login by login name (mirrors login.html + /login). */
export function LoginPage() {
  const { user, loading, login } = useSession();
  const navigate = useNavigate();
  const [users, setUsers] = useState<LoginChoice[] | null>(null);
  const [loginRef, setLoginRef] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    document.title = "Log in · EvolvingClass";
  }, []);

  useEffect(() => {
    if (user !== null) {
      return;
    }
    api
      .loginChoices()
      .then((payload) => setUsers(payload.users))
      .catch((exc: unknown) =>
        setError(exc instanceof Error ? exc.message : "Could not load."),
      );
  }, [user]);

  if (!loading && user !== null) {
    return <Navigate to="/home" replace />;
  }

  async function submit(ref: string) {
    const name = ref.trim();
    if (name === "" || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const message = await login(name);
      navigate("/home", { state: { flash: message } });
    } catch (exc: unknown) {
      if (exc instanceof ApiError) {
        setError(exc.message);
      } else {
        setError("Could not log in.");
      }
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void submit(loginRef);
  }

  return (
    <>
      <h1>Log in</h1>
      <p className="muted">
        Pilot login: use your login name. Passwords arrive with school SSO
        post-pilot.
      </p>
      {error !== null && <p className="flash">{error}</p>}
      <form method="post" className="block" onSubmit={onSubmit}>
        <label htmlFor="login_ref">Login name</label>
        <input
          type="text"
          id="login_ref"
          name="login_ref"
          required
          autoFocus
          value={loginRef}
          onChange={(event) => setLoginRef(event.target.value)}
        />
        <div>
          <button type="submit" disabled={busy}>
            Log in
          </button>
        </div>
      </form>
      <h2>Pilot users</h2>
      {users === null ? (
        <p className="loading">Loading…</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Role</th>
              <th>Login</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {users.map((candidate) => (
              <tr key={candidate.id}>
                <td>{candidate.name}</td>
                <td>{candidate.role}</td>
                <td>{candidate.login}</td>
                <td>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void submit(candidate.login)}
                  >
                    Use
                  </button>
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  No users yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </>
  );
}
