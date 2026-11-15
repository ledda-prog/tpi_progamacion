import argparse
import csv
import os
from tempfile import NamedTemporaryFile
from pathlib import Path

CAMPOS = ["nombre", "poblacion", "superficie", "continente"]
RUTA_CSV = Path(__file__).with_name("paises.csv")


def normalizar(texto):
    texto = texto.lower().strip()
    con_tilde = "áéíóúü"
    sin_tilde = "aeiouu"
    for i in range(len(con_tilde)):
        texto = texto.replace(con_tilde[i], sin_tilde[i])
    return " ".join(texto.split())


def validar_entero(texto, campo, minimo=0):
    try:
        numero = int(texto)
    except ValueError:
        raise ValueError(f"{campo}: ingresá un número entero.")

    if numero < minimo:
        raise ValueError(f"{campo}: ingresá un número mayor o igual a {minimo}.")
    return numero


def crear_pais(nombre, poblacion, superficie, continente):
    nombre = " ".join(nombre.split())
    continente = " ".join(continente.split())
    if not nombre or not continente:
        raise ValueError("El nombre y el continente son obligatorios.")

    pais = {
        "nombre": nombre,
        "poblacion": validar_entero(poblacion, "Población"),
        "superficie": validar_entero(superficie, "Superficie", 1),
        "continente": continente,
    }
    return pais


def buscar_indice(paises, nombre):
    nombre = normalizar(nombre)
    for i in range(len(paises)):
        if normalizar(paises[i]["nombre"]) == nombre:
            return i
    return -1


def cargar_paises(ruta):
    paises = []
    try:
        with open(ruta, encoding="utf-8-sig", newline="") as archivo:
            lector = csv.DictReader(archivo, strict=True)
            if lector.fieldnames != CAMPOS:
                raise ValueError("Revisá los encabezados de paises.csv.")

            for fila in lector:
                try:
                    if None in fila or None in fila.values():
                        raise ValueError("Cantidad incorrecta de columnas.")
                    pais = crear_pais(fila["nombre"], fila["poblacion"],
                                      fila["superficie"], fila["continente"])
                    if buscar_indice(paises, pais["nombre"]) != -1:
                        raise ValueError("El país está repetido.")
                except ValueError as error:
                    raise ValueError(f"Fila {lector.line_num} del CSV: {error}")
                paises.append(pais)
    except FileNotFoundError:
        return []
    return paises


def guardar_paises(ruta, paises, nuevos):
    # Guardamos en un archivo temporal para proteger el CSV original.
    temporal = NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                  dir=ruta.parent, delete=False)
    try:
        with temporal:
            escritor = csv.DictWriter(temporal, fieldnames=CAMPOS)
            escritor.writeheader()
            escritor.writerows(nuevos)
        if cargar_paises(ruta) != paises:
            raise ValueError("El CSV cambió. Volvé a abrir el programa y repetí el cambio.")
        os.replace(temporal.name, ruta)
    finally:
        Path(temporal.name).unlink(missing_ok=True)


def agregar_pais(paises, ruta, nombre, poblacion, superficie, continente):
    pais = crear_pais(nombre, poblacion, superficie, continente)
    if buscar_indice(paises, pais["nombre"]) != -1:
        raise ValueError("Ese país ya existe.")

    nuevos = paises.copy()
    nuevos.append(pais)
    guardar_paises(ruta, paises, nuevos)
    paises.append(pais)


def actualizar_pais(paises, ruta, nombre, poblacion, superficie):
    indice = buscar_indice(paises, nombre)
    if indice == -1:
        raise ValueError("No se encontró ese país. Escribí el nombre completo.")

    actual = paises[indice]
    pais = crear_pais(actual["nombre"], poblacion, superficie, actual["continente"])
    nuevos = paises.copy()
    nuevos[indice] = pais
    guardar_paises(ruta, paises, nuevos)
    paises[indice] = pais


def buscar_paises(paises, texto):
    texto = normalizar(texto)
    encontrados = []
    for pais in paises:
        if texto in normalizar(pais["nombre"]):
            encontrados.append(pais)
    return encontrados


def leer_limite(texto, campo):
    if not texto.strip():
        return None
    return validar_entero(texto, campo)


def filtrar_paises(paises, continente, pob_min, pob_max, sup_min, sup_max):
    continente = normalizar(continente)
    pob_min = leer_limite(pob_min, "Población mínima")
    pob_max = leer_limite(pob_max, "Población máxima")
    sup_min = leer_limite(sup_min, "Superficie mínima")
    sup_max = leer_limite(sup_max, "Superficie máxima")

    if pob_min is not None and pob_max is not None and pob_min > pob_max:
        raise ValueError("La población mínima supera la máxima.")
    if sup_min is not None and sup_max is not None and sup_min > sup_max:
        raise ValueError("La superficie mínima supera la máxima.")

    filtrados = []
    for pais in paises:
        if continente and normalizar(pais["continente"]) != continente:
            continue
        if pob_min is not None and pais["poblacion"] < pob_min:
            continue
        if pob_max is not None and pais["poblacion"] > pob_max:
            continue
        if sup_min is not None and pais["superficie"] < sup_min:
            continue
        if sup_max is not None and pais["superficie"] > sup_max:
            continue
        filtrados.append(pais)
    return filtrados


