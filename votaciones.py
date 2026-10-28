#!/usr/bin/env python3
"""Asistencia y votaciones del Pleno para los congresistas de Cusco.

Fuente: los PDF de "asistencia y votación" que cada cámara publica en su página del Pleno.
Los PDF con texto se leen directamente; los escaneados pasan por OCR (motor Vision de macOS).
Cada lectura dudosa queda marcada como "REVISAR" y se corrige a mano en
votaciones/correcciones.json, de modo que nada dudoso se publica sin verificar.

Uso:  python3 votaciones.py
"""
import difflib
import json
import os
import re
import time
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pypdf

BASE = Path(__file__).resolve().parent
CARPETA = BASE / "votaciones"
PDFS, CACHE_OCR = CARPETA / "pdfs", CARPETA / "ocr"
PAGINAS_PLENO = {
    "D": "https://diputados.congreso.gob.pe/sesiones-del-pleno/",
    "S": "https://senado.congreso.gob.pe/sesiones_del_pleno/",
}
API_FILTROS = "https://api.congreso.gob.pe/spley-portal-service/periodo-parlamentario/2026/filtros?codTipoParl={}"
CODIGOS = {"SI", "NO", "ABST", "SINRES", "PRE", "AUS", "LO", "LP", "LE", "LV", "SUS", "***"}
# Errores típicos del OCR en la columna de códigos.
ARREGLOS = {"PR-": "PRE", "PRF": "PRE", "PKE": "PRE", "PR": "PRE", "SÍ": "SI", "SL": "SI", "S1": "SI",
            "N0": "NO", "SINRESP": "SINRES", "AU5": "AUS", "AUSS": "AUS", "ABS": "ABST", "ABST.": "ABST", "*": "***", "**": "***"}
SIGNIFICADO = {"SI": "A favor", "NO": "En contra", "ABST": "Abstención", "SINRES": "Presente, sin marcar voto", "PRE": "Presente", "AUS": "Ausente",
               "LO": "Licencia oficial", "LP": "Licencia personal", "LE": "Licencia por enfermedad",
               "LV": "Licencia por viaje", "SUS": "Suspendido", "***": "Presidía la sesión"}
MESES = {m: i + 1 for i, m in enumerate("enero febrero marzo abril mayo junio julio agosto setiembre "
                                        "octubre noviembre diciembre".split())}
MESES["septiembre"] = 9


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto.upper())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^A-Z, ]", "", texto.replace(".", ",")).strip()


def codigo(texto):
    t = texto.strip().upper().split(" ")[0] if texto.strip() else ""
    t = t.rstrip("-") or t  # "NO---": el acta digital pega los guiones al código
    t = ARREGLOS.get(t, t)
    return t if t in CODIGOS else None


# ---------- descarga ----------

def leer_url(url, intentos=4):
    for i in range(intentos):
        try:
            pedido = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return urllib.request.urlopen(pedido, timeout=120).read()
        except Exception:
            if i == intentos - 1:
                raise
            time.sleep(5 * (i + 1))


def descargar():
    PDFS.mkdir(parents=True, exist_ok=True)
    for camara, url in PAGINAS_PLENO.items():
        html = leer_url(url).decode("utf-8", "ignore")
        enlaces = sorted(set(re.findall(r'href="([^"]+/uploads/[^"]+\.pdf)"', html)))
        for enlace in enlaces:
            if not re.search(r"asist|votaci|finales", enlace, re.I):
                continue
            destino = PDFS / f"{camara}_{os.path.basename(enlace)}"
            if not destino.exists():
                destino.write_bytes(leer_url(enlace))
                print("Descargado:", destino.name)
                time.sleep(0.5)
            (PDFS / (destino.name + ".url")).write_text(enlace)


# ---------- lectura de páginas como (texto, x, y) ----------

def paginas_de(pdf):
    lector = pypdf.PdfReader(str(pdf))
    if len((lector.pages[0].extract_text() or "").strip()) > 200:
        paginas = []
        for p in lector.pages:
            lineas = (p.extract_text(extraction_mode="layout") or "").splitlines()
            ancho = max((len(l) for l in lineas), default=1)
            items = [(m.group(), m.start() / ancho, i / max(len(lineas), 1))
                     for i, l in enumerate(lineas) for m in re.finditer(r"\S+(?: \S+)*", l)]
            paginas.append((items, 0.4 / max(len(lineas), 1), None))
        return paginas
    cache = CACHE_OCR / (pdf.stem + ".json")
    if not cache.exists():
        import ocr  # solo hace falta para PDFs escaneados
        CACHE_OCR.mkdir(exist_ok=True)
        cache.write_text(json.dumps(ocr.ocr_pdf(str(pdf)), ensure_ascii=False))
    imagenes = [p.images[0].data if p.images else None for p in lector.pages]
    return [(items, 0.007, img) for items, img in zip(json.loads(cache.read_text()), imagenes)]


