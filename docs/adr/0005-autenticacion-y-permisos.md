# ADR 0005 — Autenticación con JWT, permisos por rol y auditoría

**Estado:** aceptada · **Fecha:** 2026-11-20

## Contexto
La fase 4 exige consultas paginadas, validación y separación de roles.
El documento pide además un privilegio separado para la inmovilización
(sección 4.1) y que se registre a quien la ordena.

## Decisión
- **Contraseñas** con Argon2 (`pwdlib`), de al menos 10 caracteres.
  Si el usuario no existe, se calcula igual un hash de relleno para que el tiempo
  de respuesta no revele qué usuarios existen.
- **JWT** HS256 de corta duración (`VALKERY_API_JWT_EXPIRE_MIN`, 60 min por defecto) con
  `sub` = id de usuario y `ver` = `token_version`. Cambiar la contraseña, deshabilitar
  al usuario o cambiarle los roles incrementa `token_version`, lo que invalida en el
  acto todas sus sesiones, sin mantener una lista de tokens revocados.
- **Permisos**: se asignan a roles (`role_permissions`) y los roles a usuarios.
  Hay 3 roles iniciales: `admin`, `operator` y `viewer`.
  `commands:immobilize` **no se incluye en ningún rol**: hay que otorgarlo explícitamente (fase 6).
- **Bloqueo** tras `VALKERY_API_LOGIN_MAX_ATTEMPTS` intentos fallidos durante
  `VALKERY_API_LOGIN_LOCKOUT_MIN` minutos. Se guarda en memoria, lo que alcanza para
  el despliegue previsto (un solo proceso de API).
- **No se puede quitar el último administrador activo**, para no quedar fuera del sistema.
- **Auditoría** (`audit_logs`) en la misma transacción que la acción: inicios de sesión,
  intentos fallidos y cambios de usuarios, dispositivos, vehículos, geocercas y reglas.
- **Un solo dueño** de los datos: todos los usuarios ven todos los dispositivos.
  La asignación por propietario (`vehicles.owner_id`) se agrega si alguna vez hay varios clientes.
- **WebSocket**: el token va en la URL porque el navegador no permite cabeceras en un
  WebSocket. En producción debe usarse `wss://` para que no viaje en claro.
  La conexión se cierra (código 4401) al expirar el token o al invalidarse el usuario.

## Consecuencias
- No hay token de refresco: al expirar la sesión, hay que volver a iniciar sesión.
  Si en la fase 5 resulta incómodo, se agrega.
- El bloqueo por intentos se reinicia al reiniciar la API.
