# Gestión de datos de países en Python

Trabajo Práctico Integrador de **Programación 1** para la Tecnicatura Universitaria en Programación de la Universidad Tecnológica Nacional (UTN).

## Descripción del proyecto

Esta aplicación permite consultar y gestionar información de países. Los datos se cargan desde un archivo CSV y cada registro contiene el nombre, la población, la superficie en km² y el continente.

El programa se puede utilizar desde un menú de consola o mediante una ventana gráfica. Esta última se incorporó como funcionalidad adicional al trabajo práctico.

## Funcionalidades

- Listar los países registrados.
- Agregar un país con sus datos y actualizar la población y la superficie de un país existente.
- Buscar países por nombre completo o por una parte del nombre.
- Filtrar por continente y por rangos de población y superficie. Los criterios se pueden combinar.
- Ordenar por nombre, población o superficie, de manera ascendente o descendente.
- Mostrar estadísticas: país con mayor y menor población, promedios de población y superficie y cantidad de países por continente.
- Validar datos de entrada y mostrar mensajes cuando se detecta un error.

La aplicación normaliza el texto para las búsquedas y los filtros por continente, de modo que se pueden ingresar diferencias de mayúsculas o tildes.

## Archivos del proyecto

```text
README.md                       Descripción e instrucciones
paises.py                       Código fuente de la aplicación
paises.csv                      Datos de los países
Informe_TPI_Programacion_1.pdf  Informe académico y técnico
```

El archivo CSV tiene los encabezados `nombre,poblacion,superficie,continente`. El informe debe estar en la raíz del repositorio para que el enlace incluido más abajo funcione.

## Requisitos

- Python 3.x instalado.
- Para la interfaz gráfica, una instalación de Python que incluya Tkinter y un entorno capaz de abrir ventanas.
- No se requieren paquetes externos: se utilizan módulos de la biblioteca estándar de Python.

## Instrucciones de uso

1. Descargá el repositorio y ubicá `paises.py` y `paises.csv` en la misma carpeta.
2. Abrí una terminal en esa carpeta.
3. Para iniciar el menú de consola, ejecutá:

   ```bash
   python paises.py
   ```

4. Para abrir la ventana gráfica, ejecutá:

   ```bash
   python paises.py --gui
   ```

Según la instalación, puede ser necesario reemplazar `python` por `python3` o `py`. Si Tkinter no está disponible o no se puede abrir la ventana, el programa intenta continuar en consola.

En la consola, ingresá el número de la operación y seguí las indicaciones. En la ventana gráfica, utilizá los campos, la tabla y los botones para realizar las consultas o modificar datos. Para actualizar un país desde la ventana, primero seleccionalo en la tabla.

## Ejemplos de entrada y salida

### Búsqueda parcial en consola

```text
Opción: 4
Nombre o parte del nombre: arge
Argelia | 47435312 hab. | 2381740 km² | África
Argentina | 45851378 hab. | 2736690 km² | América
Países encontrados: 2
```

### Filtro por continente

En la ventana gráfica, escribí `america` en el campo **Continente** y presioná **Aplicar**. Con el conjunto de datos utilizado en la demostración, la tabla muestra 35 países de América. Para usar filtros de población o superficie, ingresá los límites que necesites; los campos vacíos no restringen la búsqueda.

Los resultados pueden cambiar si se agregan o actualizan registros del CSV.

## Video demostrativo

[Ver el video explicativo del programa](https://youtu.be/gOF1OZbHLng)

## Informe académico

[Abrir el informe en PDF](Informe_TPI_Programacion_1.pdf)

## Integrantes y participación

Todos los integrantes participaron en el desarrollo del código, con mayor protagonismo de Ignacio Ledda. Además, las tareas se distribuyeron de la siguiente manera:

- **Ignacio Ledda:** participación principal en el desarrollo del código.
- **Santiago Zorrilla:** desarrollo de la interfaz gráfica con Tkinter.
- **Diego Robledo:** realización del video explicativo.
- **Máximo Quiroga:** elaboración del informe académico y técnico.

## Docentes

Ramiro Hualpa y Cinthia Rigoni.
