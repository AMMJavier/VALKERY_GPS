import { describe, expect, it } from "vitest";
import {
  formatDistance,
  formatDuration,
  formatRelative,
  formatUtc,
  formatVoltage,
  localInputToIso,
  parseDate,
  toLocalInput,
} from "./format";

const NOW = Date.parse("2026-11-20T12:00:00Z");

describe("formatRelative", () => {
  it.each([
    ["2026-11-20T12:00:00Z", "ahora"],
    ["2026-11-20T11:59:30Z", "hace 30 s"],
    ["2026-11-20T11:57:00Z", "hace 3 min"],
    ["2026-11-20T09:00:00Z", "hace 3 h"],
    ["2026-11-17T12:00:00Z", "hace 3 d"],
  ])("%s → %s", (iso, expected) => {
    expect(formatRelative(iso, NOW)).toBe(expected);
  });

  it("marca un reloj del equipo adelantado en vez de mostrar 'hace -X'", () => {
    expect(formatRelative("2026-11-20T12:10:00Z", NOW)).toBe("en el futuro (reloj adelantado)");
  });

  it("valores vacíos", () => {
    expect(formatRelative(null, NOW)).toBe("nunca");
    expect(parseDate("no es fecha")).toBeNull();
  });
});

describe("conversión de zonas horarias", () => {
  it("la API usa UTC y el tooltip lo muestra exacto", () => {
    expect(formatUtc("2026-11-20T23:52:49.140+00:00")).toBe("2026-11-20 23:52:49 UTC");
    expect(formatUtc("2026-11-20T18:52:49-05:00")).toBe("2026-11-20 23:52:49 UTC");
  });

  it("datetime-local (hora local) → ISO UTC y vuelta", () => {
    const local = toLocalInput(new Date(2026, 10, 20, 8, 30));
    expect(local).toBe("2026-11-20T08:30");
    const iso = localInputToIso(local);
    expect(new Date(iso).getHours()).toBe(8);
    expect(iso.endsWith("Z")).toBe(true);
    expect(localInputToIso("")).toBeNull();
  });
});

describe("magnitudes", () => {
  it("voltaje, distancia y duración", () => {
    expect(formatVoltage(12684)).toMatch(/^12[.,]7 V$/);
    expect(formatVoltage(null)).toBe("—");
    expect(formatDistance(850)).toBe("850 m");
    expect(formatDistance(1530)).toMatch(/^1[.,]5 km$/);
    expect(formatDuration(3_725_000)).toBe("1 h 2 min");
    expect(formatDuration(65_000)).toBe("1 min 5 s");
  });
});
