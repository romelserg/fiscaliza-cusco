#!/usr/bin/env python3
"""Análisis de redes (SNA) de los congresistas de Cusco, en el contexto de toda su cámara.

1. Coautoría: red de TODOS los congresistas de la cámara. Vínculo = proyectos de ley firmados juntos
   (autor o coautor). Así los indicadores de cada cusqueño se comparan con los de sus 129 colegas, y la
   intermediación (quién conecta grupos que no firman entre sí) se mide sobre la red real, no recortada.
   Comunidades: algoritmo de Louvain (grupos que firman más entre sí que con el resto).
2. Votación: con la votación nominal validada (nominal.py) se calcula, para cada par de congresistas,
   el porcentaje de votaciones en que votaron igual. De esa matriz salen: el mapa de votación (escalamiento
   multidimensional: quien vota parecido queda cerca), la lealtad de cada cusqueño a su bancada comparada
   con la de sus compañeros de bancada, y los colegas con los que más coincide.

Uso:  python3 redes.py   → datos/redes.json   (requiere networkx, numpy y scikit-learn)
"""
import json
import re
import time
import unicodedata
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import networkx as nx
import numpy as np
import pypdf

BASE = Path(__file__).resolve().parent
API = "https://api.congreso.gob.pe/spley-portal-service"
# Actas con texto digital donde figura cada congresista con su bancada
# Actas de las que se lee la bancada de cada congresista. El Congreso cambia el nombre del archivo cuando
# reemplaza la versión provisional por la final, así que se buscan por patrón y se prefiere la final.
ACTAS_PADRON = {"D": "D_ASISTENCIA-PLENO-DIPUTADOS-20261006*.pdf",
                "S": "S_Asistencias_y_votaciones*sesion_del_7_10_2026*.pdf"}
CODIGO = {"Ahora Nación": "AN", "Juntos por el Perú": "JP", "Partido del Buen Gobierno": "PBG",
          "Partido Cívico Obras": "PCO", "Fuerza Popular": "FP", "Renovación Popular": "RP"}
ANCHO, ALTO = 960, 720
RADIO = 108  # radio del círculo de la bancada más grande
MIN_COMUNES = 8  # votaciones en común mínimas para comparar a dos congresistas (y para entrar al mapa)


def clave(nombre):
    """'Manrique Olivera, Bernardino' y 'MANRIQUE OLIVERA, BERNARDINO' → 'MANRIQUE OLIVERA'."""
    t = unicodedata.normalize("NFKD", nombre.split(",")[0].upper())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def bancadas():
    salida = {}
    for camara, patron in ACTAS_PADRON.items():
        actas = sorted((BASE / "votaciones" / "pdfs").glob(patron), key=lambda a: "PROVISIONAL" in a.name)
        if not actas:
            raise SystemExit(f"redes.py: no se encontró el acta {patron} en votaciones/pdfs")
        texto = "\n".join(pg.extract_text(extraction_mode="layout") for pg in pypdf.PdfReader(str(actas[0])).pages[:4])
        # El nombre no cruza columnas: termina en coma o en un hueco de 2+ espacios (apellidos compuestos
        # que no caben en la celda, como "ANDRADE SALGUERO DE", quedan sin coma).
        for b, nombre in re.findall(r"\b(FP|JP|PBG|RP|PCO|AN) +([A-ZÁÉÍÓÚÑÜ\-]+(?: [A-ZÁÉÍÓÚÑÜ\-]+)*)(?=,| {2,}|$)", texto, re.M):
            salida.setdefault(clave(nombre), b)
    return salida


def buscar_bancada(nombre, banc):
    k = clave(nombre)
    if k in banc:
        return banc[k]
    # Apellidos compuestos ("Andrade Salguero de Álvarez"): el acta corta el nombre antes.
    candidatos = {b for kk, b in banc.items() if k.startswith(kk) or kk.startswith(k)}
    return candidatos.pop() if len(candidatos) == 1 else None


