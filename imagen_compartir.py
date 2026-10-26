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


def main():
    congresistas = [c for c in json.loads((BASE / "congresistas.json").read_text()) if c["camara"] == "D"]
    eventos = [e for e in json.loads((BASE / "votaciones" / "eventos.json").read_text())
               if e["camara"] == "D" and e["tipo"] == "VOTACIÓN"]
    eventos.sort(key=lambda e: (e["fecha"], e["hora"] or ""))

    cardo = lambda t: fuente("Cardo-Bold.ttf", t)
    cardo_it = lambda t: fuente("Cardo-Italic.ttf", t)
    cardo_reg = lambda t: fuente("Cardo-Regular.ttf", t)
    franklin = lambda t, p=500: fuente("LibreFranklin[wght].ttf", t, p)
    courier = lambda t: fuente("CourierPrime-Regular.ttf", t)

    lz = Lienzo()
    lz.rect(0, 0, W, H, PAPEL)

    # Barra de Ciudad Sur, como en la web
    lz.rect(0, 0, W, 74, "#000000")
    lz.imagen(BASE / "web" / "logo-ciudadsur.png", 56, 9, 56)
    ancho = lz.texto("PROYECTOS ESPECIALES", 0, 0, cardo_reg(21), "#000000", 3)  # solo para medir
    lz.texto("PROYECTOS ESPECIALES", W - 56 - ancho, 45, cardo_reg(21), "#dddddd", 3)

    # Columna izquierda: nombre y propósito
    lz.texto("PERÍODO PARLAMENTARIO 2026–2031", 64, 128, courier(18), TINTA2, 0.5)
    lz.texto("Fiscaliza", 56, 240, cardo(116), TINTA)
    ancho_cusco = lz.texto("Cusco", 60, 350, cardo_it(116), CS)
    icono(lz, 60 + ancho_cusco + 22, 350 - 82, 82)  # a la altura de las mayúsculas
    lz.parrafo("Qué proponen, cuándo asisten y cómo votan los seis congresistas elegidos por Cusco.",
               64, 384, 480, 120, franklin(27), TINTA)
    lz.texto("romelserg.github.io/fiscaliza-cusco", 64, 540, courier(20), TINTA2)

    # Columna derecha: tejido de votos real
    C, G, SG = 15, 3, 9
    x0, y0 = 700, 212
    lz.texto("EL TEJIDO DE VOTOS · PLENO", 600, 150, courier(16), TINTA2, 0.5)
    lz.rect(600, 164, 536, 2, TINTA)
    xs, x, prev = [], x0, None
    for e in eventos:
        if prev and e["fecha"] != prev:
            x += SG
        if not prev or e["fecha"][:7] != prev[:7]:  # solo el mes, para que las etiquetas no se encimen
            lz.texto(MESES[int(e["fecha"][5:7]) - 1], x, y0 - 14, courier(14), TINTA2)
        xs.append(x)
        x += C + G
        prev = e["fecha"]
    for r, c in enumerate(congresistas):
        y = y0 + r * (C + G + 6)
        lz.texto(c["corto"].split(" ")[-1], 600, y + 13, franklin(16, 600), TINTA)
        for e, cx in zip(eventos, xs):
            v = e["votos"].get(str(c["id"]))
            if v == "***":  # presidía la sesión: cuadro en contorno
                lz.rect(cx, y, C, C, TINTA2)
                lz.rect(cx + 2, y + 2, C - 4, C - 4, PAPEL)
            else:
                lz.rect(cx, y, C, C, {"SI": SI, "NO": NO, "ABST": ABST}.get(v, VACIO))
    ly = y0 + len(congresistas) * (C + G + 6) + 26
    lx = 600
    for nombre, col in (("A favor", SI), ("En contra", NO), ("Abst.", ABST), ("Sin votar", VACIO), ("Presidía", None)):
        if col:
            lz.rect(lx, ly - 12, 13, 13, col)
        else:
            lz.rect(lx, ly - 12, 13, 13, TINTA2)
            lz.rect(lx + 2, ly - 10, 9, 9, PAPEL)
        lx += 19 + lz.texto(nombre, lx + 19, ly, franklin(15, 500), TINTA2) + 16

    lz.texto("Cada dato enlaza al acta oficial del Congreso.", 600, ly + 52, franklin(19, 500), TINTA)

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