# ---------- interpretación ----------

class Padron:
    def __init__(self, camara):
        datos = json.loads(leer_url(API_FILTROS.format(camara)))["data"]["autores"]
        self.nombres = [(a["id"], normalizar(a["descripcion"])) for a in datos]

    def identificar(self, texto):
        t = normalizar(texto)
        if len(t) < 8 or "," not in t:
            return None
        puntajes = []
        for i, n in self.nombres:
            comparador = difflib.SequenceMatcher(None, t, n[:len(t) + 2])
            # quick_ratio es una cota superior barata: descarta lo que no puede parecerse
            puntajes.append((comparador.ratio() if comparador.quick_ratio() >= 0.55 else 0, i))
        puntajes.sort(reverse=True)
        (mejor, ident), (segundo, _) = puntajes[0], puntajes[1]
        return ident if mejor >= 0.6 and mejor - segundo >= 0.06 else None


def en_renglones(items, tolerancia):
    """Une los fragmentos en renglones reales (misma altura) y los ordena de izquierda a derecha."""
    renglones = []
    for it in sorted(items, key=lambda it: it[2]):
        if renglones and it[2] - renglones[-1][0][2] <= tolerancia:
            renglones[-1].append(it)
        else:
            renglones.append([it])
    return " ".join(t for r in renglones for t, x, y in sorted(r, key=lambda it: it[1]))


def interpretar_pagina(items, tolerancia, padron, objetivo, imagen=None):
    filas = sorted(items, key=lambda it: (it[2], it[1]))
    texto_cabecera = " ".join(t for t, x, y in filas if y < 0.2)
    tipo = "VOTACIÓN" if re.search(r"VOTAC", texto_cabecera, re.I) else (
        "ASISTENCIA" if re.search(r"ASIS", texto_cabecera, re.I) else None)
    hora = re.search(r"(\d{1,2})\s?:\s?(\d{2})\s*([AP]M)", texto_cabecera)  # a veces "01 :06 PM"
    fecha = None
    m = re.search(r"Sesi[oó]n del (\d{1,2}) de (\w+) de (\d{4})", texto_cabecera, re.I)
    if m and m.group(2).lower() in MESES:
        fecha = f"{m.group(3)}-{MESES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    else:
        m = re.search(r"Fecha:?\s*(\d{2})/(\d{2})/(20\d{2})", texto_cabecera)
        if m and 1 <= int(m.group(2)) <= 12:
            fecha = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    votos, primera_fila = {}, None
    for texto, x, y in filas:
        if re.search(r"[a-zñáéíóú]", texto):  # en la tabla los nombres van en mayúsculas
            continue
        ident = padron.identificar(re.sub(r"\s+(\S+(?: ---)?)$", lambda m: "" if codigo(m.group(1)) else m.group(), texto))
        if ident is None:
            continue
        primera_fila = y if primera_fila is None else min(primera_fila, y)
        if ident not in objetivo or votos.get(ident, "REVISAR") != "REVISAR":
            continue
        final = re.search(r"\s(\S+)(?: ---)?$", texto)
        cod = codigo(final.group(1)) if final else None
        if cod is None:  # el código está en la columna siguiente de la misma fila
            vecinos = sorted((xx - x, t) for t, xx, yy in filas
                             if abs(yy - y) <= tolerancia and 0.03 < xx - x < 0.3 and codigo(t))
            cod = codigo(vecinos[0][1]) if vecinos else None
        if cod is None and imagen is not None:
            # El OCR de página entera suele omitir "SI"/"NO" sueltos: se relee solo esa celda, ampliada.
            import ocr
            recorte = ocr.ocr_recorte(imagen, x + 0.12, max(y - 0.004, 0), min(x + 0.25, 1), y + 0.013)
            cod = next((codigo(t) for t in recorte.split() if codigo(t)), None)
        votos[ident] = cod or "REVISAR"

    asunto = ""
    if tipo == "VOTACIÓN":
        bancadas = [y for t, x, y in filas if re.fullmatch(r"FP|JP|PBG|RP|PCO|AN|OB[RK]AS|0BRAS", t.strip())]
        limite = min(bancadas + ([primera_fila] if primera_fila is not None else [])) if bancadas or primera_fila else 0.3
        primera_fila = limite
        cabecera = en_renglones([it for it in filas if it[2] < limite - tolerancia / 2], tolerancia)
        m = re.search(r"Asun\w*[:.]?\s*(.*)", cabecera, re.I | re.S) or \
            re.search(r"Hora:?\s*\d{1,2}:\d{2}\s*[AP]M(?:\s*\(REGISTRO DIGITAL\))?\s*(.*)", cabecera, re.I | re.S)
        asunto = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

    prosa = en_renglones([it for it in filas if re.search(r"[a-zñáéíóú]{3}", it[0])
                          and it[2] > (primera_fila or 0.3)], tolerancia)
    # Cada constancia hasta la siguiente o el pie de página; las cláusulas (";") pueden ser de distinto tipo.
    notas = [c.strip() for n in re.findall(r"deja(?:ron)? constancia(.*?)(?=deja(?:ron)? constancia|\*\*\*|$)", prosa)
             for c in n.split(";") if c.strip()]
    return {"tipo": tipo, "fecha": fecha, "hora": f"{hora.group(1)}:{hora.group(2)} {hora.group(3)}" if hora else None,
            "asunto": asunto, "votos": votos, "notas": notas}