def todos_los_proyectos():
    """Listado completo del período (ambas cámaras), con los firmantes en orden: el primero es el autor."""
    from extraer_proyectos import PERIODO, http_json
    cache = BASE / "datos" / "cache" / "todos_proyectos.json"
    todo = {}
    for cam in "DS":
        fila = 0
        while True:
            d = http_json(f"{API}/proyecto-ley/lista-con-filtro",
                          {"perParId": PERIODO, "codTipoParl": cam, "pageSize": 100, "rowStart": fila})
            ps = d.get("proyectos") or []
            for p in ps:
                todo[f'{cam}-{p["pleyNum"]}'] = p
            fila += len(ps)
            if not ps or fila >= (d.get("rowsTotal") or 0):
                break
            time.sleep(0.5)
    cache.parent.mkdir(exist_ok=True)
    cache.write_text(json.dumps(todo, ensure_ascii=False))
    return todo


def padron(camara, banc):
    from votaciones import Padron
    return {str(i): {"nombre": n, "bancada": buscar_bancada(n, banc)} for i, n in Padron(camara).nombres}


def rango(valores, clave_):
    """Puesto (1 = el más alto) de clave_ entre los valores."""
    return 1 + sum(1 for v in valores.values() if v > valores[clave_])


def acomodar(g, x0, y0, ancho, alto, semilla=7):
    """Disposición por fuerzas (más firmas juntos → más cerca), escalada al rectángulo dado."""
    if len(g) == 1:
        return {n: (x0 + ancho / 2, y0 + alto / 2) for n in g}
    pos = nx.spring_layout(g, weight="peso", k=1.6 / np.sqrt(len(g)), iterations=300, seed=semilla)
    xs, ys = np.array([p[0] for p in pos.values()]), np.array([p[1] for p in pos.values()])
    return {n: (round(x0 + (x - xs.min()) / ((xs.max() - xs.min()) or 1) * ancho, 1),
                round(y0 + (y - ys.min()) / ((ys.max() - ys.min()) or 1) * alto, 1)) for n, (x, y) in pos.items()}


