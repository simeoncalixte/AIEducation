import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, type User } from "./api";

interface SessionValue {
  user: User | null;
  loading: boolean;
  /** Log in by pilot login name; resolves with the welcome message. */
  login: (loginRef: string) => Promise<string>;
  /** Log out; resolves with the goodbye message. */
  logout: () => Promise<string>;
  refresh: () => Promise<void>;
}

const SessionContext = createContext<SessionValue>({
  user: null,
  loading: true,
  login: () => Promise.reject(new Error("no provider")),
  logout: () => Promise.reject(new Error("no provider")),
  refresh: () => Promise.reject(new Error("no provider")),
});

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const { user: current } = await api.session();
    setUser(current);
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  const login = useCallback(
    async (loginRef: string) => {
      const payload = await api.login(loginRef);
      setUser(payload.user);
      return payload.message;
    },
    [],
  );

  const logout = useCallback(async () => {
    const payload = await api.logout();
    setUser(null);
    return payload.message;
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, logout, refresh }),
    [user, loading, login, logout, refresh],
  );
  return (
    <SessionContext.Provider value={value}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionValue {
  return useContext(SessionContext);
}
