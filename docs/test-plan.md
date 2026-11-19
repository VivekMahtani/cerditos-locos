# Plan de pruebas — Cerditos Locos 0.1.0

## Entorno de las pruebas ejecutadas

| Elemento | Valor |
|---|---|
| Python | 3.13 |
| Home Assistant | **No disponible** en el entorno de desarrollo (ver «Pendiente de verificar») |
| Servidor | `dev/devserver.py`: mismo núcleo `game/` y mismo frontend que la integración |
| Navegador | Google Chrome (headless) vía Playwright: TV 1920×1080, móviles 390×844, panel 1280×900 |
| Red | Local (127.0.0.1) |
| Fecha | 2026-11-19 |

## Pruebas automatizadas (`python3 -m pytest`) — 102 superadas

| Archivo | Cubre |
|---|---|
| `tests/test_engine.py` (66) | Catálogo incluido válido y 12 casos de cartas mal definidas rechazadas; sala (nombres duplicados, sala llena, mínimo de jugadores, desconectados fuera, no entrar a mitad); reparto y meta automática; ciclo de turno; jugadas fuera de turno, carta que no está en la mano, réplica en fase de acción; límite de mano y descarte; chollos de robo y límite; ventana de réplica (pasar, tiempo agotado, réplica, contrarréplica, imbatible, ventana caducada, doble «pasar», moscas, réplicas desactivadas); fastidios con objetivo; barro pegajoso; cada carta con efecto (Glotón, Jabalí opcional y Guardián, sin objetivos no pregunta, Carterista/Mercadillo, Cerca abierta y Valla nueva, Baño de barro, Tamborilero en paralelo, Trufero, Valla rota, Comadrona, Dormilón); victoria y bloqueo posterior; mazo agotado; objetivo que desaparece; decisiones ajenas o repetidas; ausentes por tiempo; desconectados fuera de la ventana; pausa; saltar; expulsar al activo y a quien decide; nueva partida; límites de configuración; **ninguna mano en vistas ajenas durante 200 jugadas**; vista del jugador; serialización completa con continuación idéntica; estado con cartas desconocidas rechazado; **200 partidas simuladas** de 2 a 6 jugadores; **60 partidas con desconexiones, tiempos agotados y expulsiones** |
| `tests/test_hub.py` (10) | Roles y autorización del anfitrión, rotación de token; turno completo por el WebSocket; **ninguna mano en los mensajes enviados a TV, anfitrión u otros jugadores**; unión solo en sala de espera, reconexión con sesión, segunda pestaña, sesión caducada; expulsar y salir; JSON inválido, rol inválido, mensajes grandes, límite de frecuencia; fuerza bruta del código; cargas maliciosas en `play`/`decide`/`react`; persistencia y reconexión tras «reinicio»; temporizador real que cierra la ventana sin clientes |
| `tests/test_support.py` (25) | QR decodificado con un lector independiente (OpenCV), red local/IP pública, URLs del QR |
| `tests/test_ha_layer.py` (1) | Capa de HA con dobles: rutas registradas una vez, panel solo admin, páginas con CSP, 403 desde IP pública, QR, token solo para administradores, WebSocket del juego, opciones en caliente, evento al bus, **guardado diferido, recuperación de la partida al recargar la integración, borrado al eliminarla**, flujo de configuración |

Comprobaciones estáticas: `mypy` sin errores en `game/`; `node --check` en los 6 módulos JS; `py_compile` en todos los `.py`; JSON de manifiesto, traducciones y catálogo válidos.

## Simulación masiva (`dev/simulate.py`)

| Ejecución | Resultado |
|---|---|
| `--games 10000` (2–6 jugadores, invariantes tras cada acción) | 10.000 terminadas, **0 fallos** (79 s) |
| `--games 10000 --chaos` (desconexiones, tiempos agotados, expulsiones) | 10.000 terminadas, **0 fallos** (58 s) |

Durante el desarrollo la simulación encontró dos fallos reales, ya corregidos y cubiertos por pruebas: una decisión pendiente que seguía ofreciendo a un jugador expulsado, y la secuencia aleatoria de una partida restaurada que no coincidía con la original.

## Prueba de extremo a extremo con navegadores reales (`tests/e2e/run_e2e.py`)

| ID | Escenario | Resultado |
|---|---|---|
| E01 | TV muestra QR (cargado), código y huecos | ✅ |
| E02 | 3 móviles se unen (uno por QR, dos tecleando el código en minúsculas) | ✅ |
| E03 | Nombre duplicado («ANA» con «Ana» dentro) | ✅ «Ese nombre ya está en uso» |
| E04 | El anfitrión empieza desde el panel | ✅ |
| E05 | Partida completa jugada tocando la interfaz: jugar cartas, elegir rival en fastidios, robar, replicar o dejar pasar, decidir sí/no, elegir rival, elegir cartas y descartar | ✅ (33–76 acciones según la partida) |
| E06 | Recargar un móvil a mitad de partida | ✅ recupera mano y sigue |
| E07 | Pantalla final en TV y móvil | ✅ |
| E08 | Ningún mensaje WebSocket recibido por la TV contiene manos | ✅ |
| E09 | Errores de consola en TV, móviles y panel | ✅ ninguno (se corrigió un aviso de vibración antes de interacción) |

Capturas en `docs/img/`.

## Pendiente de verificar en un Home Assistant real

| ID | Escenario | Cómo comprobarlo |
|---|---|---|
| H01 | La integración carga sin errores en HA ≥ 2025.1 | Instalar, reiniciar, añadirla y revisar **Ajustes → Sistema → Registros** |
| H02 | El panel aparece solo para administradores | Entrar con un usuario no administrador |
| H03 | El panel obtiene el token y muestra «Conectado» | Navegador y app Companion |
| H04 | `/cerditos_locos/tv` y `/cerditos_locos/play` cargan sin sesión de HA | TV y móvil sin iniciar sesión |
| H05 | Partida completa a través de HA | 2–6 móviles reales |
| H06 | Persistencia real | Reiniciar HA a mitad de partida: la TV y los móviles vuelven a la misma partida; comprobar `/config/.storage/cerditos_locos.partida` |
| H07 | Eliminar la integración borra la partida guardada | El archivo anterior desaparece |
| H08 | «Solo red local» con proxy inverso | `use_x_forwarded_for` y `trusted_proxies` en `http:` |
| H09 | Navegador real de tu TV | Legibilidad de las pocilgas con 6 jugadores y fluidez |
| H10 | Móviles reales (iOS Safari y Android Chrome) | Tamaño de botones, hoja de carta, vibración, bloqueo de pantalla |
| H11 | GitHub Actions (hassfest, HACS y pytest) | Tras publicar el repositorio |

## Pendiente de diseño (con partidas reales)

- Confirmar la ventaja del primer jugador observada en la simulación (≈ +3–5 puntos) y, si se confirma, aplicar «el primer jugador no roba en su primer turno».
- Ajustar la duración de la ventana de réplica (8 s) y la meta (6/5) según el ritmo real de la familia.