def ordenar_paises(paises, campo, descendente=False):
    if campo == "nombre":
        return sorted(paises, key=lambda pais: normalizar(pais["nombre"]), reverse=descendente)
    if campo in ["poblacion", "superficie"]:
        return sorted(paises, key=lambda pais: pais[campo], reverse=descendente)
    raise ValueError("Elegí nombre, poblacion o superficie.")


def estadisticas(paises):
    if not paises:
        return "No hay países para calcular estadísticas."

    mayor = paises[0]
    menor = paises[0]
    total_poblacion = 0
    total_superficie = 0
    por_continente = {}

    for pais in paises:
        poblacion = pais["poblacion"]
        continente = pais["continente"]
        if poblacion > mayor["poblacion"]:
            mayor = pais
        if poblacion < menor["poblacion"]:
            menor = pais
        total_poblacion += poblacion
        total_superficie += pais["superficie"]
        por_continente[continente] = por_continente.get(continente, 0) + 1

    mensaje = f"Mayor población: {mayor['nombre']} ({mayor['poblacion']})\n"
    mensaje += f"Menor población: {menor['nombre']} ({menor['poblacion']})\n"
    mensaje += f"Promedio de población: {total_poblacion / len(paises):.2f}\n"
    mensaje += f"Promedio de superficie: {total_superficie / len(paises):.2f} km²\n"
    mensaje += "\nPaíses por continente:\n"
    for continente in sorted(por_continente):
        mensaje += f"{continente}: {por_continente[continente]}\n"
    return mensaje


def mostrar_paises(paises):
    for pais in paises:
        print(f"{pais['nombre']} | {pais['poblacion']} hab. | "
              f"{pais['superficie']} km² | {pais['continente']}")
    print(f"Países encontrados: {len(paises)}")


def consola(paises, ruta):
    while True:
        print("\n1. Listar\n2. Agregar\n3. Actualizar\n4. Buscar\n"
              "5. Filtrar\n6. Ordenar\n7. Estadísticas\n0. Salir")
        try:
            opcion = input("Opción: ").strip()
            if opcion == "0":
                break
            elif opcion == "1":
                mostrar_paises(paises)
            elif opcion == "2":
                nombre = input("Nombre: ")
                poblacion = input("Población: ")
                superficie = input("Superficie en km²: ")
                continente = input("Continente: ")
                agregar_pais(paises, ruta, nombre, poblacion, superficie, continente)
                print("País agregado.")
            elif opcion == "3":
                nombre = input("Nombre completo: ")
                poblacion = input("Nueva población: ")
                superficie = input("Nueva superficie en km²: ")
                actualizar_pais(paises, ruta, nombre, poblacion, superficie)
                print("País actualizado.")
            elif opcion == "4":
                texto = input("Nombre o parte del nombre: ")
                mostrar_paises(buscar_paises(paises, texto))
            elif opcion == "5":
                print("Dejá en blanco los campos que no quieras filtrar.")
                continente = input("Continente: ")
                pob_min = input("Población mínima: ")
                pob_max = input("Población máxima: ")
                sup_min = input("Superficie mínima: ")
                sup_max = input("Superficie máxima: ")
                mostrar_paises(filtrar_paises(paises, continente, pob_min, pob_max, sup_min, sup_max))
            elif opcion == "6":
                campo = normalizar(input("Ordenar por nombre, poblacion o superficie: "))
                orden = normalizar(input("¿Descendente? (s/n): "))
                if orden not in ["s", "n"]:
                    raise ValueError("Ingresá s o n.")
                mostrar_paises(ordenar_paises(paises, campo, orden == "s"))
            elif opcion == "7":
                print(estadisticas(paises))
            else:
                print("Opción inválida.")
        except (ValueError, OSError, csv.Error) as error:
            print(f"Error: {error}")
        except (EOFError, KeyboardInterrupt):
            break


