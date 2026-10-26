#!/usr/bin/env python3
"""Votación nominal completa: el voto de cada congresista (no solo los cusqueños) en cada votación del Pleno.

Reutiliza la lectura de votaciones.py (texto digital u OCR) y valida cada página contra la tabla oficial
de totales por bancada del acta (votaciones/totales_bancadas.json): una votación solo se usa si, al contar
los votos leídos de cada bancada, los a favor, en contra y abstenciones coinciden exactamente con la tabla.
Así un error de OCR descarta la página en vez de colarse en el análisis.

Uso:  python3 nominal.py   → votaciones/nominal.json   (después de votaciones.py y promedios.py)
"""
import json
import re
import statistics
from collections import Counter
from pathlib import Path

import votaciones as V
from redes import bancadas, buscar_bancada

BASE = Path(__file__).resolve().parent
CACHE = V.CARPETA / "ocr" / "nominal_filas.json"  # lecturas fila por fila de las actas escaneadas


BANC = {"FP", "JP", "PBG", "RP", "PCO", "AN"}


def filas_tabla(items):
    """Altura de cada fila de la tabla, a partir de lo leído en la primera columna (bancada o nombre)."""
    # Códigos de bancada en el borde izquierdo, o nombres de la primera columna (no las líneas del asunto)
    ys = sorted(y for txt, x, y in items if 0.12 < y < 0.8 and (
        (txt.strip() in BANC and x < 0.1) or (0.1 < x < 0.33 and re.match(r"^[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ .\-]{4,}", txt.strip()))))
    grupos = []
    for y in ys:  # bancada y nombre de una misma fila quedan a la misma altura
        if grupos and y - grupos[0 if False else -1][0] < 0.0065:
            grupos[-1].append(y)
        else:
            grupos.append([y])
    centros = [statistics.mean(g) for g in grupos]
    difs = [b - a for a, b in zip(centros, centros[1:]) if 0.006 < b - a < 0.02]
    if len(difs) < 3:
        return [], 0
    paso = statistics.median(difs)
    filas = [centros[0]]
    for y in centros[1:]:
        if y - filas[-1] > 3.5 * paso:  # fin de la tabla
            break
        while y - filas[-1] > 1.5 * paso:  # fila que no se leyó
            filas.append(filas[-1] + paso)
        if y - filas[-1] > 0.5 * paso:
            filas.append(y)
    # La primera o la última fila pueden no haberse detectado: se prueba una más a cada lado.
    return [filas[0] - paso] + filas + [filas[-1] + paso], paso


def leer_por_filas(imagen, items, padron):
    """Actas escaneadas: el OCR de página entera pierde los "SI" sueltos. Se relee cada fila de la tabla como
    una franja ampliada; cada fragmento va a su columna (de las tres) por su posición horizontal. Si un nombre
    queda sin voto, se relee solo esa celda, ampliada, a la altura x donde están los votos de esa columna."""
    import ocr
    filas, paso = filas_tabla(items)
    # Dónde empieza cada una de las tres columnas: la posición de sus códigos de bancada
    xs = sorted(x for txt, x, y in items if txt.strip() in BANC)
    inicios = [xs[0]] if xs else []
    for x in xs[1:]:
        if x - inicios[-1] > 0.15:
            inicios.append(x)
    if len(inicios) != 3:
        inicios = [0.03, 0.335, 0.645]
    limites = [-1, inicios[1] - 0.012, inicios[2] - 0.012, 2]
    lecturas = []  # (columna, y, nombre, código o None)
    x_codigos = [[], [], []]
    for y in filas:
        trozos = ocr.ocr_zona(imagen, max(y - paso * 0.35, 0), y + paso * 0.95, escala=3)
        for c in range(3):
            col = sorted((tr for tr in trozos if limites[c] <= tr[1] < limites[c + 1]), key=lambda tr: tr[1])
            nombre, cod = [], None
            for txt, x, yy, w in col:
                txt = txt.strip()
                if not nombre and (txt in BANC or len(txt) <= 3 and V.codigo(txt) is None):
                    continue  # código de bancada (a veces mal leído: "FF")
                if nombre and V.codigo(txt.upper()):
                    cod = V.codigo(txt.upper()); x_codigos[c].append(x)
                    continue
                final = re.search(r"\s(\S+(?: -+)?)$", txt)
                if final and V.codigo(final.group(1).upper()) and "," in txt[:final.start()] + ",":
                    cod = V.codigo(final.group(1).upper()); txt = txt[:final.start()]
                nombre.append(txt)
            if nombre:
                lecturas.append((c, y, " ".join(nombre), cod))
    votos = {}
    for c, y, nombre, cod in lecturas:
        ident = padron.identificar(nombre if "," in nombre else nombre + ",")  # "JÁUREGUI MARTÍNEZ DE" no cabe con su coma
        if ident is None:
            continue
        if cod is None and x_codigos[c]:
            x = statistics.median(x_codigos[c])
            texto = ocr.ocr_recorte(imagen, x - 0.012, max(y - paso * 0.3, 0), x + 0.05, y + paso * 0.9, escala=5)
            cod = next((V.codigo(tt.upper()) for tt in texto.split() if V.codigo(tt.upper())), None)
        if cod:
            votos[ident] = cod
    return votos


