#!/usr/bin/env python3
"""Piezas semanales para Instagram Stories (1080×1920): lo que hicieron los congresistas de Cusco en la semana.

Genera docs/historias/AAAA-MM-DD/ (fecha del último día de la semana) con:
  01 portada · 02 votación clave · 03 asistencia · 04 proyectos nuevos · 05 lo que dijeron · 06 escríbeles
y docs/historias/index.html para descargarlas desde el celular. Solo dibuja las piezas que tienen datos.

Reglas de formato (Stories): nada importante arriba de y≈260 (barra de progreso y perfil) ni debajo de
y≈1580 (barra de respuestas); @sieteborreguitos en cada pieza; la fuente exacta en cada gráfico; la fecha
en el título grande; sin la tipografía de máquina de escribir.

Uso:  python3 historias.py [AAAA-MM-DD]   (por defecto, la semana que termina en el último día con Pleno)
"""
import html
import json
import shutil
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import CoreText

from imagen_compartir import ABST, CS, NO, PAPEL, SI, TINTA, TINTA2, VACIO, Lienzo, fuente, icono

BASE = Path(__file__).resolve().parent
W, H = 1080, 1920
ARRIBA, ABAJO = 270, 1570  # zona segura
X0, X1 = 80, 1000
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "setiembre", "octubre", "noviembre", "diciembre"]
URL = "fiscaliza.ciudadsur.pe"
CONSERVAR = 8  # semanas que se guardan

cardo = lambda t: fuente("Cardo-Bold.ttf", t)
cardo_it = lambda t: fuente("Cardo-Italic.ttf", t)
franklin = lambda t, p=500: fuente("LibreFranklin[wght].ttf", t, p)
cifra = lambda t: fuente("BigShouldersDisplay[wght].ttf", t, 800)


def fecha_larga(f):
    d = date.fromisoformat(f) if isinstance(f, str) else f
    return f"{d.day} de {MESES[d.month - 1]}"


def rango(d0, d1):
    if d0.month == d1.month:
        return f"{d0.day} AL {d1.day} DE {MESES[d1.month - 1].upper()}"
    return f"{d0.day} DE {MESES[d0.month - 1].upper()} AL {d1.day} DE {MESES[d1.month - 1].upper()}"


def ancho(s, f):
    linea = CoreText.CTLineCreateWithAttributedString(CoreText.CFAttributedStringCreate(None, s, {CoreText.kCTFontAttributeName: f}))
    return CoreText.CTLineGetTypographicBounds(linea, None, None, None)[0]


def lineas(s, f, maximo):
    salida, actual = [], ""
    for palabra in s.split():
        prueba = (actual + " " + palabra).strip()
        if actual and ancho(prueba, f) > maximo:
            salida.append(actual)
            actual = palabra
        else:
            actual = prueba
    return salida + ([actual] if actual else [])


def bloque(lz, s, x, y, f, col, maximo, interlinea, tope=None):
    """Texto con saltos de línea automáticos; devuelve la y siguiente. Recorta con «…» si pasa de `tope` líneas."""
    ls = lineas(s, f, maximo)
    if tope and len(ls) > tope:
        ls = ls[:tope]
        ls[-1] = ls[-1].rstrip(",.;:") + "…"
    for k, l in enumerate(ls):
        lz.texto(l, x, y + k * interlinea, f, col)
    return y + len(ls) * interlinea


