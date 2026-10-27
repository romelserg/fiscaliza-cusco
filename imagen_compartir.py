#!/usr/bin/env python3
"""Dibuja docs/og.png (1200×630): la imagen que muestran WhatsApp, Facebook, X, etc.
al compartir el enlace. Usa los datos reales del tejido de votos de Diputados.

Requiere macOS (Quartz + CoreText vía pyobjc) y las fuentes de la carpeta fuentes/.
"""
import json
from pathlib import Path

import CoreText
import Quartz
from Foundation import NSURL

BASE = Path(__file__).resolve().parent
W, H = 1200, 630
PAPEL, TINTA, TINTA2 = "#f4ede0", "#2b2520", "#6b6157"
SI, NO, ABST, VACIO = "#1f6fa3", "#b23a48", "#a8761a", "#cfc3ad"
CS = "#671b27"  # borgoña de Ciudad Sur: marca, no datos
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]


def color(h, a=1.0):
    h = h.lstrip("#")
    return Quartz.CGColorCreateGenericRGB(*(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)), a)


def fuente(archivo, tam, peso=None):
    proveedor = Quartz.CGDataProviderCreateWithURL(NSURL.fileURLWithPath_(str(BASE / "fuentes" / archivo)))
    f = CoreText.CTFontCreateWithGraphicsFont(Quartz.CGFontCreateWithDataProvider(proveedor), tam, None, None)
    if peso:  # eje de peso de la fuente variable ('wght')
        desc = CoreText.CTFontDescriptorCreateWithAttributes({CoreText.kCTFontVariationAttribute: {0x77676874: peso}})
        f = CoreText.CTFontCreateCopyWithAttributes(f, tam, None, desc)
    return f


class Lienzo:
    """Coordenadas con origen arriba a la izquierda, como en la web."""

    def __init__(self, ancho=W, alto=H):
        self.h = alto
        self.ctx = Quartz.CGBitmapContextCreate(None, ancho, alto, 8, 0, Quartz.CGColorSpaceCreateDeviceRGB(),
                                                Quartz.kCGImageAlphaPremultipliedLast)

    def redondeado(self, x, y, w, h, r, col):
        Quartz.CGContextSetFillColorWithColor(self.ctx, color(col))
        Quartz.CGContextAddPath(self.ctx, Quartz.CGPathCreateWithRoundedRect(
            Quartz.CGRectMake(x, self.h - y - h, w, h), r, r, None))
        Quartz.CGContextFillPath(self.ctx)

    def rect(self, x, y, w, h, col):
        Quartz.CGContextSetFillColorWithColor(self.ctx, color(col))
        Quartz.CGContextFillRect(self.ctx, Quartz.CGRectMake(x, self.h - y - h, w, h))

    def poligono(self, puntos, col):
        Quartz.CGContextSetFillColorWithColor(self.ctx, color(col))
        Quartz.CGContextBeginPath(self.ctx)
        Quartz.CGContextMoveToPoint(self.ctx, puntos[0][0], self.h - puntos[0][1])
        for x, y in puntos[1:]:
            Quartz.CGContextAddLineToPoint(self.ctx, x, self.h - y)
        Quartz.CGContextClosePath(self.ctx)
        Quartz.CGContextFillPath(self.ctx)

    def texto(self, s, x, base, f, col, espaciado=0):
        attrs = {CoreText.kCTFontAttributeName: f, CoreText.kCTForegroundColorAttributeName: color(col),
                 CoreText.kCTKernAttributeName: espaciado}
        linea = CoreText.CTLineCreateWithAttributedString(CoreText.CFAttributedStringCreate(None, s, attrs))
        Quartz.CGContextSetTextPosition(self.ctx, x, self.h - base)
        CoreText.CTLineDraw(linea, self.ctx)
        return CoreText.CTLineGetTypographicBounds(linea, None, None, None)[0]

    def parrafo(self, s, x, y, ancho, alto, f, col):
        attrs = {CoreText.kCTFontAttributeName: f, CoreText.kCTForegroundColorAttributeName: color(col)}
        marco = CoreText.CTFramesetterCreateFrame(
            CoreText.CTFramesetterCreateWithAttributedString(CoreText.CFAttributedStringCreate(None, s, attrs)),
            CoreText.CFRangeMake(0, 0), Quartz.CGPathCreateWithRect(Quartz.CGRectMake(x, self.h - y - alto, ancho, alto), None), None)
        CoreText.CTFrameDraw(marco, self.ctx)

    def circulo(self, x, y, r, col):
        Quartz.CGContextSetFillColorWithColor(self.ctx, color(col))
        Quartz.CGContextFillEllipseInRect(self.ctx, Quartz.CGRectMake(x - r, self.h - y - r, 2 * r, 2 * r))

    def imagen(self, ruta, x, y, alto):
        """Pega un PNG con su transparencia; devuelve el ancho dibujado."""
        fuente_img = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(str(ruta)), None)
        img = Quartz.CGImageSourceCreateImageAtIndex(fuente_img, 0, None)
        ancho = alto * Quartz.CGImageGetWidth(img) / Quartz.CGImageGetHeight(img)
        Quartz.CGContextDrawImage(self.ctx, Quartz.CGRectMake(x, self.h - y - alto, ancho, alto), img)
        return ancho

    def guardar(self, ruta):
        imagen = Quartz.CGBitmapContextCreateImage(self.ctx)
        destino = Quartz.CGImageDestinationCreateWithURL(NSURL.fileURLWithPath_(str(ruta)), "public.png", 1, None)
        Quartz.CGImageDestinationAddImage(destino, imagen, None)
        Quartz.CGImageDestinationFinalize(destino)


