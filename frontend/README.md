# Frontend VALKERY GPS

React + Tailwind + Vite + Leaflet. Se implementa en la fase 5.

```
src/
├── components/layout   # Shell, navegación
├── components/map      # Mapa Leaflet, marcadores, trayectos
├── components/common   # Botones, tablas, alertas
├── pages/              # Login, Dashboard, LiveTracking, History, Events, Devices, Settings
├── services/           # Cliente HTTP y WebSocket de la API
├── hooks/
├── context/            # Sesión de usuario
└── utils/
```

El frontend solo habla con la API: nunca envía bytes del protocolo al GPS.
