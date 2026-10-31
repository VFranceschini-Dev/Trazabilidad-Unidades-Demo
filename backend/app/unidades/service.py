"""Servicios de dominio del núcleo: alta, asignación, liberación y service.

Transacciones explicitas: cada operacion abre su unidad de trabajo, delega la validacion
de estados al motor (`core.estados.transicionar`) y confirma o revierte completa.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import estados
from app.core.auditoria import registrar as auditar
from app.core.excepciones import ErrorDominio, NoEncontrado, TransicionInvalida
from app.core.historial import Responsable, responsable_vigente
from app.tablas_generales.models import Sucursal, valor_parametro
from app.unidades.models import Asignacion, Circuito, EventoUnidad, UnidadDemo


def _instante_normal(fecha_hora: Optional[datetime]) -> datetime:
    if fecha_hora is None:
        return datetime.now(timezone.utc)
    if fecha_hora.tzinfo is None:
        return fecha_hora.replace(tzinfo=timezone.utc)
    return fecha_hora


def validar_carga_diferida(sesion: Session, id_unidad: int | None, fecha_hora: Optional[datetime]) -> Optional[datetime]:
    """Reglas de carga diferida: no futura, no anterior al ultimo evento de la unidad."""
    if fecha_hora is None:
        return None
    instante = _instante_normal(fecha_hora)
    ahora = datetime.now(timezone.utc)
    if instante > ahora:
        raise ErrorDominio(
            codigo="FECHA_FUTURA",
            mensaje="La fecha y hora no puede ser futura.",
            detalle={"fecha_hora": instante.isoformat()},
            estado_http=422,
        )
    if id_unidad is not None:
        ultimo = sesion.scalar(
            select(EventoUnidad.fecha_hora)
            .where(EventoUnidad.id_unidad == id_unidad)
            .order_by(EventoUnidad.fecha_hora.desc())
            .limit(1)
        )
        if ultimo is not None and instante < ultimo:
            raise ErrorDominio(
                codigo="FECHA_ANTERIOR_ULTIMO_EVENTO",
                mensaje="La fecha y hora no puede ser anterior al último evento registrado.",
                detalle={"ultimo_evento": ultimo.isoformat(), "solicitada": instante.isoformat()},
                estado_http=422,
            )
    return instante


def fecha_limite_rotacion(sesion: Session, circuito: Circuito, fecha_alta: datetime) -> datetime:
    """HU-02.4: plazo configurado segun politica de la marca (parametro por circuito).

    El TFG fija rotacion de entre seis meses y un ano: defaults 6 (COMERCIAL) y 12
    (POSVENTA) si el parametro no esta cargado (docs/decisiones.md).
    """
    por_defecto = "6" if circuito is Circuito.COMERCIAL else "12"
    meses = int(valor_parametro(sesion, "plazo_rotacion_meses", por_defecto, circuito=circuito.value))
    return fecha_alta + timedelta(days=meses * 30)


def obtener_unidad(sesion: Session, id_unidad: int) -> UnidadDemo:
    unidad = sesion.get(UnidadDemo, id_unidad)
    if unidad is None:
        raise NoEncontrado("la unidad")
    return unidad


def verificar_acceso(sesion: Session, usuario: Any, unidad: UnidadDemo) -> None:
    """Tabla 30: el Asesor solo ve sus unidades y el Resp. Posventa las de su circuito."""
    from app.identidad.models import Rol

    if usuario.rol is Rol.RESP_POSVENTA and unidad.circuito is not Circuito.POSVENTA:
        raise ErrorDominio(codigo="SIN_PERMISO", mensaje="La unidad no pertenece a su circuito.", estado_http=403)
    if usuario.rol is Rol.ASESOR:
        asignada = sesion.scalar(
            select(Asignacion.id).where(
                Asignacion.id_unidad == unidad.id,
                Asignacion.id_responsable == usuario.id,
                Asignacion.fecha_hasta.is_(None),
            )
        )
        if asignada is None:
            raise ErrorDominio(codigo="SIN_PERMISO", mensaje="La unidad no está asignada a este usuario.", estado_http=403)


def filtrar_por_perfil(sesion: Session, usuario: Any, unidades: list[UnidadDemo]) -> list[UnidadDemo]:
    from app.identidad.models import Rol

    if usuario.rol is Rol.RESP_POSVENTA:
        return [u for u in unidades if u.circuito is Circuito.POSVENTA]
    if usuario.rol is Rol.ASESOR:
        propias = set(
            sesion.scalars(
                select(Asignacion.id_unidad).where(
                    Asignacion.id_responsable == usuario.id, Asignacion.fecha_hasta.is_(None)
                )
            )
        )
        return [u for u in unidades if u.id in propias]
    return unidades


def obtener_unidad_bloqueada(sesion: Session, id_unidad: int) -> UnidadDemo:
    """Bloquea la fila hasta el fin de la transaccion y la devuelve con sus datos vigentes.

    Las operaciones la usan antes de evaluar precondiciones: el km, el responsable y el
    estado no pueden cambiar entre la validacion y la transicion del motor.
    """
    unidad = sesion.scalar(
        select(UnidadDemo)
        .where(UnidadDemo.id == id_unidad)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if unidad is None:
        raise NoEncontrado("la unidad")
    return unidad


def alta_unidad(
    sesion: Session,
    *,
    vin: str,
    patente: str,
    modelo: str,
    version: str,
    circuito: Circuito,
    id_sucursal: str,
    km_inicial: int,
    usuario: Any,
    km_proximo_service: Optional[int] = None,
    origen: estados.Origen = estados.Origen.WEB,
    fecha_hora: Optional[datetime] = None,
    ip: Optional[str] = None,
) -> UnidadDemo:
    """HU-02: VIN de 17 caracteres, patente/VIN no registrados; queda DISPONIBLE con evento ALTA."""
    if len(vin) != 17:
        raise ErrorDominio(
            codigo="VIN_INVALIDO",
            mensaje="El VIN debe tener 17 caracteres.",
            detalle={"vin_longitud": len(vin)},
            estado_http=422,
        )
    existente = sesion.scalar(select(UnidadDemo).where(UnidadDemo.vin == vin))
    if existente is not None:
        raise ErrorDominio(
            codigo="VIN_EXISTENTE",
            mensaje="Ya existe una unidad con ese VIN.",
            detalle={"id": existente.id, "patente": existente.patente},
            estado_http=409,
        )
    existente = sesion.scalar(select(UnidadDemo).where(UnidadDemo.patente == patente))
    if existente is not None:
        raise ErrorDominio(
            codigo="PATENTE_EXISTENTE",
            mensaje="Ya existe una unidad con esa patente.",
            detalle={"id": existente.id, "vin": existente.vin},
            estado_http=409,
        )
    if sesion.scalar(select(Sucursal).where(Sucursal.codigo == id_sucursal)) is None:
        raise ErrorDominio(codigo="SUCURSAL_INEXISTENTE", mensaje="La sucursal no existe.", estado_http=422)

    instante = validar_carga_diferida(sesion, None, fecha_hora)
    unidad = UnidadDemo(
        vin=vin,
        patente=patente,
        modelo=modelo,
        version=version,
        circuito=circuito,
        estado_actual=estados.EstadoUnidad.DISPONIBLE.value,
        id_sucursal=id_sucursal,
        km_actual=km_inicial,
        km_proximo_service=km_proximo_service,
        fecha_alta=datetime.now(timezone.utc),
        fecha_limite_rotacion=None,
    )
    sesion.add(unidad)
    sesion.flush()
    # carga_diferida debe reflejar si el llamante envio fecha_hora: se pasa el
    # instante validado (o None) y la fecha del alta se toma del evento resultante.
    evento = estados.transicionar(
        sesion,
        unidad,
        estados.TipoEvento.ALTA,
        usuario,
        origen,
        datos={"modelo": modelo, "version": version, "km_inicial": km_inicial},
        fecha_hora=instante,
    )
    unidad.fecha_alta = evento.fecha_hora
    unidad.fecha_limite_rotacion = fecha_limite_rotacion(sesion, circuito, evento.fecha_hora)
    auditar(sesion, id_usuario=getattr(usuario, "id", None), accion="ALTA_UNIDAD", recurso=f"unidad:{unidad.id}", ip=ip, resultado="EXITO")
    return unidad


def _abrir_asignacion(
    sesion: Session, unidad: UnidadDemo, id_responsable: int, id_sucursal: str, instante: datetime, evento_id: int
) -> Asignacion:
    asig = Asignacion(
        id_unidad=unidad.id,
        id_responsable=id_responsable,
        id_sucursal=id_sucursal,
        fecha_desde=instante,
        id_evento_apertura=evento_id,
    )
    sesion.add(asig)
    return asig


def _cerrar_asignaciones_abiertas(sesion: Session, id_unidad: int, instante: datetime) -> None:
    abiertas = sesion.scalars(
        select(Asignacion).where(Asignacion.id_unidad == id_unidad, Asignacion.fecha_hasta.is_(None))
    ).all()
    for a in abiertas:
        a.fecha_hasta = instante


def _validar_responsable(sesion: Session, id_responsable: int, id_sucursal: str) -> Any:
    from app.identidad.models import Usuario

    resp = sesion.get(Usuario, id_responsable)
    if resp is None:
        raise ErrorDominio(codigo="RESPONSABLE_INEXISTENTE", mensaje="El responsable no existe.", estado_http=422)
    precondiciones: list[str] = []
    if not resp.activo:
        precondiciones.append("El responsable seleccionado está inactivo.")
    if resp.id_sucursal != id_sucursal:
        precondiciones.append(
            f"El responsable pertenece a la sucursal {resp.id_sucursal} y la unidad se asigna a {id_sucursal}."
        )
    return resp


def asignar(
    sesion: Session,
    id_unidad: int,
    *,
    id_responsable: int,
    id_sucursal: str,
    usuario: Any,
    reasignacion: bool = False,
    motivo: Optional[str] = None,
    origen: estados.Origen = estados.Origen.WEB,
    fecha_hora: Optional[datetime] = None,
    ip: Optional[str] = None,
) -> tuple[UnidadDemo, EventoUnidad]:
    """HU-03: asignacion desde DISPONIBLE o reasignacion desde ASIGNADA (cierra la anterior)."""
    unidad = obtener_unidad_bloqueada(sesion, id_unidad)
    instante = validar_carga_diferida(sesion, id_unidad, fecha_hora)
    evento_tipo = estados.TipoEvento.REASIGNACION if reasignacion else estados.TipoEvento.ASIGNACION

    precondiciones: list[str] = []
    if unidad.circuito is not Circuito.COMERCIAL:
        precondiciones.append("Solo unidades del circuito COMERCIAL pueden asignarse a un responsable comercial.")
    resp = None
    try:
        resp = _validar_responsable(sesion, id_responsable, id_sucursal)
    except ErrorDominio as exc:
        precondiciones.append(exc.mensaje)
    if resp is not None:
        if not resp.activo:
            precondiciones.append("El responsable seleccionado está inactivo.")
        if resp.id_sucursal != id_sucursal:
            precondiciones.append(
                f"El responsable pertenece a la sucursal {resp.id_sucursal} y la unidad se asigna a {id_sucursal}."
            )

    evento = estados.transicionar(
        sesion, unidad, evento_tipo, usuario, origen,
        datos={"id_responsable": id_responsable, "id_sucursal": id_sucursal, **({"motivo": motivo} if motivo else {})},
        fecha_hora=instante,
        precondiciones=tuple(precondiciones),
    )
    _cerrar_asignaciones_abiertas(sesion, unidad.id, evento.fecha_hora)
    _abrir_asignacion(sesion, unidad, id_responsable, id_sucursal, evento.fecha_hora, evento.id_evento)
    unidad.id_sucursal = id_sucursal
    auditar(sesion, id_usuario=getattr(usuario, "id", None), accion="ASIGNACION", recurso=f"unidad:{unidad.id}", ip=ip, resultado="EXITO")
    return unidad, evento


def liberar(
    sesion: Session,
    id_unidad: int,
    *,
    usuario: Any,
    motivo: Optional[str] = None,
    origen: estados.Origen = estados.Origen.WEB,
    fecha_hora: Optional[datetime] = None,
    ip: Optional[str] = None,
) -> tuple[UnidadDemo, EventoUnidad]:
    """HU-03.5: cierra la asignacion vigente y la unidad vuelve a DISPONIBLE."""
    unidad = obtener_unidad_bloqueada(sesion, id_unidad)
    instante = validar_carga_diferida(sesion, id_unidad, fecha_hora)
    evento = estados.transicionar(
        sesion, unidad, estados.TipoEvento.LIBERACION, usuario, origen,
        datos={"motivo": motivo} if motivo else {},
        fecha_hora=instante,
    )
    _cerrar_asignaciones_abiertas(sesion, unidad.id, evento.fecha_hora)
    auditar(sesion, id_usuario=getattr(usuario, "id", None), accion="LIBERACION", recurso=f"unidad:{unidad.id}", ip=ip, resultado="EXITO")
    return unidad, evento


def service_ingreso(
    sesion: Session,
    id_unidad: int,
    *,
    usuario: Any,
    observaciones: Optional[str] = None,
    origen: estados.Origen = estados.Origen.WEB,
    fecha_hora: Optional[datetime] = None,
    ip: Optional[str] = None,
) -> tuple[UnidadDemo, EventoUnidad]:
    """HU-07.5: DISPONIBLE -> EN_SERVICE."""
    unidad = obtener_unidad_bloqueada(sesion, id_unidad)
    instante = validar_carga_diferida(sesion, id_unidad, fecha_hora)
    evento = estados.transicionar(
        sesion, unidad, estados.TipoEvento.INGRESO_SERVICE, usuario, origen,
        datos={"observaciones": observaciones} if observaciones else {},
        fecha_hora=instante,
    )
    auditar(sesion, id_usuario=getattr(usuario, "id", None), accion="SERVICE_INGRESO", recurso=f"unidad:{unidad.id}", ip=ip, resultado="EXITO")
    return unidad, evento


def service_fin(
    sesion: Session,
    id_unidad: int,
    *,
    km: int,
    proximo_service_km: Optional[int],
    usuario: Any,
    origen: estados.Origen = estados.Origen.WEB,
    fecha_hora: Optional[datetime] = None,
    ip: Optional[str] = None,
) -> tuple[UnidadDemo, EventoUnidad]:
    """HU-07.5: EN_SERVICE -> DISPONIBLE actualizando km y proximo service.

    El umbral de aviso (500 km) se guarda en los datos del evento para el tablero (etapa 4).
    """
    unidad = obtener_unidad_bloqueada(sesion, id_unidad)
    instante = validar_carga_diferida(sesion, id_unidad, fecha_hora)
    precondiciones: tuple[str, ...] = ()
    if km < unidad.km_actual:
        precondiciones = (f"El kilometraje ({km}) no puede ser menor al actual ({unidad.km_actual}).",)
    evento = estados.transicionar(
        sesion, unidad, estados.TipoEvento.FIN_SERVICE, usuario, origen,
        datos={"km": km, "proximo_service_km": proximo_service_km},
        fecha_hora=instante,
        precondiciones=precondiciones,
    )
    unidad.km_actual = km
    if proximo_service_km is not None:
        unidad.km_proximo_service = proximo_service_km
    else:
        intervalo = int(valor_parametro(sesion, "service_intervalo_km", "10000"))
        unidad.km_proximo_service = km + intervalo
    auditar(sesion, id_usuario=getattr(usuario, "id", None), accion="SERVICE_FIN", recurso=f"unidad:{unidad.id}", ip=ip, resultado="EXITO")
    return unidad, evento


def listar_unidades(
    sesion: Session,
    *,
    estados_unidad: Optional[list[str]] = None,
    circuito: Optional[Circuito] = None,
    texto: Optional[str] = None,
) -> list[UnidadDemo]:
    """Unidades por patente; `texto` busca por patente o VIN, sin distinguir mayusculas."""
    consulta = select(UnidadDemo).order_by(UnidadDemo.patente)
    if estados_unidad:
        consulta = consulta.where(UnidadDemo.estado_actual.in_(estados_unidad))
    if circuito is not None:
        consulta = consulta.where(UnidadDemo.circuito == circuito)
    if texto:
        patron = f"%{texto.strip()}%"
        consulta = consulta.where(or_(UnidadDemo.patente.ilike(patron), UnidadDemo.vin.ilike(patron)))
    return list(sesion.scalars(consulta))


def altas_recientes(sesion: Session, limite: int = 5) -> list[tuple[UnidadDemo, EventoUnidad]]:
    """Ultimas altas, mas reciente primero, con su evento ALTA (fecha y origen)."""
    filas = sesion.execute(
        select(UnidadDemo, EventoUnidad)
        .join(EventoUnidad, EventoUnidad.id_unidad == UnidadDemo.id)
        .where(EventoUnidad.tipo_evento == estados.TipoEvento.ALTA.value)
        .order_by(EventoUnidad.fecha_hora.desc(), EventoUnidad.id_evento.desc())
        .limit(limite)
    ).all()
    return [(unidad, evento) for unidad, evento in filas]


def asignaciones_de(sesion: Session, id_unidad: int) -> list[Asignacion]:
    """Asignaciones de la unidad, la mas reciente primero."""
    return list(
        sesion.scalars(
            select(Asignacion)
            .where(Asignacion.id_unidad == id_unidad)
            .order_by(Asignacion.fecha_desde.desc(), Asignacion.id.desc())
        )
    )


def historial_eventos(sesion: Session, id_unidad: int) -> list[EventoUnidad]:
    """HU-07.2: orden cronologico inverso (mas reciente primero)."""
    return list(
        sesion.scalars(
            select(EventoUnidad)
            .where(EventoUnidad.id_unidad == id_unidad)
            .order_by(EventoUnidad.fecha_hora.desc(), EventoUnidad.id_evento.desc())
        ).all()
    )


def responsable_en(sesion: Session, id_unidad: int, instante: Optional[datetime]) -> Optional[Responsable]:
    """HU-07.4: responsable vigente en una fecha y hora (default: ahora)."""
    momento = _instante_normal(instante) if instante else datetime.now(timezone.utc)
    return responsable_vigente(sesion, id_unidad, momento)
