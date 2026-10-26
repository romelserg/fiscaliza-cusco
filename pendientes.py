#!/usr/bin/env python3
"""Lista de lo que necesita revisión humana después de una actualización automática.

- Votos de los cusqueños que el OCR no pudo leer con certeza (se publican como "Por verificar").
- Proyectos de los cusqueños sin resumen (se publican con su título oficial y "Resumen pendiente").
- Intervenciones en el Pleno sin resumen.

Uso:  python3 pendientes.py   → pendientes.md (la actualización automática lo publica como un aviso en GitHub)
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def cargar(ruta, defecto):
    f = BASE / ruta
    return json.loads(f.read_text()) if f.exists() else defecto


def main():
    congresistas = {str(c["id"]): c["corto"] for c in cargar("congresistas.json", [])}
    eventos = cargar("votaciones/eventos.json", [])
    proyectos = cargar("datos/proyectos.json", {})
    resumenes = cargar("datos/resumenes.json", {})
    turnos = cargar("intervenciones/intervenciones.json", [])
    res_int = cargar("intervenciones/resumenes.json", {})

    votos = [(e["fecha"], e["pdf"], e["pagina"], congresistas.get(i, i)) for e in eventos for i, v in e["votos"].items() if v == "REVISAR"]
    # Solo se resumen los proyectos en que un cusqueño es autor principal
    sin_resumen = sorted((p["fecha"], p["numero"], p["titulo"]) for p in proyectos.values()
                         if p["numero"] not in resumenes and "Autor principal" in p["cusco"].values())
    sin_res_int = sorted((t["fecha"], t["id"], congresistas.get(str(t["congresista"]), ""), t["palabras"], t["fuente"])
                         for t in turnos if t["id"] not in res_int and not t.get("preside"))
    l = ["Lista generada por la actualización automática. Lo que está aquí ya se publicó, marcado como pendiente.", ""]
    l += [f"## Votos por verificar ({len(votos)})", ""]
    l += [f"- [ ] {f} · {n} · `{pdf}` pág. {pag}" for f, pdf, pag, n in votos] or ["Ninguno."]
    l += ["", "Se corrigen en `votaciones/correcciones.json` (clave `archivo.pdf#página|id`).", ""]
    l += [f"## Proyectos sin resumen ({len(sin_resumen)})", ""]
    l += [f"- [ ] {f} · {num} · {tit.capitalize()[:120]}" for f, num, tit in sin_resumen] or ["Ninguno."]
    l += ["", "Los resúmenes van en `datos/resumenes.json`.", ""]
    l += [f"## Intervenciones sin resumen ({len(sin_res_int)})", ""]
    l += [f"- [ ] {f} · {n} · {pal} palabras · [transcripción]({url})" for f, _, n, pal, url in sin_res_int] or ["Ninguna."]
    l += ["", "Los resúmenes van en `intervenciones/resumenes.json`."]
    (BASE / "pendientes.md").write_text("\n".join(l) + "\n")
    print(f"pendientes.md: {len(votos)} votos por verificar, {len(sin_resumen)} proyectos y {len(sin_res_int)} intervenciones sin resumen")


if __name__ == "__main__":
    main()
