# Frontend VALKERY GPS

React 19 + Tailwind 4 + Vite 8 + Leaflet (react-leaflet 5) + React Router 7.

## Desarrollo

Con la API corriendo en `http://127.0.0.1:8000` (ver README raíz):

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173
npm test           # pruebas (vitest)
npm run build      # versión de producción en dist/
```

En desarrollo, Vite redirige `/api` (incluido el WebSocket) y `/health` a la API, así
que el navegador usa un solo origen y no hace falta CORS. Para otra dirección:
`$env:VALKERY_API_TARGET = "http://host:puerto"`.

## Variables opcionales (`frontend/.env.local`)

| Variable | Uso |
|---|---|
| `VITE_API_URL` | URL de la API si no se sirve en el mismo origen |
| `VITE_WS_URL` | URL base del WebSocket (`wss://…`) si difiere |
| `VITE_MAP_TILE_URL` / `VITE_MAP_TILE_ATTRIBUTION` | Proveedor de mapas. Por defecto OpenStreetMap, apto para uso personal de bajo tráfico según su [política](https://operations.osmfoundation.org/policies/tiles/) |

## Estructura

```
src/
├── components/common   # ui.jsx (botones, tarjetas, TimeText), DeviceStatus, EventList
├── components/layout   # Shell (menú, estado del WebSocket, sesión)
├── components/map      # BaseMap, geocercas, marcador orientado por rumbo
├── context/            # AuthContext (sesión JWT), LiveContext (WebSocket único)
├── hooks/              # useNow (reloj para "hace X"), useAsync
├── pages/              # Login, Dashboard, History, Events, Geofences, Rules, Devices, Users, Audit, Account
├── services/           # api.js (REST), live.js (WebSocket con reconexión)
├── styles/
└── utils/              # format (fechas/zonas), status (conexión/GPS), liveReducer, geo
```

## Criterios de presentación

- **Fechas**: la API entrega UTC; se muestran en la zona del navegador y el valor UTC exacto
  aparece al pasar el mouse. Si el reloj del equipo va adelantado, se indica en vez de mostrar "hace -X".
- **Conexión ≠ contacto**: el estado de conexión se calcula con `online`, `reported_offline`
  y `last_seen`, nunca con ignition.
- **Posición**: se distingue la "última comunicación" de la "última posición GPS válida";
  una posición antigua o sin señal se marca como tal.
- **Desconocido no es "No"**: los valores `null` (contacto, DOUT1) se muestran como "Desconocido".
- **DOUT1** es el estado lógico informado por el equipo, no la confirmación del relé.
- **Sesión** en `sessionStorage`: se borra al cerrar la pestaña y al expirar el token, o ante un 401 o un cierre 4401 del WebSocket.
- **Permisos**: el menú y los botones se ocultan según los permisos del usuario; la API vuelve a validarlos.