def constancia_a_codigo(nota, tipo):
    n = nota.lower()
    if tipo == "ASISTENCIA":
        return "PRE" if "asistencia" in n else None
    for frase, cod in (("a favor", "SI"), ("en contra", "NO"), ("abstenc", "ABST")):
        if frase in n:
            return cod
    return None


def fecha_de_archivo(nombre):
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", nombre)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(\d{1,2})[-_.](\d{1,2})[-_.](20\d{2})", nombre)
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None


def apellidos(nombre):
    return normalizar(nombre.split(",")[0]).split()[0]


def main():
    descargar()
    congresistas = json.loads((BASE / "congresistas.json").read_text())
    correcciones_f = CARPETA / "correcciones.json"
    correcciones = json.loads(correcciones_f.read_text()) if correcciones_f.exists() else {}
    padrones = {c: Padron(c) for c in PAGINAS_PLENO}
    eventos, vistos = [], set()

    # El acta final va antes que la provisional de la misma sesión: si ambas traen la misma votación, queda la final.
    for pdf in sorted(PDFS.glob("*.pdf"), key=lambda f: ("PROVISIONAL" in f.name.upper(), f.name)):
        camara = pdf.name[0]
        objetivo = {c["id"]: c for c in congresistas if c["camara"] == camara}
        url = (PDFS / (pdf.name + ".url")).read_text() if (PDFS / (pdf.name + ".url")).exists() else ""
        fecha_previa = None
        for n, (items, tol, imagen) in enumerate(paginas_de(pdf), start=1):
            ev = interpretar_pagina(items, tol, padrones[camara], objetivo, imagen)
            ev["tipo"] = correcciones.get(f"{pdf.name}#{n}|tipo", ev["tipo"])
            if ev["tipo"] == "OMITIR":  # hojas de totales o notas sin votos individuales
                continue
            if not ev["tipo"]:
                print("  Página sin tipo reconocible:", pdf.name, n)
                continue
            ev["fecha"] = ev["fecha"] or fecha_previa or fecha_de_archivo(pdf.name)  # el OCR a veces deforma la fecha
            fecha_previa = ev["fecha"]
            for ident in objetivo:  # quien no aparece en la página también se revisa
                ev["votos"].setdefault(ident, "REVISAR")
            ref = f"{pdf.name}#{n}"
            for ident in list(ev["votos"]):
                if f"{ref}|{ident}" in correcciones:
                    ev["votos"][ident] = correcciones[f"{ref}|{ident}"]
            for campo in ("fecha", "hora", "asunto"):
                if f"{ref}|{campo}" in correcciones:
                    ev[campo] = correcciones[f"{ref}|{campo}"]
            # Constancias verbales leídas por la presidencia sobre un cusqueño.
            # Solo cuentan los nombres que siguen a "deja constancia" (no quien preside y la lee).
            ev["constancias"] = {str(i): "Constancia" + (nota if nota.startswith(" ") else " " + nota) for nota in ev.pop("notas")
                                 for i, c in objetivo.items() if apellidos(c["nombre"]) in normalizar(nota)}
            ev["registro_sistema"] = {}
            for i, nota in ev["constancias"].items():
                valor = constancia_a_codigo(nota, ev["tipo"])
                if valor and ev["votos"].get(int(i)) != valor:
                    ev["registro_sistema"][i] = ev["votos"].get(int(i))
                    ev["votos"][int(i)] = valor
            clave = (camara, ev["fecha"], ev["hora"], ev["tipo"], ev["asunto"][:60])
            if clave in vistos:
                continue
            vistos.add(clave)
            ev.update(camara=camara, fuente=url, pdf=pdf.name, pagina=n,
                      votos={str(k): v for k, v in ev["votos"].items()})
            eventos.append(ev)

    conservar_lo_revisado(eventos)
    eventos.sort(key=lambda e: (e["fecha"] or "", e["camara"], e["hora"] or ""))
    (CARPETA / "eventos.json").write_text(json.dumps(eventos, ensure_ascii=False, indent=1))
    pendientes = [(e["pdf"], e["pagina"], i) for e in eventos for i, v in e["votos"].items() if v == "REVISAR"]
    pendientes += [(e["pdf"], e["pagina"], "fecha") for e in eventos if not e["fecha"]]
    escribir_reporte(eventos, congresistas)
    print(f"{len(eventos)} registros (asistencias y votaciones); {len(pendientes)} lecturas por revisar.")
    for p in pendientes:
        print("  REVISAR", *p)


