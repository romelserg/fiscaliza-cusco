#!/usr/bin/env python3
"""Convierte los contornos de las 13 provincias de Cusco (GeoJSON de provincias del Perú,
github.com/juaneladio/peru-geojson) en trazos SVG livianos para la web. Se corre una sola vez."""
import json
import math
from pathlib import Path

BASE = Path(__file__).resolve().parent
ANCHO = 520


def main():
    geo = json.loads((BASE / "datos" / "peru_provincias.geojson").read_text())
    cusco = [f for f in geo["features"] if f["properties"]["FIRST_NOMB"] == "CUSCO"]
    anillos = lambda g: [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    puntos = [p for f in cusco for poli in anillos(f["geometry"]) for anillo in poli for p in anillo]
    lon0, lon1 = min(p[0] for p in puntos), max(p[0] for p in puntos)
    lat0, lat1 = min(p[1] for p in puntos), max(p[1] for p in puntos)
    k = math.cos(math.radians((lat0 + lat1) / 2))       # proyección equirectangular local
    escala = ANCHO / ((lon1 - lon0) * k)
    alto = round((lat1 - lat0) * escala)
    xy = lambda p: ((p[0] - lon0) * k * escala, (lat1 - p[1]) * escala)
    salida = {"ancho": ANCHO, "alto": alto, "provincias": {}}
    for f in cusco:
        d, area, cx, cy = [], 0, 0, 0
        for poli in anillos(f["geometry"]):
            for anillo in poli:
                pts, ultimo = [], None
                for p in anillo:
                    x, y = xy(p)
                    if ultimo is None or math.dist((x, y), ultimo) >= 1.2:  # simplifica: puntos a ≥1,2 px
                        pts.append((x, y)); ultimo = (x, y)
                if len(pts) < 3:
                    continue
                d.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
                for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):  # centroide del polígono
                    a = x1 * y2 - x2 * y1
                    area += a; cx += (x1 + x2) * a; cy += (y1 + y2) * a
        nombre = f["properties"]["NOMBPROV"]
        salida["provincias"][nombre] = {"d": "".join(d), "x": round(cx / (3 * area), 1), "y": round(cy / (3 * area), 1)}
    (BASE / "datos" / "mapa_cusco.json").write_text(json.dumps(salida, ensure_ascii=False))
    print(len(salida["provincias"]), "provincias;", ANCHO, "x", alto, "px;",
          round((BASE / "datos" / "mapa_cusco.json").stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