def marco(lz, kicker, titulo, fuente_txt, n, total):
    """Fondo, franja de tocapu decorativa (fuera de la zona segura), encabezado, título y fuente."""
    lz.rect(0, 0, W, H, PAPEL)
    # Tocapu en los bordes (decorativo: puede quedar tapado por la interfaz)
    k = 2.2
    for y0 in (150, H - 230):
        lz.rect(0, y0, W, 18 * k, TINTA)
        for x0 in range(0, W, int(36 * k)):
            p = lambda pts: [(x0 + px * k, y0 + py * k) for px, py in pts]
            lz.poligono(p([(2, 16), (6, 16), (6, 12), (10, 12), (10, 8), (14, 8), (14, 4), (18, 4), (18, 16)]), CS)
            lz.poligono(p([(20, 2), (24, 2), (24, 6), (28, 6), (28, 10), (32, 10), (32, 14), (36, 14), (36, 2)]), ABST)
            for px, py in ((22, 12), (10, 2)):
                lz.rect(x0 + px * k, y0 + py * k, 4 * k, 4 * k, PAPEL)
    lz.texto(kicker.upper(), X0, ARRIBA + 34, franklin(27, 650), TINTA2, 2)
    a = ancho("@sieteborreguitos", franklin(29, 700))
    lz.texto("@sieteborreguitos", X1 - a, ARRIBA + 34, franklin(29, 700), CS)
    lz.rect(X0, ARRIBA + 56, X1 - X0, 3, TINTA)
    y = ARRIBA + 160
    for parte, f, col, il in titulo:
        y = bloque(lz, parte, X0, y, f, col, X1 - X0, il) + 4
    # Pie: fuente exacta y número de pieza
    y_f = ABAJO - 20
    ls = lineas("Fuente: " + fuente_txt, franklin(23, 500), X1 - X0 - 90)
    for k_, l in enumerate(reversed(ls)):
        lz.texto(l, X0, y_f - k_ * 31, franklin(23, 500), TINTA2)
    lz.texto(f"{n}/{total}", X1 - ancho(f"{n}/{total}", franklin(23, 600)), y_f, franklin(23, 600), TINTA2)
    lz.rect(X0, y_f - len(ls) * 31 - 8, X1 - X0, 2, TINTA2)
    return y + 40, y_f - len(ls) * 31 - 40


def semana(eventos, hasta=None):
    fechas = sorted(e["fecha"] for e in eventos if e.get("fecha"))
    fin = date.fromisoformat(hasta) if hasta else date.fromisoformat(fechas[-1])
    return fin - timedelta(days=6), fin


