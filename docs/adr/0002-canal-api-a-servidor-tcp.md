# ADR 0002 — Comunicación API → servidor TCP mediante MySQL

**Estado:** propuesta · **Fecha:** 2026-11-20

## Contexto
FastAPI y el servidor TCP son procesos separados. Solo el servidor TCP posee el socket del FMC920.
Traccar resuelve el multi-instancia con `broadcast/` (multicast o Redis); aquí no hace falta.

## Decisión
- La tabla `commands` actúa como canal. FastAPI inserta la orden en estado `AUTORIZADO`
  con `expires_at` corto.
- `commands/dispatcher.py` consulta periódicamente las órdenes pendientes y las envía **solo si**
  existe una sesión TCP activa y no han expirado.
- Diferencia deliberada con Traccar: `CommandsManager` guarda `QueuedCommand` y lo envía al
  reconectar. VALKERY **no** hace eso con comandos de inmovilización (regla 4.1 del documento).
- Datos en vivo: la API consulta `device_states` cada 1–2 s y empuja por WebSocket.

## Consecuencias
- Sin infraestructura adicional (ni Redis ni Kafka); todo queda auditado en MySQL.
- Latencia de comando igual al intervalo de consulta (~1 s), aceptable para un vehículo.
- Si crece el número de dispositivos, se reevalúa con notificación interna o Redis.
