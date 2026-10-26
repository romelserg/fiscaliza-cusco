#!/usr/bin/env python3
"""Datos de contacto oficiales de cada congresista: correo institucional, ficha y votos obtenidos.

Fuente: la ficha de cada congresista en el portal de su cámara (diputados.congreso.gob.pe/diputado/... y
senado.congreso.gob.pe/senador/...). Solo se publica lo que figura ahí; si una ficha no responde, se conserva
el último dato leído.

Uso:  python3 contacto.py   → datos/contacto.json
"""
import html
import json
import re
import unicodedata
from pathlib import Path

from votaciones import leer_url

BASE = Path(__file__).resolve().parent
SITIO = {"D": "https://diputados.congreso.gob.pe/diputado/{}/", "S": "https://senado.congreso.gob.pe/senador/{}/"}


def slug(nombre):
    """'Holguín Loaiza, César Augusto' → 'holguin-loaiza-cesar-augusto' (así nombra el portal cada ficha)."""
    t = unicodedata.normalize("NFKD", nombre.replace(",", " ").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def main():
    congresistas = json.loads((BASE / "congresistas.json").read_text())
    destino = BASE / "datos" / "contacto.json"
    previo = json.loads(destino.read_text()) if destino.exists() else {}
    salida = {}
    for c in congresistas:
        url = SITIO[c["camara"]].format(slug(c["nombre"]))
        try:
            pagina = leer_url(url).decode("utf-8", "ignore")
        except Exception as e:
            print(f"  {c['corto']}: la ficha no respondió ({e}); se conserva el dato anterior")
            if str(c["id"]) in previo:
                salida[str(c["id"])] = previo[str(c["id"])]
            continue
        texto = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", pagina, flags=re.S))))
        correo = re.search(r"Correo institucional\s+([\w.\-]+@congreso\.gob\.pe)", texto)
        votos = re.search(r"Votación obtenida\s+([\d.,]+)", texto)
        salida[str(c["id"])] = {"correo": correo.group(1) if correo else None, "ficha": url,
                                "votos_obtenidos": int(re.sub(r"\D", "", votos.group(1))) if votos else None}
        print(f"  {c['corto']}: {salida[str(c['id'])]['correo']} · {salida[str(c['id'])]['votos_obtenidos']} votos")
    destino.write_text(json.dumps(salida, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