def main():
    congresistas = json.loads((BASE / "congresistas.json").read_text())
    eventos = json.loads((BASE / "votaciones" / "eventos.json").read_text())
    proyectos = json.loads((BASE / "datos" / "proyectos.json").read_text())
    resumenes = json.loads((BASE / "datos" / "resumenes.json").read_text()) if (BASE / "datos" / "resumenes.json").exists() else {}
    turnos = json.loads((BASE / "intervenciones" / "intervenciones.json").read_text())
    res_int = json.loads((BASE / "intervenciones" / "resumenes.json").read_text())
    contacto = json.loads((BASE / "datos" / "contacto.json").read_text()) if (BASE / "datos" / "contacto.json").exists() else {}
    totales = {(t["pdf"], t["pagina"]): t for t in json.loads((BASE / "votaciones" / "totales_bancadas.json").read_text())}

    d0, d1 = semana(eventos, sys.argv[1] if len(sys.argv) > 1 else None)
    en_semana = lambda f: f and d0.isoformat() <= f <= d1.isoformat()
    ev = [e for e in eventos if en_semana(e["fecha"])]
    dip = [c for c in congresistas if c["camara"] == "D"]
    corto = {str(c["id"]): c["corto"] for c in congresistas}
    piezas = []  # (nombre, función de dibujo)

    # 02 · Votación clave: donde los cusqueños se dividieron; si no, la más reñida del Pleno
    votos_d = [e for e in ev if e["tipo"] == "VOTACIÓN" and e["camara"] == "D"]
    clave_v = None
    if votos_d:
        def dividida(e):
            vs = {v for v in (e["votos"].get(str(c["id"])) for c in dip) if v in ("SI", "NO", "ABST")}
            return len(vs) > 1
        def renida(e):
            t = totales.get((e["pdf"], e["pagina"]))
            if not t:
                return 0
            si = sum(b["si"] for b in t["bancadas"].values()); no = sum(b["no"] for b in t["bancadas"].values())
            return min(si, no) / max(si + no, 1)
        clave_v = max(votos_d, key=lambda e: (dividida(e), renida(e)))

    asis = [e for e in ev if e["tipo"] == "ASISTENCIA"]
    nuevos = sorted((p for p in proyectos.values() if en_semana(p["fecha"]) and "Autor principal" in p["cusco"].values()), key=lambda p: p["fecha"])
    dichos = []
    for t in turnos:
        r = res_int.get(t["id"], {})
        if en_semana(t["fecha"]) and r.get("cita") and not r.get("procedimiento") and not t.get("preside"):
            dichos.append((t, r))
    dichos.sort(key=lambda tr: (not tr[1].get("cusco"), -tr[0]["palabras"]))  # primero lo que habla de Cusco

    total_v = len([e for e in ev if e["tipo"] == "VOTACIÓN"])
    sesiones = len({(e["camara"], e["fecha"]) for e in ev})

    def portada(lz, n, tot):
        y, _ = marco(lz, "Fiscaliza Cusco · Ciudad Sur", [("La semana de", cardo(104), TINTA, 104),
                                                        ("tus congresistas", cardo_it(104), CS, 104),
                                                        (rango(d0, d1) + f" {d1.year}", franklin(40, 700), TINTA, 50)],
                     "actas del Pleno de la Cámara de Diputados y del Senado, Diario de Debates y sistema de proposiciones legislativas del Congreso.", n, tot)
        y += 30
        icono(lz, X1 - 140, y + 10, 140)
        plural = lambda n, uno, varios: uno if n == 1 else varios
        for valor, texto in ((sesiones, plural(sesiones, "día con sesión del Pleno", "días con sesión del Pleno")),
                             (total_v, plural(total_v, "votación", "votaciones")),
                             (len(nuevos), plural(len(nuevos), "proyecto nuevo de los cusqueños", "proyectos nuevos de los cusqueños")),
                             (len(dichos), plural(len(dichos), "intervención en el Pleno", "intervenciones en el Pleno"))):
            lz.texto(str(valor), X0, y + 96, cifra(120), TINTA)
            bloque(lz, texto, X0 + 190, y + 60, franklin(38, 500), TINTA, X1 - X0 - 190, 46)
            y += 150
        lz.texto("Desliza para ver el detalle →", X0, y + 70, franklin(30, 600), TINTA2)

    def votacion(lz, n, tot):
        e = clave_v
        t = totales.get((e["pdf"], e["pagina"]))
        fuente_txt = f"acta de votación del Pleno de la Cámara de Diputados del {fecha_larga(e['fecha'])} de {d1.year}, {e['hora'] or ''} (archivo {e['pdf'].split('_', 1)[1]}, pág. {e['pagina']})."
        y, tope = marco(lz, "Votación de la semana · Diputados", [("Así votaron", cardo(100), TINTA, 100),
                                                                 (f"el {fecha_larga(e['fecha'])}", cardo_it(100), CS, 100)], fuente_txt, n, tot)
        asunto = e["asunto"][:1].upper() + e["asunto"][1:].lower()
        y = bloque(lz, asunto, X0, y + 10, franklin(32, 500), TINTA, X1 - X0, 42, tope=4) + 34
        if t:
            si = sum(b["si"] for b in t["bancadas"].values()); no = sum(b["no"] for b in t["bancadas"].values()); ab = sum(b["abst"] for b in t["bancadas"].values())
            tot_ = max(si + no + ab, 1)
            x = X0
            for v, col in ((si, SI), (no, NO), (ab, ABST)):
                w = (X1 - X0 - 6) * v / tot_
                if v:
                    lz.rect(x, y, w, 26, col)
                x += w + 3
            res = f"Resultado en el Pleno: {si} a favor, {no} en contra, {ab} abstenciones"
            y = bloque(lz, res, X0, y + 66, franklin(28, 600), TINTA2, X1 - X0, 36) + 24
        paso = min(92, (tope - y) / len(dip))
        for c in dip:
            v = e["votos"].get(str(c["id"]), "")
            col = {"SI": SI, "NO": NO, "ABST": ABST}.get(v)
            nombre = {"SI": "A favor", "NO": "En contra", "ABST": "Abstención", "***": "Presidía", "AUS": "Ausente"}.get(v, "No votó" if v else "Sin registro")
            alto = paso - 16
            lz.texto(c["corto"], X0, y + alto * 0.72, franklin(42, 650), TINTA)
            lz.redondeado(X1 - 330, y, 330, alto, 6, col or VACIO)
            lz.texto(nombre, X1 - 330 + (330 - ancho(nombre, franklin(34, 700))) / 2, y + alto * 0.7, franklin(34, 700), PAPEL if col else TINTA)
            y += paso

    def asistencia(lz, n, tot):
        fechas = sorted({e["fecha"] for e in asis})
        y, tope = marco(lz, "Asistencia · Pleno", [("¿Fueron a", cardo(104), TINTA, 104), ("trabajar?", cardo_it(104), CS, 104),
                                                    (rango(d0, d1), franklin(36, 700), TINTA, 46)],
                        f"actas de asistencia del Pleno de cada cámara ({len(asis)} pases de lista entre el {fecha_larga(fechas[0])} y el {fecha_larga(fechas[-1])} de {d1.year}).", n, tot)
        y += 30
        filas = [c for c in congresistas if any(e["camara"] == c["camara"] for e in asis)]
        paso = min(150, (tope - y - 40) / max(len(filas), 1))
        for c in filas:
            pases = [e["votos"].get(str(c["id"])) for e in asis if e["camara"] == c["camara"]]
            pres = sum(1 for v in pases if v in ("PRE", "***"))
            lz.texto(c["corto"], X0, y + 40, franklin(42, 650), TINTA)
            lz.texto(f"{pres} de {len(pases)}", X1 - ancho(f"{pres} de {len(pases)}", cifra(64)), y + 46, cifra(64), TINTA if pres == len(pases) else NO)
            x, lado = X0, min(26, (X1 - X0) / max(len(pases), 1) - 6)
            for v in pases:
                if v in ("PRE", "***"):
                    lz.rect(x, y + 60, lado, 30, TINTA)
                else:
                    lz.rect(x, y + 60, lado, 30, NO); lz.rect(x + 3, y + 63, lado - 6, 24, PAPEL)
                x += lado + 6
            y += paso
        lz.texto("Lleno: presente · Contorno rojo: ausente o con licencia", X0, y + 14, franklin(26, 500), TINTA2)

    def proyectos_nuevos(lz, n, tot):
        nums = ", ".join(str(int(p["numero"].split("-")[0])) for p in nuevos)
        y, tope = marco(lz, "Proyectos de ley", [("Lo que", cardo(104), TINTA, 104), ("propusieron", cardo_it(104), CS, 104),
                                                 (rango(d0, d1), franklin(36, 700), TINTA, 46)],
                        f"sistema de proposiciones legislativas del Congreso (proyectos {nums}).", n, tot)
        y += 20
        compacto = len(nuevos) > 2
        dibujados = 0
        for p in nuevos:
            if y > tope - (230 if len(nuevos) <= 3 else 100 if compacto else 300):  # deja sitio para la línea «y N más»
                break
            autor = next(i for i, r in p["cusco"].items() if r == "Autor principal")
            r = resumenes.get(p["numero"], {})
            titulo = r.get("tema") or p["titulo"].capitalize()
            lz.texto(f"{corto.get(autor, '')} · PL {int(p['numero'].split('-')[0])}", X0, y + 34, franklin(30, 700), CS)
            y = bloque(lz, titulo, X0, y + 86, cardo(48), TINTA, X1 - X0, 54, tope=1 if compacto else 2)
            if r.get("resumen") and len(nuevos) <= 3:  # con muchos proyectos, solo autor y tema
                y = bloque(lz, r["resumen"], X0, y + 4, franklin(29, 450), TINTA2, X1 - X0, 38, tope=2 if compacto else 3)
            y += 30 if len(nuevos) <= 3 else 6
            dibujados += 1
        if dibujados < len(nuevos):
            lz.texto(f"y {len(nuevos) - dibujados} más en {URL}", X0, y + 30, franklin(30, 650), TINTA)

    def dijeron(lz, n, tot):
        t, r = dichos[0]
        quien = corto.get(str(t["congresista"]), "")
        y, tope = marco(lz, "Lo que dijeron en el Pleno", [(quien, cardo(96), TINTA, 100), (f"el {fecha_larga(t['fecha'])}", cardo_it(80), CS, 90)],
                        f"Diario de Debates {'de la Cámara de Diputados' if t['camara'] == 'D' else 'del Senado'}, sesión del {fecha_larga(t['fecha'])} de {d1.year}, pág. {t['pagina']}.", n, tot)
        lz.texto("“", X0 - 6, y + 150, cardo(220), CS)
        y = bloque(lz, r["cita"], X0, y + 150, cardo(58), TINTA, X1 - X0, 70, tope=7) + 40
        if r.get("tema"):
            lz.texto(r["tema"].upper(), X0, y, franklin(26, 700), TINTA2, 1.5)
            y += 50
        if r.get("resumen"):
            bloque(lz, r["resumen"], X0, y, franklin(32, 450), TINTA, X1 - X0, 42, tope=5)

    def escribeles(lz, n, tot):
        y, tope = marco(lz, "Participa", [("Escríbeles", cardo(110), TINTA, 110), ("tú también", cardo_it(110), CS, 110)],
                        "fichas oficiales de cada congresista en los portales de la Cámara de Diputados y del Senado.", n, tot)
        con_correo = [c for c in congresistas if contacto.get(str(c["id"]), {}).get("correo")]
        paso = min(128, (tope - y - 90) / max(len(con_correo), 1))
        for c in con_correo:
            lz.texto(c["corto"], X0, y + 40, franklin(36, 650), TINTA)
            lz.texto(contacto[str(c["id"])]["correo"], X0, y + 82, franklin(32, 500), CS)
            y += paso
        bloque(lz, f"Arma tu mensaje en {URL}", X0, y + 40, franklin(32, 650), TINTA, X1 - X0, 42)

    piezas.append(("01-portada", portada))
    if clave_v:
        piezas.append(("02-votacion", votacion))
    if asis:
        piezas.append(("03-asistencia", asistencia))
    if nuevos:
        piezas.append(("04-proyectos", proyectos_nuevos))
    if dichos:
        piezas.append(("05-dijeron", dijeron))
    piezas.append(("06-escribeles", escribeles))

    raiz = BASE / "docs" / "historias"
    carpeta = raiz / d1.isoformat()
    if carpeta.exists():
        shutil.rmtree(carpeta)
    carpeta.mkdir(parents=True)
    for k, (nombre, dibujar) in enumerate(piezas, start=1):
        lz = Lienzo(W, H)
        dibujar(lz, k, len(piezas))
        lz.guardar(carpeta / f"{nombre}.png")
    # Se conservan las últimas semanas
    semanas = sorted((p for p in raiz.iterdir() if p.is_dir()), reverse=True)
    for viejo in semanas[CONSERVAR:]:
        shutil.rmtree(viejo)
    escribir_indice(raiz, sorted((p for p in raiz.iterdir() if p.is_dir()), reverse=True))
    print(f"docs/historias/{d1.isoformat()}: {len(piezas)} piezas ({', '.join(n for n, _ in piezas)})")


