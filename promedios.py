#!/usr/bin/env python3
"""Promedios de cada cámara y bancada, para poner en contexto las cifras de los congresistas de Cusco.

Fuente: la tabla de totales por bancada que trae al pie cada acta de asistencia y votación.
Cada página se valida sola: la suma de las bancadas debe dar el total de la cámara; si no cuadra,
la página se descarta. Las intervenciones se cuentan en el Diario de Debates para todos los oradores.

Uso:  python3 promedios.py   (después de votaciones.py e intervenciones.py)
"""
import json
import re
from collections import defaultdict
from pathlib import Path

import votaciones as vot
import intervenciones as itv

BASE = Path(__file__).resolve().parent
BANCADAS = {"FP": "FP", "JP": "JP", "PBG": "PBG", "P8G": "PBG", "RP": "RP", "PCO": "PCO", "OBRAS": "PCO", "AN": "AN"}
NOMBRE_BANCADA = {"FP": "Fuerza Popular", "JP": "Juntos por el Perú", "PBG": "Partido del Buen Gobierno",
                  "RP": "Renovación Popular", "PCO": "Partido Cívico Obras", "AN": "Ahora Nación"}
PARTIDO_A_CODIGO = {v: k for k, v in NOMBRE_BANCADA.items()}
# Cada fila de la tabla se reconoce por el nombre del partido (el OCR a veces omite la sigla).
PATRONES = [(r"FUERZA\s*POPULAR", "FP"), (r"JUNTOS\s*POR", "JP"), (r"BUEN\s*GOB", "PBG"),
            (r"RENOVA", "RP"), (r"C[IÍ]VICO|OBRAS", "PCO"), (r"AHORA\s*NACI", "AN")]
ASIS_COLS = ["pre", "aus", "lic", "sus", "otr"]
VOTO_COLS = ["si", "no", "abst", "sinres"]
TOTALES = {"PRESENTE": "pre", "AUSENTE": "aus", "A FAVOR": "si", "EN CONTRA": "no", "ABSTENCI": "abst",
           "SIN RESPUESTA": "sinres"}


def tokens(items):
    """Parte cada fragmento en palabras con su x aproximada (proporcional a la posición del carácter)."""
    salida = []
    for it in items:
        texto, x, y = it[0], it[1], it[2]
        ancho = it[3] if len(it) > 3 else 0.6 * len(texto) / 120
        for m in re.finditer(r"\S+", texto):
            cx = x + ancho * (m.start() + len(m.group()) / 2) / max(len(texto), 1)
            salida.append((m.group(), cx, y))
    return salida


def renglones(toks, tol):
    filas = []
    for t in sorted(toks, key=lambda t: t[2]):
        if filas and abs(t[2] - filas[-1][0][2]) <= tol:
            filas[-1].append(t)
        else:
            filas.append([t])
    return [sorted(f, key=lambda t: t[1]) for f in filas]


