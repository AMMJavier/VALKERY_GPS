# VALKERY GPS

Plataforma propia de monitoreo GPS para un **Teltonika FMC920** (motocicleta con relé de inmovilización).

Estado: **fase 2 completa** (servidor TCP + persistencia en MySQL). Sin validación en hardware real.

| Fase | Estado |
|---|---|
| 1 · TCP y codecs | ✅ IMEI, tramas fragmentadas, CRC, varios AVL, ACK, simulador |
| 2 · Persistencia | ✅ MySQL + Alembic, posiciones sin duplicados, estado actual, sesiones, retención |
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
│   ├── handlers/             #   validity, normalize, database  (antes del ACK)
│   │   └── events/           #   ignition, alarm, geofence, command_result (después de guardar)
│   ├── commands/             #   dispatcher: MySQL -> sesión TCP activa
│   ├── schedule/             #   retención de tramas; inactividad y expiración (fases 3/6)
│   └── pipeline.py           #   orden de handlers; ACK solo tras persistir
├── backend/valkery_api/      # FastAPI: auth, recursos REST v1, WebSocket      (≈ traccar api/)
├── frontend/                 # React + Tailwind + Vite                         (≈ traccar-web)
├── database/                 # Alembic (migrations/) y setup/ (script SQL inicial) (≈ traccar schema/)
├── tools/                    # Simulador FMC920, alta de dispositivos, hex       (≈ traccar tools/)
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

### 1. Entorno Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e shared -r requirements-dev.txt
```

### 2. Base de datos (una sola vez)

1. Abre [database/setup/01_crear_bd_y_usuario.sql](database/setup/01_crear_bd_y_usuario.sql) en MySQL Workbench
   (conectado como root), cambia `CAMBIAR_ESTA_CLAVE` y ejecútalo. Crea `valkery_gps`, `valkery_gps_test`
   y el usuario `valkery`.
2. Copia `.env.example` a `.env` y pon esa contraseña en `VALKERY_DB_URL` y `VALKERY_TEST_DB_URL`.
3. Crea las tablas:

```powershell
alembic -c database/alembic.ini upgrade head
```

### 3. Pruebas

```powershell
python -m pytest
```

Las pruebas de MySQL usan `valkery_gps_test` (se vacía en cada ejecución). Sin `VALKERY_TEST_DB_URL` se omiten.

### 4. Registrar el equipo y arrancar el servidor

Solo se aceptan IMEIs registrados y habilitados en la tabla `devices`:

```powershell
python tools/manage_devices.py add --imei 356307042441013 --name "Simulador" --vehicle "Moto de prueba"
python tools/manage_devices.py list
```

Terminal 1 (servidor):

```powershell
cd gps-server; python -m valkery_gps
```

Terminal 2 (simulador del FMC920):

```powershell
python tools/device_simulator.py --codec 8e --records 3 --packets 5 --fragment 9
python tools/device_simulator.py --pdf-example
```

El IMEI `356307042441013` es el del ejemplo del PDF. El IMEI real se registra con `manage_devices.py`
y nunca se guarda en el repositorio.

### Consultas útiles en Workbench

```sql
SELECT * FROM device_states;
SELECT gps_time, received_at, valid, latitude, longitude, speed, ignition, dout1
  FROM positions ORDER BY gps_time DESC LIMIT 50;
SELECT * FROM device_sessions ORDER BY connected_at DESC LIMIT 20;
SELECT id, received_at, codec, record_count, parse_status, error FROM raw_packets ORDER BY id DESC LIMIT 20;
```

## Reglas de seguridad

- Nunca subir `.env`, IMEI reales, ICCID ni datos de la SIM.
- Comandos de inmovilización: deshabilitados hasta completar la prueba física del relé (fase 6).
- Un ACK o respuesta Codec 12 **no** equivale a éxito físico del relé.