def red_coautoria(camara, proyectos, miembros, cusquenos):
    por_nombre = {clave(m["nombre"]): i for i, m in miembros.items()}
    g = nx.Graph()
    lidera, firmas_reunidas = Counter(), Counter()
    sin_id = Counter()
    for p in proyectos.values():
        if p["codTipoParl"] != camara or not p.get("autores"):
            continue
        firmantes = []
        for nombre in (x.strip() for x in p["autores"].split(";")):
            i = por_nombre.get(clave(nombre)) or next((j for k, j in por_nombre.items() if k.startswith(clave(nombre)) or clave(nombre).startswith(k)), None)
            if i is None:
                sin_id[nombre] += 1
            elif i not in firmantes:
                firmantes.append(i)
        if not firmantes:
            continue
        lidera[firmantes[0]] += 1
        firmas_reunidas[firmantes[0]] += len(firmantes) - 1
        for i in firmantes:
            g.add_node(i)
        for a, b in combinations(firmantes, 2):
            g.add_edge(a, b, peso=g.get_edge_data(a, b, {"peso": 0})["peso"] + 1)
    if sin_id:
        print(f"  {camara}: firmantes sin identificar → {dict(sin_id)}")
    for i in g:
        g.nodes[i].update(nombre=miembros[i]["nombre"], bancada=miembros[i]["bancada"])
    for _, _, d in g.edges(data=True):
        d["distancia"] = 1 / d["peso"]

    # Indicadores de toda la cámara
    grado = dict(g.degree())
    fuerza = dict(g.degree(weight="peso"))
    inter = nx.betweenness_centrality(g, weight="distancia")
    fuera = {}
    for i in g:
        total = sum(d["peso"] for _, _, d in g.edges(i, data=True))
        otras = sum(d["peso"] for _, j, d in g.edges(i, data=True) if g.nodes[j]["bancada"] != g.nodes[i]["bancada"])
        fuera[i] = round(100 * otras / total, 1) if total else None
    comunidades = nx.community.louvain_communities(g, weight="peso", seed=11, resolution=1.0) if len(g) > 2 else [set(g)]
    comunidades = sorted(comunidades, key=len, reverse=True)
    comunidad = {i: k for k, c in enumerate(comunidades) for i in c}
    modularidad = nx.community.modularity(g, comunidades, weight="peso") if len(comunidades) > 1 else 0
    # Modularidad de la partición por bancadas: cuánto explican las bancadas la red
    por_banc = defaultdict(set)
    for i in g:
        por_banc[g.nodes[i]["bancada"]].add(i)
    mod_bancadas = nx.community.modularity(g, list(por_banc.values()), weight="peso") if len(por_banc) > 1 else 0

    # Disposición agrupada: casi nadie firma con otras bancadas, así que una disposición por fuerzas de toda la
    # cámara deja seis manchas diminutas en un lienzo vacío. Cada bancada ocupa un círculo (área proporcional a
    # sus miembros), acomodado por fuerzas por dentro; las líneas entre círculos son los vínculos entre bancadas.
    posicion = {}
    orden = [b for b in ("FP", "RP", "PCO", "AN", "JP", "PBG") if por_banc.get(b)] + [b for b in por_banc if b not in CODIGO.values()]
    mayor = max(len(por_banc[b]) for b in orden)
    for k, b in enumerate(orden):
        ang = -np.pi / 2 + 2 * np.pi * k / len(orden)
        cx, cy = ANCHO / 2 + 0.36 * ANCHO * np.cos(ang), ALTO / 2 + 0.34 * ALTO * np.sin(ang)
        radio = RADIO * np.sqrt(len(por_banc[b]) / mayor) + 12
        sub = g.subgraph(por_banc[b])
        if len(sub) == 1:
            pos = {next(iter(sub)): np.zeros(2)}
        else:
            pos = nx.spring_layout(sub, weight="peso", k=1.2 / np.sqrt(len(sub)), iterations=400, seed=5)
        xy = np.array(list(pos.values()), dtype=float)
        xy -= np.median(xy, axis=0)
        # Distancia al centro reemplazada por su rango: el disco se llena parejo (sin núcleo apretado ni
        # hojas sueltas en el borde) y se conserva la dirección, que es lo que agrupa a los que firman juntos.
        dist = np.hypot(xy[:, 0], xy[:, 1])
        ang_n = np.arctan2(xy[:, 1], xy[:, 0])
        rango_ = np.argsort(np.argsort(dist))
        r_n = np.sqrt((rango_ + 0.5) / len(dist)) * radio if len(dist) > 1 else np.zeros(1)
        for n_, rr, aa in zip(pos, r_n, ang_n):
            posicion[n_] = (round(cx + rr * np.cos(aa), 1), round(cy + rr * np.sin(aa), 1))
    grupos = [{"bancada": b, "miembros": len(por_banc[b]),
               "x": round(ANCHO / 2 + 0.36 * ANCHO * np.cos(-np.pi / 2 + 2 * np.pi * k / len(orden)), 1),
               "y": round(ALTO / 2 + 0.34 * ALTO * np.sin(-np.pi / 2 + 2 * np.pi * k / len(orden)), 1),
               "r": round(RADIO * np.sqrt(len(por_banc[b]) / mayor) + 12, 1)} for k, b in enumerate(orden)]

    nodos = [{"id": i, "nombre": d["nombre"].split(",")[0], "completo": d["nombre"], "bancada": d["bancada"],
              "cusco": i in cusquenos, "x": posicion[i][0], "y": posicion[i][1], "grado": grado[i],
              "fuerza": fuerza[i], "comunidad": comunidad[i], "inter": round(inter[i], 4), "fuera": fuera[i],
              "propios": lidera[i], "firmas_prom": round(firmas_reunidas[i] / lidera[i], 1) if lidera[i] else None}
             for i, d in g.nodes(data=True)]
    aristas = [{"a": a, "b": b, "peso": d["peso"]} for a, b, d in g.edges(data=True)]

    composicion = []
    for k, c in enumerate(comunidades):
        cuenta = Counter(g.nodes[i]["bancada"] for i in c)
        composicion.append({"id": k, "tamano": len(c), "bancadas": dict(cuenta.most_common()),
                            "cusquenos": [i for i in c if i in cusquenos]})

    n_lider = [lidera[i] for i in g]
    con_firmas = {i: firmas_reunidas[i] / lidera[i] for i in g if lidera[i]}
    metricas = {}
    for c in cusquenos:
        if c not in g:
            continue
        vecinos = sorted(g[c], key=lambda v: -g[c][v]["peso"])
        metricas[c] = {
            "coautores": grado[c], "puesto_coautores": rango(grado, c),
            "firmas_compartidas": fuerza[c],
            "intermediacion": round(inter[c], 3), "puesto_intermediacion": rango(inter, c),
            "fuera_de_bancada": fuera[c], "mediana_fuera_camara": round(float(np.median([v for v in fuera.values() if v is not None])), 1),
            "puesto_fuera": rango({k: v for k, v in fuera.items() if v is not None}, c) if fuera[c] is not None else None,
            "bancadas": sorted({g.nodes[v]["bancada"] for v in vecinos if g.nodes[v]["bancada"]}),
            "socios": [{"id": v, "nombre": g.nodes[v]["nombre"], "bancada": g.nodes[v]["bancada"], "peso": g[c][v]["peso"]} for v in vecinos[:5]],
            "proyectos_propios": lidera[c], "mediana_propios_camara": float(np.median(n_lider)),
            "firmas_por_proyecto": round(con_firmas[c], 1) if c in con_firmas else None,
            "mediana_firmas_camara": round(float(np.median(list(con_firmas.values()))), 1) if con_firmas else None,
            "comunidad": comunidad[c],
            "cusquenos_vinculados": [v for v in vecinos if v in cusquenos],
        }
    # Firmas cruzadas entre bancadas (cada proyecto firmado juntos cuenta una vez por par)
    entre = Counter()
    for a, b, d in g.edges(data=True):
        ba, bb = sorted([g.nodes[a]["bancada"] or "?", g.nodes[b]["bancada"] or "?"])
        entre[f"{ba}-{bb}"] += d["peso"]
    return {"nodos": nodos, "aristas": aristas, "metricas": metricas, "comunidades": composicion, "grupos": grupos,
            "modularidad": round(modularidad, 3), "modularidad_bancadas": round(mod_bancadas, 3),
            "miembros_camara": len(miembros), "sin_proyectos": len(miembros) - len(g),
            "proyectos": sum(lidera.values()), "entre_bancadas": dict(entre),
            "mediana_coautores": float(np.median(list(grado.values()))), "ancho": ANCHO, "alto": ALTO}


