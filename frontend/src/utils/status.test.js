import { describe, expect, it } from "vitest";
import { boolLabel, connectionStatus, fixStatus } from "./status";
import { trackSummary } from "./geo";

const NOW = Date.parse("2026-11-20T12:00:00Z");
const ago = (minutes) => new Date(NOW - minutes * 60_000).toISOString();

describe("connectionStatus", () => {
  it("sin datos", () => {
    expect(connectionStatus(null, NOW).key).toBe("never");
    expect(connectionStatus({ last_seen: null }, NOW).key).toBe("never");
  });

  it("conectado aunque el contacto esté apagado (no depende de ignition)", () => {
    expect(connectionStatus({ online: true, ignition: false, last_seen: ago(1) }, NOW).key).toBe("online");
  });

  it("OFFLINE informado por el servidor tiene prioridad", () => {
    expect(connectionStatus({ online: true, reported_offline: true, last_seen: ago(1) }, NOW).key).toBe("offline");
  });

  it("desconexión reciente frente a comunicación antigua", () => {
    expect(connectionStatus({ online: false, last_seen: ago(5) }, NOW).key).toBe("idle");
    expect(connectionStatus({ online: false, last_seen: ago(45) }, NOW).key).toBe("stale");
  });
});

describe("fixStatus", () => {
  it("distingue posición vigente, antigua y sin señal", () => {
    expect(fixStatus({ fix_time: ago(1), gnss_status: 1 }, NOW).key).toBe("ok");
    expect(fixStatus({ fix_time: ago(30), gnss_status: 1 }, NOW).key).toBe("old");
    expect(fixStatus({ fix_time: ago(1), gnss_status: 2 }, NOW).key).toBe("lost");
    expect(fixStatus({ fix_time: null }, NOW).key).toBe("none");
  });
});

describe("boolLabel", () => {
  it("null es desconocido, no 'No'", () => {
    expect(boolLabel(null)).toBe("Desconocido");
    expect(boolLabel(false, "Encendido", "Apagado")).toBe("Apagado");
  });
});

describe("trackSummary", () => {
  it("usa solo posiciones válidas para distancia y velocidad", () => {
    const p = (i, valid, lat, speed) => ({ gps_time: ago(10 - i), valid, latitude: lat, longitude: 25, speed });
    const summary = trackSummary([p(0, true, 54.0, 10), p(1, false, 60.0, 200), p(2, true, 54.001, 40)]);
    expect(summary.points).toBe(3);
    expect(summary.validPoints).toBe(2);
    expect(summary.distanceM).toBeGreaterThan(100);
    expect(summary.distanceM).toBeLessThan(120);
    expect(summary.maxSpeed).toBe(40);
    expect(summary.durationMs).toBe(2 * 60_000);
  });
});
