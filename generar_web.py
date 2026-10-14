#!/usr/bin/env python3
"""Arma la web de fiscalización a partir de los datos ya descargados.

Uso:  python3 generar_web.py   (después de extraer_proyectos.py y votaciones.py)
Escribe web/index.html: una sola página con los datos incluidos.
"""
import json
import unicodedata
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent


def slug(texto):
    t = unicodedata.normalize("NFKD", texto.split(" ")[-1].lower())
    return "".join(c for c in t if c.isalnum())


def cargar(ruta, defecto):
    ruta = BASE / ruta
    return json.loads(ruta.read_text()) if ruta.exists() else defecto


def main():
    congresistas = cargar("congresistas.json", [])
    proyectos = cargar("datos/proyectos.json", {})
    resumenes = cargar("datos/resumenes.json", {})
    eventos = cargar("votaciones/eventos.json", [])

    datos = {
        "actualizado": datetime.now().strftime("%Y-%m-%d"),
        "congresistas": [dict(id=str(c["id"]), slug=slug(c["corto"]), corto=c["corto"], nombre=c["nombre"],
                              camara=c["camara"], partido=c["partido"]) for c in congresistas],
        "proyectos": [{
            "numero": p["numero"], "fecha": p["fecha"], "estado": p["estado"], "titulo": p["titulo"],
            "pdf": p["pdf"], "cusco": p["cusco"],
            "autor": p["firmantes"][0]["nombre"] if p["firmantes"] else "",
            "ultimo": p["seguimiento"][0] if p.get("seguimiento") else None,
            "resumen": resumenes.get(p["numero"]),
        } for p in sorted(proyectos.values(), key=lambda p: p["fecha"], reverse=True)],
        "eventos": [{
            "camara": e["camara"], "fecha": e["fecha"], "hora": e["hora"], "tipo": e["tipo"],
            "asunto": e["asunto"], "votos": e["votos"], "sistema": e.get("registro_sistema", {}),
            "fuente": e["fuente"],
        } for e in eventos],
    }
    plantilla = (BASE / "web" / "plantilla.html").read_text(encoding="utf-8")
    js = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
    pagina = plantilla.replace("/*DATOS*/null", js)
    # web/index.html: versión para la vista previa en Claude (el visor agrega <html>, <head> y <body>).
    (BASE / "web" / "index.html").write_text(pagina, encoding="utf-8")
    # docs/index.html: documento completo para GitHub Pages.
    cabeza, cuerpo = pagina.split('<div class="wrap"', 1)
    completo = ('<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                '<style>body{margin:0}[hidden]{display:none!important}img{max-width:100%}</style>\n'
                f'{cabeza}</head>\n<body>\n<div class="wrap"{cuerpo}\n</body>\n</html>\n')
    (BASE / "docs").mkdir(exist_ok=True)
    (BASE / "docs" / "index.html").write_text(completo, encoding="utf-8")
    print(f'web/index.html y docs/index.html: {len(datos["proyectos"])} proyectos, {len(datos["eventos"])} registros del Pleno')


if __name__ == "__main__":
    main()
