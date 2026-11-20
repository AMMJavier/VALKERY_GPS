# Despliegue

- `nginx/`: proxy inverso con TLS para la API y el frontend. El puerto TCP del GPS va directo, sin proxy HTTP.
- `systemd/`: unidades para `valkery-gps` y `valkery-api`.
- `docker-compose.yml`: se agrega cuando se defina el host (fase 7).

El firewall solo abre 443 (HTTPS) y el puerto TCP del GPS. MySQL no se expone.
