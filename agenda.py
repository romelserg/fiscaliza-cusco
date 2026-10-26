#!/usr/bin/env python3
"""Agenda del Pleno: la última agenda publicada por cada cámara, separada en puntos,
con su tema y una marca cuando involucra a un congresista de Cusco o a una provincia cusqueña.

Uso:  python3 agenda.py   → datos/agenda.json
"""
import json
import re
from pathlib import Path

import pypdf

import temas
from intervenciones import leer_url, sin_tildes

BASE = Path(__file__).resolve().parent
CARPETA = BASE / "agenda"
PAGINAS = {"D": "https://diputados.congreso.gob.pe/sesiones-del-pleno/",
           "S": "https://senado.congreso.gob.pe/sesiones_del_pleno/"}
MESES = {m: i + 1 for i, m in enumerate("enero febrero marzo abril mayo junio julio agosto setiembre "
                                        "octubre noviembre diciembre".split())}
MESES["septiembre"] = 9
# Cómo empieza cada punto de agenda
INICIO = re.compile(r"^(?:\d{1,3}\.\s+)?(Proyecto de Ley \d+|En la sesi[oó]n del Pleno|Proyectos? de Resoluci[oó]n Legislativa \d+|Proposici[oó]n|Moci[oó]n \d+|"
                    r"Mociones? de Orden del D[ií]a \d+|De la Presidencia de la Rep[uú]blica|De los? (senador|diputad)|"
                    r"Decreto Supremo \d|Informe final)", re.I)
# Citas legales que la agenda transcribe como referencia: se omiten hasta el siguiente punto.
CITA = re.compile(r"^(Constituci[oó]n Pol[ií]tica|Reglamento d|REGLAMENTO D|Art[ií]culo \d+\.)")
RUIDO = re.compile(r"^(AGENDA |Agenda del Pleno|CÁMARA DE DIPUTADOS \||SENADO DE LA REPÚBLICA \||\d{1,3}$|Constituci[oó]n Pol[ií]tica|"
                   r"Reglamento d|Art[ií]culo \d|\[…\])", re.I)


def fecha_agenda(texto):
    m = re.search(r"(\d{1,2}) de (\w+) de (20\d{2})", texto[:1500])
    if m and m.group(2).lower() in MESES:
        return f"{m.group(3)}-{MESES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return None


def puntos(texto):
    lineas = [l.strip() for l in texto.splitlines()]
    seccion, actual, salida, citando = "", None, [], False
    for l in lineas:
        if not l:
            continue
        if CITA.match(l):
            citando = True
            continue
        if RUIDO.match(l):
            continue
        if re.match(r"^(I|II|III|IV|V|VI|VII|VIII|IX|X)\.\s+[A-ZÁÉÍÓÚÑ ]{4,}$", l):
            seccion = l.split(".", 1)[1].strip().capitalize()
            citando = False
            continue
        if re.fullmatch(r"[A-ZÁÉÍÓÚÑ ]{8,}", l):  # subtítulo: "COMISIONES DE INVESTIGACIÓN"
            seccion = l.strip().capitalize()
            citando = False
            continue
        if INICIO.match(l):
            if actual:
                salida.append(actual)
            actual = {"seccion": seccion, "texto": re.sub(r"^\d{1,3}\.\s+", "", l)}
            citando = False
        elif actual and not citando and len(actual["texto"]) < 1500:
            actual["texto"] += " " + l
    if actual:
        salida.append(actual)
    return salida


def main():
    CARPETA.mkdir(exist_ok=True)
    congresistas = json.loads((BASE / "congresistas.json").read_text())
    resultado = {}
    for camara, url in PAGINAS.items():
        html = leer_url(url).decode("utf-8", "ignore")
        enlaces = sorted(set(re.findall(r'href="([^"]+/uploads/[^"]+AGENDA[^"]+\.pdf)"', html, re.I)))
        agendas = []
        for e in enlaces:
            destino = CARPETA / f"{camara}_{e.rsplit('/', 1)[-1]}"
            if not destino.exists():
                destino.write_bytes(leer_url(e))
            texto = "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(str(destino)).pages)
            agendas.append((fecha_agenda(texto) or "", e, texto))
        fecha, enlace, texto = max(agendas)  # la de fecha más reciente
        items = []
        for p in puntos(texto):
            t = re.sub(r"\s+", " ", p["texto"]).strip()
            norm = sin_tildes(t)
            quienes = [str(c["id"]) for c in congresistas if c["camara"] == camara
                       and sin_tildes(c["nombre"].split(",")[0]) in norm]
            items.append({"seccion": p["seccion"], "texto": t, "temas": temas.clasificar(t),
                          "cusqueños": quienes, "provincias": temas.provincias(t),
                          "menciona_cusco": bool(re.search(r"\bCUSCO\b", norm)) or bool(temas.provincias(t))})
        resultado[camara] = {"fecha": fecha, "fuente": enlace, "puntos": items}
        print(f"{camara}: agenda del {fecha}, {len(items)} puntos, "
              f"{sum(1 for i in items if i['cusqueños'] or i['menciona_cusco'])} con relación a Cusco")
    (BASE / "datos" / "agenda.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
