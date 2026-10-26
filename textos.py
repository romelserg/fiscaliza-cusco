#!/usr/bin/env python3
"""Texto completo de cada proyecto en que un cusqueño es autor principal (texto/NÚMERO.txt).

Se usa para detectar qué provincias menciona cada proyecto (mapa). Si el PDF tiene capa de texto se lee
directamente; si es un escaneo, pasa por OCR (motor Vision de macOS). Solo procesa los que faltan.

Uso:  python3 textos.py   (después de extraer_proyectos.py, que descarga los PDF en pdfs/)
"""
import json
import re
from pathlib import Path

import pypdf

BASE = Path(__file__).resolve().parent


def main():
    proyectos = json.loads((BASE / "datos" / "proyectos.json").read_text())
    (BASE / "texto").mkdir(exist_ok=True)
    hechos = 0
    for p in proyectos.values():
        if "Autor principal" not in p["cusco"].values():
            continue
        destino = BASE / "texto" / f'{p["numero"]}.txt'
        pdf = BASE / "pdfs" / f'{p["numero"]}.pdf'
        if destino.exists() or not pdf.exists():
            continue
        texto = " ".join((pg.extract_text() or "") for pg in pypdf.PdfReader(str(pdf)).pages)
        if len(texto.strip()) < 300:  # escaneo: OCR página por página
            import ocr
            texto = " ".join(t for pagina in ocr.ocr_pdf(str(pdf)) for t, x, y in sorted(pagina, key=lambda it: (round(it[2], 2), it[1])))
        destino.write_text(re.sub(r"\s+", " ", texto).strip())
        hechos += 1
        print("  texto:", p["numero"])
    print(f"textos.py: {hechos} textos nuevos")


if __name__ == "__main__":
    main()
