"""Servicio de sincronización DMS (HU-15).

Reglas:
1. empleados nuevos/actualizados por legajo (nombre, correo, sucursal, rol);
2. empleado dado de baja en el DMS -> usuario inactivo, historial intacto;
3. error de comunicacion -> se registra en auditoria y logs, y se reintenta en el
   siguiente ciclo (no rompe la aplicacion).
Las unidades del DMS que no existen aun se dan de alta a traves del motor de estados
(origen DMS), nunca con inserts directos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import auditoria, correo, estados, logs, seguridad
from app.core.config import settings
from app.core.excepciones import ErrorDominio
from app.identidad.models import Rol, Usuario
from app.identidad.service import generar_clave_temporal
from app.sincronizacion.dms import DMSAdapter, EmpleadoDMS, ErrorDMS, UnidadDMS
from app.unidades.models import Circuito
from app.unidades.service import alta_unidad


@dataclass
class ResultadoSync:
    creados: int = 0
    actualizados: int = 0
    dados_de_baja: int = 0
    unidades_alta: int = 0
    unidades_omitidas: int = 0
    error: Optional[str] = None
    detalle: list[str] = field(default_factory=list)


def _sincronizar_empleado(
    sesion: Session, emp: EmpleadoDMS, resultado: ResultadoSync, temporales: list[tuple[str, str]]
) -> None:
    existente = sesion.scalar(select(Usuario).where(Usuario.legajo == emp.legajo))
    if existente is None:
        temporal = generar_clave_temporal()
        sesion.add(
            Usuario(
                legajo=emp.legajo,
                correo=emp.correo,
                nombre=emp.nombre,
                rol=Rol[emp.rol] if emp.rol in Rol.__members__ else Rol.ASESOR,
                id_sucursal=emp.id_sucursal,
                activo=emp.activo,
                hash_clave=seguridad.hash_clave(temporal),
                debe_cambiar_clave=True,
                clave_temporal_hasta=datetime.now(timezone.utc) + timedelta(hours=settings.validez_clave_temporal_horas),
            )
        )
        if emp.activo:
            temporales.append((emp.correo, temporal))
        resultado.creados += 1
        resultado.detalle.append(f"alta legajo {emp.legajo}")
        return

    cambio = False
    rol_nuevo = Rol[emp.rol] if emp.rol in Rol.__members__ else existente.rol
    for atributo, valor in (
        ("nombre", emp.nombre),
        ("correo", emp.correo),
        ("id_sucursal", emp.id_sucursal),
        ("rol", rol_nuevo),
    ):
        if getattr(existente, atributo) != valor:
            setattr(existente, atributo, valor)
            cambio = True
    if existente.activo != emp.activo:
        existente.activo = emp.activo  # HU-15.2: la baja conserva su historial
        cambio = True
        if not emp.activo:
            resultado.dados_de_baja += 1
    if cambio:
        resultado.actualizados += 1
        resultado.detalle.append(f"actualizacion legajo {emp.legajo}")


def _sincronizar_unidad(sesion: Session, uni: UnidadDMS, usuario: Any, resultado: ResultadoSync) -> None:
    try:
        alta_unidad(
            sesion,
            vin=uni.vin,
            patente=uni.patente,
            modelo=uni.modelo,
            version=uni.version,
            circuito=Circuito[uni.circuito] if uni.circuito in Circuito.__members__ else Circuito.COMERCIAL,
            id_sucursal=uni.id_sucursal,
            km_inicial=uni.km_actual,
            usuario=usuario,
            origen=estados.Origen.DMS,
        )
        resultado.unidades_alta += 1
    except ErrorDominio as exc:  # ya registrada: se omite y sigue el ciclo
        if exc.codigo not in ("VIN_EXISTENTE", "PATENTE_EXISTENTE"):
            raise
        resultado.unidades_omitidas += 1


def sincronizar(sesion: Session, adaptador: DMSAdapter, usuario: Any) -> ResultadoSync:
    """Ejecuta un ciclo completo; devuelve el resultado (con `error` si fallo HU-15.3)."""
    resultado = ResultadoSync()
    id_usuario = getattr(usuario, "id", None)
    try:
        empleados = adaptador.traer_empleados()
        unidades = adaptador.traer_unidades()
    except ErrorDMS as exc:
        resultado.error = str(exc)
        auditoria.registrar(sesion, id_usuario=id_usuario, accion="SYNC_DMS", recurso="dms", ip=None, resultado="FRACASO")
        sesion.commit()
        logs.log_evento("sync.dms", estado="fracaso", motivo=str(exc)[:200])
        return resultado

    temporales: list[tuple[str, str]] = []
    for emp in empleados:
        _sincronizar_empleado(sesion, emp, resultado, temporales)
    sesion.flush()

    for uni in unidades:
        _sincronizar_unidad(sesion, uni, usuario, resultado)

    auditoria.registrar(sesion, id_usuario=id_usuario, accion="SYNC_DMS", recurso="dms", ip=None, resultado="EXITO")
    sesion.commit()
    # Despues del commit: si este envio falla, la persona puede pedir el enlace de recuperacion
    for destino, temporal in temporales:
        correo.enviar(
            destino,
            "Su cuenta de Parque Demo",
            f"Su contraseña temporal es: {temporal}\n\n"
            f"Vale {settings.validez_clave_temporal_horas} horas y un solo uso: "
            f"deberá reemplazarla al ingresar en {settings.url_publica}.",
        )
    logs.log_evento(
        "sync.dms",
        estado="exito",
        creados=resultado.creados,
        actualizados=resultado.actualizados,
        bajas=resultado.dados_de_baja,
        unidades=resultado.unidades_alta,
    )
    return resultado
