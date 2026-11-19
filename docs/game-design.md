# Cerditos Locos — Reglas y diseño del juego

## 1. Resumen

| Campo | Valor |
|---|---|
| Nombre | **Cerditos Locos** (dominio HA: `cerditos_locos`) |
| Género | Juego de cartas competitivo por turnos: construye tu pocilga y fastidia a los demás |
| Promesa | «Junta tus cerdos antes que nadie… mientras te los espantan, te los roban y te dicen ¡Ni hablar!» |
| Inspiración | Mecánicas generales de Unstable Unicorns. Sin textos, arte, nombres ni reglas copiadas; proyecto no afiliado. |
| Jugadores | 2 a 6, cada uno con su móvil |
| Duración | 20–35 min (estimación a partir de simulaciones; ver §9) |
| Edad / tono | Familiar, 8+. Sin violencia: los cerdos se *espantan* y se van al monte. |
| Idioma | Español |
| Internet | No necesario |

## 2. Dispositivos

- **TV (pública, solo lectura):** `…/cerditos_locos/tv`. Pocilgas, turno, ventana de réplica, registro, final.
- **Móvil de cada jugador:** `…/cerditos_locos/play`. Su mano, sus decisiones y sus réplicas. Sin cuenta ni app.
- **Anfitrión:** panel «Cerditos Locos» en la barra lateral de HA (solo administradores).
- **Audio:** efectos sintetizados en la TV (opcional, botón «Activar sonido»).

## 3. Preparación

- El anfitrión configura (solo en la sala de espera):
  - **Cerdos para ganar:** automático (6 con 2–4 jugadores, 5 con 5–6) o fijo entre 3 y 8.
  - **Tiempo para replicar:** 5–20 s (8 por defecto) o **0 = sin réplicas** (las réplicas se retiran del mazo).
  - **Espera a desconectados:** 10–120 s (30 por defecto).
- La sala tiene un **código de 4 letras** y un QR. Los jugadores entran con nombre (1–16 caracteres, único sin distinguir mayúsculas ni acentos) y avatar.
- **Solo se entra en la sala de espera.** Durante la partida solo se admite la reconexión de quien ya estaba.
- Al empezar: los jugadores desconectados en la sala de espera quedan fuera; se baraja el mazo; el orden de turno se sortea; cada jugador recibe **1 lechón** en su pocilga y **5 cartas**.

## 4. Zonas

| Zona | Visibilidad |
|---|---|
| **Pocilga** (una por jugador): cerdos, chollos y fastidios | Pública |
| **Mano** | Privada: solo el móvil de su dueño. Los demás ven cuántas cartas tiene. |
| **Corral de lechones** (8 lechones, fuera del mazo) | Se muestra el número |
| **Mazo** (70 cartas, o 60 sin réplicas) | Se muestra el número |
| **El monte** (descarte) | Público: número y últimas cartas |
| **En juego**: carta jugada mientras se resuelve o espera réplicas | Pública |

## 5. Bucle principal (turno)

1. **Inicio:** se resuelven los efectos «al inicio de tu turno» de las cartas de tu pocilga, en el orden en que entraron. Los opcionales preguntan «¿Usar…?».
2. **Robo:** robas 1 carta (+1 por cada *Charca de barro*).
3. **Acción:** juegas 1 carta de la mano **o** robas 1 carta.
4. **Final:** si tienes más cartas que tu límite (7, +2 por cada *Comedero XXL*), eliges cuáles descartar.
5. Pasa el turno al siguiente en el orden sorteado.

### Jugar una carta

1. La carta sale de la mano y queda **en juego**. Si es un **fastidio**, eliges ya a qué rival se lo pones.
2. Se abre la **ventana de réplica** (§6).
3. Si nadie la anula:
   - **Cerdo / cerdo con mañas / chollo:** entra en tu pocilga y se apilan sus efectos de entrada.
   - **Fastidio:** entra en la pocilga del rival elegido.
   - **Trastada:** se resuelve su efecto y después va al monte.
4. Si la anulan, va al monte sin efecto.

## 6. Réplicas

- Tras jugar una carta desde la mano, **todos los demás jugadores conectados** reciben a la vez la pregunta «¿Replicas?» con sus réplicas (si tienen) y «Dejar pasar». Todos la reciben, tengan réplicas o no, para no revelar quién las guarda.
- La ventana se cierra cuando **todos los que pueden contestar han dejado pasar**, cuando se agota el tiempo o cuando se juega una réplica imbatible.
- **¡Ni hablar!** abre una ventana nueva en la que pueden contestar todos menos quien acaba de replicar (incluido el jugador original).
- **¡Ni hablar, y punto!** no admite respuesta: cierra la ventana.
- Resultado: con un número **impar** de réplicas encadenadas, la carta original queda anulada; con un número **par**, vale. Todas las réplicas van al monte.
- Si dos jugadores replican a la vez, vale la primera que llega al servidor; la otra recibe «Ya no se puede replicar a esa jugada» y conserva su carta.
- Las réplicas solo anulan **jugar una carta desde la mano**; nunca el efecto de una carta que ya está en una pocilga.
- No se pueden jugar réplicas en la fase de acción propia.

