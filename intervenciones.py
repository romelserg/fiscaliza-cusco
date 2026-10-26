#!/usr/bin/env python3
"""Intervenciones de los congresistas de Cusco en el Pleno, desde el Diario de Debates
(transcripción oficial "PLO-…" que publica cada cámara en su página del Pleno).

Uso:  python3 intervenciones.py
Escribe intervenciones/intervenciones.json. Los resúmenes van en intervenciones/resumenes.json
(se escriben aparte, leyendo cada intervención).
"""
import hashlib
import json
import os
import re
import time
import unicodedata
import urllib.request
from pathlib import Path

import pypdf

BASE = Path(__file__).resolve().parent
CARPETA = BASE / "intervenciones"
PDFS = CARPETA / "pdfs"
PAGINAS_PLENO = {
    "D": "https://diputados.congreso.gob.pe/sesiones-del-pleno/",
    "S": "https://senado.congreso.gob.pe/sesiones_del_pleno/",
}
MESES = {m: i + 1 for i, m in enumerate("enero febrero marzo abril mayo junio julio agosto setiembre "
                                        "octubre noviembre diciembre".split())}
MESES["septiembre"] = 9
# Inicio de cada turno de palabra: "El señor PÉREZ MALLQUI (JP).—", "La señora PRESIDENTA (Analí Márquez Huanca).—"
TURNO = re.compile(r"(?m)^\s*(El señor|La señora|El|La)\s+([A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ\s\-]+?)\s*\(([^)]{1,80})\)\s*\.?\s*[—–-]{1,2}")
# Acotaciones de relatoría que cierran el turno ("—Los señores diputados registran…"). Las de idioma
# ("—Se expresa en su idioma originario:", "—Traducción:") son parte de la intervención y no la cortan.
ACOTACION = re.compile(r"(?m)^\s*—(?!\s*(Se expresa en|Traducci|Intervenci[oó]n en|Habla en|Continúa en))")


def sin_tildes(t):
    return "".join(c for c in unicodedata.normalize("NFKD", t.upper()) if not unicodedata.combining(c))


def leer_url(url, intentos=4):
    for i in range(intentos):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                                          timeout=120).read()
        except Exception:
            if i == intentos - 1:
                raise
            time.sleep(5 * (i + 1))


def descargar():
    PDFS.mkdir(parents=True, exist_ok=True)
    for camara, url in PAGINAS_PLENO.items():
        html = leer_url(url).decode("utf-8", "ignore")
        for enlace in sorted(set(re.findall(r'href="([^"]+/uploads/[^"]+\.pdf)"', html))):
            if not re.search(r"PLO-\d{4}-\d+", os.path.basename(enlace)):
                continue
            destino = PDFS / f"{camara}_{os.path.basename(enlace)}"
            if not destino.exists():
                destino.write_bytes(leer_url(enlace))
                print("Descargado:", destino.name)
                time.sleep(0.5)
            (PDFS / (destino.name + ".url")).write_text(enlace)


def limpiar(texto):
    lineas = []
    for l in texto.splitlines():
        s = l.strip()
        if re.fullmatch(r"\d{1,4}", s):          # número de página
            continue
        if re.match(r"^\d{1,2}\s+(Por |Con |En |La |El )", s) and len(s) > 60:  # notas al pie
            continue
        lineas.append(l)
    return "\n".join(lineas)


def leer_sesion(pdf):
    """Texto con marcas de página y datos de cabecera."""
    lector = pypdf.PdfReader(str(pdf))
    partes = []
    for n, p in enumerate(lector.pages, start=1):
        partes.append(f"\n<<PAG {n}>>\n" + limpiar(p.extract_text() or ""))
    texto = "".join(partes)
    cab = sin_tildes(texto[:4000])
    m = re.search(r"(LUNES|MARTES|MIERCOLES|JUEVES|VIERNES|SABADO|DOMINGO),?\s+(\d{1,2})\s+DE\s+([A-Z]+)\s+DE\s+(\d{4})", cab)
    fecha = f"{m.group(4)}-{MESES[m.group(3).lower()]:02d}-{int(m.group(2)):02d}" if m and m.group(3).lower() in MESES else None
    s = re.search(r"(\d+)\.?\s*[ªA]?\s*SESION", cab)
    turno = re.search(r"\((MATINAL|VESPERTINA|NOCTURNA)\)", cab)
    etiqueta = (f"{s.group(1)}.ª sesión" if s else "Sesión") + (f" ({turno.group(1).lower()})" if turno else "")
    return texto, fecha, etiqueta


