"""Componentes HTML para los reportes de resultados."""

from ui.curvas_presentacion import usa_puntos,puntos_total,resumen_puntos,curvas_estacion

import math
from html import escape


RPT_AZUL = "#0c4e77"


RPT_SECUNDARIO = "#006398"


RPT_VERDE = "#16a34a"


RPT_ROJO = "#ba1a1a"


RPT_NARANJA = "#d97706"


RPT_TEXTO = "#0b1c30"


RPT_SUAVE = "#72787f"


RPT_FONDO = "#f2f6ff"


RPT_CABECERA = "#e2e8f0"


_RPT_TONOS = {
    "ok": ("#006398", "#f2f6ff", "#0c4e77", "✓", "VÁLIDO", "#e5eeff", "#006398"),
    "error": ("#ba1a1a", "#fff5f5", "#93000a", "✕", "ERROR", "#ffdad6", "#93000a"),
    "aviso": ("#d97706", "#fffbeb", "#92400e", "!", "ADVERTENCIA", "#fef3c7", "#b45309"),
    "info": ("#006398", "#f2f6ff", "#0c4e77", "i", "INFO", "#e5eeff", "#006398"),
}


_SUPERSCRIPTS = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")


def formatear_reynolds_html(re_val):
    if re_val <= 0 or not math.isfinite(re_val):
        return "0"
    exp = int(math.floor(math.log10(abs(re_val))))
    mant = re_val / (10 ** exp)
    exp_sup = str(exp).translate(_SUPERSCRIPTS)
    return f"{mant:.2f}×10{exp_sup}"


def rpt_espacio(px=6):
    return f"<p style='margin:0; font-size:{px}px;'>&nbsp;</p>"


def rpt_encabezado(icono, titulo, subtitulo="", color=RPT_AZUL):
    sub = (
        f"<br><span style='font-size:11px; color:#ecf3f9;'>{subtitulo}</span>"
        if subtitulo
        else ""
    )
    return (
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td bgcolor='{color}' style='padding:10px 14px;'>"
        f"<span style='font-size:15px; font-weight:bold; color:#ffffff;'>"
        f"{icono}&nbsp;{titulo}</span>{sub}</td></tr></table>"
    )


def _tarjeta_metrica(titulo, valor, unidad, nota="", acento="#0284c7", principal=False):
    """Tarjeta compatible con QTextDocument, sin CSS de navegador ni emojis."""
    fondo = "#e9f7fc" if principal else "#f4f7fb"
    tamano = 30 if principal else 23
    # Cifras grandes conservan la precisión, reduciendo el tamaño cuando hace falta.
    tamano = min(tamano, 26 if len(str(valor)) > 7 else tamano)
    if len(str(valor)) > 12:
        tamano = 16
    return (
        f"<td width='50%' bgcolor='{fondo}' style='padding:12px; border-top:3px solid {acento};'>"
        f"<p style='margin:0 0 6px 0; font-size:11px; color:{acento}; font-weight:600;'>{titulo}</p>"
        f"<p style='margin:0; font-size:{tamano}px; font-weight:700; color:#103d56;'>{valor}</p>"
        f"<p style='margin:0 0 5px 0; font-size:12px; color:{acento};'>{unidad}</p>"
        f"<p style='margin:0; font-size:11px; color:#52677a;'>{nota}</p></td>"
    )


def rpt_grid_2x2(tarjetas):
    filas = []
    for idx in range(0, len(tarjetas), 2):
        celdas = []
        for titulo, icono, valor, unidad, nota, *color in tarjetas[idx:idx + 2]:
            acento = color[0] if color else RPT_SECUNDARIO
            celdas.append(_tarjeta_metrica(titulo, valor, unidad, nota, acento, idx == 0))
        if len(celdas) == 1:
            celdas.append("<td width='50%'></td>")
        filas.append("<tr>" + "".join(celdas) + "</tr>")
    return "<table width='100%' cellspacing='5' cellpadding='0'>" + "".join(filas) + "</table>"