def icono(lz, x, y, lado, redondeo=True):
    """El ícono (escalón de tocapu con un borreguito en la cima), dibujado sobre una grilla de 32."""
    k = lado / 32
    r = lambda gx, gy, gw, gh, col: lz.rect(x + gx * k, y + gy * k, gw * k, gh * k, col)
    if redondeo:
        lz.redondeado(x, y, lado, lado, 6 * k, TINTA)
    else:
        lz.rect(x, y, lado, lado, TINTA)
    lz.poligono([(x + px * k, y + py * k) for px, py in
                 [(4, 28), (4, 23), (10, 23), (10, 18), (16, 18), (16, 13), (28, 13), (28, 28)]], NO)
    r(17, 5, 9, 5, PAPEL); r(16, 6, 11, 3, PAPEL); r(25, 4, 4, 4, ABST)
    r(18, 10, 2, 3, PAPEL); r(23, 10, 2, 3, PAPEL)


def tocapu(lz, y, alto):
    """Franja escalonada: el mismo módulo de 36×18 que usa la web, escalado."""
    k = alto / 18
    lz.rect(0, y, W, alto, TINTA)
    for x0 in range(0, W, int(36 * k)):
        p = lambda pts: [(x0 + px * k, y + py * k) for px, py in pts]
        lz.poligono(p([(2, 16), (6, 16), (6, 12), (10, 12), (10, 8), (14, 8), (14, 4), (18, 4), (18, 16)]), CS)
        lz.poligono(p([(20, 2), (24, 2), (24, 6), (28, 6), (28, 10), (32, 10), (32, 14), (36, 14), (36, 2)]), ABST)
        for px, py in ((22, 12), (10, 2)):
            lz.rect(x0 + px * k, y + py * k, 4 * k, 4 * k, PAPEL)


BANCADA_COLOR = {"FP": "#bd6a24", "PCO": "#665f00", "AN": "#05987a", "RP": "#1d58a3", "PBG": "#8a6fc0", "JP": "#1f2f5e"}


def hemiciclo(lz, cx, cy, R, padron, cusquenos, orden, filas=8, r0=0.4, rad=8.4):
    """Hemiciclo de la cámara: un círculo por escaño, por bancada de izquierda a derecha; los cusqueños,
    con borde y en las filas de adelante de su bancada (ubicación ilustrativa). Devuelve sus posiciones."""
    import math
    n = len(padron)
    radios = [r0 + (1 - r0) * k / (filas - 1) for k in range(filas)]
    cupos = [round(n * r / sum(radios)) for r in radios]
    cupos[-1] += n - sum(cupos)
    pts = sorted(((math.pi * (1 - (j + 0.5) / c), r) for r, c in zip(radios, cupos) for j in range(c)), key=lambda p: (-p[0], p[1]))
    k, marcados = 0, []
    for b in orden:
        miembros = [m for m in padron if m["bancada"] == b]
        bloque = pts[k:k + len(miembros)]
        k += len(miembros)
        adelante = sorted(bloque, key=lambda p: (p[1], abs(p[0] - math.pi / 2)))
        usados = set()
        for m in sorted(miembros, key=lambda m: str(m["id"]) not in cusquenos):
            es = str(m["id"]) in cusquenos
            a, r = next(p for p in (adelante if es else bloque) if p not in usados)
            usados.add((a, r))
            x, y = cx + math.cos(a) * r * R, cy - math.sin(a) * r * R
            if es:
                lz.circulo(x, y, rad + 6, TINTA)
                lz.circulo(x, y, rad + 1.5, BANCADA_COLOR[b])
                marcados.append((x, y, cusquenos[str(m["id"])]))
            else:
                lz.circulo(x, y, rad, BANCADA_COLOR.get(b, VACIO))
    return marcados


