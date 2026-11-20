# ADR 0003 — ACK al dispositivo solo después de persistir

**Estado:** aceptada · **Fecha:** 2026-11-20

## Contexto
El FMC920 borra registros de su memoria cuando recibe el ACK (nº de registros aceptados).
Traccar envía el ACK desde `AcknowledgementHandler` cuando el pipeline marca la posición como
procesada (`EventHandled`), es decir, tras `DatabaseHandler`.

## Decisión
`pipeline.py` envía el ACK de 4 bytes solo cuando todos los registros de la trama se guardaron.
La escritura es idempotente (clave: device_id + gps_time + hash del registro), de modo que las
retransmisiones del equipo no generan duplicados.

## Consecuencias
- Si MySQL falla, no se envía ACK y el equipo reintenta: no se pierden datos.
- Las pruebas deben cubrir retransmisión de la misma trama.
