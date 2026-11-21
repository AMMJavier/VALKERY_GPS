import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setToken, setUnauthorizedHandler } from "../services/api";

// Sesión: el token vive en sessionStorage (se borra al cerrar la pestaña) y se
// descarta automáticamente al expirar. Un 401 de la API también cierra la sesión.

const STORAGE_KEY = "valkery.session";
const AuthContext = createContext(null);

function readStored() {
  try {
    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "null");
    if (stored && Date.parse(stored.expiresAt) > Date.now()) return stored;
  } catch {
    // almacenamiento no disponible o corrupto
  }
  return null;
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => {
    const stored = readStored();
    setToken(stored?.token ?? null);
    return stored;
  });
  const [user, setUser] = useState(null);
  const [notice, setNotice] = useState(null);

  const logout = useCallback((reason = null) => {
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignorar
    }
    setToken(null);
    setSession(null);
    setUser(null);
    setNotice(reason);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => logout("Tu sesión expiró o fue cerrada. Vuelve a iniciar sesión."));
  }, [logout]);

  // Cierre automático al vencer el token.
  useEffect(() => {
    if (!session) return undefined;
    const ms = Date.parse(session.expiresAt) - Date.now();
    const timer = setTimeout(() => logout("La sesión expiró. Vuelve a iniciar sesión."), Math.max(ms, 0));
    return () => clearTimeout(timer);
  }, [session, logout]);

  useEffect(() => {
    if (!session || user) return;
    api.me().then(setUser).catch(() => {});
  }, [session, user]);

  const login = useCallback(async (username, password) => {
    const result = await api.login(username, password);
    const next = { token: result.access_token, expiresAt: result.expires_at };
    setToken(next.token);
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // sin almacenamiento: la sesión dura hasta recargar
    }
    setNotice(null);
    setUser(await api.me());
    setSession(next);
  }, []);

  const value = useMemo(
    () => ({
      token: session?.token ?? null,
      expiresAt: session?.expiresAt ?? null,
      user,
      notice,
      login,
      logout,
      can: (permission) => Boolean(user?.permissions?.includes(permission)),
    }),
    [session, user, notice, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth fuera de AuthProvider");
  return ctx;
}
