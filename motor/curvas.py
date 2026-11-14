"""Muestreo único SI de curvas: se conservan todos los puntos, incluso fallidos."""

from motor.resultados import PuntoCurva
from motor.validacion import numero, caudal, tramo as validar_tramo
from motor.numerica import ErrorConvergencia, ResultadoEscalar


def _malla(q_min, q_max, N, Q_op=None):
    q_min, q_max = caudal(q_min), caudal(q_max)
    if not isinstance(N,int) or isinstance(N,bool) or N<2 or q_max<q_min:
        raise ValueError('Se requiere N>=2 y Q_max>=Q_min>=0.')
    valores = [q_min+(q_max-q_min)*i/(N-1) for i in range(N)]
    if Q_op is not None and q_min<Q_op<q_max and Q_op not in valores and N>2:
        indice = min(range(1,N-1),key=lambda i:abs(valores[i]-Q_op))
        valores[indice] = caudal(Q_op)
        valores.sort()
    return valores


def muestrear_curva_sistema(H_sistema, q_max, *, q_min=0.0, N=101, Q_op=None):
    puntos = []
    for q in _malla(q_min,q_max,N,Q_op):
        try:
            h = numero(H_sistema(q),'H del sistema')
        except Exception as error:
            puntos.append(PuntoCurva(q,None,False,f'NO_CALCULADO: {error}'))
        else:
            puntos.append(PuntoCurva(q,h,True,'OK'))
    return puntos


def muestrear_curva_bomba(bomba, q_max=None, *, q_min=0.0, N=101, Q_op=None):
    puntos = []
    for q in _malla(q_min,bomba.Q_max if q_max is None else q_max,N,Q_op):
        try:
            if not getattr(bomba,'valida',True):
                raise ValueError(getattr(bomba,'mensaje','Curva inválida'))
            if not bomba.caudal_en_dominio(q):
                raise ValueError('FUERA_DE_RANGO_CURVA')
            h = numero(bomba.H_de_Q(q),'H de bomba',minimo=0)
            eta = bomba.eta_de_Q(q)
            nr = bomba.npsh_r_de_Q(q)
        except Exception as error:
            puntos.append(PuntoCurva(q,None,False,f'NO_CALCULADO: {error}'))
        else:
            puntos.append(PuntoCurva(q,h,True,'OK',eta,nr))
    return puntos


def curva_equivalente_estacion(estacion, q_max=None, *, q_min=0.0, N=101, Q_op=None):
    from motor.bombas import _estacion_normalizada, _calcular_desglose, _potencias_desglose
    est = _estacion_normalizada(estacion)
    puntos = []
    for q in _malla(q_min,est.Q_max if q_max is None else q_max,N,Q_op):
        try:
            h = numero(est.H_estacion(q),'H de estación',minimo=0)
            desglose = _calcular_desglose(est,q,1000.0,9.81)
            if not est.validar_dominio(q,desglose):
                raise ValueError('FUERA_DE_RANGO_CURVA')
            eta = _potencias_desglose(desglose)[1]
        except Exception as error:
            puntos.append(PuntoCurva(q,None,False,f'NO_CALCULADO: {error}'))
        else:
            puntos.append(PuntoCurva(q,h,True,'OK',eta))
    return puntos


def construir_curvas_estacion(estacion, H_sistema, *, N=101, Q_op=None, q_max=None):
    """Las mismas instancias de listas se entregan al gráfico y a Excel."""
    from motor.bombas import _estacion_normalizada, ecuacion_total
    est = _estacion_normalizada(estacion)
    limite = max(est.Q_max,(Q_op or 0)*1.35) if q_max is None else q_max
    bombas = [b for e in est.etapas for b in e]
    return dict(muestras_sistema=muestrear_curva_sistema(H_sistema,limite,N=N,Q_op=Q_op),
        muestras_bombas=[muestrear_curva_bomba(b,limite,N=N,Q_op=Q_op) for b in bombas],
        muestras_equivalente=curva_equivalente_estacion(est,limite,N=N,Q_op=Q_op),
        ecuacion_total=ecuacion_total(est,Q_op=Q_op),
        ecuaciones_bombas=[ecuacion_total(b) for b in bombas])


def evaluar_carga_sistema_ramificada(q, principal, ramales, rho, mu, *, motor=None):
    """Carga exacta para Q: núcleo compartido con la curva histórica ramificada."""
    if motor is None:
        from motor import MotorFluidos
        motor = MotorFluidos
    caudal(q)
    validar_tramo(principal,rho,mu,motor.g)
    for r in ramales:
        validar_tramo(r,rho,mu,motor.g)
    if not ramales:
        raise ValueError('Se requiere al menos un ramal.')
    alturas = [r.get('H',0.0) for r in ramales]
    def evaluar(h, estricto=False):
        ramas, neto, escala, error_h, escala_h = [], 0.0, q, 0.0, 0.0
        for r in ramales:
            delta = h-r.get('H',0.0)
            carga = abs(delta)
            qi = (motor._caudal_tramo(carga,r,rho,mu) if estricto else
                  motor._caudal_para_acotar(carga,r,rho,mu))
            neto += qi if delta>=0 else -qi
            escala += qi
            if estricto:
                perdida = motor._perdida_tramo(qi,r,rho,mu)[0]
                error_h = max(error_h,abs(perdida-carga))
                escala_h = max(escala_h,carga)
            ramas.append(dict(Q=float(qi),direccion='Sale de la unión' if delta>=0 else 'Entra a la unión'))
        return float(neto-q),max(escala,1e-300),ramas,error_h,escala_h
    inferior, superior = min(alturas),max(alturas)
    paso = max(superior-inferior,1.0)
    for expansiones in range(80):
        fa,fb = evaluar(inferior)[0],evaluar(superior)[0]
        if fa<=0<=fb:
            break
        if fa>0: inferior = numero(inferior-paso,'H inferior expandida')
        if fb<0: superior = numero(superior+paso,'H superior expandida')
        paso *= 2
    else:
        raise ValueError('No se pudo acotar H para la curva del sistema.')
    h = inferior
    for it in range(1,201):
        h = (inferior+superior)/2
        residuo,escala,_,_,_ = evaluar(h)
        if abs(residuo)/escala<=1e-10:
            break
        nuevos = (h,superior) if residuo<0 else (inferior,h)
        if nuevos==(inferior,superior):
            break
        inferior,superior = nuevos
    residuo,escala,ramas,error_h,escala_h = evaluar(h,True)
    comprobacion = ResultadoEscalar(h,iteraciones=it+expansiones,
        residuo_masa=residuo,escala_masa=escala,residuo_energia=error_h,escala_energia=escala_h)
    if not comprobacion.convergio:
        raise ErrorConvergencia(comprobacion)
    hf = motor._perdida_tramo(q,principal,rho,mu)[0]
    H = numero(h-principal.get('H',0.0)+hf,'H del sistema')
    diagnostico = dict(Q=float(q),H_j=h,ramas=ramas,residuo_masa=residuo,
        residuo_masa_relativo=comprobacion.residuo_masa_relativo,residuo_energia=error_h,
        residuo_energia_relativo=comprobacion.residuo_energia_relativo,iteraciones=it+expansiones)
    return H,diagnostico
