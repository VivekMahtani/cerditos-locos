# Cerditos Locos — Arquitectura

## Visión general

```
Home Assistant (proceso único, asyncio)
└── custom_components/cerditos_locos
    ├── __init__.py          Ciclo de vida: rutas, panel, comandos WS, persistencia (Store)
    ├── config_flow.py       Alta desde la UI (una sola instancia) + opciones
    ├── http_views.py        Vistas aiohttp públicas: WebSocket del juego, QR, páginas
    ├── ha_websocket.py      Comandos WS autenticados de HA (token de anfitrión, solo admin)
    ├── game/                Núcleo puro Python, sin dependencias de HA (testeable)
    │   ├── catalog.py       Carga y validación del catálogo de cartas (vocabulario cerrado)
    │   ├── engine.py        Estado, turnos, pila de trabajo, decisiones, réplicas, victoria, vistas, serialización
    │   ├── effects.py       Operaciones de efecto registradas (@op) y cálculo de objetivos
    │   ├── bots.py          Jugadores automáticos (solo pruebas y simulación)
    │   ├── hub.py           Sesiones, roles, validación de mensajes, rate limit, difusión, persistencia
    │   ├── qr.py · netutil.py · names.py · web.py   (procedentes de Quiz del Salón)
    ├── data/cards_es.json   Catálogo de cartas (datos, no código)
    └── frontend/            HTML/CSS/JS sin paso de compilación
        ├── tv.html / tv.js      Pantalla pública
        ├── play.html / play.js  Mando del jugador
        ├── panel.js / panel.css Panel de anfitrión (custom element dentro de HA)
        ├── cards.js             Cartas e ilustraciones SVG (originales, generadas por código)
        ├── common.js            Cliente WS con reconexión, utilidades seguras, sonido
        └── app.css
dev/devserver.py   Servidor sin dependencias con el mismo núcleo y frontend
dev/simulate.py    Simulación masiva con bots (bloqueos, invariantes, equilibrio)
```

## Qué viene de Quiz del Salón y qué es nuevo

| Pieza | Origen |
|---|---|
| `qr.py`, `netutil.py`, `web.py`, `common.js` (salvo sonidos), `http_views.py`, `ha_websocket.py`, `config_flow.py`, devserver, dobles de prueba de HA, CI | Copiados con cambio de rutas y nombres |
| `names.py` | Copiado; avatares de granja |
| `hub.py` | Adaptado: mismos roles, sesiones, límites y difusión; comandos nuevos y gancho de persistencia |
| `__init__.py` | Adaptado: catálogo en lugar de preguntas, `Store` para la partida, `async_remove_entry` |
| `catalog.py`, `engine.py`, `effects.py`, `bots.py`, `simulate.py`, todo el frontend de juego | Nuevo |

Cada integración es autocontenida (HACS no comparte código entre integraciones), así que las piezas comunes están duplicadas. Si aparece un tercer juego conviene extraerlas a un paquete común copiado («vendorizado») en cada repo.

## Decisiones

| Decisión | Motivo |
|---|---|
| Integración custom, `requirements: []` | Igual que el quiz: funciona en cualquier instalación y se instala por HACS. |
| Núcleo `game/` sin imports de HA | Pruebas rápidas y deterministas; el mismo núcleo corre en HA, devserver y simulación. |
| Un móvil por jugador | Manos privadas sin trucos de pantalla compartida; réplicas simultáneas naturales. |
| **Pila de trabajo** de tareas serializables | Turnos, efectos encadenados y esperas se modelan igual. El motor se detiene cuando necesita una decisión y continúa con la respuesta. Todo es JSON. |
| Efectos como **datos** con vocabulario cerrado | Las cartas nuevas se añaden en JSON. El catálogo se valida al cargar (sin `eval`, sin código en el JSON). Una operación nueva = un manejador en `effects.py` + su firma en `catalog.OPS` + pruebas. |
| Efectos permanentes **derivados** | Chollos y fastidios se consultan en cada momento a partir de la pocilga (`hand_limit`, `is_protected`…). No hay estado que deshacer. |
| Objetivos calculados y **revalidados** en el servidor | El cliente nunca propone opciones; si el objetivo cambió, el efecto se esfuma. |
| `decision_id` y `window_id` | Evitan respuestas dobles o a una pregunta antigua (como el índice de pregunta del quiz). |
| Vista construida **por asiento** en el servidor | Las manos solo viajan a su dueño. La TV y el anfitrión comparten una vista sin manos. |
| Persistencia con `homeassistant.helpers.storage.Store` | Las partidas duran 20–35 min. Se guarda la partida y los tokens de sesión con `async_delay_save` (5 s) y al descargar. Al reiniciar se recupera; si el archivo es de otra versión o está corrupto, se empieza de cero. |
| RNG con semilla serializada | La partida restaurada continúa igual que la original (probado). |
| Ilustraciones SVG generadas por código | Arte original, sin archivos externos ni licencias de terceros. |

## Motor: pila de trabajo

`Game.work` es una lista de diccionarios. El bucle `_run` ejecuta siempre la tarea de arriba:

