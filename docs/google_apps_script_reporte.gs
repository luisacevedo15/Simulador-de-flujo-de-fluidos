/**
 * Script de Google Apps Script para recibir reportes de error con foto adjunta
 * desde el Simulador de Flujo de Fluidos y enviarlos a luis.acevedos@unmsm.edu.pe.
 *
 * Pasos (1 minuto):
 * 1. Abre https://script.google.com con tu cuenta y crea un "Nuevo proyecto".
 * 2. Pega este código reemplazando el contenido de Código.gs.
 * 3. Haz clic en "Implementar" > "Nueva implementación" > Tipo: "Aplicación web".
 * 4. En "Ejecutar como" elige "Yo" y en "Quién tiene acceso" elige "Cualquier persona".
 * 5. Copia la URL generada (https://script.google.com/macros/s/.../exec) y pégala en
 *    `URL_WEBHOOK_REPORTE` dentro de `ui/constantes.py`.
 */
function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents || "{}");
    var destinatario = "luis.acevedos@unmsm.edu.pe";
    var asunto = data.asunto || "[Simulador de Fluidos] Reporte de error";
    var cuerpo = [
      "Nuevo reporte de error desde Simulador de Flujo de Fluidos",
      "----------------------------------------------------------",
      "Versión: " + (data.version || "N/D"),
      "Sistema: " + (data.plataforma || "N/D"),
      "Contacto del usuario: " + (data.contacto || "No especificado"),
      "",
      "Descripción:",
      data.descripcion || "(Sin descripción)"
    ].join("\n");

    var opciones = { name: "Simulador de Flujo de Fluidos" };
    if (data.imagen_base64) {
      var bytes = Utilities.base64Decode(data.imagen_base64);
      var mime = data.mime_imagen || "image/png";
      var nombre = data.nombre_imagen || "captura_error.png";
      opciones.attachments = [Utilities.newBlob(bytes, mime, nombre)];
    }

    MailApp.sendEmail(destinatario, asunto, cuerpo, opciones);
    return ContentService
      .createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