def red_votacion(camara, nominal, miembros, cusquenos):
    votos = [v for v in nominal if v["camara"] == camara]
    validos = ("SI", "NO", "ABST")
    ids = [i for i in miembros if sum(1 for v in votos if v["votos"].get(i) in validos) >= MIN_COMUNES]
    n = len(ids)
    igual, comunes = np.zeros((n, n)), np.zeros((n, n))
    for v in votos:
        fila = np.array([v["votos"].get(i, "") for i in ids])
        ok = np.isin(fila, validos)
        comunes += np.outer(ok, ok)
        igual += np.outer(ok, ok) * (fila[:, None] == fila[None, :])
    with np.errstate(invalid="ignore", divide="ignore"):
        acuerdo = np.where(comunes >= MIN_COMUNES, igual / comunes, np.nan)
    # Mapa de votación: escalamiento multidimensional sobre la disimilitud (1 − acuerdo)
    from sklearn.manifold import MDS
    dis = 1 - np.nan_to_num(acuerdo, nan=np.nanmean(acuerdo))
    np.fill_diagonal(dis, 0)
    xy = MDS(n_components=2, dissimilarity="precomputed", random_state=3, n_init=8, normalized_stress="auto").fit_transform(dis)
    # Orientación estable: Fuerza Popular (la bancada más grande) a la derecha
    fp = [k for k, i in enumerate(ids) if miembros[i]["bancada"] == "FP"]
    if fp and xy[fp, 0].mean() < 0:
        xy[:, 0] *= -1
    rx, ry = np.ptp(xy[:, 0]) or 1, np.ptp(xy[:, 1]) or 1
    W, H = 620, 460
    escala = min((W - 60) / rx, (H - 60) / ry)
    cx, cy = xy[:, 0].mean(), xy[:, 1].mean()
    puntos = [{"id": i, "nombre": miembros[i]["nombre"].split(",")[0], "bancada": miembros[i]["bancada"], "cusco": i in cusquenos,
               "x": W / 2 + (xy[k, 0] - cx) * escala, "y": H / 2 + (xy[k, 1] - cy) * escala} for k, i in enumerate(ids)]
    # Quienes votaron exactamente igual caen en el mismo punto: se reparten en un racimo (girasol) alrededor de él
    racimos = []
    for pt in puntos:
        r = next((r for r in racimos if abs(r[0]["x"] - pt["x"]) < 3 and abs(r[0]["y"] - pt["y"]) < 3), None)
        r.append(pt) if r else racimos.append([pt])
    for r in racimos:
        x0, y0 = r[0]["x"], r[0]["y"]
        for k, pt in enumerate(sorted(r, key=lambda q: (q["bancada"] or "", q["nombre"]))):
            radio, ang = 6.2 * np.sqrt(k), k * 2.39996
            pt["x"], pt["y"] = round(x0 + radio * np.cos(ang), 1), round(y0 + radio * np.sin(ang), 1)
            pt["grupo"] = len(r)

    # Lealtad: % de votaciones en que votó como la mayoría de su bancada (sin contarse a sí mismo)
    def lealtad(i):
        b = miembros[i]["bancada"]
        si = tot = 0
        for v in votos:
            mio = v["votos"].get(i)
            if mio not in validos:
                continue
            cuenta = Counter(x for j, x in v["votos"].items() if j != i and miembros.get(j, {}).get("bancada") == b and x in validos)
            if not cuenta:
                continue
            (mayor, k1), *resto = cuenta.most_common()
            if resto and resto[0][1] == k1:
                continue  # bancada empatada
            tot += 1
            si += mio == mayor
        return (round(100 * si / tot, 1), tot) if tot else (None, 0)

    leal = {i: lealtad(i) for i in ids}
    metricas = {}
    for c in cusquenos:
        if c not in ids:
            continue
        k = ids.index(c)
        b = miembros[c]["bancada"]
        companeros = [leal[i][0] for i in ids if miembros[i]["bancada"] == b and i != c and leal[i][0] is not None]
        orden = [j for j in np.argsort(-np.nan_to_num(acuerdo[k], nan=-1)) if ids[j] != c]
        parecidos = [{"id": ids[j], "nombre": miembros[ids[j]]["nombre"], "bancada": miembros[ids[j]]["bancada"],
                      "pct": round(100 * acuerdo[k, j], 1), "comunes": int(comunes[k, j])} for j in orden[:5]]
        por_bancada = {}
        for bb in CODIGO.values():
            js = [j for j, i in enumerate(ids) if miembros[i]["bancada"] == bb and i != c and not np.isnan(acuerdo[k, j])]
            if js:
                por_bancada[bb] = round(100 * float(np.mean(acuerdo[k, js])), 1)
        metricas[c] = {"lealtad": leal[c][0], "votaciones_lealtad": leal[c][1],
                       "lealtad_mediana_bancada": round(float(np.median(companeros)), 1) if companeros else None,
                       "lealtad_minima_bancada": min(companeros) if companeros else None,
                       "puesto_lealtad_bancada": 1 + sum(1 for x in companeros if x > leal[c][0]) if leal[c][0] is not None else None,
                       "tamano_bancada": len(companeros) + 1,
                       "parecidos": parecidos, "acuerdo_por_bancada": por_bancada,
                       "identicos": dict(Counter(miembros[ids[j]]["bancada"] for j in range(n)
                                                 if ids[j] != c and comunes[k, j] >= MIN_COMUNES and igual[k, j] == comunes[k, j]).most_common()),
                       "votaciones": int(comunes[k, k])}
    pares = {}
    for a, b in combinations([c for c in cusquenos if c in ids], 2):
        ka, kb = ids.index(a), ids.index(b)
        if not np.isnan(acuerdo[ka, kb]):
            pares[f"{a}-{b}"] = {"igual": int(igual[ka, kb]), "total": int(comunes[ka, kb]), "pct": round(100 * acuerdo[ka, kb], 1)}
    return {"votaciones": len(votos), "congresistas": len(ids), "puntos": puntos, "ancho": W, "alto": H,
            "metricas": metricas, "pares": pares}


