"""Script para compilar el Simulador de Flujo de Fluidos usando PyInstaller.

Por defecto compila en modo carpeta (--onedir), ideal para empaquetar con
Inno Setup (instalador.iss) y minimizar falsos positivos de antivirus.
Usa `--onefile` si necesitas un único ejecutable portátil.
"""

import os
import sys
import PyInstaller.__main__


def compilar(onefile=False):
    modo = "--onefile" if onefile else "--onedir"
    print(f"Iniciando compilación con PyInstaller ({modo})...")
    print(f"Python: {sys.version}")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    args = [
        "main.py",
        "--name=Simulador_Flujo_de_Fluidos",
        modo,
        "--windowed",
        "--icon=logo_1.ico",
        "--add-data=logo_1.ico;.",
        "--add-data=Gota_archivo_para_los_json.ico;.",
        "--add-data=logo_2.jpg;.",
        "--add-data=logo_3.png;.",
        "--add-data=Recto.mp4;.",
        "--add-data=Ortogonal.mp4;.",
        "--clean",
        "--noconfirm",
    ]

    print("Ejecutando PyInstaller con argumentos:", args)
    PyInstaller.__main__.run(args)

    exe_path = (
        os.path.join(base_dir, "dist", "Simulador_Flujo_de_Fluidos.exe")
        if onefile
        else os.path.join(
            base_dir, "dist", "Simulador_Flujo_de_Fluidos", "Simulador_Flujo_de_Fluidos.exe"
        )
    )
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print("\n=======================================================")
        print("¡Compilación exitosa!")
        print(f"Ejecutable generado: {exe_path}")
        print(f"Tamaño del ejecutable: {size_mb:.2f} MB")
        print("=======================================================\n")
    else:
        print("\nERROR: No se encontró el ejecutable generado en dist/")
        sys.exit(1)


if __name__ == "__main__":
    compilar(onefile="--onefile" in sys.argv[1:])
