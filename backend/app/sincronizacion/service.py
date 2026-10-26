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
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import auditoria, estados, logs
from app.core.config import settings
from app.identidad.models import Rol, Usuario
from app.sincronizacion.dms import DMSAdapter, ErrorDMS
from app.unidades.models import Circuito
from app.unidades.service import alta_unidad


@dataclass
class ResultadoSync:
    creados: int = 0
    actualizados: int = 0
    dados_de_baja: int = 0
    unidades_alta: int = 0
    unidades_omitas: int = 0
    error: Optional[str] = None
    detalle: list[str] = field(default_factory=list)


def sincronizar(sesion: Session, adaptador: DMSAdapter, usuario: Any, *, fallar: bool = False) -> ResultadoSync:
    """Ejecuta un ciclo completo; devuelve el resultado (con `error` si fallo HU-15.3)."""
    resultado = ResultadoSync()
    try:
        if isinstance(adaptador, object) and hasattr(adaptador, "traer_empleados"):
            try:
                import inspect

                sig = inspect.signature(adaptador.traer_empleados)
                kwargs = {"fallar": fallar} if "fallar" in sig.parameters else {}
            except (TypeError, ValueError):  # pragma: no cover
                kwargs = {}
            empleados = adaptador.traer_empleados(**kwargs)
            unidades = adaptador.traer_unidades(**kwargs)
        else:  # pragma: no cover
            raise ErrorDMS("Adaptador invalido.")
    except ErrorDMS as exc:
        resultado.error = str(exc)
        auditoria.registrar(sesion, id_usuario=getattr(usuario, "id", None), accion="SYNC_DMS", recurso="dms", ip=None, resultado="FRACASO")
        sesion.commit()
        logs.log_evento("sync.dms", estado="fracaso", motivo=str(exc)[:200])
        return resultado

    for emp in empleados:
        existente = sesion.scalar(select(Usuario).where(Usuario.legajo == emp.legajo))
        if existente is None:
            rol = Rol[emp.rol] if emp.rol in Rol.__members__ else Rol.ASESOR
            sesion.add(
                Usuario(
                    legajo=emp.legajo,
                    correo=emp.correo,
                    nombre=emp.nombre,
                    rol=rol,
                    id_sucursal=emp.id_sucursal,
                    activo=emp.activo,
                    hash_clave="",  # sin clave hasta recuperacion (HU-01)
                    debe_cambiar_clave=True,
                )
            )
            resultado.creados += 1
            resultado.detalle.append(f"alta legajo {emp.legajo}")
        else:
            cambio = False
            if existente.nombre != emp.nombre:
                existente.nombre = emp.nombre
                cambio = True
            if existente.id_sucursal != emp.id_sucursal:
                existente.id_sucursal = emp.id_sucursal
                cambio = True
            rol_nuevo = Rol[emp.rol] if emp.rol in Rol.__members__ else existente.rol
            if existente.rol is not rol_nuevo:
                existente.rol = rol_nuevo
                cambio = True
            if existente.activo and not emp.activo:
                existente.activo = False  # HU-15.2: inactivo, conserva su historial
                cambio = True
                resultado.dados_de_baja += 1
            elif not existente.activo and emp.activo:
                existente.activo = True
                cambio = True
            if cambio:
                resultado.actualizados += 1
                resultado.detalle.append(f"actualizacion legajo {emp.legajo}")
    sesion.flush()

    admin = usuario if usuario is not None and getattr(usuario, "id", None) else None
    for uni in unidades:
        circuito = Circuito[uni.circuito] if uni.circuito in Circuito.__members__ else Circuito.COMERCIAL
        try:
            alta_unidad(
                sesion,
                vin=uni.vin,
                patente=uni.patente,
                modelo=uni.modelo,
                version=uni.version,
                circuito=circuito,
                id_sucursal=uni.id_sucursal,
                km_inicial=uni.km_actual,
                usuario=admin,
                origen=estados.Origen.DMS,
            )
            resultado.unidades_alta += 1
        except Exception as exc:  # duplicado u otra regla: se omite y sigue el ciclo
            from app.core.excepciones import ErrorDominio

            if isinstance(exc, ErrorDominio) and exc.codigo in ("VIN_EXISTENTE", "PATENTE_EXISTENTE"):
                sesion.rollback() if False else None
                resultado.unidades_omitas += 1
            else:
                raise

    auditoria.registrar(sesion, id_usuario=getattr(usuario, "id", None), accion="SYNC_DMS", recurso="dms", ip=None, resultado="EXITO")
    sesion.commit()
    logs.log_evento(
        "sync.dms",
        estado="exito",
        creados=resultado.creados,
        actualizados=resultado.actualizados,
        bajas=resultado.dados_de_baja,
        unidades=resultado.unidades_alta,
    )
    return resultado


def ciclo_programado(sesion_factory: Any, adaptador: DMSAdapter) -> None:
    """Invocado por el planificador interno cada SYNC_DMS_CADA_MINUTOS."""
    sesion = sesion_factory()
    try:
        sincronizar(sesion, adaptador, usuario=None)
    finally:
        sesion.close()