def escribir_indice(raiz, semanas):
    """Página sencilla para abrir en el celular y guardar las imágenes."""
    bloques = []
    for s in semanas:
        d = date.fromisoformat(s.name)
        imgs = "".join(f'<a href="{s.name}/{p.name}" download><img src="{s.name}/{p.name}" alt="{html.escape(p.stem)}" loading="lazy"></a>'
                       for p in sorted(s.glob("*.png")))
        bloques.append(f'<section><h2>Semana al {d.day} de {MESES[d.month - 1]} de {d.year}</h2><div class="g">{imgs}</div></section>')
    (raiz / "index.html").write_text(f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Historias · Fiscaliza Cusco</title>
<meta name="robots" content="noindex">
<style>body{{margin:0;background:#f4ede0;color:#2b2520;font:16px/1.5 system-ui,sans-serif}}main{{max-width:1100px;margin:0 auto;padding:20px 16px 60px}}
h1{{font-family:Georgia,serif;font-size:2rem;margin:.2em 0}}h2{{font-size:1.1rem;margin:28px 0 10px}}
.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}}img{{width:100%;display:block;border:1px solid #d6c9b2}}
p{{color:#6b6157;max-width:60ch}}</style></head><body><main><h1>Historias para Instagram</h1>
<p>Toca una imagen para descargarla (en el celular: mantén presionado y elige «Guardar imagen»). Se generan solas cada semana con los datos de Fiscaliza Cusco.</p>
{''.join(bloques)}</main></body></html>""")


if __name__ == "__main__":
    main()