def rpt_kpis(items):
    ancho = 100 // max(len(items), 1)
    celdas = "".join(
        f"<td width='{ancho}%' bgcolor='#f4f8ff' style='border:1px solid #e2e8f0; padding:8px 10px;'>"
        f"<span style='font-size:10px; font-weight:500; color:{RPT_SUAVE};'>{icono}&nbsp;{etiqueta.upper()}</span><br>"
        f"<span style='font-family:Segoe UI; font-size:18px; font-weight:700; color:{color};'>{valor}</span></td>"
        for icono, etiqueta, valor, color in items
    )
    return f"<table width='100%' cellspacing='6' cellpadding='0'><tr>{celdas}</tr></table>"


def rpt_tarjeta(contenido, acento=RPT_SECUNDARIO, fondo=RPT_FONDO):
    return (
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td width='3' bgcolor='{acento}'></td>"
        f"<td bgcolor='{fondo}' style='padding:8px 11px; border:1px solid #dce4ee;'>{contenido}</td>"
        "</tr></table>"
    )


def rpt_estado(tono, titulo, detalle="", badge=None):
    acento, fondo, texto, icono, badge_def, bg_badge, fg_badge = _RPT_TONOS.get(
        tono, _RPT_TONOS["info"]
    )
    etiqueta_badge = badge if badge is not None else badge_def
    det = (
        f"<div style='margin-top:4px; font-family:Segoe UI; font-size:11px; font-weight:400; color:#596573; line-height:1.35;'>{detalle}</div>"
        if detalle
        else ""
    )
    cabecera = (
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td align='left'><span style='font-family:Segoe UI; font-size:12px; font-weight:600; color:{texto};'>"
        f"<span style='color:{acento}; font-weight:700;'>{icono}</span>&nbsp;{titulo}</span></td>"
        f"<td align='right' width='92'><span style='background-color:{bg_badge}; color:{fg_badge}; "
        f"font-family:Segoe UI; font-size:9.5px; font-weight:700; border-radius:4px; padding:2px 7px;'>&nbsp;{etiqueta_badge}&nbsp;</span></td>"
        "</tr></table>"
    )
    return (
        "<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:4px; margin-bottom:4px;'><tr>"
        f"<td bgcolor='{fondo}' style='padding:8px 11px; border:1px solid #dce4ee; border-radius:6px;'>{cabecera}{det}</td>"
        "</tr></table>"
    )


def rpt_seccion_cad(titulo_izq, titulo_der="UNIDADES SI"):
    der_html = (
        f"<td align='right'><span style='font-family:Segoe UI; font-size:10px; font-weight:500; color:#72787f;'>{titulo_der}</span></td>"
        if titulo_der
        else ""
    )
    return (
        "<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:9px; margin-bottom:4px;'><tr>"
        f"<td align='left'><span style='font-family:Segoe UI; font-size:10.5px; font-weight:500; color:#72787f;'>{titulo_izq.upper()}</span></td>"
        f"{der_html}</tr></table>"
    )


def rpt_seccion(icono, texto):
    return rpt_seccion_cad(texto, "")


def rpt_num(texto, color=RPT_AZUL):
    return f"<span style='font-family:Segoe UI; font-weight:600; color:{color};'>{texto}</span>"


