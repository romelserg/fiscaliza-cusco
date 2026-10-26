# Fiscaliza Cusco

Proyectos de ley, asistencia y votaciones de los congresistas elegidos por Cusco (período 2026–2031), con enlace a cada documento oficial del Congreso.

Web: https://romelserg.github.io/fiscaliza-cusco/

## Cómo se actualiza

**Automáticamente, cada sábado**, con GitHub Actions (`.github/workflows/actualizar.yml`): corre en una Mac de GitHub (gratis en repositorios públicos), publica la web actualizada y las piezas para Stories, y deja en un aviso (*issue*) "Pendientes de revisión" lo que necesita una persona. También se puede lanzar a mano: pestaña **Actions → Actualizar Fiscaliza Cusco → Run workflow**.

A mano, en una Mac:

```sh
pip3 install --user -r requirements.txt
./actualizar.sh
```

1. `extraer_proyectos.py` descarga los proyectos de ley desde el sistema de proposiciones legislativas del Congreso.
2. `textos.py` guarda el texto completo de cada proyecto propio de un cusqueño (`texto/`, con OCR si es un escaneo); de ahí salen las provincias del mapa.
3. `votaciones.py` lee las actas de asistencia y votación del Pleno (con OCR para las escaneadas). Las lecturas dudosas se publican como "Por verificar" y se corrigen a mano en `votaciones/correcciones.json`. Si hay acta final y provisional de una sesión, manda la final.
4. `intervenciones.py` extrae lo que dijo cada congresista en el Pleno desde el Diario de Debates (transcripción oficial). Los resúmenes están en `intervenciones/resumenes.json`.
5. `promedios.py` calcula los promedios de cada cámara y bancada desde la tabla de totales de cada acta; solo usa las tablas cuya suma cuadra con el total de la cámara.
6. `agenda.py` descarga la última agenda del Pleno de cada cámara y marca los puntos relacionados con Cusco.
7. `contacto.py` lee el correo institucional, la ficha y los votos obtenidos de cada congresista en el portal de su cámara.
8. `nominal.py` lee el voto de **todos** los congresistas en cada votación (no solo los cusqueños). En las actas escaneadas relee cada fila de la tabla como una franja ampliada. Una votación solo se usa si los votos leídos de cada bancada suman exactamente lo que dice la tabla oficial de totales; si en una bancada faltan votos de un solo tipo y hay exactamente esa cantidad de miembros sin leer, esos votos se deducen de la tabla (queda marcado en `deducidos`).
9. `redes.py` arma las redes (análisis de redes sociales): coautoría de toda la cámara (comunidades de Louvain, intermediación, firmas con otras bancadas) y mapa de votación por escalamiento multidimensional.
10. `recorrido.py` clasifica cada proyecto del período según la etapa a la que llegó (presentado, en comisión, con dictamen, aprobado, ley, archivado) y compara los de cada cusqueño con los de su cámara.
11. `generar_web.py` arma `docs/index.html`, que es la página publicada.
12. `imagen_compartir.py` dibuja la imagen que aparece al compartir el enlace (`docs/og.png`).
13. `historias.py` dibuja las piezas semanales para Instagram Stories (`docs/historias/AAAA-MM-DD/`); se descargan desde https://romelserg.github.io/fiscaliza-cusco/historias/
14. `pendientes.py` arma `pendientes.md`: votos por verificar, proyectos propios e intervenciones sin resumen.

Lo único que no es automático son los resúmenes (de proyectos e intervenciones) y la verificación de votos dudosos: mientras tanto se publican marcados como pendientes.

Los resúmenes de los proyectos están en `datos/resumenes.json`.

Temas y provincias se asignan con las reglas de `temas.py`. El mapa de provincias (`datos/mapa_cusco.json`) se generó una vez con `mapa.py` a partir de [peru-geojson](https://github.com/juaneladio/peru-geojson).