def conservar_lo_revisado(eventos):
    """El OCR no lee igual en todas las máquinas (la actualización semanal corre en una Mac de GitHub):
    una celda ya verificada no vuelve a "REVISAR", y un registro publicado no desaparece porque el
    Congreso reemplazó el acta provisional por una final que el OCR lee peor."""
    anterior_f = CARPETA / "eventos.json"
    if not anterior_f.exists():
        return
    clave = lambda e: (e["camara"], e["fecha"], e["hora"], e["tipo"])
    anteriores = {clave(e): e for e in json.loads(anterior_f.read_text())}
    actuales = {clave(e) for e in eventos}
    for ev in eventos:
        previo = anteriores.get(clave(ev))
        if previo:
            for ident, v in ev["votos"].items():
                if v == "REVISAR" and previo["votos"].get(ident, "REVISAR") != "REVISAR":
                    ev["votos"][ident] = previo["votos"][ident]
    perdidos = [e for k, e in anteriores.items() if k not in actuales]
    for e in perdidos:
        print("  Se conserva el registro anterior:", e["camara"], e["fecha"], e["hora"], e["tipo"], e["pdf"])
    eventos.extend(perdidos)


def escribir_reporte(eventos, congresistas):
    l = ["# Asistencia y votaciones en el Pleno — congresistas de Cusco",
         f"_Actualizado: {datetime.now():%Y-%m-%d %H:%M}_", "",
         "Fuente: PDF oficiales de asistencia y votación de cada cámara. Cada pase de lista y cada "
         "votación del Pleno cuenta por separado.", "",
         "| Congresista | Pases de lista: presente | Votaciones: participó | A favor | En contra | Abst. | "
         "Sin marcar | Ausente | Licencia | Presidía |", "|---|---|---|---|---|---|---|---|---|---|"]
    for c in congresistas:
        cid = str(c["id"])
        asis = [e["votos"].get(cid) for e in eventos if e["camara"] == c["camara"] and e["tipo"] == "ASISTENCIA"]
        vots = [e["votos"].get(cid) for e in eventos if e["camara"] == c["camara"] and e["tipo"] == "VOTACIÓN"]
        n = Counter(vots)
        participo = n["SI"] + n["NO"] + n["ABST"]
        lic = sum(n[k] for k in ("LO", "LP", "LE", "LV"))
        pres = sum(1 for a in asis if a in ("PRE", "***"))
        l.append(f'| {c["corto"]} ({"Senado" if c["camara"] == "S" else "Diputados"}) | '
                 f'{pres}/{len(asis)} | {participo}/{len(vots)} | {n["SI"]} | {n["NO"]} | {n["ABST"]} | '
                 f'{n["SINRES"]} | {n["AUS"]} | {lic} | {n["***"]} |')
    for c in congresistas:
        cid = str(c["id"])
        l += ["", f'## {c["corto"]} — cómo votó', ""]
        for e in eventos:
            if e["camara"] != c["camara"] or e["tipo"] != "VOTACIÓN":
                continue
            v = e["votos"].get(cid, "REVISAR")
            extra = (f' _(por constancia de la presidencia; el sistema marcaba '
                     f'{SIGNIFICADO.get(e["registro_sistema"][cid], e["registro_sistema"][cid])})_'
                     if cid in e.get("registro_sistema", {}) else "")
            l.append(f'- {e["fecha"]} {e["hora"] or ""} · **{SIGNIFICADO.get(v, v)}** · '
                     f'{e["asunto"][:220]}{extra} · [PDF]({e["fuente"]})')
    (BASE / "reporte_votaciones.md").write_text("\n".join(l) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
