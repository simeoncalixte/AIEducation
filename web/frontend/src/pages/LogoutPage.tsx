import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useSession } from "../session";

/** Log out through the API, then land on login (mirrors /logout). */
export function LogoutPage() {
  const { logout } = useSession();
  const navigate = useNavigate();
  const done = useRef(false);

  useEffect(() => {
    if (done.current) {
      return;
    }
    done.current = true;
    logout()
      .then((message) => navigate("/login", { state: { flash: message } }))
      .catch(() => navigate("/login"));
  }, [logout, navigate]);

  return <p className="loading">Logging out…</p>;
}