| Tarea | Qué hace |
|---|---|
| `turn_start` | Apila los disparos «al inicio de turno» de la pocilga del activo y deja debajo `draw_phase` |
| `draw_phase` | Roba (1 + bonus) y deja debajo `action` |
| `action` | Crea la decisión `turn`; con la respuesta, roba o se convierte en `play`, dejando debajo `end_phase` |
| `play` | Mueve la carta a «en juego», abre la ventana de réplica, y al cerrarse la anula o la resuelve |
| `trigger` | Disparo de una carta; si es opcional pregunta «¿Usar…?» y luego se convierte en `ops` |
| `ops` | Ejecuta las operaciones de un disparo una a una, con un contexto compartido (p. ej., el rival elegido) |
| `to_discard` | Manda una trastada al monte cuando termina |
| `end_phase` | Descarte por límite de mano y `next_turn` |
| `next_turn` | Pasa al siguiente jugador y apila `turn_start` |

Resultados de cada paso: `done` (se retira), `again` (sigue; normalmente porque apiló otras tareas encima) o `block` (espera una decisión o la ventana de réplica). La victoria se comprueba antes de ejecutar cualquier tarea de fase (no hay efectos a medio resolver).

**Decisiones** (`Decision`): `turn`, `yes_no`, `cards`, `discard`, `player`. Pueden ser varias a la vez (descarte de todos los rivales); el paso continúa cuando todas están respondidas. Cada una tiene una respuesta por defecto para ausentes.

**Invariantes** (`check_invariants`, en pruebas y simulación): cada carta está en exactamente una zona, ninguna carta desaparece, no hay lechones en manos ni trastadas en pocilgas, una partida en curso siempre tiene algo pendiente y las decisiones abiertas son de jugadores existentes.

## Flujo de datos

```
Panel HA (admin) ──callWS cerditos_locos/host_token──▶ HA WS (auth) ──▶ token
Panel HA ──WS /api/cerditos_locos/ws {hello, role:host, token}──▶ Hub
TV       ──WS /api/cerditos_locos/ws {hello, role:tv}──────────▶ Hub
Móvil    ──WS /api/cerditos_locos/ws {hello, role:player, code, name | session}─▶ Hub

Hub ──comando validado──▶ Game.apply (muta estado) ──▶ vista por rol y asiento ──▶ difusión
                                            └──▶ on_save(snapshot) ──▶ Store.async_delay_save
Ticker asyncio ──Game.tick(now)──▶ cierre de ventana / acción por defecto ──▶ difusión
```

### Protocolo (JSON, ≤ 4 KB por mensaje entrante)

| type | rol | payload |
|---|---|---|
| `hello` | todos | `role`; `token` (host); `code` + `name` + `avatar` o `session` (player) |
| `play` | player | `card` (uid), `target` (id de rival, solo fastidios) |
| `draw_instead` | player | — |
| `decide` | player | `decision` (id), `choice` (bool, id de jugador o lista de uids) |
| `react` | player | `window` (id), `card` (uid de réplica) o `null` para dejar pasar |
| `leave` | player | — |
| `configure` | host | `settings`: `goal`, `react_seconds`, `absent_seconds` |
| `start` / `pause` / `resume` / `end` | host | — |
| `skip` | host | `player_id` opcional |
| `kick` | host | `player_id` |
| `new_game` | host | `keep_players` |
| `ping` | todos | — |

Servidor → cliente: `welcome`, `state` (vista filtrada con `version`), `error` (`code` y mensaje en español), `ack`, `kicked`, `removed`, `left`, `replaced`, `pong`. El asiento de un jugador se deduce de su sesión, nunca del mensaje.

## APIs de Home Assistant usadas

Las mismas que Quiz del Salón (verificadas en su desarrollo) más el helper de almacenamiento:

- `StaticPathConfig` + `hass.http.async_register_static_paths`, `HomeAssistantView` + `hass.http.register_view`.
- `panel_custom.async_register_panel(..., require_admin=True)` y `frontend.async_remove_panel`.
- `websocket_api.websocket_command`, `require_admin`, `async_register_command`.
- `homeassistant.helpers.storage.Store(hass, versión, clave)` con `async_load`, `async_delay_save`, `async_save` y `async_remove`.
- `manifest.json` con `single_config_entry`, `config_flow`, `integration_type: service`, `iot_class: local_push`. Versión mínima declarada: **2025.1.0**.

## Seguridad

- Mismo modelo que el quiz: validación estricta de mensajes, 4 KB por mensaje, 20 msg / 5 s por conexión, bloqueo de fuerza bruta del código por IP, tokens con `secrets` y comparación en tiempo constante, «solo red local» por defecto, CSP en las páginas y todo el texto con `textContent`.
- Las manos, las opciones privadas (p. ej., búsqueda en el mazo) y los tokens solo viajan a quien corresponde. Hay pruebas sobre los mensajes reales del hub y del navegador.
- El catálogo no puede ejecutar código: claves y operaciones desconocidas se rechazan.
- `async_remove_entry` borra la partida guardada al eliminar la integración.

## Limitaciones conocidas

- Las rutas HTTP de `hass.http` no se pueden desregistrar en caliente (comportamiento estándar de HA).
- La TV necesita un navegador moderno (ES2020, WebSocket, SVG).
- Mantener la pantalla del móvil encendida (Wake Lock) solo funciona con HTTPS.
- No hay navegación con el mando de la TV: la TV es solo de lectura y no lo necesita.
- Solo hay un catálogo integrado; los paquetes de cartas propios quedan para una versión posterior.
