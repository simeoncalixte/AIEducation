import { Outlet, useLocation } from "react-router-dom";
import { Shell } from "./components/Shell";
import { useSession } from "./session";

/** App layout: session-backed shell around the routed page. */
export function Layout() {
  const { user } = useSession();
  const location = useLocation();
  const state = location.state as { flash?: string } | null;
  const flash = state?.flash ?? null;
  return (
    <Shell user={user} flash={flash}>
      <Outlet />
    </Shell>
  );
}