## 7. Catálogo

70 cartas en el mazo + 8 lechones en el corral. Textos e ideas originales (CC BY-SA 4.0). Definidas en `data/cards_es.json`.

| Carta | Tipo | Copias | Efecto |
|---|---|---|---|
| Lechón | Lechón | 8 (corral) | Empieza en tu pocilga. Si sale de ella, vuelve al corral. |
| Cerdo Rosado / Manchado / Rizado, Cerda Coqueta | Cerdo | 5 + 5 + 5 + 5 | Sin efecto. |
| Cerdo Glotón | Con mañas | 2 | Al entrar, roba 1 carta. |
| Jabalí Gruñón | Con mañas | 2 | Al entrar, *puedes* espantar un cerdo de otra pocilga. |
| Cerda Comadrona | Con mañas | 2 | Al inicio de tu turno, *puedes* traer un lechón del corral. |
| Cerdo Guardián | Con mañas | 2 | Tus otros cerdos no pueden ser espantados (él sí). |
| Cerdo Carterista | Con mañas | 2 | Al entrar, elige un rival y quédate una carta de su mano al azar. |
| Cerdo Tamborilero | Con mañas | 2 | Al entrar, cada rival descarta 1 carta (eligen a la vez). |
| Cerdo Trufero | Con mañas | 2 | Al entrar, busca una trastada en el mazo y llévatela; se baraja el mazo. |
| Cerdo Dormilón | Con mañas | 2 | Cuenta como dos cerdos. |
| Baño de barro | Trastada | 2 | Un cerdo de cualquier pocilga vuelve a la mano de su dueño (un lechón, al corral). |
| Cerca abierta | Trastada | 2 | Llévate a tu pocilga un cerdo normal de otra pocilga. |
| Mercadillo | Trastada | 2 | Elige un rival: quédate una carta suya al azar y luego dale una tuya. |
| ¡Que se escapan! | Trastada | 2 | Espanta un cerdo de otra pocilga. |
| Limpieza general | Trastada | 2 | Retira un chollo o un fastidio de cualquier pocilga. |
| Siesta en el pajar | Trastada | 2 | Roba 2 cartas. |
| Charca de barro | Chollo | 2 | En tu fase de robo, robas 1 más. |
| Comedero XXL | Chollo | 2 | +2 a tu límite de mano. |
| Valla nueva | Chollo | 2 | Nadie puede llevarse cerdos de tu pocilga. |
| Nube de moscas | Fastidio | 2 | No puedes jugar réplicas. |
| Valla rota | Fastidio | 2 | Al inicio de tu turno, descarta 1 carta. |
| Barro pegajoso | Fastidio | 2 | No puedes jugar trastadas. |
| ¡Ni hablar! | Réplica | 8 | Anula la carta que otro acaba de jugar. Se puede replicar. |
| ¡Ni hablar, y punto! | Réplica imbatible | 2 | Igual, pero no se puede replicar. |

### Reglas de interacción

- **Espantar:** el cerdo va al monte; un lechón vuelve al corral. *Cerdo Guardián* protege a los demás cerdos de su pocilga (no a sí mismo).
- **Llevarse un cerdo** (*Cerca abierta*): el cerdo entra en tu pocilga y se aplican sus efectos de entrada para ti. *Valla nueva* lo impide.
- **Objetivos:** el servidor calcula las opciones válidas. Si solo hay una, se aplica sin preguntar; si no hay ninguna, el efecto «no encuentra a quién afectar» y se anota en el registro.
- **Efectos opcionales:** si no tienen ningún objetivo posible, no se pregunta.
- **Revalidación:** cuando el jugador elige, el objetivo se vuelve a comprobar; si ya no es válido, el efecto se esfuma.
- **Encadenados:** los efectos de entrada que provoca un efecto se resuelven antes de seguir con el resto de ese efecto (pila).
- **Efectos permanentes** (chollos, fastidios, Guardián, Dormilón) se calculan en cada momento a partir de la pocilga: no hay que deshacer nada cuando la carta sale.

## 8. Victoria y final

- Se comprueba **cada vez que no hay ningún efecto a medio resolver** (al empezar cada fase del turno). Gana quien tenga al menos los cerdos objetivo; si varios lo alcanzan a la vez, comparten la victoria quienes tengan más.
- Los lechones cuentan como cerdos; el *Cerdo Dormilón* cuenta como dos.
- **Mazo agotado:** si alguien debe robar (en cualquier momento) y el mazo está vacío, la partida termina y gana quien tenga más cerdos (empates comparten la victoria).
- **El anfitrión termina la partida:** gana quien tenga más cerdos en ese momento.
- **Queda un solo jugador** (los demás se van o son expulsados): gana él.

## 9. Equilibrio (simulaciones)

`dev/simulate.py --games 10000` con bots que eligen al azar entre jugadas legales (no juegan como personas: sirven para encontrar bloqueos y para comparar). Resultado a 2026-11-19:

