# ADR 0001 — Estructura modular tomando Traccar como referencia

**Estado:** aceptada · **Fecha:** 2026-11-20

## Contexto
El documento de arquitectura propone un monorepo (backend, gps-server, frontend). Su árbol de
ejemplo tenía dos paquetes llamados `app`, modelos duplicados entre backend y gps-server y
pruebas mezcladas en la raíz.

## Decisión
Seguir el reparto de responsabilidades de Traccar, sin copiar su código ni sus 200+ protocolos:

| Traccar | VALKERY |
|---|---|
| `model/`, `storage/` | `shared/valkery_core` (modelos SQLAlchemy únicos) |
| `protocol/Teltonika*` | `gps-server/valkery_gps/protocol/teltonika/` |
| `session/` | `gps-server/valkery_gps/session/` |
| `handler/` + `handler/events/` | `gps-server/valkery_gps/handlers/` (+ `events/`) |
| `ProcessingHandler` / `BasePipelineFactory` | `gps-server/valkery_gps/pipeline.py` |
| `database/CommandsManager` | `gps-server/valkery_gps/commands/dispatcher.py` |
| `schedule/` | `gps-server/valkery_gps/schedule/` |
| `api/` | `backend/valkery_api/` |
| `schema/` (Liquibase) | `database/migrations/` (Alembic) |
| `tools/` | `tools/` |
| `traccar-web` | `frontend/` |

Paquetes con nombre propio (`valkery_core`, `valkery_gps`, `valkery_api`) para evitar colisiones.
Pruebas dentro de cada servicio, como `src/test` en Traccar.

## Consecuencias
- Un solo lugar para el esquema; Alembic importa `valkery_core.models`.
- `shared` se instala en modo editable en ambos servicios.
