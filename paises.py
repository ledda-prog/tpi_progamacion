"""Gestión de países en un solo archivo.

Ejecutar: python3 paises.py
Ventana:  python3 paises.py --gui
Los datos se leen y guardan en paises.csv, junto a este archivo.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import math
import os
import queue
import sys
import tempfile
import threading
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# Validación de datos

CAMPOS = ("nombre", "poblacion", "superficie", "continente")
CONTINENTES = ("África", "América", "Asia", "Europa", "Oceanía", "Antártida")


class ErrorPaises(Exception):
    """Error recuperable que puede mostrarse directamente al usuario."""


def normalizar(texto: str) -> str:
    # Primero quitamos tildes, mayúsculas y espacios repetidos para comparar nombres.
    base = unicodedata.normalize("NFKD", str(texto).casefold())
    return " ".join("".join(c for c in base if not unicodedata.combining(c)).split())


def entero(valor: object, campo: str, minimo: int = 0) -> int:
    # Después comprobamos que un dato numérico sea entero antes de guardarlo.
    texto = str(valor).strip()
    if not texto or not texto.isascii() or not texto.isdigit() or len(texto) > 18:
        raise ErrorPaises(f"{campo.capitalize()}: ingresá un número entero no negativo.")
    numero = int(texto)
    if numero < minimo:
        raise ErrorPaises(f"{campo.capitalize()}: el mínimo permitido es {minimo}.")
    return numero


def validar(nombre: str, poblacion: object, superficie: object, continente: str) -> dict:
    # Finalmente unificamos las reglas para CSV, consola, ventana y API.
    if nombre is None or continente is None:
        raise ErrorPaises("Nombre y continente son obligatorios.")
    if any(ord(c) < 32 or ord(c) == 127 for c in str(nombre) + str(continente)):
        raise ErrorPaises("Nombre y continente no pueden contener caracteres de control.")
    nombre = " ".join(str(nombre).split())
    continente = " ".join(str(continente).split())
    if not nombre or not continente:
        raise ErrorPaises("Nombre y continente son obligatorios.")
    if len(nombre) > 100 or len(continente) > 40:
        raise ErrorPaises("Nombre o continente demasiado largo.")
    return {
        "nombre": nombre,
        "poblacion": entero(poblacion, "población"),
        "superficie": entero(superficie, "superficie", 1),
        "continente": continente,
    }

# Búsquedas, filtros, orden y estadísticas

def buscar(paises: list[dict], texto: str) -> list[dict]:
    # Buscamos primero coincidencias exactas y parciales; luego nombres parecidos.
    consulta = normalizar(texto)
    if not consulta:
        raise ErrorPaises("Escribí un nombre o parte de él.")
    resultados = []
    for pais in paises:
        nombre = normalizar(pais["nombre"])
        similitud = SequenceMatcher(None, consulta, nombre).ratio()
        if consulta in nombre or (len(consulta) >= 3 and similitud >= 0.68):
            if consulta == nombre:
                rango = 0
            elif nombre.startswith(consulta):
                rango = 1
            elif consulta in nombre:
                rango = 2
            else:
                rango = 3
            resultados.append((rango, -similitud, nombre, pais))
    resultados.sort(key=lambda x: x[:3])
    return [item[3] for item in resultados]


def filtrar(
    paises: list[dict],
    continente: str = "",
    poblacion_min: str = "",
    poblacion_max: str = "",
    superficie_min: str = "",
    superficie_max: str = "",
) -> list[dict]:
    # Los límites vacíos no filtran; los valores indicados se incluyen en el rango.
    def limite(valor: str, nombre: str) -> int | None:
        return None if str(valor).strip() == "" else entero(valor, nombre)

    pmin = limite(poblacion_min, "población mínima")
    pmax = limite(poblacion_max, "población máxima")
    smin = limite(superficie_min, "superficie mínima")
    smax = limite(superficie_max, "superficie máxima")
    if pmin is not None and pmax is not None and pmin > pmax:
        raise ErrorPaises("La población mínima supera la máxima.")
    if smin is not None and smax is not None and smin > smax:
        raise ErrorPaises("La superficie mínima supera la máxima.")
    return [
        pais for pais in paises
        if (not continente or normalizar(continente) == normalizar(pais["continente"]))
        and (pmin is None or pais["poblacion"] >= pmin)
        and (pmax is None or pais["poblacion"] <= pmax)
        and (smin is None or pais["superficie"] >= smin)
        and (smax is None or pais["superficie"] <= smax)
    ]


def ordenar(paises: list[dict], campo: str, descendente: bool = False) -> list[dict]:
    # sorted crea una nueva lista y conserva el orden original del repositorio.
    if campo not in ("nombre", "poblacion", "superficie"):
        raise ErrorPaises("El criterio debe ser nombre, población o superficie.")
    if campo == "nombre":
        return sorted(paises, key=lambda p: normalizar(p["nombre"]), reverse=descendente)
    return sorted(paises, key=lambda p: p[campo], reverse=descendente)


def estadisticas(paises: list[dict]) -> dict:
    # Verificamos que haya datos antes de calcular promedios.
    if not paises:
        raise ErrorPaises("No hay países válidos para calcular estadísticas.")
    return {
        "mayor": max(paises, key=lambda p: p["poblacion"]),
        "menor": min(paises, key=lambda p: p["poblacion"]),
        "promedio_poblacion": sum(p["poblacion"] for p in paises) / len(paises),
        "promedio_superficie": sum(p["superficie"] for p in paises) / len(paises),
        "por_continente": dict(sorted(Counter(p["continente"] for p in paises).items())),
    }

# Consulta de datos al Banco Mundial

API_BASE = "https://api.worldbank.org/v2/country/all/indicator"
CODIGOS = {
    # Nombres del CSV incluidos con su código ISO 3166-1 alfa-3.
    "Afganistán": "AFG",
    "Albania": "ALB",
    "Alemania": "DEU",
    "Andorra": "AND",
    "Angola": "AGO",
    "Antigua y Barbuda": "ATG",
    "Arabia Saudí": "SAU",
    "Argelia": "DZA",
    "Argentina": "ARG",
    "Armenia": "ARM",
    "Australia": "AUS",
    "Austria": "AUT",
    "Azerbaiyán": "AZE",
    "Bahamas": "BHS",
    "Bahrein": "BHR",
    "Bangladesh": "BGD",
    "Barbados": "BRB",
    "Bélgica": "BEL",
    "Belice": "BLZ",
    "Benín": "BEN",
    "Bielorrusia": "BLR",
    "Bolivia": "BOL",
    "Bosnia y Herzegovina": "BIH",
    "Botswana": "BWA",
    "Brasil": "BRA",
    "Brunei": "BRN",
    "Bulgaria": "BGR",
    "Burkina Faso": "BFA",
    "Burundi": "BDI",
    "Bután": "BTN",
    "Cabo Verde": "CPV",
    "Camboya": "KHM",
    "Camerún": "CMR",
    "Canadá": "CAN",
    "Catar": "QAT",
    "Chad": "TCD",
    "Chequia": "CZE",
    "Chile": "CHL",
    "China": "CHN",
    "Chipre": "CYP",
    "Colombia": "COL",
    "Comoras": "COM",
    "Congo": "COG",
    "Congo (Rep. Dem.)": "COD",
    "Corea del Norte": "PRK",
    "Corea del Sur": "KOR",
    "Costa de Marfil": "CIV",
    "Costa Rica": "CRI",
    "Croacia": "HRV",
    "Cuba": "CUB",
    "Dinamarca": "DNK",
    "Djibouti": "DJI",
    "Dominica": "DMA",
    "Ecuador": "ECU",
    "Egipto": "EGY",
    "El Salvador": "SLV",
    "Emiratos Árabes Unidos": "ARE",
    "Eritrea": "ERI",
    "Eslovaquia": "SVK",
    "Eslovenia": "SVN",
    "España": "ESP",
    "Estados Unidos": "USA",
    "Estonia": "EST",
    "Esuatini": "SWZ",
    "Etiopía": "ETH",
    "Filipinas": "PHL",
    "Finlandia": "FIN",
    "Fiyi": "FJI",
    "Francia": "FRA",
    "Gabón": "GAB",
    "Gambia": "GMB",
    "Georgia": "GEO",
    "Ghana": "GHA",
    "Grecia": "GRC",
    "Grenada": "GRD",
    "Guatemala": "GTM",
    "Guinea": "GIN",
    "Guinea Ecuatorial": "GNQ",
    "Guinea-Bisáu": "GNB",
    "Guyana": "GUY",
    "Haití": "HTI",
    "Honduras": "HND",
    "Hungría": "HUN",
    "India": "IND",
    "Indonesia": "IDN",
    "Irak": "IRQ",
    "Iran": "IRN",
    "Irlanda": "IRL",
    "Islandia": "ISL",
    "Islas Marshall": "MHL",
    "Islas Salomón": "SLB",
    "Israel": "ISR",
    "Italia": "ITA",
    "Jamaica": "JAM",
    "Japón": "JPN",
    "Jordania": "JOR",
    "Kazajistán": "KAZ",
    "Kenia": "KEN",
    "Kirguizistán": "KGZ",
    "Kiribati": "KIR",
    "Kuwait": "KWT",
    "Laos": "LAO",
    "Lesotho": "LSO",
    "Letonia": "LVA",
    "Líbano": "LBN",
    "Liberia": "LBR",
    "Libia": "LBY",
    "Liechtenstein": "LIE",
    "Lituania": "LTU",
    "Luxemburgo": "LUX",
    "Macedonia del Norte": "MKD",
    "Madagascar": "MDG",
    "Malasia": "MYS",
    "Malawi": "MWI",
    "Maldivas": "MDV",
    "Mali": "MLI",
    "Malta": "MLT",
    "Marruecos": "MAR",
    "Mauricio": "MUS",
    "Mauritania": "MRT",
    "México": "MEX",
    "Micronesia": "FSM",
    "Moldavia": "MDA",
    "Mónaco": "MCO",
    "Mongolia": "MNG",
    "Montenegro": "MNE",
    "Mozambique": "MOZ",
    "Myanmar": "MMR",
    "Namibia": "NAM",
    "Nauru": "NRU",
    "Nepal": "NPL",
    "Nicaragua": "NIC",
    "Níger": "NER",
    "Nigeria": "NGA",
    "Noruega": "NOR",
    "Nueva Zelanda": "NZL",
    "Omán": "OMN",
    "Países Bajos": "NLD",
    "Pakistán": "PAK",
    "Palau": "PLW",
    "Palestina": "PSE",
    "Panamá": "PAN",
    "Papúa Nueva Guinea": "PNG",
    "Paraguay": "PRY",
    "Perú": "PER",
    "Polonia": "POL",
    "Portugal": "PRT",
    "Reino Unido": "GBR",
    "República Centroafricana": "CAF",
    "República Dominicana": "DOM",
    "Ruanda": "RWA",
    "Rumania": "ROU",
    "Rusia": "RUS",
    "Samoa": "WSM",
    "San Cristóbal y Nieves": "KNA",
    "San Marino": "SMR",
    "San Vicente y Granadinas": "VCT",
    "Santa Lucía": "LCA",
    "Santo Tomé y Príncipe": "STP",
    "Senegal": "SEN",
    "Serbia": "SRB",
    "Seychelles": "SYC",
    "Sierra Leone": "SLE",
    "Singapur": "SGP",
    "Siria": "SYR",
    "Somalia": "SOM",
    "Sri Lanka": "LKA",
    "Sudáfrica": "ZAF",
    "Sudán": "SDN",
    "Sudán del Sur": "SSD",
    "Suecia": "SWE",
    "Suiza": "CHE",
    "Surinam": "SUR",
    "Tailandia": "THA",
    "Tanzania": "TZA",
    "Tayikistán": "TJK",
    "Timor Oriental": "TLS",
    "Togo": "TGO",
    "Tonga": "TON",
    "Trinidad y Tobago": "TTO",
    "Túnez": "TUN",
    "Turkmenistán": "TKM",
    "Turquía": "TUR",
    "Tuvalu": "TUV",
    "Ucrania": "UKR",
    "Uganda": "UGA",
    "Uruguay": "URY",
    "Uzbekistán": "UZB",
    "Vanuatu": "VUT",
    "Venezuela": "VEN",
    "Vietnam": "VNM",
    "Yemen": "YEM",
    "Zambia": "ZMB",
    "Zimbabue": "ZWE",
}


def obtener_indicador(codigo: str) -> dict[str, int]:
    # Recorremos todas las páginas JSON antes de devolver datos a la capa de guardado.
    datos = {}
    pagina = 1
    while True:
        url = f"{API_BASE}/{codigo}?format=json&mrnev=1&per_page=500"
        if pagina > 1:
            url += f"&page={pagina}"
        for intento in range(2):
            try:
                with urlopen(Request(url, headers={"User-Agent": "TPI-Paises/1.0"}), timeout=25) as respuesta:
                    cuerpo = json.load(respuesta)
                break
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                if intento == 1:
                    raise ErrorPaises(f"La API no respondió correctamente ({codigo}): {exc}") from exc
            except (UnicodeError, ValueError) as exc:
                raise ErrorPaises(f"La API devolvió datos ilegibles ({codigo}): {exc}") from exc
        if not isinstance(cuerpo, list) or len(cuerpo) != 2 or not isinstance(cuerpo[0], dict) or not isinstance(cuerpo[1], list):
            raise ErrorPaises("La API devolvió un formato inesperado; no se modificó el CSV.")
        try:
            paginas = int(cuerpo[0]["pages"])
            if paginas < 1 or paginas > 50:
                raise ValueError("cantidad de páginas inválida")
            for fila in cuerpo[1]:
                iso = fila.get("countryiso3code")
                valor = fila.get("value")
                if (iso and isinstance(valor, (int, float)) and not isinstance(valor, bool)
                        and valor >= 0 and (not isinstance(valor, float) or math.isfinite(valor))):
                    datos[iso] = round(valor)
        except (KeyError, AttributeError, TypeError, ValueError, OverflowError) as exc:
            raise ErrorPaises(f"Datos inesperados en la API: {exc}") from exc
        if pagina >= paginas:
            return datos
        pagina += 1

# Lectura y escritura del CSV

class Repositorio:
    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self.paises: list[dict] = []
        self.advertencias: list[str] = []
        self.bloqueo_escritura = False
        self._huella: bytes | None = None
        self.cargar()

    def _huella_actual(self) -> bytes | None:
        # Esta huella revela si otra persona reemplazó el CSV durante la sesión.
        try:
            return hashlib.sha256(self.ruta.read_bytes()).digest()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ErrorPaises(f"No se puede comprobar el CSV: {exc}") from exc

    def cargar(self) -> None:
        # Leemos UTF-8; utf-8-sig también acepta archivos con BOM de algunos editores.
        self.advertencias = []
        self.paises = []
        self.bloqueo_escritura = False
        self._huella = None
        lector = None
        try:
            contenido = self.ruta.read_bytes()
            self._huella = hashlib.sha256(contenido).digest()
            texto = contenido.decode("utf-8-sig")
            lector = csv.DictReader(io.StringIO(texto, newline=""), strict=True)
            if lector.fieldnames is None or tuple(lector.fieldnames) != CAMPOS:
                raise ErrorPaises("El CSV debe tener las columnas: " + ", ".join(CAMPOS))
            vistos = set()
            for fila in lector:
                try:
                    if None in fila or any(fila[c] is None for c in CAMPOS):
                        raise ErrorPaises("cantidad de columnas incorrecta")
                    pais = validar(*(fila[c] for c in CAMPOS))
                    clave = normalizar(pais["nombre"])
                    if clave in vistos:
                        raise ErrorPaises("nombre duplicado")
                    vistos.add(clave)
                    self.paises.append(pais)
                except ErrorPaises as exc:
                    self.advertencias.append(f"Línea {lector.line_num}: {exc}")
                    self.bloqueo_escritura = True
        except FileNotFoundError:
            self.advertencias.append("No se encontró el CSV; se inicia vacío. Al agregar, se creará.")
        except UnicodeDecodeError:
            self.advertencias.append("El CSV no está codificado en UTF-8. Guardalo como UTF-8 antes de continuar.")
            self.bloqueo_escritura = True
        except csv.Error as exc:
            linea = lector.line_num if lector is not None else "?"
            self.advertencias.append(f"CSV dañado cerca de la línea {linea}: {exc}")
            self.bloqueo_escritura = True
        except OSError as exc:
            self.advertencias.append(f"No se pudo leer el CSV: {exc}")
            self.bloqueo_escritura = True
        except ErrorPaises as exc:
            self.advertencias.append(str(exc))
            self.bloqueo_escritura = True

    def sincronizar(self) -> list[str]:
        # Antes de una operación revisamos cambios externos y recargamos el archivo.
        if self._huella_actual() != self._huella:
            self.cargar()
            return ["El CSV cambió fuera del programa; se volvió a cargar.", *self.advertencias]
        return []

    def _verificar_escritura(self) -> None:
        if self.bloqueo_escritura:
            raise ErrorPaises("El CSV contiene errores. Corregilo antes de guardar para no perder filas originales.")
        if self._huella_actual() != self._huella:
            raise ErrorPaises("El CSV cambió fuera del programa. Volvé al menú para recargarlo antes de guardar.")

    def _guardar(self, nuevos: list[dict]) -> None:
        # Primero validamos y escribimos un temporal; solo luego reemplazamos el original.
        self._verificar_escritura()
        temporal = None
        try:
            buffer = io.StringIO(newline="")
            escritor = csv.DictWriter(buffer, fieldnames=CAMPOS)
            escritor.writeheader()
            escritor.writerows(nuevos)
            datos = buffer.getvalue().encode("utf-8")
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "wb", dir=self.ruta.parent, prefix=".paises-", suffix=".csv", delete=False
            ) as archivo:
                temporal = Path(archivo.name)
                archivo.write(datos)
                archivo.flush()
                os.fsync(archivo.fileno())
            # Una última comprobación protege cambios ocurridos durante la escritura.
            self._verificar_escritura()
            os.replace(temporal, self.ruta)
            self._huella = hashlib.sha256(datos).digest()
            self.paises = nuevos
        except (OSError, UnicodeError, csv.Error) as exc:
            raise ErrorPaises(f"No se pudieron guardar los cambios: {exc}") from exc
        finally:
            if temporal is not None:
                try:
                    temporal.unlink(missing_ok=True)
                except OSError:
                    logging.exception("No se pudo borrar el archivo temporal %s", temporal)

    def agregar(self, nombre: str, poblacion: object, superficie: object, continente: str) -> dict:
        pais = validar(nombre, poblacion, superficie, continente)
        if any(normalizar(p["nombre"]) == normalizar(pais["nombre"]) for p in self.paises):
            raise ErrorPaises("Ese país ya existe.")
        self._guardar(self.paises + [pais])
        return pais

    def actualizar(self, nombre: str, poblacion: object, superficie: object) -> dict:
        # Exigimos nombre exacto normalizado para no editar una coincidencia aproximada.
        nombre_buscado = normalizar(nombre)
        indice = None
        for i, pais in enumerate(self.paises):
            if normalizar(pais["nombre"]) == nombre_buscado:
                indice = i
                break
        if indice is None:
            raise ErrorPaises("No existe ese país. Elegí un resultado de la búsqueda.")
        nuevo = validar(
            self.paises[indice]["nombre"],
            poblacion,
            superficie,
            self.paises[indice]["continente"],
        )
        copia = self.paises.copy()
        copia[indice] = nuevo
        self._guardar(copia)
        return nuevo

    def buscar(self, texto: str) -> list[dict]:
        return buscar(self.paises, texto)

    def filtrar(
        self,
        continente: str = "",
        poblacion_min: str = "",
        poblacion_max: str = "",
        superficie_min: str = "",
        superficie_max: str = "",
    ) -> list[dict]:
        return filtrar(
            self.paises, continente, poblacion_min,
            poblacion_max, superficie_min, superficie_max,
        )

    def ordenar(self, paises: list[dict], campo: str, descendente: bool = False) -> list[dict]:
        return ordenar(paises, campo, descendente)

    def estadisticas(self) -> dict:
        return estadisticas(self.paises)

    def _indicador(self, codigo: str) -> dict[str, int]:
        return obtener_indicador(codigo)

    def actualizar_desde_api(self) -> int:
        # Si el CSV está dañado, evitamos una descarga que no se podrá guardar.
        self._verificar_escritura()
        poblaciones = self._indicador("SP.POP.TOTL")
        superficies = self._indicador("AG.LND.TOTL.K2")
        nuevos = []
        cambios = 0
        for pais in self.paises:
            iso = CODIGOS.get(pais["nombre"])
            if iso in poblaciones and iso in superficies and superficies[iso] > 0:
                actualizado = validar(
                    pais["nombre"], poblaciones[iso], superficies[iso], pais["continente"]
                )
                nuevos.append(actualizado)
                cambios += 1
            else:
                nuevos.append(pais.copy())
        if cambios == 0:
            raise ErrorPaises("La API no devolvió datos de los países compatibles; no se guardó nada.")
        self._guardar(nuevos)
        return cambios


def registrar_error(exc: Exception) -> None:
    logging.exception("Error inesperado: %s", exc)

# Ventana opcional

def iniciar(repo) -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    try:
        raiz = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError("no hay pantalla gráfica disponible") from exc
    raiz.title("Gestión de países")
    raiz.geometry("1050x630")
    raiz.minsize(900, 520)
    estilo = ttk.Style()
    if "clam" in estilo.theme_names():
        estilo.theme_use("clam")
    estilo.configure("Treeview", rowheight=25)
    estilo.configure("Titulo.TLabel", font=("Arial", 17, "bold"))

    marco = ttk.Frame(raiz, padding=16)
    marco.pack(fill="both", expand=True)
    ttk.Label(marco, text="Gestión de países", style="Titulo.TLabel").pack(anchor="w")
    ttk.Label(marco, text="Búsqueda parcial o aproximada · datos locales con actualización opcional").pack(anchor="w", pady=(2, 12))

    controles = ttk.Frame(marco)
    controles.pack(fill="x")
    consulta = tk.StringVar()
    continente = tk.StringVar()
    pmin, pmax, smin, smax = (tk.StringVar() for _ in range(4))
    orden = tk.StringVar(value="nombre")
    descendente = tk.BooleanVar()

    ttk.Label(controles, text="Buscar").grid(row=0, column=0, sticky="w")
    consulta_entry = ttk.Entry(controles, textvariable=consulta, width=25)
    consulta_entry.grid(row=1, column=0, padx=(0, 10), sticky="ew")
    ttk.Label(controles, text="Continente").grid(row=0, column=1, sticky="w")
    ttk.Combobox(controles, textvariable=continente, values=("", *CONTINENTES), width=16).grid(row=1, column=1, padx=(0, 10))
    filtros = (
        ("Pobl. mín.", pmin), ("Pobl. máx.", pmax),
        ("Sup. mín.", smin), ("Sup. máx.", smax),
    )
    for columna, (etiqueta, variable) in enumerate(filtros, start=2):
        ttk.Label(controles, text=etiqueta).grid(row=0, column=columna, sticky="w")
        ttk.Entry(controles, textvariable=variable, width=12).grid(row=1, column=columna, padx=(0, 8))
    controles.columnconfigure(0, weight=1)

    barra = ttk.Frame(marco)
    barra.pack(fill="x", pady=12)
    ttk.Label(barra, text="Orden:").pack(side="left")
    selector_orden = ttk.Combobox(
        barra, textvariable=orden, values=("nombre", "poblacion", "superficie"),
        width=13, state="readonly",
    )
    selector_orden.pack(side="left", padx=5)
    ttk.Checkbutton(barra, text="Descendente", variable=descendente).pack(side="left", padx=6)

    columnas = ("nombre", "poblacion", "superficie", "continente")
    tabla = ttk.Treeview(marco, columns=columnas, show="headings", selectmode="browse")
    for campo, titulo, ancho, alineacion in (("nombre", "País", 240, "w"),
                                            ("poblacion", "Población", 160, "e"),
                                            ("superficie", "Superficie km²", 180, "e"),
                                            ("continente", "Continente", 150, "w")):
        tabla.heading(campo, text=titulo)
        tabla.column(campo, width=ancho, anchor=alineacion)
    tabla.pack(fill="both", expand=True)
    estado = tk.StringVar(value="Listo")
    ttk.Label(marco, textvariable=estado).pack(anchor="w", pady=(8, 0))
    descargando = False

    def proteger(accion):
        # Cada botón informa el problema sin cerrar la ventana.
        if descargando:
            estado.set("Esperá a que termine la actualización desde la API.")
            return
        try:
            avisos = repo.sincronizar()
            if avisos:
                ver(repo.paises)
                messagebox.showwarning("CSV actualizado", "\n".join(avisos), parent=raiz)
            accion()
        except ErrorPaises as exc:
            messagebox.showerror("Dato inválido", str(exc), parent=raiz)
            estado.set(str(exc))
        except Exception as exc:
            registrar_error(exc)
            messagebox.showerror("Error inesperado", "Revisá la terminal para ver el detalle. La aplicación sigue abierta.", parent=raiz)
            estado.set("Ocurrió un error inesperado.")

    def ver(paises):
        tabla.delete(*tabla.get_children())
        for p in paises:
            tabla.insert("", "end", values=(p["nombre"], f"{p['poblacion']:,}",
                                            f"{p['superficie']:,}", p["continente"]))
        estado.set(f"{len(paises)} país(es) visible(s).")

    def aplicar():
        encontrados = repo.buscar(consulta.get()) if consulta.get().strip() else repo.paises
        filtrados = repo.filtrar(continente.get(), pmin.get(), pmax.get(), smin.get(), smax.get())
        permitidos = {p["nombre"] for p in filtrados}
        ver(repo.ordenar([p for p in encontrados if p["nombre"] in permitidos], orden.get(), descendente.get()))

    def editar(es_nuevo: bool):
        elegido = tabla.selection()
        if not es_nuevo and not elegido:
            raise ErrorPaises("Seleccioná un país de la tabla para actualizar.")
        actual = tabla.item(elegido[0], "values") if elegido else ("", "", "", "")
        ventana = tk.Toplevel(raiz)
        ventana.title("Agregar país" if es_nuevo else "Actualizar país")
        ventana.transient(raiz)
        ventana.grab_set()
        formulario = ttk.Frame(ventana, padding=16)
        formulario.pack(fill="both", expand=True)
        variables = []
        for fila, (etiqueta, valor) in enumerate(zip(("Nombre", "Población", "Superficie km²", "Continente"), actual)):
            variable = tk.StringVar(value=valor.replace(",", "") if fila in (1, 2) else valor)
            variables.append(variable)
            ttk.Label(formulario, text=etiqueta).grid(row=fila, column=0, sticky="w", pady=5)
            entrada = ttk.Entry(formulario, textvariable=variable, width=30)
            entrada.grid(row=fila, column=1, pady=5)
            if not es_nuevo and fila in (0, 3):
                entrada.state(["disabled"])

        def guardar():
            def operacion():
                valores = [v.get() for v in variables]
                if es_nuevo:
                    repo.agregar(*valores)
                else:
                    repo.actualizar(valores[0], valores[1], valores[2])
                ventana.destroy()
                aplicar()
                messagebox.showinfo("Guardado", "Los datos se guardaron correctamente.", parent=raiz)

            proteger(operacion)

        ttk.Button(formulario, text="Guardar", command=guardar).grid(row=4, column=1, sticky="e", pady=(10, 0))

    def estadisticas():
        e = repo.estadisticas()
        lineas = [
            f"Mayor población: {e['mayor']['nombre']} ({e['mayor']['poblacion']:,})",
            f"Menor población: {e['menor']['nombre']} ({e['menor']['poblacion']:,})",
            f"Promedio de población: {e['promedio_poblacion']:,.2f}",
            f"Promedio de superficie: {e['promedio_superficie']:,.2f} km²",
            "",
            "Países por continente:",
        ]
        lineas.extend(f"{c}: {n}" for c, n in e["por_continente"].items())
        messagebox.showinfo("Estadísticas", "\n".join(lineas), parent=raiz)

    boton_api = ttk.Button(barra, text="Actualizar API")

    def descargar():
        # La red trabaja en otro hilo; la ventana se modifica solo desde el hilo principal.
        nonlocal descargando
        descargando = True
        boton_api.state(["disabled"])
        estado.set("Consultando la API del Banco Mundial…")
        resultados = queue.Queue()

        def tarea():
            try:
                cantidad = repo.actualizar_desde_api()
                resultados.put((f"Se actualizaron {cantidad} países.", True))
            except Exception as exc:
                if not isinstance(exc, ErrorPaises):
                    registrar_error(exc)
                mensaje = str(exc) if isinstance(exc, ErrorPaises) else "Error inesperado. Revisá la terminal."
                resultados.put((mensaje, False))

        threading.Thread(target=tarea, daemon=True).start()

        def revisar_resultado():
            try:
                mensaje, exito = resultados.get_nowait()
            except queue.Empty:
                raiz.after(100, revisar_resultado)
            else:
                terminar(mensaje, exito)

        raiz.after(100, revisar_resultado)

    def terminar(mensaje, exito):
        nonlocal descargando
        descargando = False
        boton_api.state(["!disabled"])
        estado.set(mensaje)
        if exito:
            proteger(aplicar)
            messagebox.showinfo("API", mensaje, parent=raiz)
        else:
            messagebox.showerror("API", mensaje, parent=raiz)

    ttk.Button(barra, text="Aplicar búsqueda y filtros", command=lambda: proteger(aplicar)).pack(side="left", padx=9)
    ttk.Button(barra, text="Agregar", command=lambda: proteger(lambda: editar(True))).pack(side="left", padx=3)
    ttk.Button(barra, text="Actualizar", command=lambda: proteger(lambda: editar(False))).pack(side="left", padx=3)
    ttk.Button(barra, text="Estadísticas", command=lambda: proteger(estadisticas)).pack(side="left", padx=3)
    boton_api.configure(command=lambda: proteger(descargar))
    boton_api.pack(side="right")
    consulta_entry.bind("<Return>", lambda _evento: proteger(aplicar))
    proteger(aplicar)
    if repo.advertencias:
        estado.set("; ".join(repo.advertencias))
        messagebox.showwarning("Problema en el CSV", "\n".join(repo.advertencias), parent=raiz)
    raiz.mainloop()

# Menú de consola y punto de entrada

RUTA_CSV = Path(__file__).with_name("paises.csv")


def mostrar(paises: list[dict]) -> None:
    # Mostramos siempre una salida completa y legible, incluso cuando está vacía.
    if not paises:
        print("No se encontraron países.")
        return
    ancho_nombre = max(24, *(len(p["nombre"]) for p in paises))
    print(f"{'País':<{ancho_nombre}} {'Población':>14} {'Superficie km²':>16}  Continente")
    print("-" * (ancho_nombre + 51))
    for p in paises:
        print(f"{p['nombre']:<{ancho_nombre}} {p['poblacion']:>14,} {p['superficie']:>16,}  {p['continente']}")
    print(f"Total: {len(paises)} país(es).")


def pedir(texto: str) -> str:
    return input(texto).strip()


def consola(repo: Repositorio) -> None:
    for aviso in repo.advertencias:
        print("AVISO:", aviso)
    acciones = {
        "1": "Listar", "2": "Agregar", "3": "Actualizar", "4": "Buscar",
        "5": "Filtrar", "6": "Ordenar", "7": "Estadísticas",
        "8": "Actualizar desde API", "0": "Salir",
    }
    while True:
        # El bucle principal captura fallos por operación y permite volver al menú.
        print("\n=== GESTIÓN DE PAÍSES ===")
        for clave, nombre in acciones.items():
            print(f"{clave}. {nombre}")
        try:
            opcion = pedir("Opción: ")
            if opcion == "0":
                print("Hasta luego.")
                return
            for aviso in repo.sincronizar():
                print("AVISO:", aviso)
            if opcion == "1":
                mostrar(repo.paises)
            elif opcion == "2":
                nombre = pedir("Nombre: ")
                poblacion = pedir("Población: ")
                superficie = pedir("Superficie km²: ")
                continente = pedir("Continente: ")
                pais = repo.agregar(nombre, poblacion, superficie, continente)
                print(f"Se agregó {pais['nombre']}.")
            elif opcion == "3":
                nombre = pedir("Nombre exacto: ")
                poblacion = pedir("Nueva población: ")
                superficie = pedir("Nueva superficie km²: ")
                pais = repo.actualizar(nombre, poblacion, superficie)
                print(f"Se actualizó {pais['nombre']}.")
            elif opcion == "4":
                mostrar(repo.buscar(pedir("Nombre o parte del nombre: ")))
            elif opcion == "5":
                mostrar(repo.filtrar(
                    pedir("Continente (vacío = todos): "),
                    pedir("Población mínima (vacío = sin límite): "),
                    pedir("Población máxima (vacío = sin límite): "),
                    pedir("Superficie mínima (vacío = sin límite): "),
                    pedir("Superficie máxima (vacío = sin límite): "),
                ))
            elif opcion == "6":
                campo = pedir("Ordenar por nombre/poblacion/superficie: ").lower()
                descendente = pedir("¿Descendente? s/n: ").lower()
                if descendente not in ("s", "n"):
                    raise ErrorPaises("Respondé s o n para el orden.")
                mostrar(repo.ordenar(repo.paises, campo, descendente == "s"))
            elif opcion == "7":
                e = repo.estadisticas()
                print(f"Mayor población: {e['mayor']['nombre']} ({e['mayor']['poblacion']:,})")
                print(f"Menor población: {e['menor']['nombre']} ({e['menor']['poblacion']:,})")
                print(f"Promedio de población: {e['promedio_poblacion']:,.2f}")
                print(f"Promedio de superficie: {e['promedio_superficie']:,.2f} km²")
                print("Países por continente:")
                for continente, cantidad in e["por_continente"].items():
                    print(f"  {continente}: {cantidad}")
            elif opcion == "8":
                print(f"Se actualizaron {repo.actualizar_desde_api()} países desde la API.")
            else:
                print("Opción inválida. Elegí un número del menú.")
        except ErrorPaises as exc:
            print("ERROR:", exc)
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            return
        except Exception as exc:
            registrar_error(exc)
            print("ERROR inesperado. Revisá la terminal; podés seguir usando el menú.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gestión de datos de países")
    parser.add_argument("--gui", action="store_true", help="Abrir ventana Tkinter")
    parser.add_argument("--csv", type=Path, default=RUTA_CSV, help="Ruta del CSV")
    args = parser.parse_args()
    logging.basicConfig(stream=sys.stderr, level=logging.ERROR,
                        format="%(asctime)s %(levelname)s %(message)s")
    repo = Repositorio(args.csv)
    if args.gui:
        try:
            iniciar(repo)
        except ImportError as exc:
            print(f"No se pudo cargar Tkinter: {exc}.")
            print("En Linux Mint/Ubuntu instalalo con: sudo apt install python3-tk")
            print("Se usará la consola.")
            consola(repo)
        except RuntimeError as exc:
            print(f"No se pudo abrir la ventana: {exc}. Se usará la consola.")
            consola(repo)
    else:
        consola(repo)


if __name__ == "__main__":
    main()
