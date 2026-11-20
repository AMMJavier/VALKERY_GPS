-- =====================================================================
-- VALKERY GPS · Creación de bases de datos y usuario (ejecutar UNA vez)
-- =====================================================================
-- Ejecutar en MySQL Workbench conectado como root (o un administrador).
--
-- 1. Reemplaza CAMBIAR_ESTA_CLAVE por una contraseña fuerte (las 2 veces).
-- 2. Ejecuta todo el script (rayo ⚡).
-- 3. Pon la misma contraseña en el archivo .env (VALKERY_DB_URL y VALKERY_TEST_DB_URL).
--
-- No guardes en el repositorio este archivo con la contraseña real.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS valkery_gps
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- Base separada para las pruebas automáticas (pytest la vacía en cada ejecución).
CREATE DATABASE IF NOT EXISTS valkery_gps_test
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- Usuario solo accesible desde esta PC.
CREATE USER IF NOT EXISTS 'valkery'@'localhost' IDENTIFIED BY 'CAMBIAR_ESTA_CLAVE';
CREATE USER IF NOT EXISTS 'valkery'@'127.0.0.1' IDENTIFIED BY 'CAMBIAR_ESTA_CLAVE';

-- Permisos para la aplicación y para las migraciones de Alembic.
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES
  ON valkery_gps.* TO 'valkery'@'localhost', 'valkery'@'127.0.0.1';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES
  ON valkery_gps_test.* TO 'valkery'@'localhost', 'valkery'@'127.0.0.1';

FLUSH PRIVILEGES;

-- Comprobación
SHOW GRANTS FOR 'valkery'@'127.0.0.1';