def main():
    descargar()
    congresistas = json.loads((BASE / "congresistas.json").read_text())
    # Apellidos tal como aparecen en el Diario de Debates: "MÁRQUEZ HUANCA"
    claves = {c["id"]: sin_tildes(c["nombre"].split(",")[0]).split() for c in congresistas}
    salida = []
    for pdf in sorted(PDFS.glob("*.pdf")):
        camara = pdf.name[0]
        objetivo = [c for c in congresistas if c["camara"] == camara]
        url = (PDFS / (pdf.name + ".url")).read_text()
        texto, fecha, etiqueta = leer_sesion(pdf)
        turnos = list(TURNO.finditer(texto))
        for i, t in enumerate(turnos):
            quien, parentesis = sin_tildes(t.group(2)), sin_tildes(t.group(3))
            preside = quien.startswith(("PRESIDENT", "VICEPRESIDENT"))
            persona = None
            for c in objetivo:
                ap = claves[c["id"]]
                # Como orador: "PÉREZ MALLQUI (JP)". Presidiendo: "PRESIDENTA (Analí Márquez Huanca)".
                if (not preside and ap[0] in quien and (len(ap) < 2 or ap[1] in quien)) or \
                   (preside and all(a in parentesis for a in ap)):
                    persona = c
            if not persona:
                continue
            fin = turnos[i + 1].start() if i + 1 < len(turnos) else len(texto)
            cuerpo = texto[t.end():fin]
            corte = ACOTACION.search(cuerpo)          # termina donde empieza una acotación de relatoría
            if corte:
                cuerpo = cuerpo[:corte.start()]
            pagina = len(re.findall(r"<<PAG (\d+)>>", texto[:t.start()]))
            cuerpo = re.sub(r"<<PAG \d+>>", " ", cuerpo)
            cuerpo = re.sub(r"[ \t]+", " ", re.sub(r"-\n(?=[a-záéíóúñ])", "", cuerpo))
            cuerpo = re.sub(r"—\s*Se expresa en su idioma originario:?", "[En quechua:]", cuerpo)
            cuerpo = re.sub(r"—\s*Traducci[oó]n:?", "[Traducción:]", cuerpo)
            cuerpo = re.sub(r"\s*\n\s*", " ", cuerpo).strip()
            if not cuerpo:
                continue
            ident = hashlib.sha1(f"{pdf.name}|{t.start()}".encode()).hexdigest()[:10]
            salida.append({
                "id": ident, "congresista": str(persona["id"]), "camara": camara, "fecha": fecha,
                "sesion": etiqueta, "preside": preside, "pagina": max(pagina, 1),
                "fuente": f"{url}#page={max(pagina, 1)}", "palabras": len(cuerpo.split()), "texto": cuerpo,
            })
    salida.sort(key=lambda x: (x["fecha"] or "", x["camara"]))
    (CARPETA / "intervenciones.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1))
    nombres = {str(c["id"]): c["corto"] for c in congresistas}
    print(f"{len(salida)} intervenciones encontradas")
    for cid, nombre in nombres.items():
        propias = [x for x in salida if x["congresista"] == cid and not x["preside"]]
        print(f"  {nombre}: {len(propias)} como orador, {sum(x['palabras'] for x in propias)} palabras"
              f"{'; ' + str(sum(1 for x in salida if x['congresista'] == cid and x['preside'])) + ' turnos presidiendo' if any(x['congresista'] == cid and x['preside'] for x in salida) else ''}")


if __name__ == "__main__":
    main()
