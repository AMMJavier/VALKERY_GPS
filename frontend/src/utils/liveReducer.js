// Estado en vivo a partir de los mensajes del WebSocket (/api/v1/ws).
//   snapshot → reemplaza dispositivos y eventos recientes
//   state    → actualiza un dispositivo
//   event    → agrega un evento al principio (sin duplicar, máximo MAX_EVENTS)

export const MAX_EVENTS = 100;

export const initialLive = { devices: {}, events: [], receivedAt: null };

export function liveReducer(state, message) {
  switch (message?.type) {
    case "snapshot": {
      const devices = Object.fromEntries((message.devices ?? []).map((d) => [d.id, d]));
      const events = [...(message.events ?? [])].sort(byNewest).slice(0, MAX_EVENTS);
      return { devices, events, receivedAt: Date.now() };
    }
    case "state": {
      const device = message.device;
      if (!device) return state;
      return { ...state, devices: { ...state.devices, [device.id]: device }, receivedAt: Date.now() };
    }
    case "event": {
      const event = message.event;
      if (!event || state.events.some((e) => e.id === event.id)) return state;
      return { ...state, events: [event, ...state.events].sort(byNewest).slice(0, MAX_EVENTS), receivedAt: Date.now() };
    }
    case "reset":
      return initialLive;
    default:
      return state;
  }
}

function byNewest(a, b) {
  return Date.parse(b.occurred_at) - Date.parse(a.occurred_at) || b.id - a.id;
}
