"""Perfiles físicos SI: solo consumen pérdidas y alturas de bomba ya resueltas."""

from dataclasses import replace
import math

from motor.numerica import relativo
from motor.resultados import PerfilRuta, PuntoPerfil, ResultadoTramo, ResultadoBomba, ResultadoEstacion
from motor.validacion import numero


def construir_perfil_ruta(tramos, H_inicio, H_final=None, *, bombas=(), g=9.81,
        cotas=None, etiquetas=None, id='ruta', s_inicio=0.0, entrada=True, salida=True):
    """bombas: pares (índice después del tramo, ResultadoBomba/ResultadoEstacion).

    El índice -1 instala la bomba antes del primer tramo. Una estación se añade
    una sola vez, con H total (no sumando las H de equipos en paralelo).
    cotas/etiquetas describen los n+1 extremos; las cotas ausentes siguen en None.
    No se llama a calcular_hf, Colebrook ni a evaluadores de curvas.
    """
    tramos = tuple(tramos)
    grupos, bombas_efectivas = set(), []
    for indice,bomba in bombas:
        if not isinstance(bomba,(ResultadoBomba,ResultadoEstacion)):
            raise ValueError('La altura debe proceder de una bomba o estación calculada.')
        if isinstance(bomba,ResultadoBomba) and not bomba.activa:
            continue
        grupo = ((indice,bomba.estacion_id,bomba.etapa) if isinstance(bomba,ResultadoBomba)
                 else (indice,bomba.id,'estacion'))
        if grupo not in grupos:
            grupos.add(grupo)
            bombas_efectivas.append((indice,bomba))
    bombas = tuple(bombas_efectivas)
    if not tramos or not all(isinstance(t, ResultadoTramo) for t in tramos):
        raise ValueError('El perfil requiere ResultadoTramo calculados.')
    g = numero(g,'g',minimo=0,estricto=True)
    inicio = numero(H_inicio,'H_inicio')
    s = numero(s_inicio,'s inicial',minimo=0)
    cotas = tuple(cotas) if cotas is not None else (None,)*(len(tramos)+1)
    etiquetas = tuple(etiquetas) if etiquetas is not None else ('',)*(len(tramos)+1)
    if len(cotas)!=len(tramos)+1 or len(etiquetas)!=len(tramos)+1:
        raise ValueError('Se requiere una cota/etiqueta por extremo de tramo.')
    for z in cotas:
        if z is not None:
            numero(z,'cota z')
    por_indice = {}
    for indice,b in bombas:
        if not isinstance(indice,int) or not -1<=indice<len(tramos):
            raise ValueError('Posición de bomba inválida.')
        if not isinstance(b,(ResultadoBomba,ResultadoEstacion)):
            raise ValueError('La altura debe proceder de una bomba o estación calculada.')
        por_indice.setdefault(indice,[]).append(b)
    puntos, H = [], inicio
    def punto(tipo, z, v, etiqueta='', tramo_id=None, perdida=0.0, salto=0.0):
        puntos.append(PuntoPerfil(s,z,H,H-v*v/(2*g),v,tipo,etiqueta,tramo_id,perdida,salto))
    if entrada:
        punto('entrada',cotas[0],0.0,
              f'Salida de {etiquetas[0]}' if etiquetas[0] else 'Entrada de la ruta')
    def agregar_bombas(indice,z,v):
        nonlocal H
        for b in por_indice.get(indice,()):
            H += numero(b.H,'H de bomba',minimo=0)
            nombre = str(b.id)
            punto('bomba',z,v,nombre if nombre.startswith('Bomba') else f'Bomba {nombre}',salto=b.H)
    agregar_bombas(-1,cotas[0],0.0 if entrada else tramos[0].v)
    anterior = None
    errores = []
    for i,t in enumerate(tramos):
        origen = etiquetas[i] or t.origen
        destino = etiquetas[i+1] or t.destino
        nombre_tuberia = (f'Tubería ({origen} -> {destino})' if origen and destino
                          else f'Tubería {t.id}' if t.id is not None else 'Tubería')
        rotulo_friccion = f'{nombre_tuberia}: Pérdida por fricción'
        if not math.isclose(t.hf_total,t.hf_distribuida+t.hf_localizada,rel_tol=1e-12,abs_tol=1e-15):
            errores.append(f'{t.id}: desglose de pérdidas inconsistente')
        if anterior is not None and (t.D!=anterior.D or t.v!=anterior.v):
            punto('cambio de diámetro',cotas[i],t.v,
                  f'Cambio de diámetro en {etiquetas[i]}' if etiquetas[i] else 'Cambio de diámetro',t.id)
        else:
            punto('tubería',cotas[i],t.v,'',t.id)
        s0 = s
        def cota(fraccion):
            if fraccion==0: return cotas[i]
            if fraccion==1: return cotas[i+1]
            return (cotas[i]+fraccion*(cotas[i+1]-cotas[i])
                    if cotas[i] is not None and cotas[i+1] is not None else None)
        # Sin posición física, el salto agregado se representa al final del
        # tramo y se etiqueta como tal; no se inventa una ubicación intermedia.
        accesorios = [(a.x if a.x is not None else t.L,a.hf,
                       a.id if a.x is not None else f'{a.id} (sin posición)') for a in t.accesorios]
        if not accesorios and t.hf_localizada:
            accesorios = [(t.L,t.hf_localizada,'Accesorios agregados (sin posición)')]
        if not math.isclose(sum(a[1] for a in accesorios),t.hf_localizada,rel_tol=1e-9,abs_tol=1e-15):
            errores.append(f'{t.id}: accesorios no coinciden con hf localizada')
        previo = 0.0
        for posicion,hf,etiqueta in sorted(accesorios,key=lambda a:a[0]):
            numero(posicion,'posición de accesorio',minimo=0)
            if posicion>t.L:
                raise ValueError('Accesorio fuera del tramo.')
            fraccion = posicion/t.L
            perdida = t.hf_distribuida*(fraccion-previo)
            s = s0+posicion
            H -= perdida
            punto('tubería',cota(fraccion),t.v,rotulo_friccion if perdida else '',t.id,perdida)
            H -= numero(hf,'hf de accesorio',minimo=0)
            if etiqueta.startswith(('Pérdida de salida', 'Pérdida de entrada')):
                punto('borde',cota(fraccion),t.v,etiqueta,t.id,hf)
            else:
                punto('accesorio',cota(fraccion),t.v,
                      etiqueta if etiqueta.startswith('Accesorio') else f'Accesorio {etiqueta}',t.id,hf)
            previo = fraccion
        perdida = t.hf_distribuida*(1-previo)
        s = s0+t.L
        H -= perdida
        punto('tubería',cotas[i+1],t.v,
              rotulo_friccion if perdida or t.hf_distribuida==0 else '',t.id,perdida)
        agregar_bombas(i,cotas[i+1],t.v)
        anterior = t
    if salida:
        punto('salida',cotas[-1],0.0,
              f'Entrada a {etiquetas[-1]}' if etiquetas[-1] else 'Salida de la ruta')
    hd = sum(t.hf_distribuida for t in tramos)
    hl = sum(t.hf_localizada for t in tramos)
    hb = sum(b.H for _,b in bombas)
    fin = H if H_final is None else numero(H_final,'H_final')
    residuo = inicio-hd-hl+hb-fin
    escala = max(abs(inicio),abs(fin),hd+hl,abs(hb))
    error = relativo(residuo,escala)
    if error>1e-9:
        errores.append('La ruta no satisface el balance de energía a 1e-9 relativo.')
    return PerfilRuta(str(id),tuple(puntos),inicio,fin,H,hd,hl,hb,residuo,error,
        'SIN_BALANCE' if errores else 'OK','; '.join(errores) or 'Balance de ruta verificado.')


