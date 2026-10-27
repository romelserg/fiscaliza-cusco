#!/usr/bin/env python3
"""Arma la web de fiscalización a partir de los datos ya descargados.

Uso:  python3 generar_web.py   (después de extraer_proyectos.py y votaciones.py)
Escribe web/index.html: una sola página con los datos incluidos.
"""
import base64
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import temas

BASE = Path(__file__).resolve().parent
URL_PUBLICA = "https://fiscaliza.ciudadsur.pe/"
DESCRIPCION = "Qué proponen, cuándo asisten y cómo votan los seis congresistas elegidos por Cusco. Cada dato enlaza al acta oficial del Congreso."


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
    turnos = cargar("intervenciones/intervenciones.json", [])
    res_int = cargar("intervenciones/resumenes.json", {})

    # Intervenciones como orador; las continuaciones del mismo turno se suman a la principal.
    intervenciones, presidio = [], {}
    por_id = {t["id"]: t for t in turnos}
    for t in turnos:
        if t["preside"]:
            presidio[t["congresista"]] = presidio.get(t["congresista"], 0) + 1
            continue
        r = res_int.get(t["id"], {})
        if "continua" in r:
            continue
        partes = [t] + [por_id[i] for i, x in res_int.items() if x.get("continua") == t["id"] and i in por_id]
        texto = " ".join(p["texto"] for p in partes)
        intervenciones.append({
            "texto": texto, "temas": temas.clasificar(f'{r.get("tema", "")} {r.get("resumen", "")} {texto}'),
            "provincias": temas.provincias(texto),
            "congresista": t["congresista"], "camara": t["camara"], "fecha": t["fecha"], "fuente": t["fuente"],
            "pagina": t["pagina"], "palabras": sum(p["palabras"] for p in partes),
            "tema": r.get("tema"), "resumen": r.get("resumen"), "cita": r.get("cita"),
            "cusco": r.get("cusco", False), "procedimiento": r.get("procedimiento", False),
        })

    # Temas y provincias de los proyectos (texto completo cuando está disponible)
    def texto_proyecto(p):
        r = resumenes.get(p["numero"], {})
        archivo = BASE / "texto" / f'{p["numero"]}.txt'
        completo = archivo.read_text(errors="ignore") if archivo.exists() else ""
        return f'{p["titulo"]} {p.get("sumilla") or ""} {r.get("tema", "")} {r.get("resumen", "")}', completo

    menciones = []  # para el mapa: cada documento de un cusqueño que nombra una provincia
    for p in proyectos.values():
        corto, completo = texto_proyecto(p)
        p["_temas"] = temas.clasificar(corto)
        for cid, rol in p["cusco"].items():
            if rol == "Autor principal":
                for prov in temas.provincias(corto + " " + completo):
                    r = resumenes.get(p["numero"], {})
                    menciones.append({"prov": prov, "tipo": "proyecto", "congresista": cid, "fecha": p["fecha"],
                                      "titulo": r.get("tema") or p["titulo"][:120], "ref": p["numero"], "url": p["pdf"]})
    for i in intervenciones:
        for prov in i["provincias"]:
            menciones.append({"prov": prov, "tipo": "intervención", "congresista": i["congresista"], "fecha": i["fecha"],
                              "titulo": i["tema"] or "Intervención en el Pleno", "url": i["fuente"]})
    for e in eventos:
        e["_temas"] = temas.clasificar(e["asunto"]) if e["tipo"] == "VOTACIÓN" else []

    datos = {
        "actualizado": datetime.now().strftime("%Y-%m-%d"),
        "congresistas": [dict(id=str(c["id"]), slug=slug(c["corto"]), corto=c["corto"], nombre=c["nombre"],
                              camara=c["camara"], partido=c["partido"]) for c in congresistas],
        "proyectos": [{
            "numero": p["numero"], "fecha": p["fecha"], "estado": p["estado"], "titulo": p["titulo"],
            "pdf": p["pdf"], "cusco": p["cusco"],
            "autor": p["firmantes"][0]["nombre"] if p["firmantes"] else "",
            "ultimo": p["seguimiento"][0] if p.get("seguimiento") else None,
            "resumen": resumenes.get(p["numero"]), "temas": p["_temas"],
        } for p in sorted(proyectos.values(), key=lambda p: p["fecha"], reverse=True)],
        "eventos": [{
            "camara": e["camara"], "fecha": e["fecha"], "hora": e["hora"], "tipo": e["tipo"],
            "asunto": e["asunto"], "votos": e["votos"], "sistema": e.get("registro_sistema", {}),
            "fuente": e["fuente"], "temas": e["_temas"],
        } for e in eventos],
        "intervenciones": [{k: v for k, v in i.items() if k != "texto"} for i in intervenciones],
        "temas": {k: v[0] for k, v in temas.TEMAS.items()},
        "menciones": menciones,
        "mapa": cargar("datos/mapa_cusco.json", None),
        "agenda": cargar("datos/agenda.json", None),
        "redes": cargar("datos/redes.json", None),
        "recorrido": cargar("datos/recorrido.json", None),
        "contacto": cargar("datos/contacto.json", {}),
        # Fotos oficiales (web/fotos/<id>.jpg, las baja contacto.py), incrustadas como el logo.
        "fotos": {f.stem: "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()
                  for f in sorted((BASE / "web" / "fotos").glob("*.jpg"))},
        # Padrón de cada cámara (para el hemiciclo): nombre y bancada de cada integrante
        "padron": {c: [{"id": str(m["id"]), "n": m["nombre"], "b": m["bancada"]} for m in cargar(f"votaciones/padron_{c}.json", [])] for c in "DS"},
        "presidio": presidio,
        "contexto": cargar("datos/contexto.json", None),
    }
    escribir_busqueda(proyectos, resumenes, eventos, intervenciones, congresistas)
    plantilla = (BASE / "web" / "plantilla.html").read_text(encoding="utf-8")
    js = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
    pagina = plantilla.replace("/*DATOS*/null", js)
    # Logo de Ciudad Sur incrustado: la página no depende de archivos sueltos.
    logo = base64.b64encode((BASE / "web" / "logo-ciudadsur.png").read_bytes()).decode()
    pagina = pagina.replace("/*LOGO_CS*/", "data:image/png;base64," + logo)
    # web/index.html: versión para la vista previa en Claude (el visor agrega <html>, <head> y <body>).
    (BASE / "web" / "index.html").write_text(pagina, encoding="utf-8")
    # docs/index.html: documento completo para GitHub Pages.
    cabeza, cuerpo = pagina.split('<div class="wrap"', 1)
    completo = ('<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                '<style>body{margin:0}[hidden]{display:none!important}img{max-width:100%}</style>\n'
                # Vista previa al compartir el enlace (WhatsApp, Facebook, X, LinkedIn, Telegram)
                f'<meta property="og:type" content="website">\n'
                f'<meta property="og:site_name" content="Fiscaliza Cusco">\n'
                f'<meta property="og:title" content="Fiscaliza Cusco · Observatorio ciudadano del Congreso">\n'
                f'<meta property="og:description" content="{DESCRIPCION}">\n'
                f'<meta property="og:url" content="{URL_PUBLICA}">\n'
                f'<meta property="og:image" content="{URL_PUBLICA}og.png">\n'
                f'<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n'
                f'<meta property="og:image:alt" content="Fiscaliza Cusco: tejido de votos de los diputados cusqueños">\n'
                f'<meta property="og:locale" content="es_PE">\n'
                f'<meta name="twitter:card" content="summary_large_image">\n'
                f'<link rel="canonical" href="{URL_PUBLICA}">\n'
                f'{cabeza}</head>\n<body>\n<div class="wrap"{cuerpo}\n</body>\n</html>\n')
    (BASE / "docs").mkdir(exist_ok=True)
    (BASE / "docs" / "index.html").write_text(completo, encoding="utf-8")
    print(f'web/index.html y docs/index.html: {len(datos["proyectos"])} proyectos, {len(datos["eventos"])} registros del Pleno')