def main():
    congresistas = {str(c["id"]): c for c in json.loads((BASE / "congresistas.json").read_text()) if c["camara"] == "D"}
    padron = json.loads((BASE / "votaciones" / "padron_D.json").read_text())
    # Bancadas de izquierda a derecha según cómo votan (como en la web)
    orden = ["JP", "PBG", "AN", "PCO", "RP", "FP"]
    try:
        lados = json.loads((BASE / "datos" / "redes.json").read_text())["votacion"]["D"]["lados"]["puntos"]
        media = {b: sum(p["x"] for p in lados if p["bancada"] == b) / max(1, sum(1 for p in lados if p["bancada"] == b)) for b in orden}
        orden.sort(key=lambda b: -media[b])
    except (KeyError, FileNotFoundError):
        pass

    cardo = lambda t: fuente("Cardo-Bold.ttf", t)
    cardo_it = lambda t: fuente("Cardo-Italic.ttf", t)
    cardo_reg = lambda t: fuente("Cardo-Regular.ttf", t)
    franklin = lambda t, p=500: fuente("LibreFranklin[wght].ttf", t, p)

    lz = Lienzo()
    lz.rect(0, 0, W, H, PAPEL)

    # Barra de Ciudad Sur, como en la web
    lz.rect(0, 0, W, 74, "#000000")
    lz.imagen(BASE / "web" / "logo-ciudadsur.png", 56, 9, 56)
    ancho = lz.texto("PROYECTOS ESPECIALES", 0, 0, cardo_reg(21), "#000000", 3)  # solo para medir
    lz.texto("PROYECTOS ESPECIALES", W - 56 - ancho, 45, cardo_reg(21), "#dddddd", 3)

    # Columna izquierda: qué es
    lz.texto("OBSERVATORIO CIUDADANO", 60, 140, franklin(22, 700), CS, 3)
    lz.texto("DEL CONGRESO", 60, 170, franklin(22, 700), CS, 3)
    lz.texto("Fiscaliza", 54, 286, cardo(112), TINTA)
    ancho_cusco = lz.texto("Cusco", 58, 392, cardo_it(112), CS)
    icono(lz, 58 + ancho_cusco + 20, 392 - 78, 78)
    lz.parrafo("De los 130 diputados, 5 representan a Cusco. Si asisten, cómo votan y qué proponen.",
               62, 420, 470, 100, franklin(27), TINTA)
    lz.texto("romelserg.github.io/fiscaliza-cusco", 62, 552, franklin(20, 500), TINTA2)

    # Columna derecha: el hemiciclo de la Cámara de Diputados
    marcados = hemiciclo(lz, 880, 500, 290, padron, congresistas, orden)
    # A este tamaño los nombres no caben: el aro oscuro basta para reconocer a los cusqueños
    lz.circulo(800, 539, 11, TINTA); lz.circulo(800, 539, 6, PAPEL)
    lz.texto("los 5 de Cusco", 818, 546, franklin(22, 700), TINTA)
    x = 600
    for b in orden:
        nombre = {"JP": "JP", "PBG": "PBG", "AN": "AN", "PCO": "PCO", "RP": "RP", "FP": "FP"}[b]
        lz.circulo(x + 7, 582, 7, BANCADA_COLOR[b])
        x += 22 + lz.texto(f"{nombre} {sum(1 for m in padron if m['bancada'] == b)}", x + 20, 589, franklin(18, 600), TINTA2) + 18

    tocapu(lz, H - 36, 36)
    (BASE / "docs").mkdir(exist_ok=True)
    lz.guardar(BASE / "docs" / "og.png")
    # Íconos para el celular (pantalla de inicio) y respaldo de la pestaña: el sistema ya los redondea.
    for nombre, lado in (("apple-touch-icon.png", 180), ("icono-512.png", 512), ("favicon.png", 48)):
        li = Lienzo(lado, lado)
        icono(li, 0, 0, lado, redondeo=nombre == "favicon.png")
        li.guardar(BASE / "docs" / nombre)
    print("docs/og.png e íconos listos")


if __name__ == "__main__":
    main()