def construir_perfiles_red(rutas, *, g=9.81):
    """Una ruta por salida; reutiliza los puntos idénticos de tramos compartidos."""
    compartidos, perfiles = {}, []
    for ruta in rutas:
        perfil = construir_perfil_ruta(g=g,**ruta)
        puntos = tuple(compartidos.setdefault(p,p) for p in perfil.puntos)
        perfiles.append(replace(perfil,puntos=puntos))
    return perfiles


def perfil_como_serie(perfil, *, nombre=None, color='#0284c7'):
    """Adaptador de nombres para el dibujante histórico, sin cálculo hidráulico."""
    causas = {'tubería':'friccion','accesorio':'accesorio','borde':'borde','bomba':'bomba',
              'entrada':None,'salida':None,'cambio de diámetro':'cambio_diametro'}
    return dict(nombre=nombre or perfil.id,color=color,perfil=perfil,estado=perfil.estado,
        mensaje=perfil.mensaje,puntos=[dict(x=p.s,z=p.z,egl=p.EGL,hgl=p.HGL,v=p.v,
        etiqueta=p.etiqueta if p.tipo!='tubería' else '',sub_etiqueta='',causa=causas[p.tipo],
        indice_evento=i,tipo_evento=p.tipo,
        hf_tramo=p.perdida if p.perdida else None,salto_bomba=p.H_bomba or None,
        energia_tramo=p.EGL,rotulo_causa=p.etiqueta) for i,p in enumerate(perfil.puntos)])