def rescatar(items, tol, leido, miembros):
    """Nombres que la lectura general no reconoce (apellidos compuestos cortados sin coma):
    se buscan por sus dos primeros apellidos y se toma el código de voto de la misma fila."""
    for i, m in miembros.items():
        if leido.get(i) not in (None, "REVISAR"):
            continue
        clave = " ".join(V.normalizar(m["nombre"].split(",")[0]).split()[:2])
        for txt, x, y in items:
            if not V.normalizar(txt).startswith(clave):
                continue
            final = re.search(r"\s(\S+)$", txt)
            cod = V.codigo(final.group(1)) if final else None
            if cod is None:
                vecinos = sorted((xx - x, tt) for tt, xx, yy in items if abs(yy - y) <= tol and 0.03 < xx - x < 0.3 and V.codigo(tt))
                cod = V.codigo(vecinos[0][1]) if vecinos else None
            if cod:
                leido[i] = cod
                break
    return leido


def main():
    banc = bancadas()
    totales = {(t["pdf"], t["pagina"]): t for t in json.loads((V.CARPETA / "totales_bancadas.json").read_text())
               if t["tipo"] == "VOTACIÓN"}
    correcciones_f = V.CARPETA / "correcciones.json"
    correcciones = json.loads(correcciones_f.read_text()) if correcciones_f.exists() else {}
    eventos = {(e["pdf"], e["pagina"]): e for e in json.loads((V.CARPETA / "eventos.json").read_text())}
    salida, informe = [], Counter()
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    for camara in "DS":
        padron = V.Padron(camara)
        miembros = {i: {"nombre": n, "bancada": buscar_bancada(n, banc)} for i, n in padron.nombres}
        sin_banc = [m["nombre"] for m in miembros.values() if not m["bancada"]]
        if sin_banc:
            print(f"  {camara}: sin bancada → {sin_banc}")
        for pdf in sorted(V.PDFS.glob(f"{camara}_*.pdf")):
            for n, (items, tol, imagen) in enumerate(V.paginas_de(pdf), start=1):
                t = totales.get((pdf.name, n))
                ev = eventos.get((pdf.name, n))
                if not t or not ev or ev["tipo"] != "VOTACIÓN":
                    continue
                if imagen is not None:
                    ref = f"{pdf.name}#{n}"
                    if ref not in cache:
                        leido = leer_por_filas(imagen, items, padron)
                        if len(leido) < len(miembros) - 3:  # tabla no reconocida: lectura general, celda por celda
                            leido = {**V.interpretar_pagina(items, tol, padron, miembros, imagen)["votos"], **leido}
                        cache[ref] = {str(i): v for i, v in leido.items()}
                        CACHE.write_text(json.dumps(cache, ensure_ascii=False))
                    leido = {int(i): v for i, v in cache[ref].items()}
                else:
                    leido = V.interpretar_pagina(items, tol, padron, miembros, None)["votos"]
                leido = rescatar(items, tol, leido, miembros)
                for i in list(leido):  # correcciones manuales ya verificadas (cusqueños)
                    leido[i] = correcciones.get(f"{pdf.name}#{n}|{i}", leido[i])
                for i, v in ev["votos"].items():  # votos de cusqueños ya verificados en eventos.json
                    leido[int(i)] = v
                # La tabla de totales refleja el registro del sistema, sin las constancias verbales
                sistema = {**leido, **{int(i): v for i, v in (ev.get("registro_sistema") or {}).items()}}
                cuenta = Counter((miembros[i]["bancada"], v) for i, v in sistema.items())
                # Deducción por totales: si en una bancada faltan k votos de un solo tipo (y sobra ninguno) y hay
                # exactamente k miembros sin lectura, esos k votaron así. Solo se usa cuando no hay otra posibilidad.
                deducidos = []
                for b, f in t["bancadas"].items():
                    faltan = {cod: f[k] - cuenta[(b, cod)] for cod, k in (("SI", "si"), ("NO", "no"), ("ABST", "abst"))}
                    sin_leer = [i for i, m in miembros.items() if m["bancada"] == b and sistema.get(i) in (None, "REVISAR")]
                    negativos = {c: k for c, k in faltan.items() if k > 0}
                    if len(negativos) == 1 and not any(k < 0 for k in faltan.values()) and len(sin_leer) == sum(negativos.values()):
                        cod = next(iter(negativos))
                        for i in sin_leer:
                            leido[i] = sistema[i] = cod
                            deducidos.append(str(i))
                        cuenta = Counter((miembros[i]["bancada"], v) for i, v in sistema.items())
                cuadra = all(cuenta[(b, "SI")] == f["si"] and cuenta[(b, "NO")] == f["no"] and cuenta[(b, "ABST")] == f["abst"]
                             for b, f in t["bancadas"].items())
                informe[(camara, cuadra)] += 1
                if not cuadra:
                    dif = {b: (cuenta[(b, "SI")] - f["si"], cuenta[(b, "NO")] - f["no"], cuenta[(b, "ABST")] - f["abst"])
                           for b, f in t["bancadas"].items()}
                    print(f"  descartada {pdf.name}#{n}: diferencias (sí, no, abst) {({b: d for b, d in dif.items() if any(d)})}")
                    continue
                salida.append({"camara": camara, "pdf": pdf.name, "pagina": n, "fecha": ev["fecha"], "hora": ev["hora"],
                               "asunto": ev["asunto"], "votos": {str(i): v for i, v in leido.items()}, "deducidos": deducidos})
                informe["deducidos"] += len(deducidos)
        for i, m in miembros.items():
            m["id"] = i
        (V.CARPETA / f"padron_{camara}.json").write_text(json.dumps(list(miembros.values()), ensure_ascii=False, indent=1))
    (V.CARPETA / "nominal.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1))
    deducidos = informe.pop("deducidos", 0)
    print("Votaciones validadas:", {f"{c} {'ok' if ok else 'descartada'}": n for (c, ok), n in sorted(informe.items())},
          f"· votos deducidos de los totales: {deducidos}")


if __name__ == "__main__":
    main()
