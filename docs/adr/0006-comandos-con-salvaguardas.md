# ADR 0006 — Comandos remotos con salvaguardas y verificación por DOUT1

**Estado:** aceptada · **Fecha:** 2026-11-20

## Contexto
La sección 4 del documento exige:
- inmovilizar solo con la moto detenida, sin confiar en la velocidad GPS como única condición;
- confirmación explícita y un privilegio aparte;
- no encolar comandos peligrosos para enviarlos al reconectar;
- trazabilidad completa;
- no confundir la confirmación (ACK) o la respuesta del equipo con el éxito físico del relé.

Hasta validar el cableado, el texto exacto de los comandos y la polaridad del relé
siguen sin confirmar.

## Decisión
1. **Catálogo cerrado** (`valkery_core.commands`): `GET_VERSION`, `GET_STATUS`, `GET_INFO`
   (consultas), `IMMOBILIZE` y `RELEASE` (relé). No existe un comando libre: un texto
   arbitrario podría cambiar el servidor o el APN del equipo.
2. **Dos interruptores apagados por defecto**:
   - `VALKERY_COMMANDS_ENABLED`, para todos los comandos;
   - `VALKERY_COMMANDS_RELAY_ENABLED`, para los de relé, que solo se activa después de la
     prueba física con un profesional.
   El texto de los comandos de relé es configurable (`VALKERY_COMMAND_IMMOBILIZE_TEXT`,
   `VALKERY_COMMAND_RELEASE_TEXT`) para ajustarlo a la sintaxis real del firmware.
3. **Permisos**:
   - todos los comandos exigen `commands:send`;
   - `IMMOBILIZE` exige además `commands:immobilize`, que ningún rol trae por defecto
     (tampoco `admin`);
   - `RELEASE` no exige ese permiso, porque es la vía de recuperación.
4. **Doble confirmación** para los comandos de relé: se solicitan (estado `CREADO`, vencen en
   `VALKERY_COMMAND_TTL_S`) y el **mismo usuario** confirma reingresando su contraseña y
   declarando que es seguro hacerlo. Las confirmaciones fallidas se bloquean igual que los
   inicios de sesión.
5. **Precondiciones de `IMMOBILIZE`**, todas obligatorias. Un valor desconocido NO cuenta como seguro:
   - el equipo está conectado;
   - comunicación y registro recientes (`VALKERY_COMMAND_STATE_MAX_AGE_S`);
   - contacto apagado;
   - velocidad 0;
   - sin movimiento;
   - DOUT1 no está ya activa.

   Se validan tres veces: al solicitar, al confirmar y, en el servidor GPS, justo antes de enviar.
   Todas las evaluaciones quedan guardadas en `commands.preconditions`.
6. **Sin cola diferida**: si al enviar el equipo no está conectado, el comando queda `FALLIDO`.
   Traccar, en cambio, guarda `QueuedCommand` para enviarlo al reconectar.
7. **Un comando activo por equipo**, porque la respuesta Codec 12 no trae identificador y se
   asocia al último comando `ENVIADO`.
8. **Estados** (documento, sección 4.2):
   `CREADO → AUTORIZADO → ENVIANDO → ENVIADO → RESPUESTA_RECIBIDA → VERIFICADO`, con las salidas
   `RECHAZADO`, `EXPIRADO`, `FALLIDO` y `RESULTADO_INCIERTO`. `VERIFICADO` exige un registro AVL
   **posterior al envío** con DOUT1 (I/O 179) en el valor esperado. Sin respuesta o sin
   verificación dentro del plazo, el comando queda `RESULTADO_INCIERTO`: la interfaz pide
   comprobar el estado físico de la moto y nunca da por hecho el éxito.
9. **Auditoría**: la API registra solicitudes, bloqueos, confirmaciones (incluidas las fallidas)
   y cancelaciones. El comando guarda la trama enviada y cada marca de tiempo, y las respuestas
   van a `command_responses`. Los comandos de relé generan los eventos `COMMAND_*`.

## Pendiente antes de activar el relé
- Confirmar con el FMC920 real la sintaxis de `setdigout` y su respuesta.
- Comprobar que el equipo envía un registro cuando cambia DOUT1. Sin ese registro, la
  verificación termina en `RESULTADO_INCIERTO`; se puede configurar en el equipo un evento
  sobre I/O 179.
- Prueba eléctrica con un profesional, con la moto detenida, más el procedimiento de
  desbloqueo manual.
