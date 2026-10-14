# Fiscaliza Cusco

Proyectos de ley, asistencia y votaciones de los congresistas elegidos por Cusco (período 2026–2031), con enlace a cada documento oficial del Congreso.

Web: https://romelserg.github.io/fiscaliza-cusco/

## Cómo se actualiza

```sh
./actualizar.sh
```

1. `extraer_proyectos.py` descarga los proyectos de ley desde el sistema de proposiciones legislativas del Congreso.
2. `votaciones.py` lee las actas de asistencia y votación del Pleno (con OCR para las escaneadas). Las lecturas dudosas se verifican a mano y se guardan en `votaciones/correcciones.json`.
3. `generar_web.py` arma `docs/index.html`, que es la página publicada.

Los resúmenes de los proyectos están en `datos/resumenes.json`.
