#!/bin/sh
# Actualiza proyectos, votaciones y la web, en ese orden.
cd "$(dirname "$0")" || exit 1
python3 extraer_proyectos.py && python3 votaciones.py && python3 generar_web.py