def leer_resumen(items, tipo, tol):
    toks = tokens(items)
    filas = renglones(toks, tol)
    i_cab = next((i for i, f in enumerate(filas) if any(re.match(r"(?i)grupo", t[0]) for t in f)), None)
    if i_cab is None:
        return None
    cab = filas[i_cab]
    filas = filas[i_cab:]  # solo la tabla de totales, no la lista de nombres de arriba
    # x de cada columna según la cabecera
    claves = ["PRESENT", "AUSENT", "LICENC", "SUPS", "OTROS"] if tipo == "ASISTENCIA" else ["SI+", "NO-", "ABST", "SIN"]
    cols = []
    for k in claves:
        cand = [t for t in cab if t[0].upper().startswith(k) or (k == "SIN" and t[0].upper() == "SIN")]
        if not cand and k in ("SI+", "NO-"):
            cand = [t for t in cab if t[0].upper().startswith(k[:2])]
        if not cand:
            return None
        cols.append(cand[-1][1] if k != "SIN" else cand[0][1])
    nombres = ASIS_COLS if tipo == "ASISTENCIA" else VOTO_COLS
    bancadas, totales, pos = {}, {}, {"cols": cols, "filas": {}, "totales": {}}
    for f in filas:
        txt = " ".join(t[0] for t in f).upper()
        for etiqueta, clave in TOTALES.items():
            m = re.search(re.escape(etiqueta) + r"[^0-9]{0,20}?(\d+)", txt)
            if etiqueta in txt and clave not in pos["totales"]:
                et = next((t for t in f if t[0].upper().startswith(etiqueta.split()[0])), f[0])
                pos["totales"][clave] = (et[1], f[0][2])
            if m and clave not in totales and not txt.startswith(("ASISTENCIA PARA",)):
                totales[clave] = int(m.group(1))
        cod = next((c for patron, c in PATRONES if re.search(patron, txt)), None)
        if not cod or cod in bancadas:
            continue
        # Números a la derecha del nombre del partido
        fin_nombre = max(t[1] for t in f if re.search(r"[A-ZÁÉÍÓÚ]{2,}", t[0].upper()) and not t[0].isdigit()
                         and t[1] > 0.3)
        nums = [t for t in f if re.fullmatch(r"\d+", t[0]) and t[1] > fin_nombre]
        if len(nums) == len(cols):  # fila completa: se asigna por orden de columna
            fila = {nombres[j]: int(t[0]) for j, t in enumerate(nums)}
        else:                       # faltan celdas (el OCR omitió algún 0): se asigna por posición
            fila = {}
            for t in nums:
                j = min(range(len(cols)), key=lambda j: abs(cols[j] - t[1]))
                if abs(cols[j] - t[1]) < 0.05 and nombres[j] not in fila:
                    fila[nombres[j]] = int(t[0])
        bancadas[cod] = fila
        pos["filas"][cod] = f[0][2]
    return bancadas, totales, pos


def completar_celdas(imagen, bancadas, totales, pos, tipo):
    """Segundo intento en escaneos: relee, ampliadas, solo las celdas que faltan."""
    import ocr
    nombres = ASIS_COLS if tipo == "ASISTENCIA" else VOTO_COLS
    leer = lambda x0, y, x1: next((int(d) for d in re.findall(r"\d+", ocr.ocr_recorte(imagen, x0, max(y - 0.005, 0), x1, y + 0.013).replace("O", "0"))), None)
    for cod, y in pos["filas"].items():
        for j, n in enumerate(nombres):
            if n not in bancadas[cod]:
                v = leer(pos["cols"][j] - 0.03, y, pos["cols"][j] + 0.035)
                if v is not None:
                    bancadas[cod][n] = v
    for clave, (x, y) in pos["totales"].items():
        if clave not in totales:
            v = leer(0.2, y, 0.34)
            if v is not None:
                totales[clave] = v
    return bancadas, totales


def validar(bancadas, totales, tipo, miembros):
    """Completa con 0 las celdas vacías solo si las sumas de control cuadran."""
    if not bancadas or len(bancadas) < len(miembros):
        return None
    nombres = ASIS_COLS if tipo == "ASISTENCIA" else VOTO_COLS
    llenas = {b: {n: f.get(n, 0) for n in nombres} for b, f in bancadas.items()}
    claves = ["pre"] if tipo == "ASISTENCIA" else ["si", "no", "abst"]
    for k in claves:
        if sum(f[k] for f in llenas.values()) != totales.get(k, 0 if k != "pre" and k != "si" else -1):
            return None
    for b, f in llenas.items():  # nadie puede sumar más que los miembros de su bancada
        if sum(f.values()) > miembros.get(b, 999):
            return None
    return llenas


