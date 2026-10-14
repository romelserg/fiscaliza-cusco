#!/usr/bin/env python3
"""Descarga los proyectos de ley de los congresistas de Cusco desde la API
pública del Congreso (la misma que usa wb2server.congreso.gob.pe/spley-portal).

Uso:  python3 extraer_proyectos.py
Sólo usa la librería estándar de Python + openssl (incluido en macOS).
"""
import base64
import csv
import json
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

API = "https://api.congreso.gob.pe/spley-portal-service"
PERIODO = 2026
# Clave pública que el portal usa para "cifrar" los IDs en la URL de detalle.
CLAVE_PORTAL = "ProdALg5ZrAsxBMD"
# Enlace que abre el portal al pulsar "PDF" en la ficha: el id del archivo va en base64.
DESCARGA_PDF = API + "/archivo/{}/pdf"
ROLES = {1: "Autor principal", 2: "Coautor", 3: "Adherente"}

BASE = Path(__file__).resolve().parent
DATOS = BASE / "datos"
ARCHIVO_PROYECTOS = DATOS / "proyectos.json"
CARPETA_PDFS = BASE / "pdfs"


def http_json(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "fiscalizacion-congresistas-cusco/1.0",
    })
    for intento in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)["data"]
        except Exception:
            if intento == 2:
                raise
            time.sleep(3)


def cifrar(texto):
    clave_hex = CLAVE_PORTAL.encode().hex()
    salida = subprocess.run(
        ["openssl", "enc", "-aes-128-ecb", "-K", clave_hex, "-nosalt"],
        input=str(texto).encode(), capture_output=True, check=True).stdout
    return base64.b64encode(salida).decode().replace("+", "-").replace("/", "_").rstrip("=")


def listar_proyectos(congresista):
    """Devuelve {clave: (resumen_listado, rol)} para un congresista."""
    encontrados = {}
    for rol_id in ROLES:
        fila = 0
        while True:
            pagina = http_json(f"{API}/proyecto-ley/lista-con-filtro", {
                "perParId": PERIODO, "codTipoParl": congresista["camara"],
                "congresistaId": congresista["id"], "tipoFirmanteId": rol_id,
                "pageSize": 100, "rowStart": fila,
            })
            proyectos = pagina.get("proyectos") or []
            for p in proyectos:
                encontrados[f'{p["codTipoParl"]}-{p["pleyNum"]}'] = (p, ROLES[rol_id])
            fila += len(proyectos)
            if not proyectos or fila >= (pagina.get("rowsTotal") or 0):
                break
            time.sleep(0.5)
    return encontrados


def detalle(p):
    d = http_json(f'{API}/expediente/{cifrar(p["perParId"])}/{cifrar(p["pleyNum"])}'
                  f'?codTipoParl={p["codTipoParl"]}')
    g = d["general"]
    # El texto del proyecto es el archivo del paso inicial ("PRESENTADO"); el seguimiento
    # viene del más reciente al más antiguo, así que si no hay marca se toma el último.
    seguimientos = d.get("seguimientos") or []
    iniciales = [s for s in seguimientos if s.get("flagInicial")] or seguimientos[::-1]
    pdf_ids = [a["proyectoArchivoId"] for s in iniciales
               for a in s.get("archivos") or [] if a.get("proyectoArchivoId")]
    return {
        "numero": g["proyectoLey"],
        "camara": p["codTipoParl"],
        "fecha": g["fecPresentacion"],
        "titulo": g["titulo"],
        "sumilla": g.get("sumilla"),
        "bancada_autor": g.get("desGpar"),
        "estado": g["desEstado"],
        "legislatura": g.get("desLegis"),
        "seguimiento": [{"fecha": (s["fecha"] or "")[:10], "estado": s["desEstado"],
                         "comisiones": s.get("desComisiones"), "detalle": s.get("detalle")}
                        for s in d.get("seguimientos") or []],
        "firmantes": [{"id": f["congresistaId"], "nombre": f["nombre"],
                       "rol": ROLES.get(f["tipoFirmanteId"], "?")}
                      for f in d.get("firmantes") or []],
        "pdf_id": pdf_ids[0] if pdf_ids else None,
        "pdf": url_pdf(pdf_ids[0]) if pdf_ids else None,
    }


def rol_real(proyecto, congresista_id, rol):
    """En algunos expedientes el sistema marca a todos los firmantes como "Autor principal";
    el autor real es el primer firmante, que es quien firma el PDF."""
    firmantes = proyecto["firmantes"]
    if rol == "Autor principal" and firmantes and firmantes[0]["id"] != congresista_id:
        return "Coautor"
    return rol


def url_pdf(archivo_id):
    return DESCARGA_PDF.format(base64.b64encode(str(archivo_id).encode()).decode())


