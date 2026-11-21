// Conexión WebSocket con reconexión automática (espera creciente hasta 30 s).
// El servidor cierra con 4401 si el token expiró o el usuario fue invalidado:
// en ese caso no se reintenta y se avisa para cerrar la sesión.

const UNAUTHORIZED = 4401;
const FORBIDDEN = 4403;

export function liveUrl(token, location = window.location) {
  const base = import.meta.env.VITE_WS_URL ?? `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;
  return `${base}/api/v1/ws?token=${encodeURIComponent(token)}`;
}

export class LiveConnection {
  constructor(token, { onMessage, onStatus, onUnauthorized, WebSocketImpl = WebSocket } = {}) {
    this.token = token;
    this.onMessage = onMessage ?? (() => {});
    this.onStatus = onStatus ?? (() => {});
    this.onUnauthorized = onUnauthorized ?? (() => {});
    this.WebSocketImpl = WebSocketImpl;
    this.retryMs = 1000;
    this.stopped = false;
    this.socket = null;
    this.timer = null;
  }

  start() {
    this.stopped = false;
    this.connect();
  }

  connect() {
    if (this.stopped) return;
    this.onStatus("connecting");
    const socket = new this.WebSocketImpl(liveUrl(this.token));
    this.socket = socket;
    socket.onopen = () => {
      this.retryMs = 1000;
      this.onStatus("open");
    };
    socket.onmessage = (event) => {
      try {
        this.onMessage(JSON.parse(event.data));
      } catch {
        // mensaje no JSON: se ignora
      }
    };
    socket.onclose = (event) => {
      this.socket = null;
      if (this.stopped) return;
      if (event.code === UNAUTHORIZED || event.code === FORBIDDEN) {
        this.onStatus("unauthorized");
        this.onUnauthorized(event.code);
        return;
      }
      this.onStatus("reconnecting");
      this.timer = setTimeout(() => this.connect(), this.retryMs);
      this.retryMs = Math.min(this.retryMs * 2, 30000);
    };
  }

  stop() {
    this.stopped = true;
    clearTimeout(this.timer);
    if (this.socket) this.socket.close(1000);
    this.onStatus("closed");
  }
}
