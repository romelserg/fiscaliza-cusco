"""Temáticas y provincias: clasificación por palabras clave, común a proyectos, votaciones,
intervenciones y agenda. Las reglas están a la vista para que cualquiera pueda revisarlas."""
import re
import unicodedata


def normal(t):
    t = unicodedata.normalize("NFKD", (t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


# id: (nombre, [patrones sobre texto en minúsculas y sin tildes])
TEMAS = {
    "seguridad": ("Seguridad y justicia", [r"segurid\w* ciudadan", r"crimen", r"criminal", r"delincu", r"extorsi", r"sicari",
                  r"polic", r"penal", r"penitenci", r"carcel", r"\binpe\b", r"orden interno", r"terroris", r"narcotr",
                  r"fiscal(?!iz)", r"prevaricato", r"detencion", r"ministro del interior", r"fuerzas armadas", r"corrupcion"]),
    "salud": ("Salud", [r"\bsalud\b", r"essalud", r"hospital", r"medic", r"\bminsa\b", r"cancer", r"sanitari", r"inocuidad"]),
    "educacion": ("Educación", [r"educaci", r"universi", r"instituto", r"escolar", r"estudiant", r"docente", r"\bminedu\b",
                  r"pasaje universitario", r"ministro de educacion"]),
    "agro": ("Agro y agua", [r"agrari", r"agricult", r"\bagro", r"\briego", r"\bagua\b", r"saneamiento", r"sunass",
             r"helada", r"friaje", r"midagri", r"ganad", r"hoja de coca"]),
    "economia": ("Economía y consumidores", [r"tribut", r"impuesto", r"\bigv\b", r"presupuest", r"banco central", r"\bbcr\b",
                 r"exoneraci", r"bancari", r"financ", r"consumidor", r"\bmype", r"inversion publica", r"\bcanon\b", r"credito"]),
    "trabajo": ("Trabajo y pensiones", [r"laboral", r"trabajador", r"empleo", r"sunafil", r"pension", r"\bcts\b", r"plazas"]),
    "ambiente": ("Ambiente, energía y minería", [r"ambient", r"miner", r"energ", r"hidrocarb", r"petroperu", r"gasoducto",
                 r"\bgas\b", r"cabeceras de cuenca", r"recursos naturales", r"forestal"]),
    "desastres": ("Desastres y El Niño", [r"fenomeno (de )?el nino", r"desastre", r"incendio", r"sism", r"riesgo de desastres",
                  r"prevencion y atencion"]),
    "obras": ("Obras y transporte", [r"carreter", r"\bvial", r"transport", r"aeropuerto", r"\bchinchero\b", r"\btren\b",
              r"ferrocarril", r"vivienda", r"\bobras?\b(?! publicas? paralizad)", r"paralizacion de obras", r"conectividad"]),
    "cultura": ("Cultura, turismo y lenguas", [r"cultur", r"patrimonio", r"turis", r"machu ?picchu", r"lenguas? originaria",
                r"quechua", r"museo"]),
    "derechos": ("Derechos e inclusión", [r"pueblos? (indigena|originari)", r"comunidades campesinas", r"discapacidad",
                 r"\bmujer", r"infancia", r"adolescen", r"derechos humanos", r"defensor\w* ambiental", r"igualdad"]),
    "territorio": ("Regiones y municipios", [r"\bvraem\b", r"corredor economico", r"gobiernos? regional", r"municipalidad",
                   r"descentraliz", r"gobiernos? locales"]),
    "control": ("Control político", [r"interpel", r"invitar? al?\b.*ministr", r"facultad\w* (de )?legisla", r"delegar en el poder",
                r"salir del territorio nacional", r"ratifica", r"censura", r"vacancia", r"estado de emergencia",
                r"proposicion legislativa 98"]),  # PL 98 = pedido de facultades legislativas del Ejecutivo (2026)
    "democracia": ("Democracia y elecciones", [r"electoral", r"eleccion", r"sufragio", r"partidos? politic", r"soberania popular"]),
    "congreso": ("Organización del Congreso", [r"reglamento del (congreso|senado|la camara)", r"comision especial",
                 r"comisiones ordinarias", r"integrantes de las comisiones", r"cuadro nominativo", r"nomina de",
                 r"mesa directiva", r"junta de portavoces", r"comision permanente",
                 r"organos de la organizacion parlamentaria", r"reconsideracion"]),
    "exterior": ("Relaciones exteriores", [r"estados unidos", r"escudo de las americas", r"\bbolivia", r"\bchina\b",
                 r"relaciones exteriores", r"cancill", r"tratado", r"\bel salvador\b"]),
}


def clasificar(texto, maximo=2):
    t = normal(texto)
    puntaje = {}
    for tema, (_, patrones) in TEMAS.items():
        n = sum(len(re.findall(p, t)) for p in patrones)
        if n:
            puntaje[tema] = n
    orden = sorted(puntaje.items(), key=lambda kv: -kv[1])
    # El segundo tema solo se asigna si pesa al menos la mitad que el principal.
    return [k for i, (k, v) in enumerate(orden[:maximo]) if i == 0 or v >= orden[0][1] / 2]


# Provincias de la región Cusco y lugares que las identifican sin ambigüedad.
PROVINCIAS = {
    "ACOMAYO": [r"\bacomayo\b"],
    "ANTA": [r"\banta\b", r"limatambo", r"zurite"],
    "CALCA": [r"\bcalca\b", r"\bpisac\b", r"\blamay\b", r"\bcoya\b"],
    "CANAS": [r"\bcanas\b", r"yanaoca"],
    "CANCHIS": [r"canchis", r"sicuani"],
    "CHUMBIVILCAS": [r"chumbivilcas", r"\bvelille\b", r"\bllusco\b", r"colquemarca"],
    "CUSCO": [r"ciudad (del? )?cusco", r"provincia del? cusco", r"wanchaq", r"\bsaylla\b", r"\bporoy\b", r"\bccorca\b"],
    "ESPINAR": [r"espinar", r"\byauri\b"],
    # "La Convención" solo como provincia: no los tratados ("la Convención Americana…") ni gremios.
    "LA CONVENCION": [r"provincias? de la convencion", r"la convencion,? \(?cusco", r"cusco,? la convencion",
                      r"quillabamba", r"\bvraem\b", r"kimbiri", r"pichari", r"echara[tc]", r"megantoni", r"kintiarina",
                      r"villa virgen"],
    "PARURO": [r"\bparuro\b"],
    "PAUCARTAMBO": [r"paucartambo"],
    "QUISPICANCHI": [r"quispicanchi", r"\burcos\b", r"ocongate", r"marcapata"],
    "URUBAMBA": [r"urubamba", r"machu ?picchu(?! foods)", r"ollantaytambo", r"\bchinchero\b", r"\bmaras\b"],
}


def provincias(texto):
    t = normal(texto)
    return [p for p, patrones in PROVINCIAS.items() if any(re.search(x, t) for x in patrones)]