def escribir_busqueda(proyectos, resumenes, eventos, intervenciones, congresistas):
    """Índice del buscador: proyectos, votaciones, intervenciones de los cusqueños y todo el Diario de Debates."""
    import intervenciones as itv
    nombres = {str(c["id"]): c["corto"] for c in congresistas}
    docs = []
    for p in proyectos.values():
        r = resumenes.get(p["numero"], {})
        docs.append({"t": "proyecto", "f": p["fecha"], "q": p["autor"] if "autor" in p else (p["firmantes"][0]["nombre"] if p["firmantes"] else ""),
                     "h": r.get("tema") or p["titulo"][:140], "x": f'{p["titulo"]} {r.get("resumen", "")}', "u": p["pdf"],
                     "c": [cid for cid in p["cusco"]]})
    vistos = set()
    for e in eventos:
        if e["tipo"] != "VOTACIÓN" or (e["camara"], e["fecha"], e["hora"]) in vistos:
            continue
        vistos.add((e["camara"], e["fecha"], e["hora"]))
        docs.append({"t": "votación", "f": e["fecha"], "q": "Senado" if e["camara"] == "S" else "Cámara de Diputados",
                     "h": e["asunto"][:140], "x": e["asunto"], "u": e["fuente"], "c": list(e["votos"])})
    # Diario de Debates completo: todo lo que dijo cualquier congresista
    for pdf in sorted(itv.PDFS.glob("*.pdf")):
        url = (itv.PDFS / (pdf.name + ".url")).read_text()
        texto, fecha, _ = itv.leer_sesion(pdf)
        turnos = list(itv.TURNO.finditer(texto))
        for i, t in enumerate(turnos):
            fin = turnos[i + 1].start() if i + 1 < len(turnos) else len(texto)
            cuerpo = texto[t.end():fin]
            pagina = max(len(re.findall(r"<<PAG (\d+)>>", texto[:t.start()])), 1)
            cuerpo = re.sub(r"\s+", " ", re.sub(r"<<PAG \d+>>", " ", cuerpo)).strip()
            if len(cuerpo.split()) < 8:
                continue
            quien = f'{t.group(2).strip().title()} ({t.group(3).strip()})'
            docs.append({"t": "diario", "f": fecha, "q": quien, "h": "", "x": cuerpo, "u": f"{url}#page={pagina}",
                         "c": [cid for cid, n in nombres.items()
                               if itv.sin_tildes(n.split()[-1]) in itv.sin_tildes(t.group(2)) and "PRESIDENT" not in itv.sin_tildes(t.group(2))]})
    contenido = json.dumps(docs, ensure_ascii=False, separators=(",", ":"))
    for destino in (BASE / "docs" / "busqueda.json", BASE / "web" / "busqueda.json"):
        destino.parent.mkdir(exist_ok=True)
        destino.write_text(contenido, encoding="utf-8")
    print(f"busqueda.json: {len(docs)} documentos, {len(contenido) // 1024} KB")


if __name__ == "__main__":
    main()
