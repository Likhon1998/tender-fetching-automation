import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, tokenStore } from "../api/client";

/**
 * Holds the signed-in user for the whole app.
 *
 * On first load we call /me with whatever token is in localStorage. That both
 * restores the session across refreshes and proves the token is still valid,
 * rather than trusting a stored token that may have expired.
 */
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      if (!tokenStore.get()) {
        setLoading(false);
        return;
      }
      try {
        const me = await api.me();
        if (!cancelled) setUser(me);
      } catch {
        tokenStore.clear();
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (identifier, password) => {
    const data = await api.login(identifier, password);
    tokenStore.set(data.access_token);
    setUser(data.user);
    return data.user;
  }, []);

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  // `can` is what every screen uses to decide whether to show a control. The
  // backend enforces the same rules, so hiding a button is convenience only.
  const can = useCallback(
    (capability) => Boolean(user?.capabilities?.includes(capability)),
    [user]
  );

  const value = { user, loading, login, logout, can, capabilities: user?.capabilities ?? [] };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside an AuthProvider");
  return context;
}
