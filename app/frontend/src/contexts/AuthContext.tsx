import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError } from "@/lib/apiClient";
import { clearAuth, readUser, writeSession, writeUser } from "@/lib/authStorage";
import { AuthService } from "@/services/auth";
import type { AuthenticatedUser } from "@/types/auth";

interface AuthValue {
  user: AuthenticatedUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  hasPermission: (permission: string) => boolean;
}

const Context = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthenticatedUser | null>(readUser);
  const [loading, setLoading] = useState(Boolean(readUser()));

  useEffect(() => {
    if (!loading) return;
    let active = true;
    AuthService.me()
      .then((current) => {
        if (!active) return;
        writeUser(current);
        setUser(current);
      })
      .catch((error: unknown) => {
        // The shared client already cleared storage when the bearer credential was rejected;
        // network, proxy, upstream and unrelated authorization failures keep the session.
        if (active && error instanceof ApiError && error.sessionExpired) setUser(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [loading]);

  const login = useCallback(async (username: string, password: string) => {
    const response = await AuthService.login(username, password);
    writeSession(response.access_token, response.user);
    setUser(response.user);
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    setUser(null);
  }, []);

  const hasPermission = useCallback(
    (permission: string) =>
      Boolean(
        user?.is_super_admin ||
          user?.permissions?.includes("*:*") ||
          user?.permissions?.includes(permission),
      ),
    [user],
  );

  const value = useMemo(
    () => ({ user, loading, login, logout, hasPermission }),
    [user, loading, login, logout, hasPermission],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(Context);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