def afinidad_cusquenos(eventos, congresistas):
    """Pares de cusqueños desde eventos.json (votos verificados a mano, todas las votaciones)."""
    dip = [str(c["id"]) for c in congresistas if c["camara"] == "D"]
    votos = [e for e in eventos if e["tipo"] == "VOTACIÓN" and e["camara"] == "D"]
    pares = {}
    for a, b in combinations(dip, 2):
        ambos = [e for e in votos if e["votos"].get(a) in ("SI", "NO", "ABST") and e["votos"].get(b) in ("SI", "NO", "ABST")]
        igual = sum(1 for e in ambos if e["votos"][a] == e["votos"][b])
        pares[f"{a}-{b}"] = {"igual": igual, "total": len(ambos), "pct": round(100 * igual / len(ambos), 1) if ambos else None}
    return pares


def lados(camara, nominal, miembros, cusquenos, a="FP", b="JP", minimo=4):
    """En las votaciones en que la mayoría de la bancada `a` y la de la bancada `b` votaron distinto,
    qué porcentaje de las veces cada congresista votó como `b` (0 = siempre como `a`, 100 = siempre como `b`)."""
    validos = ("SI", "NO", "ABST")
    divididas = []
    for v in (x for x in nominal if x["camara"] == camara):
        may = {}
        for banc in (a, b):
            c = Counter(x for i, x in v["votos"].items() if miembros.get(i, {}).get("bancada") == banc and x in validos)
            if c:
                (voto, n1), *resto = c.most_common()
                if not resto or resto[0][1] < n1:  # mayoría clara
                    may[banc] = voto
        if len(may) == 2 and may[a] != may[b]:
            divididas.append((v, may))
    puntos = []
    for i, m in miembros.items():
        como_a = sum(1 for v, may in divididas if v["votos"].get(i) == may[a])
        como_b = sum(1 for v, may in divididas if v["votos"].get(i) == may[b])
        if como_a + como_b >= minimo:
            puntos.append({"id": i, "nombre": m["nombre"], "bancada": m["bancada"], "cusco": i in cusquenos,
                           "como_a": como_a, "como_b": como_b, "x": round(como_b / (como_a + como_b), 3)})
    return {"a": a, "b": b, "votaciones": len(divididas), "minimo": minimo, "puntos": puntos,
            "asuntos": [{"fecha": v["fecha"], "hora": v["hora"], "asunto": v["asunto"][:200], a: may[a], b: may[b]} for v, may in divididas]}


