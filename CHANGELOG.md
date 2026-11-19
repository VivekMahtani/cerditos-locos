# Changelog

## 0.1.0 — 2026-11-19

Primera versión jugable.

- Integración personalizada `cerditos_locos` para Home Assistant ≥ 2025.1, con flujo de configuración (una instancia) y opciones «Solo red local» y URL base. Instalable por HACS o a mano.
- Juego de cartas para 2–6 jugadores, cada uno con su móvil: pocilgas, turno de 4 fases, 70 cartas originales en 27 diseños (cerdos, cerdos con mañas, trastadas, chollos, fastidios y réplicas) y 8 lechones.
- Motor autoritativo en el servidor: pila de trabajo serializable, decisiones (también en paralelo), efectos encadenados, objetivos revalidados, efectos permanentes derivados, ventana de réplica simultánea con contrarréplicas y réplica imbatible, victoria por objetivo, por mazo agotado o al terminar.
- Catálogo en JSON con vocabulario cerrado de operaciones y validación al cargar.
- Jugadores ausentes: espera configurable y acción por defecto; el anfitrión puede saltar o expulsar.
- La partida sobrevive a reinicios de Home Assistant (`Store`) y se borra al eliminar la integración.
- Pantalla de TV, mando del móvil y panel de anfitrión con estilo propio «Pocilga pop» e ilustraciones SVG originales.
- Evento `cerditos_locos_event` para automatizaciones.
- Bots y simulación masiva (`dev/simulate.py`), servidor de desarrollo y prueba de extremo a extremo con Playwright.
- Infraestructura (QR, red, hub, capa de HA) adaptada de Quiz del Salón.
