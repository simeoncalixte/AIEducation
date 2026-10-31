import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import type { User } from "../api";

/**
 * Shared page shell: header with role-based nav plus a flash line.
 * Pure presentational component (mirrors base.html); Layout wires it
 * to the session. Flash messages ride navigation state, shown once
 * like Flask flashes.
 */
export function Shell({
  user,
  flash,
  children,
}: {
  user: User | null;
  flash: string | null;
  children: ReactNode;
}) {
  const staff = user !== null && user.role !== "student";
  return (
    <>
      <header>
        <nav>
          <Link className="brand" to="/home">
            EvolvingClass
          </Link>
          {staff && (
            <>
              <Link to="/review">Review</Link>
              <Link to="/lessons">Lessons</Link>
              <Link to="/assignments">Assign</Link>
              {user?.role === "admin" && <Link to="/audit">Audit</Link>}
            </>
          )}
          {user !== null && !staff && <Link to="/home">Home</Link>}
          {user !== null ? (
            <>
              <span className="user">
                {`${user.name} (${user.role})`}
              </span>
              <Link to="/logout">Log out</Link>
            </>
          ) : (
            <>
              <span className="user"></span>
              <Link to="/login">Log in</Link>
            </>
          )}
        </nav>
      </header>
      <main>
        {flash !== null && flash !== "" && (
          <p className="flash">{flash}</p>
        )}
        {children}
      </main>
    </>
  );
}
