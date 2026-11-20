# Notas de protocolo Teltonika para el FMC920

Fuentes: PDF «FMB1YX Protocols V0.15» (2018), wiki de Teltonika para el FMC920 y
`TeltonikaFrameDecoder`, `TeltonikaProtocolDecoder` y `TeltonikaProtocolEncoder` de Traccar.
El PDF es de otra familia de equipos: el FMC920 real manda sobre él.

## Tramas TCP

| Trama | Forma de detectarla | Largo total |
|---|---|---|
| IMEI | los 2 primeros bytes != 0 | `len(2B) + 2` |
| AVL / Codec 12 | los 4 primeros bytes == 0 | `dataLength(4B @ offset 4) + 12` |
| Ping | el byte 0 es `0xFF` | 1 |

Como en Traccar, se espera tener al menos 12 bytes antes de intentar armar una trama, salvo el ping.

## Codecs

| ID | Uso | Diferencias |
|---|---|---|
| 0x08 | Codec 8 | ID de evento, totales, contadores e IDs de I/O de 1 byte |
| 0x8E | Codec 8 Extended | lo anterior pasa a 2 bytes, más una sección final de I/O de largo variable |
| 0x0C | Codec 12 | comandos (tipo 0x05) y respuestas (tipo 0x06) |

## Codec 12: envío de un comando (confirmado en `TeltonikaProtocolEncoder`)

```
00000000 | len = cmd+8 (4B) | 0C | 01 | 05 | cmdLen (4B) | cmd ASCII | 01 | CRC16-IBM (4B)
```
El CRC se calcula desde el byte del codec hasta el segundo campo de cantidad.

Traccar traduce: `ENGINE_STOP` = `setdigout 1` y `ENGINE_RESUME` = `setdigout 0`.
**Hay que verificarlo contra el firmware y el cableado reales antes de usarlo.**

## CRC
CRC-16/IBM: polinomio reflejado 0xA001 y valor inicial 0x0000. Se guarda en 4 bytes, con los dos primeros en 0.

## Errores del ejemplo de la pág. 20 del PDF
- Pone latitud y longitud al revés: `0f0ea850` es la **longitud** (25.2618832) y `209a6900` es la **latitud** (54.6990336).
- "Angle 0000 = 214º" no tiene sentido: 0x0000 es 0°.
- Dice "12 visible satellites", pero 0x12 son **18** satélites.
- El CRC 0x3FCA es correcto y confirma que el algoritmo es CRC-16/IBM (lo verifica un test).
- Varios bytes aparecen como `0` en vez de `00`.
- El largo total (152 bytes) y el campo de largo de datos 0x8C (140) sí son correctos.
- Se usa como fixture, pero los valores esperados salen del cálculo, no de la tabla del PDF.

## Comprobado contra las tramas de Traccar (fase 1)
- En Codec 8E, el "total de I/O" **incluye** los elementos de largo variable (NX).
- Algunos firmwares viejos declaran un total de I/O que no coincide con lo que envían.
  El decodificador solo deja una advertencia en el log, porque rechazar la trama dejaría al equipo reintentando sin fin.
  El CRC y la validación de cada grupo de I/O siguen siendo obligatorios.
- Hay respuestas Codec 12 de tipo 0x0D (cámara / Codec 13), que no se soportan.
- Fixtures en `gps-server/tests/fixtures/teltonika/traccar_vectors.json` (34 tramas, Apache 2.0).

## Posición válida
Sin señal GPS el equipo repite la última latitud, longitud y altitud, y manda ángulo, satélites y velocidad en 0.
Para decidir si la posición es válida se combinan los satélites, la velocidad y el I/O 69 (estado del GPS).

## I/O principales
239 ignition · 240 movement · 21 señal GSM · 69 estado del GPS · 66 voltaje externo (mV) ·
67 voltaje de batería (mV) · 179 DOUT1 · 246 remolque · 247 choque · 249 jamming ·
248 = iButton (**no** es el relé).
