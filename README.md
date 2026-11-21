# VALKERY GPS

Plataforma propia de monitoreo GPS para un **Teltonika FMC920** (motocicleta con relé de inmovilización).

Estado: **fase 5 completa** (servidor TCP, persistencia, eventos, API y dashboard web). Sin validación en hardware real.

| Fase | Estado |
|---|---|
| 1 · TCP y codecs | ✅ IMEI, tramas fragmentadas, CRC, varios AVL, ACK, simulador |
| 2 · Persistencia | ✅ MySQL + Alembic, posiciones sin duplicados, estado actual, sesiones, retención |
| 3 · Eventos | ✅ encendido, alarmas nativas, geocercas, conexión/desconexión, reglas |
| 4 · API | ✅ JWT, roles y permisos, historial paginado, eventos, geocercas, auditoría, WebSocket |
| 5 · Dashboard | ✅ mapa en vivo por WebSocket, historial con reproducción, eventos, geocercas, reglas, usuarios |
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
│   │   └── events/           #   engine, ignition, alarm, geofence (misma transacción, ADR 0004)
│   ├── commands/             #   dispatcher: MySQL -> sesión TCP activa
│   ├── schedule/             #   retención de tramas, inactividad (DEVICE_OFFLINE)
│   └── pipeline.py           #   orden de handlers; ACK solo tras persistir
├── backend/valkery_api/      # FastAPI: auth JWT, REST v1, WebSocket, auditoría (≈ traccar api/)
├── frontend/                 # React + Tailwind + Vite + Leaflet (ver frontend/README) (≈ traccar-web)
├── database/                 # Alembic (migrations/) y setup/ (script SQL inicial) (≈ traccar schema/)
├── tools/                    # Simulador, admin, dispositivos, geocercas, eventos (≈ traccar tools/)
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
pip install -e shared -r backend/requirements.txt -r requirements-dev.txt
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

### 5. Eventos y geocercas (fase 3)

```powershell
python tools/manage_geofences.py add-circle --name "Casa" --lat 54.6990336 --lon 25.2618832 --radius 150
python tools/device_simulator.py --scenario trip --records 4
python tools/manage_events.py list
python tools/manage_events.py rules
python tools/manage_events.py set-rule --type GEOFENCE_ENTER --disable
```

El escenario `trip` produce `IGNITION_ON`, `GEOFENCE_EXIT`, `IGNITION_OFF` y `TOWING`.

| Evento | Origen | Severidad por defecto | Cuándo |
|---|---|---|---|
| IGNITION_ON / IGNITION_OFF | plataforma | info | Cambio real de encendido (no en cada registro) |
| TOWING / CRASH / JAMMING / POWER_CUT | equipo | critical | El registro fue causado por ese I/O (246/247/249/252) |
| GEOFENCE_ENTER / GEOFENCE_EXIT | plataforma | info / warning | Cruce de geocerca con posición válida e histéresis |
| DEVICE_OFFLINE / DEVICE_ONLINE | plataforma | warning / info | Sin comunicación por `VALKERY_EVENT_OFFLINE_AFTER_S` / vuelve a comunicar |

### 6. API (fase 4)

Crea el primer administrador (pide la contraseña por teclado):

```powershell
python tools/create_admin.py --username admin --name "Tu nombre"
```

Arranca la API (desde `backend`) y abre la documentación interactiva en http://localhost:8000/docs:

```powershell
cd backend; uvicorn valkery_api.main:app --reload --port 8000
```

| Recurso | Permiso | Notas |
|---|---|---|
| `POST /api/v1/auth/login` | — | Devuelve un token Bearer; se bloquea tras varios intentos fallidos |
| `GET /api/v1/devices` | devices:read | Incluye el estado actual de cada equipo |
| `GET /api/v1/devices/{id}/positions?from=&to=` | positions:read | Rango ≤ 31 días, paginado por cursor |
| `GET /api/v1/events` | events:read | Filtros por equipo, tipo, severidad y fechas |
| `/api/v1/geofences` | geofences:manage (escritura) | Círculos y polígonos validados |
| `PUT /api/v1/event-rules` | event_rules:manage | Habilitar o deshabilitar tipos y cambiar severidad |
| `/api/v1/users` | users:manage | No permite quitar el último administrador |
| `GET /api/v1/audit` | audit:read | Inicios de sesión y cambios sensibles |
| `ws://…/api/v1/ws?token=` | positions:read | Snapshot inicial y luego cambios de estado y eventos en vivo |

Roles iniciales: `admin` (todo excepto inmovilizar), `operator` (lectura, geocercas y reglas) y
`viewer` (solo lectura). El permiso `commands:immobilize` no lo tiene ningún rol por defecto.
Ver [ADR 0005](docs/adr/0005-autenticacion-y-permisos.md).

### 7. Dashboard web (fase 5)

Con la API en `:8000` y el servidor GPS corriendo:

```powershell
cd frontend; npm install; npm run dev
```

Abre http://localhost:5173 e inicia sesión con el usuario creado en el paso 6. Detalles y
criterios de presentación (fechas, estados) en [frontend/README.md](frontend/README.md).

### Consultas útiles en Workbench

```sql
SELECT * FROM device_states;
SELECT gps_time, received_at, valid, latitude, longitude, speed, ignition, dout1
  FROM positions ORDER BY gps_time DESC LIMIT 50;
SELECT * FROM device_sessions ORDER BY connected_at DESC LIMIT 20;
SELECT id, received_at, codec, record_count, parse_status, error FROM raw_packets ORDER BY id DESC LIMIT 20;
SELECT occurred_at, event_type, severity, source, attributes FROM events ORDER BY occurred_at DESC LIMIT 50;
```

## Reglas de seguridad

- Nunca subir `.env`, IMEI reales, ICCID ni datos de la SIM.
- Comandos de inmovilización: deshabilitados hasta completar la prueba física del relé (fase 6).
- Un ACK o respuesta Codec 12 **no** equivale a éxito físico del relé.