def posiciones_afinidad(pares, ids):
    """Ubica a los cusqueños en el plano según cuánto coinciden (más coincidencia, más cerca)."""
    from sklearn.manifold import MDS
    n = len(ids)
    dis = np.zeros((n, n))
    for x, y in combinations(range(n), 2):
        d = pares.get(f"{ids[x]}-{ids[y]}") or pares.get(f"{ids[y]}-{ids[x]}")
        bruto = 1 - (d["pct"] / 100 if d and d["pct"] is not None else 0.5)
        # Raíz: separa las diferencias pequeñas (95% vs 100%) sin cambiar el orden; mínimo para no encimar a nadie.
        dis[x, y] = dis[y, x] = max(np.sqrt(bruto), 0.16)
    xy = MDS(n_components=2, dissimilarity="precomputed", random_state=2, n_init=16, normalized_stress="auto").fit_transform(dis)
    xy -= xy.mean(axis=0)
    escala = 180 / (np.abs(xy).max() or 1)
    return {i: (round(float(xy[k, 0] * escala), 1), round(float(xy[k, 1] * escala), 1)) for k, i in enumerate(ids)}


def main():
    congresistas = json.loads((BASE / "congresistas.json").read_text())
    eventos = json.loads((BASE / "votaciones" / "eventos.json").read_text())
    nominal_f = BASE / "votaciones" / "nominal.json"
    nominal = json.loads(nominal_f.read_text()) if nominal_f.exists() else []
    banc = bancadas()
    proyectos = todos_los_proyectos()
    salida = {"coautoria": {}, "votacion": {}, "pares_cusquenos": afinidad_cusquenos(eventos, congresistas)}
    for camara in "DS":
        miembros = padron(camara, banc)
        sin = [m["nombre"] for m in miembros.values() if not m["bancada"]]
        if sin:
            print(f"  {camara}: sin bancada → {sin}")
        cus = {str(c["id"]) for c in congresistas if c["camara"] == camara}
        salida["coautoria"][camara] = red_coautoria(camara, proyectos, miembros, cus)
        if nominal:
            salida["votacion"][camara] = red_votacion(camara, nominal, miembros, cus)
            if camara == "D":
                salida["votacion"][camara]["lados"] = lados(camara, nominal, miembros, cus)
    dip = [str(c["id"]) for c in congresistas if c["camara"] == "D"]
    salida["afinidad_xy"] = posiciones_afinidad(salida["pares_cusquenos"], dip)
    (BASE / "datos" / "redes.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1))

    for camara, co in salida["coautoria"].items():
        print(f'Coautoría {camara}: {len(co["nodos"])} congresistas con proyectos, {len(co["aristas"])} vínculos, '
              f'{len(co["comunidades"])} comunidades (modularidad {co["modularidad"]}; por bancadas {co["modularidad_bancadas"]})')
        for cid, m in co["metricas"].items():
            print("  ", cid, {k: m[k] for k in ("coautores", "puesto_coautores", "intermediacion", "puesto_intermediacion",
                                                "fuera_de_bancada", "mediana_fuera_camara", "proyectos_propios", "firmas_por_proyecto", "comunidad")})
        for c in co["comunidades"][:8]:
            print("   comunidad", c)
    for camara, vo in salida["votacion"].items():
        print(f'Votación {camara}: {vo["votaciones"]} votaciones validadas, {vo["congresistas"]} congresistas')
        for cid, m in vo["metricas"].items():
            print("  ", cid, {k: m[k] for k in ("lealtad", "votaciones_lealtad", "lealtad_mediana_bancada", "puesto_lealtad_bancada", "tamano_bancada")},
                  m["acuerdo_por_bancada"], [(p["nombre"].split(",")[0], p["pct"]) for p in m["parecidos"][:3]])


if __name__ == "__main__":
    main()
