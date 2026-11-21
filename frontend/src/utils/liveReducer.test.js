import { describe, expect, it } from "vitest";
import { MAX_EVENTS, initialLive, liveReducer } from "./liveReducer";

const device = (id, online) => ({ id, name: `D${id}`, state: { online } });
const event = (id, minute) => ({ id, event_type: "IGNITION_ON", occurred_at: `2026-11-20T12:${String(minute).padStart(2, "0")}:00Z` });

describe("liveReducer", () => {
  it("snapshot reemplaza todo y ordena eventos del más reciente al más antiguo", () => {
    const state = liveReducer(initialLive, {
      type: "snapshot",
      devices: [device(1, false), device(2, true)],
      events: [event(1, 1), event(3, 3), event(2, 2)],
    });
    expect(Object.keys(state.devices)).toEqual(["1", "2"]);
    expect(state.events.map((e) => e.id)).toEqual([3, 2, 1]);
  });

  it("state actualiza solo ese dispositivo", () => {
    let state = liveReducer(initialLive, { type: "snapshot", devices: [device(1, false), device(2, false)], events: [] });
    state = liveReducer(state, { type: "state", device: device(1, true) });
    expect(state.devices[1].state.online).toBe(true);
    expect(state.devices[2].state.online).toBe(false);
  });

  it("event agrega al principio sin duplicar", () => {
    let state = liveReducer(initialLive, { type: "snapshot", devices: [], events: [event(1, 1)] });
    state = liveReducer(state, { type: "event", event: event(2, 5) });
    const same = liveReducer(state, { type: "event", event: event(2, 5) });
    expect(same).toBe(state);
    expect(state.events.map((e) => e.id)).toEqual([2, 1]);
  });

  it("un evento antiguo que llega tarde queda en su lugar cronológico", () => {
    let state = liveReducer(initialLive, { type: "snapshot", devices: [], events: [event(5, 30)] });
    state = liveReducer(state, { type: "event", event: event(6, 10) });
    expect(state.events.map((e) => e.id)).toEqual([5, 6]);
  });

  it("limita la cantidad de eventos en memoria", () => {
    let state = initialLive;
    for (let i = 0; i < MAX_EVENTS + 10; i += 1) state = liveReducer(state, { type: "event", event: event(i, i % 60) });
    expect(state.events).toHaveLength(MAX_EVENTS);
  });

  it("ignora mensajes desconocidos y reset vuelve al inicio", () => {
    const state = liveReducer(initialLive, { type: "snapshot", devices: [device(1, true)], events: [] });
    expect(liveReducer(state, { type: "otra-cosa" })).toBe(state);
    expect(liveReducer(state, { type: "reset" })).toBe(initialLive);
  });
});