def ventana(paises, ruta):
    import tkinter as tk
    from tkinter import messagebox, ttk

    try:
        raiz = tk.Tk()
    except tk.TclError as error:
        raise RuntimeError(str(error))
    raiz.title("Gestión de países")
    raiz.geometry("860x540")

    filtros = ttk.Frame(raiz, padding=10)
    filtros.pack(fill="x")
    etiquetas = ["Buscar", "Continente", "Pobl. mínima", "Pobl. máxima",
                 "Sup. mínima", "Sup. máxima"]
    entradas = []
    for i in range(len(etiquetas)):
        ttk.Label(filtros, text=etiquetas[i]).grid(row=0, column=i, sticky="w")
        entrada = ttk.Entry(filtros, width=17)
        entrada.grid(row=1, column=i, padx=(0, 6))
        entradas.append(entrada)

    botones = ttk.Frame(raiz, padding=10)
    botones.pack(fill="x")
    ttk.Label(botones, text="Orden").pack(side="left")
    orden = ttk.Combobox(botones, values=CAMPOS[:3], state="readonly", width=12)
    orden.set("nombre")
    orden.pack(side="left", padx=4)
    descendente = tk.BooleanVar()
    ttk.Checkbutton(botones, text="Descendente", variable=descendente).pack(side="left")

    listado = ttk.Frame(raiz, padding=(10, 0))
    listado.pack(fill="both", expand=True)
    tabla = ttk.Treeview(listado, columns=CAMPOS, show="headings", selectmode="browse")
    titulos = ["País", "Población", "Superficie (km²)", "Continente"]
    for i in range(len(CAMPOS)):
        tabla.heading(CAMPOS[i], text=titulos[i])
        tabla.column(CAMPOS[i], width=150)
    barra = ttk.Scrollbar(listado, orient="vertical", command=tabla.yview)
    tabla.configure(yscrollcommand=barra.set)
    barra.pack(side="right", fill="y")
    tabla.pack(side="left", fill="both", expand=True)

    estado = ttk.Label(raiz, padding=10)
    estado.pack(anchor="w")

    def mostrar():
        try:
            encontrados = buscar_paises(paises, entradas[0].get())
            filtrados = filtrar_paises(encontrados, entradas[1].get(), entradas[2].get(),
                                      entradas[3].get(), entradas[4].get(), entradas[5].get())
            resultados = ordenar_paises(filtrados, orden.get(), descendente.get())
        except ValueError as error:
            messagebox.showerror("Revisá los filtros", str(error), parent=raiz)
            return

        for fila in tabla.get_children():
            tabla.delete(fila)
        for pais in resultados:
            tabla.insert("", "end", values=(pais["nombre"], pais["poblacion"],
                                            pais["superficie"], pais["continente"]))
        estado.config(text=f"Países encontrados: {len(resultados)}")

    def formulario(nuevo):
        valores = ["", "", "", ""]
        if not nuevo:
            seleccion = tabla.selection()
            if not seleccion:
                messagebox.showinfo("Actualizar", "Seleccioná un país de la tabla.", parent=raiz)
                return
            valores = tabla.item(seleccion[0], "values")

        dialogo = tk.Toplevel(raiz)
        dialogo.title("Agregar país" if nuevo else "Actualizar país")
        dialogo.transient(raiz)
        dialogo.grab_set()
        campos = []
        for i in range(len(titulos)):
            ttk.Label(dialogo, text=titulos[i]).grid(row=i, column=0, padx=10, pady=6)
            entrada = ttk.Entry(dialogo, width=30)
            entrada.grid(row=i, column=1, padx=10, pady=6)
            entrada.insert(0, valores[i])
            if not nuevo and i in [0, 3]:
                entrada.config(state="readonly")
            campos.append(entrada)

        def guardar():
            try:
                nombre = campos[0].get()
                poblacion = campos[1].get()
                superficie = campos[2].get()
                if nuevo:
                    agregar_pais(paises, ruta, nombre, poblacion, superficie, campos[3].get())
                else:
                    actualizar_pais(paises, ruta, nombre, poblacion, superficie)
            except (ValueError, OSError, csv.Error) as error:
                messagebox.showerror("No se pudo guardar", str(error), parent=dialogo)
                return
            dialogo.destroy()
            mostrar()

        ttk.Button(dialogo, text="Guardar", command=guardar).grid(row=4, column=1, pady=8)

    def ver_estadisticas():
        messagebox.showinfo("Estadísticas", estadisticas(paises), parent=raiz)

    ttk.Button(botones, text="Aplicar", command=mostrar).pack(side="left", padx=4)
    ttk.Button(botones, text="Agregar", command=lambda: formulario(True)).pack(side="left", padx=4)
    ttk.Button(botones, text="Actualizar", command=lambda: formulario(False)).pack(side="left", padx=4)
    ttk.Button(botones, text="Estadísticas", command=ver_estadisticas).pack(side="left", padx=4)
    entradas[0].bind("<Return>", lambda evento: mostrar())
    mostrar()
    raiz.mainloop()


def main():
    parser = argparse.ArgumentParser(description="Gestión de países")
    parser.add_argument("--gui", action="store_true", help="Abrir la ventana de Tkinter")
    parser.add_argument("--csv", type=Path, default=RUTA_CSV, help="Usar otro archivo CSV")
    args = parser.parse_args()

    try:
        paises = cargar_paises(args.csv)
    except (OSError, ValueError, csv.Error) as error:
        print(f"No se pudo cargar el CSV: {error}")
        return

    if args.gui:
        try:
            ventana(paises, args.csv)
            return
        except ImportError:
            print("Tkinter no está instalado. Se abrirá el menú de consola.")
        except RuntimeError as error:
            print(f"No se pudo abrir la ventana: {error}")
    consola(paises, args.csv)


if __name__ == "__main__":
    main()
