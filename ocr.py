"""OCR de PDFs escaneados con el motor Vision de macOS (gratis, sin internet).

Devuelve, por página, una lista de líneas (texto, x, y) con coordenadas normalizadas
(0-1, origen arriba a la izquierda) para poder reconstruir tablas.
"""
import pypdf
import Quartz
import Vision
from Foundation import NSData


def _cgimage(datos):
    fuente = Quartz.CGImageSourceCreateWithData(NSData.dataWithBytes_length_(datos, len(datos)), None)
    return Quartz.CGImageSourceCreateImageAtIndex(fuente, 0, None)


def ocr_imagen(datos):
    pedido = Vision.VNRecognizeTextRequest.alloc().init()
    pedido.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    pedido.setRecognitionLanguages_(["es-ES"])
    pedido.setUsesLanguageCorrection_(False)  # nombres propios y códigos de voto
    manejador = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(_cgimage(datos), None)
    manejador.performRequests_error_([pedido], None)
    lineas = []
    for obs in pedido.results() or []:
        caja = obs.boundingBox()
        texto = obs.topCandidates_(1)[0].string()
        lineas.append((texto, caja.origin.x, 1 - caja.origin.y - caja.size.height))
    return lineas


def ocr_pdf(ruta):
    """Lista de páginas; cada página es una lista de (texto, x, y)."""
    paginas = []
    for pagina in pypdf.PdfReader(ruta).pages:
        imagenes = pagina.images
        paginas.append(ocr_imagen(imagenes[0].data) if imagenes else [])
    return paginas


def ocr_recorte(datos, x0, y0, x1, y1, escala=4):
    """OCR de una zona (coordenadas 0-1, origen arriba a la izquierda), ampliada."""
    imagen = _cgimage(datos)
    ancho, alto = Quartz.CGImageGetWidth(imagen), Quartz.CGImageGetHeight(imagen)
    rect = Quartz.CGRectMake(x0 * ancho, y0 * alto, (x1 - x0) * ancho, (y1 - y0) * alto)
    recorte = Quartz.CGImageCreateWithImageInRect(imagen, rect)
    w, h = int(rect.size.width * escala), int(rect.size.height * escala)
    ctx = Quartz.CGBitmapContextCreate(None, w + 40, h + 40, 8, 0, Quartz.CGColorSpaceCreateDeviceRGB(),
                                       Quartz.kCGImageAlphaNoneSkipLast)
    Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
    Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, w + 40, h + 40))
    Quartz.CGContextDrawImage(ctx, Quartz.CGRectMake(20, 20, w, h), recorte)
    pedido = Vision.VNRecognizeTextRequest.alloc().init()
    pedido.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    pedido.setUsesLanguageCorrection_(False)
    pedido.setCustomWords_(["SI", "NO", "ABST", "PRE", "AUS", "LO", "LP", "LE", "LV", "SUS"])
    manejador = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        Quartz.CGBitmapContextCreateImage(ctx), None)
    manejador.performRequests_error_([pedido], None)
    return " ".join(o.topCandidates_(1)[0].string() for o in pedido.results() or [])


def ocr_zona(datos, y0, y1, escala=3):
    """OCR de una franja horizontal ampliada; devuelve (texto, x, y) en coordenadas de la página (0-1)."""
    imagen = _cgimage(datos)
    ancho, alto = Quartz.CGImageGetWidth(imagen), Quartz.CGImageGetHeight(imagen)
    rect = Quartz.CGRectMake(0, y0 * alto, ancho, (y1 - y0) * alto)
    recorte = Quartz.CGImageCreateWithImageInRect(imagen, rect)
    w, h = int(rect.size.width * escala), int(rect.size.height * escala)
    ctx = Quartz.CGBitmapContextCreate(None, w, h, 8, 0, Quartz.CGColorSpaceCreateDeviceRGB(),
                                       Quartz.kCGImageAlphaNoneSkipLast)
    Quartz.CGContextDrawImage(ctx, Quartz.CGRectMake(0, 0, w, h), recorte)
    pedido = Vision.VNRecognizeTextRequest.alloc().init()
    pedido.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    pedido.setUsesLanguageCorrection_(False)
    manejador = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        Quartz.CGBitmapContextCreateImage(ctx), None)
    manejador.performRequests_error_([pedido], None)
    salida = []
    for obs in pedido.results() or []:
        caja = obs.boundingBox()
        yy = y0 + (1 - caja.origin.y - caja.size.height) * (y1 - y0)
        salida.append((obs.topCandidates_(1)[0].string(), caja.origin.x, yy, caja.size.width))
    return salida