def descargar_pdfs(proyectos):
    """Baja el PDF de los proyectos donde algún cusqueño es autor principal."""
    CARPETA_PDFS.mkdir(exist_ok=True)
    for p in proyectos.values():
        destino = CARPETA_PDFS / f'{p["numero"]}.pdf'
        if not p.get("pdf_id") or destino.exists() or "Autor principal" not in p["cusco"].values():
            continue
        req = urllib.request.Request(p["pdf"], headers={"User-Agent": "fiscalizacion-congresistas-cusco/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            destino.write_bytes(r.read())
        print("PDF descargado:", destino.name)
        time.sleep(0.5)


def main():
    DATOS.mkdir(exist_ok=True)
    congresistas = json.loads((BASE / "congresistas.json").read_text())
    previos = json.loads(ARCHIVO_PROYECTOS.read_text()) if ARCHIVO_PROYECTOS.exists() else {}
    proyectos, novedades = {}, []

    for c in congresistas:
        lista = listar_proyectos(c)
        print(f'{c["corto"]}: {len(lista)} proyectos')
        for clave, (resumen, rol) in lista.items():
            previo = previos.get(clave)
            if clave in proyectos:  # ya procesado en esta ejecución (otro cusqueño también firma)
                proyecto = proyectos[clave]
            elif previo and previo["estado"] == resumen["desEstado"] and "pdf_id" in previo:
                proyecto = dict(previo, cusco={})
            else:
                proyecto = detalle(resumen)
                time.sleep(0.5)
                if not previos.get(clave):
                    novedades.append(("NUEVO", clave, proyecto))
                elif previos[clave]["estado"] != proyecto["estado"]:
                    novedades.append((f'CAMBIO: {previos[clave]["estado"]} → {proyecto["estado"]}',
                                      clave, proyecto))
            proyecto.setdefault("cusco", {})[str(c["id"])] = rol_real(proyecto, c["id"], rol)
            proyectos[clave] = proyecto

    if not previos:  # primera ejecución: todo es "nuevo", no tiene sentido listarlo
        novedades = []
    ARCHIVO_PROYECTOS.write_text(json.dumps(proyectos, ensure_ascii=False, indent=1))
    descargar_pdfs(proyectos)
    escribir_csv(proyectos, congresistas)
    escribir_reporte(proyectos, congresistas, novedades)
    print(f"\n{len(proyectos)} proyectos guardados; {len(novedades)} novedades.")


def escribir_csv(proyectos, congresistas):
    nombres = {str(c["id"]): c["corto"] for c in congresistas}
    with open(DATOS / "proyectos.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["congresista", "rol", "numero", "fecha", "estado", "titulo", "pdf"])
        for p in sorted(proyectos.values(), key=lambda p: p["fecha"], reverse=True):
            for cid, rol in p["cusco"].items():
                w.writerow([nombres[cid], rol, p["numero"], p["fecha"], p["estado"], p["titulo"], p["pdf"]])


def escribir_reporte(proyectos, congresistas, novedades):
    hoy = datetime.now().strftime("%Y-%m-%d %H:%M")
    archivo_resumenes = DATOS / "resumenes.json"
    resumenes = json.loads(archivo_resumenes.read_text()) if archivo_resumenes.exists() else {}
    l = [f"# Proyectos de ley — congresistas de Cusco", f"_Actualizado: {hoy}_", ""]
    if novedades:
        l += ["## Novedades desde la última revisión", ""]
        for tipo, clave, p in novedades:
            l.append(f'- **{tipo}** · [{p["numero"]}]({p["pdf"]}) · {p["titulo"][:160]}')
        l.append("")
    l += ["## Resumen", "", "| Congresista | Cámara | Autor principal | Coautor | Adherente | Total |",
          "|---|---|---|---|---|---|"]
    for c in congresistas:
        roles = [p["cusco"][str(c["id"])] for p in proyectos.values() if str(c["id"]) in p["cusco"]]
        n = {r: roles.count(r) for r in ROLES.values()}
        camara = "Diputados" if c["camara"] == "D" else "Senado"
        l.append(f'| {c["corto"]} ({c["partido"]}) | {camara} | {n["Autor principal"]} | '
                 f'{n["Coautor"]} | {n["Adherente"]} | {len(roles)} |')
    for c in congresistas:
        propios = sorted((p for p in proyectos.values()
                          if p["cusco"].get(str(c["id"])) == "Autor principal"),
                         key=lambda p: p["fecha"], reverse=True)
        l += ["", f'## {c["corto"]} — proyectos como autor principal ({len(propios)})', ""]
        for p in propios:
            r = resumenes.get(p["numero"])
            if not r:
                l += [f'### {p["numero"]} · {p["fecha"]} · {p["estado"]}', "",
                      f'{p["titulo"]}', "", "_Resumen pendiente._", f'[PDF oficial]({p["pdf"]})', ""]
                continue
            etiqueta = {"directa": "🟢 Relación directa con Cusco", "indirecta": "🟡 Relación indirecta con Cusco",
                        "nacional": "⚪ Alcance nacional"}[r["cusco"]]
            l += [f'### {p["numero"]} · {r["tema"]}', "",
                  f'{p["fecha"]} · **{p["estado"]}** · {etiqueta}', "", r["resumen"]]
            if r.get("por_que_cusco"):
                l.append(f'\n*Por qué importa en Cusco:* {r["por_que_cusco"]}')
            if r.get("nota"):
                l.append(f'\n*Nota:* {r["nota"]}')
            l += ["", f'[PDF oficial]({p["pdf"]})', ""]
    l += ["", "---", "*Autor principal = primer firmante del expediente. En algunos expedientes el "
          "sistema del Congreso marca a todos los firmantes como autores principales; aquí solo cuenta el primero.*"]
    (BASE / "reporte.md").write_text("\n".join(l) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
