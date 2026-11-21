import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LiveConnection, liveUrl } from "./live";

class FakeSocket {
  static instances = [];
  constructor(url) {
    this.url = url;
    FakeSocket.instances.push(this);
  }
  close() {}
  open() {
    this.onopen?.();
  }
  message(data) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
  drop(code = 1006) {
    this.onclose?.({ code });
  }
}

describe("liveUrl", () => {
  it("usa wss con https y codifica el token", () => {
    expect(liveUrl("a b", { protocol: "https:", host: "gps.example" })).toBe("wss://gps.example/api/v1/ws?token=a%20b");
    expect(liveUrl("t", { protocol: "http:", host: "localhost:5173" })).toBe("ws://localhost:5173/api/v1/ws?token=t");
  });
});

describe("LiveConnection", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeSocket.instances = [];
  });
  afterEach(() => vi.useRealTimers());

  it("entrega mensajes y reconecta con espera creciente", () => {
    const messages = [];
    const statuses = [];
    const conn = new LiveConnection("tok", { onMessage: (m) => messages.push(m), onStatus: (s) => statuses.push(s), WebSocketImpl: FakeSocket });
    conn.start();
    FakeSocket.instances[0].open();
    FakeSocket.instances[0].message({ type: "snapshot", devices: [], events: [] });
    expect(messages).toHaveLength(1);

    FakeSocket.instances[0].drop();
    expect(statuses.at(-1)).toBe("reconnecting");
    vi.advanceTimersByTime(999);
    expect(FakeSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(FakeSocket.instances).toHaveLength(2);

    FakeSocket.instances[1].drop();
    vi.advanceTimersByTime(1999);
    expect(FakeSocket.instances).toHaveLength(2); // segunda espera: 2 s
    vi.advanceTimersByTime(1);
    expect(FakeSocket.instances).toHaveLength(3);
    conn.stop();
  });

  it("no reintenta si el servidor rechaza el token (4401)", () => {
    const onUnauthorized = vi.fn();
    const conn = new LiveConnection("tok", { onUnauthorized, WebSocketImpl: FakeSocket });
    conn.start();
    FakeSocket.instances[0].drop(4401);
    vi.advanceTimersByTime(60_000);
    expect(onUnauthorized).toHaveBeenCalledWith(4401);
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("stop() evita reconexiones", () => {
    const conn = new LiveConnection("tok", { WebSocketImpl: FakeSocket });
    conn.start();
    conn.stop();
    FakeSocket.instances[0].drop();
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(1);
  });
});
