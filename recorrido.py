#!/usr/bin/env python3
"""Recorrido de los proyectos de ley: hasta qué etapa llegó cada proyecto del período.

Toma el estado actual de TODOS los proyectos presentados por congresistas (listado completo que descarga
redes.py) y los agrupa en etapas. Compara los proyectos de cada cusqueño como autor principal con los de toda
su cámara, para no juzgar como lentitud propia lo que es el ritmo general del Congreso.

Uso:  python3 recorrido.py   → datos/recorrido.json   (después de redes.py)
"""
import json
from collections import Counter
from datetime import date
from pathlib import Path
from statistics import median

from redes import clave

BASE = Path(__file__).resolve().parent
# Estado del sistema → etapa. "Archivado de plano" y "Retirado por su autor" salen del camino.
ETAPAS = ["Presentado", "En comisión", "Con dictamen", "Aprobado en el Pleno", "Ley publicada", "Archivado o retirado"]
ESTADO_A_ETAPA = {
    "PRESENTADO": 0, "ACTUALIZADA": 0,
    "EN COMISIÓN": 1,
    "CON DICTAMEN": 2, "EN AGENDA DEL PLENO": 2,
    "APROBADO": 3, "EXPEDIENTE DE PROPUESTA LEGISLATIVA REMITIDA AL SENADO DE LA REPÚBLICA": 3, "AUTÓGRAFA": 3,
    "PUBLICADA EN EL DIARIO OFICIAL EL PERUANO": 4,
    "ARCHIVADO DE PLANO": 5, "RETIRADO POR SU AUTOR": 5, "AL ARCHIVO": 5, "DECRETO DE ARCHIVO": 5,
}


def etapa(estado):
    e = (estado or "").strip().upper()
    if e in ESTADO_A_ETAPA:
        return ESTADO_A_ETAPA[e]
    if "ARCHIV" in e or "RETIRAD" in e:
        return 5
    if "PUBLICAD" in e or "LEY N" in e:
        return 4
    if "APROBAD" in e or "AUTÓGRAFA" in e or "REMITID" in e:
        return 3
    if "DICTAMEN" in e or "AGENDA" in e:
        return 2
    print("  estado sin etapa conocida (se cuenta como 'En comisión'):", estado)
    return 1


def main():
    congresistas = json.loads((BASE / "congresistas.json").read_text())
    todos = json.loads((BASE / "datos" / "cache" / "todos_proyectos.json").read_text())
    hoy = date.today()
    salida = {"etapas": ETAPAS, "camaras": {}, "congresistas": {}}
    por_camara = {"D": [], "S": []}
    por_autor = {str(c["id"]): [] for c in congresistas}
    claves = {clave(c["nombre"]): str(c["id"]) for c in congresistas}
    for p in todos.values():
        autores = [a.strip() for a in (p.get("autores") or "").split(";") if a.strip()]
        if not autores:  # proyectos del Ejecutivo, de instituciones o "actualizaciones" sin firmantes
            continue
        fila = {"numero": p["proyectoLey"], "titulo": p["titulo"], "estado": p["desEstado"], "etapa": etapa(p["desEstado"]),
                "dias": (hoy - date.fromisoformat(p["fecPresentacion"][:10])).days}
        por_camara[p["codTipoParl"]].append(fila)
        autor = claves.get(clave(autores[0]))
        if autor:
            por_autor[autor].append(fila)
        for a in autores[1:]:
            if clave(a) in claves:
                por_autor.setdefault(claves[clave(a)] + "-co", []).append(fila)

    def resumen(filas):
        cuenta = Counter(f["etapa"] for f in filas)
        en_comision = [f["dias"] for f in filas if f["etapa"] in (0, 1)]
        return {"total": len(filas), "por_etapa": [cuenta.get(k, 0) for k in range(len(ETAPAS))],
                "dictamen_o_mas": sum(cuenta.get(k, 0) for k in (2, 3, 4)),
                "dias_esperando_mediana": round(median(en_comision)) if en_comision else None}

    # Cuántos proyectos firma cada congresista de la cámara como autor y como coautor (para la mediana)
    firmas = {"D": {}, "S": {}}
    for p in todos.values():
        autores = [clave(a) for a in (p.get("autores") or "").split(";") if a.strip()]
        for k, a in enumerate(autores):
            f = firmas[p["codTipoParl"]].setdefault(a, [0, 0])
            f[0 if k == 0 else 1] += 1
    for cam, filas in por_camara.items():
        salida["camaras"][cam] = resumen(filas)
        vals = list(firmas[cam].values())
        if vals:
            salida["camaras"][cam].update(firmantes=len(vals), mediana_propios=median(v[0] for v in vals),
                                          mediana_coautor=median(v[1] for v in vals),
                                          max_propios=max(v[0] for v in vals), max_coautor=max(v[1] for v in vals))
    for c in congresistas:
        i = str(c["id"])
        avanzados = sorted((f for f in por_autor[i] if f["etapa"] in (2, 3, 4)), key=lambda f: -f["etapa"])
        salida["congresistas"][i] = {**resumen(por_autor[i]), "coautor": resumen(por_autor.get(i + "-co", [])),
                                     "avanzados": [{k: f[k] for k in ("numero", "titulo", "estado")} for f in avanzados],
                                     "proyectos": [{k: f[k] for k in ("numero", "titulo", "estado", "etapa", "dias")}
                                                   for f in sorted(por_autor[i], key=lambda f: (-f["etapa"] if f["etapa"] < 5 else 1, f["numero"]))]}
    (BASE / "datos" / "recorrido.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1))
    for cam, r in salida["camaras"].items():
        print(f"{cam}: {r['total']} proyectos de congresistas · por etapa {r['por_etapa']} · mediana de días esperando {r['dias_esperando_mediana']}")
    for c in congresistas:
        r = salida["congresistas"][str(c["id"])]
        print(f"  {c['corto']}: {r['total']} como autor {r['por_etapa']} · coautor {r['coautor']['total']} {r['coautor']['por_etapa']}")


if __name__ == "__main__":
    main()