def main():
    congresistas = json.loads((BASE / "congresistas.json").read_text())
    eventos = json.loads((BASE / "votaciones" / "eventos.json").read_text())
    vistos = {(e["pdf"], e["pagina"]): e for e in eventos}
    miembros = {"D": {"FP": 41, "JP": 32, "PBG": 18, "RP": 15, "PCO": 14, "AN": 10},
                "S": {"FP": 22, "JP": 14, "RP": 8, "PBG": 7, "PCO": 5, "AN": 4}}
    import ocr
    # Las tablas ya leídas y validadas se reutilizan; solo se procesan páginas nuevas.
    archivo = BASE / "votaciones" / "totales_bancadas.json"
    previas = {(r.get("pdf"), r.get("pagina")): r for r in (json.loads(archivo.read_text()) if archivo.exists() else [])}
    archivo_desc = BASE / "votaciones" / "totales_descartados.json"
    ya_descartadas = {tuple(d[:2]) for d in (json.loads(archivo_desc.read_text()) if archivo_desc.exists() else [])}
    resumenes, descartes = [], []
    for (pdf, n), e in sorted(vistos.items()):
        if (pdf, n) in ya_descartadas:  # ya se intentó y no cuadró; borrar el archivo para reintentar
            descartes.append((pdf, n, "no cuadra (intento previo)"))
            continue
        if (pdf, n) in previas:
            resumenes.append(dict(previas[(pdf, n)], votos_cusco=e["votos"]))
            continue
        items, tol, imagen = vot.paginas_de(vot.PDFS / pdf)[n - 1]
        if imagen is not None:  # escaneado: se relee la franja de totales, ampliada
            ys = [y for t, x, y in items if re.search(r"(?i)grupo|resultado|kesu", t)]
            if not ys:
                descartes.append((pdf, n, "sin tabla")); continue
            items, tol = ocr.ocr_zona(imagen, max(min(ys) - 0.012, 0), min(min(ys) + 0.16, 1)), 0.006
        leido = leer_resumen(items, e["tipo"], tol)
        ok = validar(*leido[:2], e["tipo"], miembros[e["camara"]]) if leido else None
        if ok is None and leido and imagen is not None:
            ok = validar(*completar_celdas(imagen, *leido, e["tipo"]), e["tipo"], miembros[e["camara"]])
        if ok is None:
            descartes.append((pdf, n, "no cuadra"))
            continue
        resumenes.append({"pdf": pdf, "pagina": n, "camara": e["camara"], "fecha": e["fecha"], "hora": e["hora"], "tipo": e["tipo"],
                          "bancadas": ok, "votos_cusco": e["votos"]})
    archivo_desc.write_text(json.dumps(descartes, ensure_ascii=False, indent=1))
    print(f"Tablas válidas: {len(resumenes)} de {len(vistos)}; descartadas: {len(descartes)}")
    for d in descartes:
        if "previo" not in d[2]:
            print("  descartada", *d)
    (BASE / "votaciones" / "totales_bancadas.json").write_text(json.dumps(resumenes, ensure_ascii=False, indent=1))
    contexto = calcular(resumenes, congresistas, miembros, len(vistos))
    (BASE / "datos" / "contexto.json").write_text(json.dumps(contexto, ensure_ascii=False, indent=1))
    for cid, c in contexto["congresistas"].items():
        print(cid, c)
    print(contexto["camaras"])


def palabras_por_orador():
    """Palabras de cada orador (sin contar a quien preside) en el Diario de Debates, por cámara."""
    conteo = {"D": defaultdict(int), "S": defaultdict(int)}
    # Solo cuentan los congresistas (no ministros ni invitados): se cruza con el padrón de cada cámara.
    padron = {c: {" ".join(itv.sin_tildes(n.split(",")[0]).split()[:2]) for _, n in vot.Padron(c).nombres} for c in "DS"}
    for pdf in sorted(itv.PDFS.glob("*.pdf")):
        texto, _, _ = itv.leer_sesion(pdf)
        turnos = list(itv.TURNO.finditer(texto))
        for i, t in enumerate(turnos):
            quien = itv.sin_tildes(t.group(2)).strip()
            if quien.startswith(("PRESIDENT", "VICEPRESIDENT", "RELATOR", "SECRETARI")) or len(quien) < 5:
                continue
            fin = turnos[i + 1].start() if i + 1 < len(turnos) else len(texto)
            cuerpo = texto[t.end():fin]
            corte = itv.ACOTACION.search(cuerpo)
            clave = " ".join(re.sub(r"[^A-Z ]", "", quien).split()[:2])
            if clave not in padron[pdf.name[0]]:
                continue
            conteo[pdf.name[0]][clave] += len(re.sub(r"<<PAG \d+>>", " ", cuerpo[:corte.start()] if corte else cuerpo).split())
    return conteo


