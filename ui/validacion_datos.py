"""Validación de propiedades y JSON antes de modificar el proyecto visible."""

import math

from motor.validacion import numero, caudal
from motor.bombas import CurvaBomba
from ui.constantes import FACTORES_SI


def datos_para_diametro(Q, *, calculado=False, alturas=(), carga_bomba=0.0, hf=None):
    if caudal(Q) <= 0 or calculado:
        return False
    return ((hf is not None and numero(hf,'hf definida',minimo=0) > 0) or
            (len(alturas)>1 and max(alturas)-min(alturas)>0) or carga_bomba>0)


def comprobar_diametro_desconocido(tubo, rho):
    pendientes = [tubo.nodo_origen,tubo.nodo_destino]
    visitados, alturas, bombeo = set(), [], 0.0
    while pendientes:
        nodo = pendientes.pop()
        if nodo in visitados:
            continue
        visitados.add(nodo)
        if hasattr(nodo,'abierto_atmosfera'):
            z = numero(nodo.elevacion_z,'Cota del tanque')
            p = 0 if nodo.abierto_atmosfera else numero(nodo.presion_P,'Presión manométrica')
            alturas.append(z+p/(rho*9.81))
        for curva in getattr(nodo,'curvas',[]):
            if getattr(curva,'valida',True):
                bombeo += curva.H_cierre
        for t in getattr(nodo,'tuberias',[]):
            pendientes.extend((t.nodo_origen,t.nodo_destino))
    q = numero(tubo.caudal_Q,'Q',minimo=0)*FACTORES_SI[tubo.u_Q]
    if not datos_para_diametro(q,calculado=getattr(tubo,'_q_por_energia',False),
            alturas=alturas,carga_bomba=bombeo,hf=getattr(tubo,'hf_dado',None)):
        raise ValueError('D=0 significa diámetro desconocido: falta un Q conocido positivo y hf o una altura disponible definida.')


def validar_propiedad(objeto, atributo, valor, rho):
    numero(valor,atributo)
    if atributo in ('longitud','rho','mu','fluido_rho','fluido_mu','P_atm'):
        numero(valor,atributo,minimo=0,estricto=True)
    elif atributo == 'diametro':
        numero(valor,'D',minimo=0)
        if valor == 0:
            comprobar_diametro_desconocido(objeto,rho)
    elif atributo in ('caudal_Q','rugosidad','valor','K','LeD','P_vap','sumatoria_K','sumatoria_Le_D'):
        numero(valor,atributo,minimo=0)


