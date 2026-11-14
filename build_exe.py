"""Script para compilar el Simulador de Flujo de Fluidos a un ejecutable independiente (.exe) usando PyInstaller."""

import os
import shutil
import sys
import PyInstaller.__main__

def compilar():
    print("Iniciando compilación con PyInstaller...")
    print(f"Python: {sys.version}")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    # Argumentos de PyInstaller
    args = [
        "main.py",
        "--name=Simulador_Flujo_de_Fluidos",
        "--onefile",
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
    
    exe_path = os.path.join(base_dir, "dist", "Simulador_Flujo_de_Fluidos.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"\n=======================================================")
        print(f"¡Compilación exitosa!")
        print(f"Ejecutable generado: {exe_path}")
        print(f"Tamaño: {size_mb:.2f} MB")
        print(f"=======================================================\n")
    else:
        print("\nERROR: No se encontró el ejecutable en dist/")
        sys.exit(1)

if __name__ == "__main__":
    compilar()
