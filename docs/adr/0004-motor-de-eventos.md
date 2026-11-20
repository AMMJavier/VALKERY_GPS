# ADR 0004 — Motor de eventos en la misma transacción que las posiciones

**Estado:** aceptada · **Fecha:** 2026-11-20

## Contexto
La fase 3 exige "transiciones correctas y ausencia de falsas alarmas repetidas".
Las fuentes de repetición son: retransmisiones del equipo, registros periódicos que
repiten el mismo valor, registros antiguos que el equipo envía tarde, ruido del GPS
en el borde de una geocerca y conexiones TCP que se cierran y se reabren con normalidad.

## Decisión
1. **Misma transacción.** Los eventos se calculan y guardan en la misma transacción
   que las posiciones y el estado. Si algo falla, se revierte todo y no hay ACK.
2. **Solo posiciones nuevas.** Antes de insertar se consultan las claves de deduplicación
   que ya existen. Una retransmisión no vuelve a pasar por los detectores. Como segunda
   barrera, `events (device_id, dedup_key)` es UNIQUE.
3. **El estado previo se toma antes de aplicar el paquete**, con la fila de
   `device_states` bloqueada (`FOR UPDATE`), para que dos paquetes del mismo equipo
   no se pisen.
4. **Detectores puros** (`handlers/events/*.py`) para probarlos sin base de datos:
   - **Encendido (ignition):** genera evento solo en una transición. Si el estado previo
     es desconocido o hubo un hueco mayor que `VALKERY_EVENT_IGNITION_MAX_GAP_S`, el
     valor nuevo solo fija el estado. Los registros antiguos no generan transiciones.
   - **Alarmas nativas:** solo cuando `event_io_id` es ese I/O y el valor indica inicio.
     Las de registros antiguos sí se generan, con su hora real.
   - **Geocercas:** solo con posiciones válidas. La primera evaluación solo fija el estado.
     Para salir hay que alejarse `VALKERY_GEOFENCE_MARGIN_M` metros del borde
     (histéresis), así el ruido del GPS no genera entradas y salidas falsas.
5. **Conectividad según `last_seen`, no según el socket.** `DEVICE_OFFLINE` se genera
   una sola vez, desde la tarea de inactividad, y `DEVICE_ONLINE` con la siguiente comunicación.
6. **Reglas (`event_rules`):** permiten deshabilitar un tipo de evento o cambiarle
   la severidad. Una regla de un dispositivo tiene prioridad sobre la global.

## Descartado
- **OVERSPEED nativo (I/O 255):** el equipo envía el mismo I/O al inicio y al final
  del exceso de velocidad, así que no se pueden distinguir sin ambigüedad. Si hace
  falta, se agrega como regla de la plataforma.
- **Geocercas nativas del equipo (I/O 155 y siguientes):** se usan las de la plataforma,
  que se editan sin reconfigurar el FMC920.

## Consecuencias
- Procesar un paquete exige más consultas, algo irrelevante para un solo vehículo.
- Notificar los eventos al frontend (WebSocket) se resuelve en las fases 4 y 5, leyendo `events`.
