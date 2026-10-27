#!/usr/bin/env python3
"""Datos de contacto oficiales de cada congresista: correo institucional, ficha, votos obtenidos y foto.

Fuente: la ficha de cada congresista en el portal de su cámara (diputados.congreso.gob.pe/diputado/... y
senado.congreso.gob.pe/senador/...). Solo se publica lo que figura ahí; si una ficha no responde, se conserva
el último dato leído.

La foto oficial de la ficha se guarda reducida en web/fotos/<id>.jpg (generar_web.py la incrusta en la página).

Uso:  python3 contacto.py   → datos/contacto.json y web/fotos/
"""
import html
import io
import json
import re
import unicodedata
from pathlib import Path

from PIL import Image

from votaciones import leer_url

BASE = Path(__file__).resolve().parent
FOTOS = BASE / "web" / "fotos"
SITIO = {"D": "https://diputados.congreso.gob.pe/diputado/{}/", "S": "https://senado.congreso.gob.pe/senador/{}/"}


def slug(nombre):
    """'Holguín Loaiza, César Augusto' → 'holguin-loaiza-cesar-augusto' (así nombra el portal cada ficha)."""
    t = unicodedata.normalize("NFKD", nombre.replace(",", " ").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def guardar_foto(pagina, id_):
    """Descarga la foto de la ficha (la del encabezado; si no, la imagen principal de la página)."""
    m = re.search(r'hero__photo"><img src="([^"]+)"', pagina) or re.search(r'"thumbnailUrl":"([^"]+)"', pagina)
    if not m:
        return None
    url = html.unescape(m.group(1).replace("\\/", "/"))
    foto = Image.open(io.BytesIO(leer_url(url)))
    if foto.mode in ("RGBA", "LA", "P"):
        foto = foto.convert("RGBA")
        fondo = Image.new("RGB", foto.size, (255, 255, 255))
        fondo.paste(foto, mask=foto.split()[-1])
        foto = fondo
    foto = foto.convert("RGB")
    foto.thumbnail((360, 480))
    FOTOS.mkdir(parents=True, exist_ok=True)
    foto.save(FOTOS / f"{id_}.jpg", quality=84, optimize=True, progressive=True)
    return url


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
        try:
            salida[str(c["id"])]["foto"] = guardar_foto(pagina, c["id"])
        except Exception as e:
            print(f"  {c['corto']}: no se pudo bajar la foto ({e}); se conserva la anterior")
            salida[str(c["id"])]["foto"] = (previo.get(str(c["id"])) or {}).get("foto")
        print(f"  {c['corto']}: {salida[str(c['id'])]['correo']} · {salida[str(c['id'])]['votos_obtenidos']} votos")
    destino.write_text(json.dumps(salida, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