def rpt_tabla(filas, cabeceras=None, alineaciones=None):
    # Compatibilidad con los llamadores todavía no migrados, sin tocar sus solvers.
    if cabeceras:
        cabeceras = ['HF TOTAL (M)' if c == 'HF FRIC. (M)' else c for c in cabeceras]
    n = len(cabeceras) if cabeceras else (len(filas[0]) if filas else 1)
    alin = alineaciones or ["left"] + ["right"] * (n - 1)
    html = "<table width='100%' cellspacing='0' cellpadding='0' style='border:1px solid #e2e8f0;'>"
    if cabeceras:
        celdas_cab = []
        for idx_c, (c, a) in enumerate(zip(cabeceras, alin)):
            es_hf = "HF" in c.upper() or (idx_c == n - 1 and n >= 4)
            color_cab = "#0c4e77" if es_hf else "#72787f"
            peso_cab = "700" if es_hf else "600"
            texto_cab = c if c == "Efic. (%)" else c.upper()
            celdas_cab.append(
                f"<td bgcolor='#f2f6ff' align='{a}' style='padding:5px 6px; border-bottom:1px solid #e2e8f0;'>"
                f"<span style='font-family:Segoe UI; font-size:9.5px; font-weight:{peso_cab}; color:{color_cab};'>{texto_cab}</span></td>"
            )
        html += "<tr>" + "".join(celdas_cab) + "</tr>"
    for i, fila in enumerate(filas):
        fondo = "#ffffff" if i % 2 == 0 else "#f8f9ff"
        if len(fila) == 1 and isinstance(fila[0], dict) and "colspan" in fila[0]:
            c_info = fila[0]
            html += (
                f"<tr><td colspan='{c_info.get('colspan', n)}' bgcolor='{fondo}' "
                f"align='{c_info.get('align', 'left')}' style='padding:4px 8px; border-bottom:1px solid #f1f5f9; {c_info.get('style', '')}'>"
                f"{c_info.get('html', '')}</td></tr>"
            )
            continue
        html += "<tr>" + "".join(
            f"<td bgcolor='{fondo}' align='{a}' style='padding:5px 6px;'>"
            f"<span style='font-size:11px; font-weight:400; color:{RPT_TEXTO};'>{v}</span></td>"
            for v, a in zip(fila, alin)
        ) + "</tr>"
    return html + "</table>"


def rpt_ecuaciones(lineas):
    cuerpo = "<br>".join(
        f"<span style='font-family:Segoe UI; font-size:12px; font-weight:600; "
        f"color:{RPT_AZUL};'>{linea}</span>"
        for linea in lineas
    )
    return rpt_tarjeta(cuerpo, RPT_SECUNDARIO, RPT_FONDO)


def _formatear_distinguir_hc_hop(hc, hop):
    """
    Formatea hc y hop con los decimales necesarios para distinguirlos (mínimo 2, hasta 4).
    """
    if hc is None or hop is None or not math.isfinite(hc) or not math.isfinite(hop):
        sx = f"{hc:.2f}" if (hc is not None and math.isfinite(hc)) else "X"
        sy = f"{hop:.2f}" if (hop is not None and math.isfinite(hop)) else "Y"
        return sx, sy
    for d in (2, 3, 4):
        sx = f"{hc:.{d}f}"
        sy = f"{hop:.{d}f}"
        if sx != sy:
            return sx, sy
    return f"{hc:.2f}", f"{hop:.2f}"


def _limpiar_nombre_equipo(nom):
    """Elimina prefijos repetidos accidentales como 'Bomba Bomba A'."""
    s = str(nom).strip()
    while s.lower().startswith("bomba bomba "):
        s = "Bomba " + s[12:]
    return s


