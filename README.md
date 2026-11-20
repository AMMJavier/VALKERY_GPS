# VALKERY GPS

Plataforma propia de monitoreo GPS para un **Teltonika FMC920** (motocicleta con relé de inmovilización).

Estado: **fase 1 completa** (servidor TCP, Codec 8/8E/12 y ACK). Sin persistencia ni validación en hardware real.

| Fase | Estado |
|---|---|
| 1 · TCP y codecs | ✅ IMEI, tramas fragmentadas, CRC, varios AVL, ACK, simulador |
| 2 · Persistencia | pendiente |
| 3 · Eventos | pendiente |
| 4 · API | pendiente |
| 5 · Dashboard | pendiente |
| 6 · Comandos | pendiente (el encoder Codec 12 ya existe; el envío no) |
| 7 · Migración | pendiente |

## Stack

| Capa | Tecnología |
|---|---|
| Servidor GPS TCP | Python 3 + asyncio |
| API | Python + FastAPI |
| Persistencia | MySQL Server (administración con MySQL Workbench) |
| ORM / migraciones | SQLAlchemy 2 (async, aiomysql) + Alembic |
| Frontend | React + Tailwind CSS + Vite + Leaflet |
| Pruebas | Pytest |

## Estructura

La organización interna toma como referencia [Traccar](https://github.com/traccar/traccar)
(licencia Apache 2.0): mismo reparto de responsabilidades, adaptado a Python y limitado
a Teltonika. Cada módulo indica en su docstring el archivo equivalente de Traccar.

```
VALKERY_GPS/
├── shared/valkery_core/      # Modelos SQLAlchemy, enums y sesión DB comunes   (≈ traccar model/, storage/)
├── gps-server/valkery_gps/   # Proceso TCP: framing, codecs, sesiones, pipeline (≈ traccar núcleo)
│   ├── protocol/teltonika/   #   frame_decoder, decoder (8/8E/12), encoder (12), crc, io_elements
│   ├── session/              #   connection_manager, device_session
│   ├── handlers/             #   validity, distance, motion, database  (antes de guardar)
│   │   └── events/           #   ignition, alarm, geofence, command_result (después de guardar)
│   ├── commands/             #   dispatcher: MySQL -> sesión TCP activa
│   ├── schedule/             #   inactividad, expiración de comandos
│   └── pipeline.py           #   orden de handlers; ACK solo tras persistir
├── backend/valkery_api/      # FastAPI: auth, recursos REST v1, WebSocket      (≈ traccar api/)
├── frontend/                 # React + Tailwind + Vite                         (≈ traccar-web)
├── database/                 # Alembic (migrations/) y seeds sin datos reales  (≈ traccar schema/)
├── tools/                    # Simulador FMC920 y utilidades hex               (≈ traccar tools/)
├── deployment/               # Compose, nginx, systemd                         (≈ traccar docker/, setup/)
└── docs/                     # ADRs y notas de protocolo
```

### Flujo de entrada

```
FMC920 → server.py → frame_decoder → decoder (IMEI / Codec 8|8E)
       → pipeline: validity → distance → motion → database (idempotente)
       → ACK al equipo (nº de registros aceptados)
       → events/* → device_states → API/WebSocket → React
```

### Flujo de comandos

```
React → FastAPI (permiso + confirmación) → commands (MySQL, estado AUTORIZADO)
      → commands/dispatcher (solo si hay sesión TCP activa y no expiró)
      → encoder Codec 12 → respuesta Codec 12 → command_result → estado
```

Ver [docs/adr](docs/adr) para las decisiones.

## Puesta en marcha (desarrollo)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install pytest pytest-asyncio
python -m pytest
```

La fase 1 no usa dependencias externas. Las de `backend/` y `shared/` se instalan a partir de la fase 2.

### Probar el servidor GPS con el simulador

Terminal 1 (servidor):

```powershell
$env:VALKERY_GPS_ALLOWED_IMEIS = "356307042441013"
cd gps-server; python -m valkery_gps
```

Terminal 2 (simulador del FMC920):

```powershell
python tools/device_simulator.py --codec 8e --records 3 --packets 5 --fragment 9
python tools/device_simulator.py --pdf-example
```

El IMEI `356307042441013` es el del ejemplo del PDF. El IMEI real no se guarda en el repositorio.

## Reglas de seguridad

- Nunca subir `.env`, IMEI reales, ICCID ni datos de la SIM.
- Comandos de inmovilización: deshabilitados hasta completar la prueba física del relé (fase 6).
- Un ACK o respuesta Codec 12 **no** equivale a éxito físico del relé.
