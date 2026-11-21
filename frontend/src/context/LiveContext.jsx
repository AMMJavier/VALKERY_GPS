import { createContext, useContext, useEffect, useReducer, useState } from "react";
import { LiveConnection } from "../services/live";
import { initialLive, liveReducer } from "../utils/liveReducer";
import { useAuth } from "./AuthContext";

// Una sola conexión WebSocket por sesión, compartida por todas las páginas.

const LiveContext = createContext(null);

export function LiveProvider({ children }) {
  const { token, logout } = useAuth();
  const [live, dispatch] = useReducer(liveReducer, initialLive);
  const [status, setStatus] = useState("closed");

  useEffect(() => {
    if (!token) {
      dispatch({ type: "reset" });
      return undefined;
    }
    const connection = new LiveConnection(token, {
      onMessage: dispatch,
      onStatus: setStatus,
      onUnauthorized: () => logout("Tu sesión expiró o fue cerrada. Vuelve a iniciar sesión."),
    });
    connection.start();
    return () => connection.stop();
  }, [token, logout]);

  return <LiveContext.Provider value={{ ...live, status }}>{children}</LiveContext.Provider>;
}

export function useLive() {
  const ctx = useContext(LiveContext);
  if (!ctx) throw new Error("useLive fuera de LiveProvider");
  return ctx;
}