def reporte_bomba(
    nombre_bomba,
    arreglo,
    Q_op,
    H_op,
    eta_op,
    potencia_hidraulica_total,
    potencia_freno_total,
    npsh_d,
    npsh_r=None,
    cavitacion=None,
    reparto=None,
    t1_nombre="Tanque 1",
    t2_nombre="Tanque 2",
    advertencia_fluido="",
    aviso_succion="",
    v_succion=0.0,
    estacion=None,
    metodo="cuadratico",
    ecuacion=None,
    puntos_curva=(),
):
    """Punto de operación, rendimiento, succión y detalle técnico, en ese orden."""
    from motor.bombas import ecuacion_total, EcuacionTotal

    html_partes = []

    sub_enc = f"{escape(t1_nombre)} → {escape(t2_nombre)} · {escape(str(arreglo).capitalize())}"
    html_partes.append(
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        "<td bgcolor='#103e58' style='padding:13px 14px;'>"
        "<p style='margin:0; font-size:10px; color:#7dd3fc; font-weight:600;'>PUNTO DE OPERACIÓN</p>"
        f"<p style='margin:3px 0; font-size:19px; color:#ffffff; font-weight:700;'>{escape(nombre_bomba)}</p>"
        f"<p style='margin:0; font-size:11px; color:#d0e9f5;'>{sub_enc}</p>"
        "</td></tr></table>"
    )
    tarjeta_q = _tarjeta_metrica("CAUDAL Q", f"{Q_op * 1000.0:.2f}", "L/s",
                               f"{Q_op:.4f} m³/s", "#0284c7", True)
    tarjeta_h = _tarjeta_metrica("ALTURA H", f"{H_op:.2f}", "m",
                               "Carga de la bomba", "#0d9488", True)
    html_partes.append(f"<table width='100%' cellspacing='5' cellpadding='0'><tr>{tarjeta_q}{tarjeta_h}</tr></table>")

    # 3. Tarjeta de la ecuación total en monoespaciado, con borde de acento:
    curvas = curvas_estacion(estacion)
    if usa_puntos(curvas,metodo):
        texto_curva = resumen_puntos(puntos_total(curvas,puntos_curva),len(curvas)>1)
        etiqueta_eq,bg_eq,fg_eq = 'Por puntos','#e5eeff','#0c4e77'
    else:
        eq_obj = ecuacion
        if eq_obj is None:
            if estacion is not None:
                try:
                    eq_obj = ecuacion_total(estacion)
                except Exception:
                    eq_obj = None
            if eq_obj is None:
                if Q_op > 1e-9:
                    a_val = H_op * 1.25
                    c_val = -(0.25 * H_op) / (Q_op ** 2)
                    txt = f"H(Q) = {a_val:.2f} − {abs(c_val):.1f}·Q²"
                else:
                    a_val = H_op
                    c_val = 0.0
                    txt = f"H(Q) = {a_val:.2f}"
                eq_obj = EcuacionTotal(a=a_val, b=0.0, c=c_val, tipo="exacta", R2=1.0, texto=txt)

        if eq_obj.tipo == "exacta":
            etiqueta_eq = "Exacta"
            bg_eq = "#e5eeff"
            fg_eq = "#0c4e77"
        else:
            r2_num = eq_obj.R2 if (eq_obj.R2 is not None and math.isfinite(eq_obj.R2)) else 1.0
            delta_txt = ""
            if hasattr(eq_obj, "delta_Qop") and eq_obj.delta_Qop is not None and math.isfinite(eq_obj.delta_Qop):
                delta_txt = f" · Δ en Q_op = {abs(eq_obj.delta_Qop):.2f} m"
            metodo_act = str(metodo).lower()
            if metodo_act == "lineal" or getattr(estacion, "metodo", "").lower() == "lineal":
                etiqueta_eq = f"Ajuste referencial (R² = {r2_num:.3f}{delta_txt})"
            else:
                etiqueta_eq = f"Ajuste (R² = {r2_num:.3f}{delta_txt})"
            bg_eq = "#fef3c7"
            fg_eq = "#92400e"

        texto_curva = eq_obj.texto
        if len(curvas)==1:
            etiqueta_eq = f'Ajuste cuadrático — error máx. {curvas[0].error_max_ajuste:.6g} m'

    tarjeta_ecuacion = rpt_tarjeta(
        "<p style='margin:0 0 6px 0; font-size:11px; font-weight:600; color:#52677a;'>CURVA DE LA BOMBA</p>"
        f"<p style='margin:0; font-family:Segoe UI; font-size:12px; color:{RPT_AZUL};'>{escape(texto_curva)}</p>"
        f"<p style='margin:6px 0 3px 0; font-size:11px; color:{fg_eq};'>{escape(etiqueta_eq)}</p>"
        "<p style='margin:0; font-size:10px; color:#64748b;'>(Q en m³/s, H en m)</p>"
    )

    # Rendimiento: etiquetas a la izquierda y valores alineados a la derecha.
    eta_val_txt = f"{eta_op * 100.0:.1f}" if eta_op is not None else "—"
    chip_eta_html = (
        f"{eta_val_txt}&nbsp;<span style='font-family:Segoe UI; font-size:10px; font-weight:400; color:#72787f;'>%</span>"
        if eta_op is not None
        else "<span style='color:#72787f;'>—</span>"
    )

    if potencia_freno_total is not None and math.isfinite(potencia_freno_total):
        p_fr_kw = potencia_freno_total / 1000.0
        p_fr_hp = potencia_freno_total / 745.7
        chip_bhp_html = (
            f"{p_fr_kw:.2f}&nbsp;<span style='font-family:Segoe UI; font-size:10px; font-weight:400; color:#72787f;'>kW</span>"
            f"&nbsp;<span style='font-family:Segoe UI; font-size:10px; font-weight:400; color:#72787f;'>({p_fr_hp:.1f} HP)</span>"
        )
    elif potencia_freno_total is None:
        chip_bhp_html = "<span style='color:#72787f;'>—</span>"
    else:
        chip_bhp_html = "∞"

    p_hid_kw = potencia_hidraulica_total / 1000.0
    chip_phid_html = (
        f"{p_hid_kw:.2f}&nbsp;<span style='font-family:Segoe UI; font-size:10px; font-weight:400; color:#72787f;'>kW</span>"
    )

    fila_chips = rpt_seccion_cad("RENDIMIENTO Y POTENCIA", "") + (
        "<table width='100%' cellspacing='0' cellpadding='0'>"
        "<tr><td bgcolor='#effaf6' style='padding:10px; color:#087f68; font-size:12px;'>η &nbsp; Eficiencia global</td>"
        f"<td bgcolor='#effaf6' align='right' style='padding:10px; color:#087f68; font-size:20px; font-weight:700;'>{chip_eta_html}</td></tr>"
        "<tr><td style='padding:8px 10px; font-size:12px; color:#52677a;'>Potencia al eje · BHP</td>"
        f"<td align='right' style='padding:8px 10px; font-size:14px; font-weight:600;'>{chip_bhp_html}</td></tr>"
        "<tr><td bgcolor='#f4f7fb' style='padding:8px 10px; font-size:12px; color:#52677a;'>Potencia hidráulica</td>"
        f"<td bgcolor='#f4f7fb' align='right' style='padding:8px 10px; font-size:14px; font-weight:600;'>{chip_phid_html}</td></tr>"
        "</table>"
    )
    html_partes.append(fila_chips)

    # 5. Tarjeta compacta 'Succión': NPSHd (m) y velocidad en succión (m/s)
    es_cavitacion = (
        str(cavitacion).strip().upper() == "RIESGO DE CAVITACIÓN"
    )

    if npsh_r is not None:
        npsh_r_html = (
            f"NPSHr = <b>{npsh_r:.2f}</b> <span style='font-size:10px; color:#72787f;'>m</span>"
        )
    else:
        npsh_r_html = "<span style='color:#72787f; font-weight:normal;'>NPSHr no ingresado</span>"

    v_s_val = v_succion
    if v_s_val <= 0.0 and aviso_succion:
        import re
        m_v = re.search(r"(\d+(\.\d+)?)", aviso_succion)
        if m_v:
            v_s_val = float(m_v.group(1))

    linea_v_succion = ""
    if v_s_val > 3.0:
        linea_v_succion = (
            f"<div style='margin-top:3px; font-family:Segoe UI; font-size:10px; color:#72787f;'>"
            f"Velocidad en línea de succión: {v_s_val:.2f} m/s (&gt; 3.00 m/s)"
            f"</div>"
        )

    alerta_cavitacion = ""
    if es_cavitacion and npsh_d <= 0.0:
        alerta_cavitacion = (
            f"<div style='margin-top:3px; font-family:Segoe UI; font-size:10.5px; font-weight:600; color:{RPT_ROJO};'>"
            f"! NPSHd negativo: la presión en la succión cae bajo la presión de vapor (cavitación)"
            f"</div>"
        )
    elif es_cavitacion:
        req_txt = f"{npsh_r:.2f} m" if npsh_r is not None else "requerido"
        alerta_cavitacion = (
            f"<div style='margin-top:3px; font-family:Segoe UI; font-size:10.5px; font-weight:600; color:{RPT_ROJO};'>"
            f"! Riesgo de cavitación detectado (NPSHd {npsh_d:.2f} m ≤ NPSHr {req_txt})"
            f"</div>"
        )

    aviso_fluido_html = ""
    if advertencia_fluido:
        aviso_fluido_html = (
            f"<div style='margin-top:2px; font-family:Segoe UI; font-size:10px; color:#92400e;'>"
            f"{advertencia_fluido}"
            f"</div>"
        )

    fondo_succion = "#fff1f0" if es_cavitacion else "#f4f7fb"
    titulo_succion = "! REVISAR SUCCIÓN · NPSH" if es_cavitacion else "SUCCIÓN · NPSH"
    color_succion = RPT_ROJO if es_cavitacion else "#475569"
    tarjeta_succion = (
        "<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:3px; margin-bottom:5px; border:1px solid #e2e8f0; border-radius:4px; background:#f8fafc;' title='NPSH Disponible Calculado'>"
        f"<tr><td bgcolor='{fondo_succion}' style='padding:10px 11px;'>"
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td align='left'><span style='font-family:Segoe UI; font-size:11px; font-weight:600; color:{color_succion};'>{titulo_succion}</span></td>"
        f"<td align='right'><span style='font-family:Segoe UI; font-size:11px; color:#0b1c30;'>v<sub>succión</sub>: <b>{v_s_val:.2f}</b> <span style='font-size:10px; color:#72787f;'>m/s</span></span></td>"
        "</tr></table>"
        "<div style='margin-top:3px; font-family:Segoe UI; font-size:11.5px; color:#0b1c30;'>"
        f"NPSHd: <b>{npsh_d:.2f}</b> <span style='font-size:10px; color:#72787f;'>m</span>"
        f"&nbsp;&nbsp;·&nbsp;&nbsp;{npsh_r_html}"
        "</div>"
        f"{alerta_cavitacion}"
        f"{linea_v_succion}"
        f"{aviso_fluido_html}"
        "</td></tr></table>"
    )
    if es_cavitacion or aviso_fluido_html or linea_v_succion:
        # Las advertencias aparecen inmediatamente después de Q/H.
        html_partes.insert(2, rpt_espacio(4) + tarjeta_succion)
    else:
        html_partes.append(tarjeta_succion)
    html_partes.append(rpt_espacio(8))
    html_partes.append(tarjeta_ecuacion)

    # 6. Desglose por equipo SOLO si hay 2 o más equipos, una única vez
    if reparto and len(reparto) >= 2:
        html_partes.append(
            rpt_seccion_cad(f"DESGLOSE POR EQUIPO ({str(arreglo).upper()})", f"{len(reparto)} EQUIPOS")
        )
        for r in reparto:
            b_nom = _limpiar_nombre_equipo(r.get("bomba", "Bomba"))
            b_q = r.get("Q", 0.0)
            b_h = r.get("H", 0.0)
            b_eta = r.get("eta")
            b_eta_str = f"{b_eta * 100.0:.1f}" if b_eta is not None else "—"
            b_pf = r.get("potencia_freno")
            if b_pf is not None and math.isfinite(b_pf):
                b_pf_str = f"{b_pf / 1000.0:.2f}"
            elif b_pf is None:
                b_pf_str = "—"
            else:
                b_pf_str = "∞"

            activa = r.get("activa", True)
            if activa:
                estado_chip = (
                    "<span style='background:#dcfce7; color:#166534; font-family:Segoe UI; "
                    "font-size:9.5px; font-weight:700; padding:2px 7px; border-radius:10px;'>Activa</span>"
                )
                fondo_fila = "#ffffff"
                color_texto = RPT_TEXTO
            else:
                estado_chip = (
                    "<span style='background:#f1f5f9; color:#64748b; font-family:Segoe UI; "
                    "font-size:9.5px; font-weight:700; padding:2px 7px; border-radius:10px;'>Cerrada</span>"
                )
                fondo_fila = "#f8fafc"
                color_texto = "#94a3b8"

            npshd = f"{r['npsh_d']:.2f} m" if r.get('npsh_d') is not None else '—'
            npshr = f"{r['npsh_r']:.2f} m" if r.get('npsh_r') is not None else '—'
            filas_html = (
                f"<tr><td colspan='2' bgcolor='{fondo_fila}' style='padding:9px; font-size:12px; color:{color_texto};'>"
                f"<b>{escape(b_nom)}</b> &nbsp; {estado_chip}</td></tr>"
            )
            pares = [
                (f"Q · <b>{b_q * 1000.0:.2f}</b> L/s", f"H · <b>{b_h:.2f}</b> m"),
                (f"Efic. · <b>{b_eta_str}</b> %", f"BHP · <b>{b_pf_str}</b> kW"),
                (f"NPSHd · {npshd}", f"NPSHr · {npshr}"),
            ]
            for izquierda, derecha in pares:
                filas_html += (
                    f"<tr><td width='50%' style='padding:6px 9px; font-size:11px; color:{color_texto};'>{izquierda}</td>"
                    f"<td width='50%' style='padding:6px 9px; font-size:11px; color:{color_texto};'>{derecha}</td></tr>"
                )

            # 7. Si está cerrada: fila atenuada y debajo UNA línea gris
            if not activa:
                hc = r.get("H_cierre")
                hop = r.get("H_op", H_op)
                sx, sy = _formatear_distinguir_hc_hop(hc, hop)
                filas_html += (
                    f"<tr><td colspan='2' bgcolor='{fondo_fila}' align='left' "
                    f"style='padding:3px 8px 6px 8px; border-bottom:1px solid #e2e8f0;'>"
                    f"<span style='font-family:Segoe UI; font-size:10px; color:#78716c;'>"
                    f"H de cierre = {sx} ≤ H de operación = {sy} m. No aporta caudal."
                    f"</span></td></tr>"
                )

            html_partes.append(
                "<table width='100%' cellspacing='0' cellpadding='0' style='border:1px solid #e2e8f0;'>"
                f"{filas_html}</table>" + rpt_espacio(5)
            )

    return "".join(html_partes)


def reporte_diagnostico_bomba(nombre_bomba, estado, mensaje):
    """
    Genera un reporte HTML visible de diagnóstico estilo Google Stitch
    cuando la estación de bombeo no puede operar o presenta un estado anómalo.
    """
    tono = "error" if estado in ("NO_ALCANZA_ALTURA_ESTATICA", "ERROR") else "aviso"
    color_hdr = "#ba1a1a" if tono == "error" else "#d97706"
    sub_enc = f"Estado: {estado}"
    enc = rpt_encabezado("⚡", f"DIAGNÓSTICO: {nombre_bomba.upper()}", sub_enc, color=color_hdr)
    est = rpt_estado(tono, f"Condición de cálculo: {estado}", mensaje, badge=estado)
    return enc + rpt_espacio(6) + est

