"""Empaqueta la compilación --onedir de PyInstaller en un archivo .msix para Microsoft Store."""

import glob
import os
import shutil
import subprocess
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPainter

from ui.constantes import ARCHIVO_ICONO, ARCHIVO_ICONO_PROYECTO, VERSION_APP


STORE_IDENTITY_NAME = "Acev.SimuladordeFlujodeFluidos"
STORE_PUBLISHER = "CN=E49B1B25-A598-4EE0-B664-8724308773D3"
STORE_PUBLISHER_DISPLAY = "Acev"
STORE_DISPLAY_NAME = "Simulador de Flujo de Fluidos"


def _normalizar_version_msix(version_app):
    """Convierte '1.0.1' en formato de 4 partes '1.0.1.0' exigido por MSIX."""
    partes = [p for p in str(version_app).strip().lstrip("vV").split(".") if p.isdigit()]
    while len(partes) < 3:
        partes.append("0")
    return f"{partes[0]}.{partes[1]}.{partes[2]}.0"


def _generar_png_centrado(ruta_origen, ruta_destino, ancho, alto, margen=0.1):
    """Renderiza un ícono centrado en un lienzo transparente con tamaño exacto."""
    origen = QImage(ruta_origen)
    if origen.isNull():
        raise FileNotFoundError(f"No se pudo cargar el ícono: {ruta_origen}")

    lienzo = QImage(ancho, alto, QImage.Format_ARGB32)
    lienzo.fill(Qt.transparent)

    lado_max = int(min(ancho, alto) * (1.0 - 2 * margen))
    escalado = origen.scaled(lado_max, lado_max, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    x = (ancho - escalado.width()) // 2
    y = (alto - escalado.height()) // 2

    pintor = QPainter(lienzo)
    pintor.drawImage(x, y, escalado)
    pintor.end()
    if not lienzo.save(ruta_destino, "PNG"):
        raise OSError(f"No se pudo guardar {ruta_destino}")


def _buscar_makeappx():
    """Encuentra makeappx.exe del Windows 10/11 SDK."""
    en_path = shutil.which("makeappx.exe")
    if en_path:
        return en_path

    patron = os.path.join(
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        "Windows Kits",
        "10",
        "bin",
        "*",
        "x64",
        "makeappx.exe",
    )
    candidatos = sorted(glob.glob(patron), reverse=True)
    if candidatos:
        return candidatos[0]
    raise FileNotFoundError(
        "No se encontró makeappx.exe. Instala Windows 10/11 SDK para empaquetar MSIX."
    )


def construir_manifest(version_msix):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap rescap">

  <Identity
    Name="{STORE_IDENTITY_NAME}"
    Publisher="{STORE_PUBLISHER}"
    Version="{version_msix}"
    ProcessorArchitecture="x64" />

  <Properties>
    <DisplayName>{STORE_DISPLAY_NAME}</DisplayName>
    <PublisherDisplayName>{STORE_PUBLISHER_DISPLAY}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>

  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.19041.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>

  <Resources>
    <Resource Language="es" />
  </Resources>

  <Applications>
    <Application
      Id="App"
      Executable="app\\Simulador_Flujo_de_Fluidos.exe"
      EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="{STORE_DISPLAY_NAME}"
        Description="Simulador hidráulico CAD para diseño de redes de tuberías y sistemas de bombeo."
        BackgroundColor="transparent"
        Square150x150Logo="Assets\\Square150x150Logo.png"
        Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="Assets\\Wide310x150Logo.png" />
      </uap:VisualElements>
      <Extensions>
        <uap:Extension Category="windows.fileTypeAssociation">
          <uap:FileTypeAssociation Name="simuladorflujofluidos_sff">
            <uap:DisplayName>Proyecto de Simulador de Flujo de Fluidos</uap:DisplayName>
            <uap:Logo>Assets\\GotaLogo.png</uap:Logo>
            <uap:SupportedFileTypes>
              <uap:FileType ContentType="application/json">.sff</uap:FileType>
            </uap:SupportedFileTypes>
          </uap:FileTypeAssociation>
        </uap:Extension>
      </Extensions>
    </Application>
  </Applications>

  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""


def empaquetar_msix(version_app=VERSION_APP):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    origen_onedir = os.path.join(base_dir, "dist", "Simulador_Flujo_de_Fluidos")
    exe_origen = os.path.join(origen_onedir, "Simulador_Flujo_de_Fluidos.exe")
    if not os.path.isfile(exe_origen):
        raise FileNotFoundError(
            "No existe dist/Simulador_Flujo_de_Fluidos. Ejecuta primero `python build_exe.py`."
        )

    version_msix = _normalizar_version_msix(version_app)
    staging_dir = os.path.join(base_dir, "build", "msix")
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)

    assets_dir = os.path.join(staging_dir, "Assets")
    app_dir = os.path.join(staging_dir, "app")
    os.makedirs(assets_dir, exist_ok=True)
    shutil.copytree(origen_onedir, app_dir)

    from PyQt5.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    _generar_png_centrado(ARCHIVO_ICONO, os.path.join(assets_dir, "StoreLogo.png"), 50, 50, margen=0.06)
    _generar_png_centrado(ARCHIVO_ICONO, os.path.join(assets_dir, "Square44x44Logo.png"), 44, 44, margen=0.06)
    _generar_png_centrado(ARCHIVO_ICONO, os.path.join(assets_dir, "Square150x150Logo.png"), 150, 150, margen=0.10)
    _generar_png_centrado(ARCHIVO_ICONO, os.path.join(assets_dir, "Wide310x150Logo.png"), 310, 150, margen=0.12)
    _generar_png_centrado(ARCHIVO_ICONO_PROYECTO, os.path.join(assets_dir, "GotaLogo.png"), 44, 44, margen=0.06)

    manifest_path = os.path.join(staging_dir, "AppxManifest.xml")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(construir_manifest(version_msix))

    salida_dir = os.path.join(base_dir, "dist", "store")
    os.makedirs(salida_dir, exist_ok=True)
    salida_msix = os.path.join(salida_dir, f"Simulador_Flujo_de_Fluidos_{version_msix}_x64.msix")

    makeappx = _buscar_makeappx()
    print(f"Empaquetando MSIX con {makeappx}...")
    subprocess.run(
        [makeappx, "pack", "/o", "/d", staging_dir, "/p", salida_msix],
        check=True,
    )
    size_mb = os.path.getsize(salida_msix) / (1024 * 1024)
    print(f"Paquete MSIX generado: {salida_msix} ({size_mb:.2f} MB)")
    return salida_msix


if __name__ == "__main__":
    ver = sys.argv[1] if len(sys.argv) > 1 else VERSION_APP
    empaquetar_msix(ver)