| Jugadores | Turnos (media) | Rondas | Victorias por puesto de salida |
|---|---|---|---|
| 2 | 15,4 | 7,7 | 52,6 % · 47,4 % |
| 3 | 21,4 | 7,1 | 35,8 % · 33,1 % · 31,1 % |
| 4 | 26,0 | 6,5 | 28,2 % · 24,9 % · 23,9 % · 23,0 % |
| 5 | 23,6 | 4,7 | 21,8 % · 21,7 % · 18,7 % · 19,4 % · 18,4 % |
| 6 | 25,5 | 4,2 | 17,7 % · 17,6 % · 16,9 % · 16,9 % · 15,5 % · 15,4 % |

El 88 % de las partidas termina por objetivo y el 12 % por mazo agotado. Hay una ventaja moderada para quien empieza (≈ +3–5 puntos sobre el reparto justo). Pendiente de calibrar con partidas reales; si se confirma, la corrección más sencilla es que el primer jugador no robe en su primer turno.

## 10. Jugadores ausentes y reconexión

- El móvil guarda un token de sesión; al recargar o perder la conexión vuelve a su asiento con su mano.
- Un desconectado **no cuenta** para cerrar la ventana de réplica.
- Si le toca decidir, se espera el tiempo configurado (30 s) y se aplica la **acción por defecto**: en su turno, robar en lugar de jugar; «¿Usar…?», no; descartes y elecciones obligatorias, al azar.
- El anfitrión puede **saltar** la espera (de un jugador o de la ventana de réplica) o **expulsar**: las cartas del expulsado van al monte y sus lechones al corral. Si era su turno, el turno pasa al siguiente.
- Tras reiniciar Home Assistant se recupera la partida; todos empiezan desconectados hasta que su móvil vuelva.

## 11. Información por vista

| Información | TV | Anfitrión | Jugador |
|---|---|---|---|
| Pocilgas y nº de cerdos | Sí | Sí | Sí |
| Mano | Solo el número | Solo el número | La suya completa |
| Acciones legales | — | — | Las suyas (cartas jugables y objetivos) |
| Decisiones pendientes | Quién y qué pregunta | Quién y qué pregunta | Las suyas, con opciones |
| Opciones de búsqueda en el mazo | No | No | Solo quien busca |
| Ventana de réplica | Carta, cadena, tiempo y a quién se espera | Igual | Igual + sus réplicas |
| Registro de jugadas | Últimas 9 | Últimas 10 | — |
| Controles | No | Sí | Solo su juego |
| Tokens | Nunca | Nunca de jugadores | Solo el suyo |

## 12. Estados

```
lobby ──start──▶ playing ──victoria / mazo agotado / end / queda 1──▶ finished
  ▲                                                                       │
  └──────────────────────────── new_game ◀────────────────────────────────┘

playing (por turno): inicio → robo → acción ─┬─ robar ───────────────────┐
                                             └─ jugar → réplica → efectos┤
                                                                         ▼
                                                    final (descartar) → siguiente turno
```

`paused` es una marca ortogonal de `playing`: congela la ventana de réplica y las esperas a ausentes.

## 13. Diferencias con el juego de referencia

No se presentan como reglas oficiales; son decisiones propias de esta adaptación.

| Aspecto | Juego de referencia (reglas generales) | Cerditos Locos | Motivo |
|---|---|---|---|
| Jugadores | 2–8 | 2–6 | Alcance de la v1 y legibilidad en la TV |
| Objetivo | 7 unicornios (6 con 6–8 jugadores) | 6 / 5 cerdos, configurable | Partidas más cortas en familia |
| Réplicas | En cualquier momento | Ventana simultánea con cuenta atrás | Orden y ritmo en digital |
| Mazo agotado | Gana quien tenga más | Igual, con empate compartido | Regla de empate explícita |
| Ausencias | No aplica | Espera y acción por defecto | Móviles que se bloquean |
| Catálogo | Más de 100 cartas | 70 + 8, 27 diseños | Alcance de la v1 |
| Destruir / sacrificar | Destruir / sacrificar | Espantar | Tono familiar |
| Entrar a mitad | — | No se puede | Protege el reparto |

## 14. Criterios de aceptación

1. Seis móviles pueden unirse; el séptimo recibe «La pocilga está llena».
2. Nadie puede unirse con la partida empezada; quien ya estaba puede reconectar.
3. Ninguna mano llega a la TV, al anfitrión ni a otro jugador (comprobado en los mensajes reales).
4. Solo el jugador activo puede jugar o robar, y solo una vez por turno; una decisión respondida no se puede repetir.
5. Las réplicas encadenadas anulan o validan la carta según su número; la imbatible cierra la ventana.
6. La ventana de réplica y las esperas a ausentes se cierran por tiempo aunque ningún navegador esté abierto.
7. La victoria se detecta al alcanzar el objetivo y la partida no acepta más jugadas.
8. 10.000 partidas simuladas (y 10.000 con desconexiones y expulsiones) terminan sin bloqueos ni estados incoherentes.
9. La partida sobrevive a recargar la integración o reiniciar Home Assistant.
10. Solo un administrador de HA puede controlar la partida.
