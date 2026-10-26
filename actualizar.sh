#!/bin/sh
# Actualiza todos los datos, la web y las piezas para Stories, en este orden.
cd "$(dirname "$0")" || exit 1
python3 extraer_proyectos.py && python3 textos.py && python3 votaciones.py && python3 intervenciones.py && python3 promedios.py && python3 agenda.py \
  && python3 contacto.py && python3 nominal.py && python3 redes.py && python3 recorrido.py \
  && python3 generar_web.py && python3 imagen_compartir.py && python3 historias.py && python3 pendientes.py