def calcular(resumenes, congresistas, miembros, total_paginas):
    total = {c: sum(m.values()) for c, m in miembros.items()}
    sal = {"camaras": {}, "bancadas": {}, "congresistas": {}, "cobertura": {"validas": len(resumenes), "total": total_paginas}}
    for cam in ("D", "S"):
        asis = [r for r in resumenes if r["camara"] == cam and r["tipo"] == "ASISTENCIA"]
        vots = [r for r in resumenes if r["camara"] == cam and r["tipo"] == "VOTACIÓN"]
        pres = sum(f["pre"] for r in asis for f in r["bancadas"].values())
        emit = sum(f["si"] + f["no"] + f["abst"] for r in vots for f in r["bancadas"].values())
        cohes_num = sum(max(f["si"], f["no"], f["abst"]) for r in vots for f in r["bancadas"].values())
        cohes_den = sum(f["si"] + f["no"] + f["abst"] for r in vots for f in r["bancadas"].values())
        sal["camaras"][cam] = {"pases": len(asis), "votaciones": len(vots),
                               "asistencia": round(100 * pres / (total[cam] * len(asis)), 1) if asis else None,
                               "participacion": round(100 * emit / ((total[cam] - 1) * len(vots)), 1) if vots else None,
                               "con_su_bancada": round(100 * cohes_num / cohes_den, 1) if cohes_den else None}
        for b, m in miembros[cam].items():
            pb = sum(r["bancadas"][b]["pre"] for r in asis)
            cn = sum(max(r["bancadas"][b]["si"], r["bancadas"][b]["no"], r["bancadas"][b]["abst"]) for r in vots)
            cd = sum(r["bancadas"][b]["si"] + r["bancadas"][b]["no"] + r["bancadas"][b]["abst"] for r in vots)
            sal["bancadas"][f"{cam}-{b}"] = {"asistencia": round(100 * pb / (m * len(asis)), 1) if asis else None,
                                             "con_su_bancada": round(100 * cn / cd, 1) if cd else None}
    habla = palabras_por_orador()
    for c in congresistas:
        cid, cam = str(c["id"]), c["camara"]
        b = PARTIDO_A_CODIGO[c["partido"]]
        asis = [r for r in resumenes if r["camara"] == cam and r["tipo"] == "ASISTENCIA"]
        vots = [r for r in resumenes if r["camara"] == cam and r["tipo"] == "VOTACIÓN"]
        presente = sum(1 for r in asis if r["votos_cusco"].get(cid) in ("PRE", "***"))
        votables = [r for r in vots if r["votos_cusco"].get(cid) != "***"]
        emitidos = [r for r in votables if r["votos_cusco"].get(cid) in ("SI", "NO", "ABST")]
        coinc, comp, distinto = 0, 0, []
        for r in emitidos:
            f = r["bancadas"][b]
            cuenta = {"SI": f["si"], "NO": f["no"], "ABST": f["abst"]}
            orden = sorted(cuenta.values(), reverse=True)
            if orden[0] == orden[1]:
                continue  # bancada empatada: no hay posición mayoritaria
            mayor = max(cuenta, key=cuenta.get)
            comp += 1
            if r["votos_cusco"][cid] == mayor:
                coinc += 1
            else:
                distinto.append({"fecha": r["fecha"], "hora": r["hora"], "voto": r["votos_cusco"][cid], "bancada": mayor})
        sapiens = itv.sin_tildes(c["nombre"].split(",")[0])
        ranking = sorted(habla[cam].items(), key=lambda kv: -kv[1])
        mias = habla[cam].get(" ".join(sapiens.split()[:2]), 0)
        puesto = 1 + sum(1 for k, v in ranking if v > mias)
        sal["congresistas"][cid] = {
            "bancada": b, "pases": len(asis), "presente": presente,
            "asistencia": round(100 * presente / len(asis), 1) if asis else None,
            "votaciones": len(votables), "participo": len(emitidos),
            "participacion": round(100 * len(emitidos) / len(votables), 1) if votables else None,
            "comparables": comp, "con_su_bancada": round(100 * coinc / comp, 1) if comp else None,
            "distinto": distinto,
            "palabras": mias, "puesto_palabras": puesto if mias else None,
            "promedio_palabras": round(sum(habla[cam].values()) / total[cam]),
            "oradores": len(habla[cam]), "miembros": total[cam],
        }
    return sal


if __name__ == "__main__":
    main()