def validar_proyecto(datos, rho):
    """Prevalida todos los números; un archivo inválido no borra la escena actual."""
    if not isinstance(datos,dict):
        raise ValueError('El proyecto JSON debe ser un objeto.')

    def finitos(valor,ruta='proyecto'):
        if isinstance(valor,(int,float)) and not isinstance(valor,bool):
            numero(valor,ruta)
        elif isinstance(valor,dict):
            for clave,v in valor.items():
                finitos(v,f'{ruta}.{clave}')
        elif isinstance(valor,list):
            for i,v in enumerate(valor):
                finitos(v,f'{ruta}[{i}]')
    finitos(datos)
    for coleccion in ('tuberias','tanques','uniones','bombas','accesorios','formas','textos'):
        if not isinstance(datos.get(coleccion,[]),list) or any(
                not isinstance(v,dict) for v in datos.get(coleccion,[])):
            raise ValueError(f'{coleccion} debe ser una lista de objetos.')
        for entrada in datos.get(coleccion,[]):
            for campo in ('x','y','x1','y1','x2','y2','elevacion_z','presion_P','energia_supuesta',
                          'hj_calculada','z_bomba','angulo_in','angulo_out','rotation'):
                if entrada.get(campo) is not None:
                    numero(entrada[campo],campo)
            if entrada.get('t_anclaje') is not None:
                anclaje = numero(entrada['t_anclaje'],'posición del accesorio',minimo=0)
                if anclaje > 1:
                    raise ValueError('La posición relativa del accesorio debe estar entre 0 y 1.')
            for punto in entrada.get('vertices_usuario',[]):
                if len(punto) != 2:
                    raise ValueError('Cada vértice de tubería debe tener dos coordenadas.')
                for coordenada in punto:
                    numero(coordenada,'coordenada del vértice')

    def clave(ref):
        if isinstance(ref,str):
            return ('nombre',ref)
        if isinstance(ref,dict):
            return (ref.get('tipo'),ref['id']) if ref.get('id') is not None else ('nombre',ref.get('nombre'))
        return None

    nodos, conexiones = {}, {}
    for tipo, lista in (('tanque','tanques'),('union','uniones'),('bomba','bombas'),('accesorio','accesorios')):
        for n in datos.get(lista,[]):
            k = (tipo,n.get('id_'+tipo))
            if k[1] is not None:
                nodos[k] = (tipo,n)
            if 'nombre' in n:
                nodos[('nombre',n['nombre'])] = (tipo,n)
    for t in datos.get('tuberias',[]):
        for unidad,permitidas in (('u_Q',('m³/s','L/s','gal/min')),('u_L',('m','cm','mm','in')),
                                 ('u_D',('m','cm','mm','in')),('u_eps',('m','mm'))):
            if t.get(unidad,permitidas[0]) not in permitidas:
                raise ValueError(f'Unidad {unidad} no válida: {t.get(unidad)}.')
        for campo in ('_q_por_energia','_d_por_energia'):
            if campo in t and not isinstance(t[campo],bool):
                raise ValueError(f'{campo} debe ser booleano.')
        numero(t.get('longitud',0),'L de la tubería',minimo=0,estricto=True)
        numero(t.get('diametro',0),'D de la tubería',minimo=0)
        numero(t.get('rugosidad',0),'eps de la tubería',minimo=0)
        caudal(t.get('caudal_Q',0))
        for campo in ('K','LeD','sumatoria_K','sumatoria_Le_D'):
            if campo in t:
                numero(t[campo],campo,minimo=0)
        for campo_conn in ('conexion_origen', 'conexion_destino'):
            conn = t.get(campo_conn)
            if conn is not None:
                if not isinstance(conn, dict):
                    raise ValueError(f'{campo_conn} debe ser un objeto.')
                modo_conn = conn.get('modo', 'ninguno')
                if modo_conn not in ('ninguno', 'salida', 'entrada'):
                    raise ValueError(f'Modo de {campo_conn} no válido: {modo_conn}.')
                numero(conn.get('K', 0.0), f'{campo_conn}.K', minimo=0)
        a,b = clave(t.get('nodo_origen')),clave(t.get('nodo_destino'))
        conexiones.setdefault(a,[]).append(b)
        conexiones.setdefault(b,[]).append(a)
    for acc in datos.get('accesorios',[]):
        numero(acc.get('valor',0),'K o Le/D del accesorio',minimo=0)
        if acc.get('tipo_perdida','K') not in ('K','Le/D'):
            raise ValueError('El accesorio debe usar K o Le/D.')

    cargas_bomba = {}
    for bomba in datos.get('bombas',[]):
        cargas = []
        for eq in bomba.get('equipos',[]):
            q,h = eq.get('Q',[]),eq.get('H',[])
            puntos = eq.get('puntos',[])
            if q or h:
                curva = CurvaBomba(eq.get('nombre','Bomba'),q,h,eq.get('eta') or None,
                    npsh_r=eq.get('npsh') or None,metodo=bomba.get('metodo','cuadratico'))
            elif puntos:
                curva = CurvaBomba(puntos,metodo=bomba.get('metodo','cuadratico'))
            else:
                continue  # un equipo sin curva aún puede guardarse como tal
            if not curva.valida:
                raise ValueError(curva.mensaje)
            cargas.append(curva.H_cierre)
        carga = sum(cargas) if bomba.get('arreglo')=='serie' else max(cargas,default=0.0)
        cargas_bomba[id(bomba)] = carga

    for t in datos.get('tuberias',[]):
        if float(t.get('diametro',0)) != 0:
            continue
        if t.get('_d_por_energia', False):
            # Tras invalidar, un D calculado vuelve a 0 conservando su bandera.
            # Es un resultado desconocido persistible, no un diámetro físico ni
            # una autorización para resolver sin suficientes datos de entrada.
            continue
        pendientes = [clave(t.get('nodo_origen')),clave(t.get('nodo_destino'))]
        vistos, alturas, bombeo = set(), [], 0.0
        while pendientes:
            k = pendientes.pop()
            if k in vistos:
                continue
            vistos.add(k)
            if k in nodos:
                tipo,n = nodos[k]
                if tipo=='tanque':
                    p = 0 if n.get('abierto_atmosfera',True) else numero(n.get('presion_P',0),'P del tanque')
                    alturas.append(numero(n.get('elevacion_z',0),'z del tanque')+p/(rho*9.81))
                elif tipo=='bomba':
                    bombeo += cargas_bomba.get(id(n),0.0)
            pendientes.extend(conexiones.get(k,[]))
        q = float(t.get('caudal_Q',0))*FACTORES_SI[t.get('u_Q','m³/s')]
        if not datos_para_diametro(q,calculado=t.get('_q_por_energia',False),alturas=alturas,carga_bomba=bombeo):
            raise ValueError('D=0: falta Q conocido positivo y hf o altura disponible para calcular el diámetro.')
