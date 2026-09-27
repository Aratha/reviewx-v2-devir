import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { clearAuth, readUser, subscribeAuth, writeSession } from "@/lib/authStorage";
import { accessOf, type Access } from "@/lib/access";
import { AuthService } from "@/services/auth";
import type { AuthenticatedUser } from "@/types/auth";

interface AuthValue {
  user: AuthenticatedUser | null;
  loading: boolean;
  /** Menu and route visibility only; the backend authorizes every request. */
  access: Access;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
}

const Context = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const user = useSyncExternalStore(subscribeAuth, readUser, readUser);
  // The token lives in memory only, so every page load restores the session from the HttpOnly
  // refresh cookie before protected routes render.
  const [restoring, setRestoring] = useState(() => readUser() === null);

  useEffect(() => {
    if (!restoring) return;
    let active = true;
    AuthService.refresh()
      .catch(() => undefined)
      .finally(() => {
        if (active) setRestoring(false);
      });
    return () => {
      active = false;
    };
  }, [restoring]);

  const login = useCallback(async (username: string, password: string) => {
    const response = await AuthService.login(username, password);
    writeSession(response.access_token, response.user);
  }, []);

  const logout = useCallback(async () => {
    // Close the refresh session on the server first; a failed call still ends the local session.
    await AuthService.logout().catch(() => undefined);
    clearAuth();
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

  const access = useMemo(() => accessOf(user), [user]);

  const value = useMemo(
    () => ({ user, loading: restoring, access, login, logout, hasPermission }),
    [user, restoring, access, login, logout, hasPermission],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(Context);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
