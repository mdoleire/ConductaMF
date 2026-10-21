# paneles/cambio_grupo.py
# Cambio de grupo de alumnos para coordinación y dirección.
#
# Qué hace un cambio:
#   1. alumnos: actualiza "Grupo_Base" (y "Área", si se elige otra).
#   2. conducta_registros: opcionalmente lleva el expediente al nuevo grupo.
#   3. alumnos_movimientos: deja constancia de quién, cuándo y por qué, para poder deshacerlo.
# La asistencia y las calificaciones del grupo anterior NO se tocan: pertenecen a las
# listas y actividades de esas clases.
import hashlib
import json
import logging
import re
import unicodedata
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from sqlalchemy import text

from database import (
    obtener_engine_sql,
    leer_todos_los_registros,
    obtener_info_alumno_por_correo,
    compilar_asistencias_grupo_tutor,
    obtener_resumen_asistencia_alumno,
)

ROLES_PERMITIDOS = ("director", "directivo", "coordinador")
SIN_AREA = "(sin área)"
PREFIJO_WIDGET = "cg_w_"   # se limpian después de cada cambio
ZONA = ZoneInfo("America/Mexico_City")

# Identifica la fila exacta del alumno. Si coincide más de una, no se hace nada.
WHERE_ALUMNO = '''"ID" IS NOT DISTINCT FROM :id
              AND "Apellido Paterno" IS NOT DISTINCT FROM :ap
              AND "Apellido Materno" IS NOT DISTINCT FROM :am
              AND "Nombres" IS NOT DISTINCT FROM :nom
              AND TRIM("Grupo_Base") = :grupo_actual'''

# Grupo de una clase "Materia - Grupo (Área X)" → "Grupo"
GRUPO_DE_CLASE = '''TRIM(SPLIT_PART(REGEXP_REPLACE("Clase", '^.* - ', ''), '(', 1))'''


# =================================================================
# AUXILIARES
# =================================================================
def _leer(engine, sql, params=None):
    with engine.connect() as conn:
        filas = conn.execute(text(sql), params or {}).mappings().all()
    return pd.DataFrame([dict(f) for f in filas])

def _valor(v):
    """None para vacíos de la base (NULL/NaN); el texto tal cual para lo demás."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v)

def _nombre(ap, am, nom):
    return " ".join(" ".join(x or "" for x in (ap, am, nom)).split())

def _sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s).lower()) if unicodedata.category(c) != "Mn")

def _grado(grupo):
    m = re.search(r"\d", str(grupo))
    return int(m.group()) if m else None

def _orden_grupo(g):
    gr = _grado(g)
    return (gr if gr is not None else 99, str(g))

def _grupos_permitidos(todos, rol, area):
    """Directores de sección solo ven su nivel (mismo criterio que el panel directivo)."""
    if str(rol).strip().lower() in ("director", "directivo"):
        area_l = str(area).strip().lower()
        if "prepa" in area_l:
            return [g for g in todos if _grado(g) in (4, 5, 6)]
        if "secun" in area_l:
            return [g for g in todos if _grado(g) in (1, 2, 3)]
    return list(todos)

def _identidad(al):
    return {"id": _valor(al["ID"]), "ap": _valor(al["Apellido Paterno"]),
            "am": _valor(al["Apellido Materno"]), "nom": _valor(al["Nombres"])}

def _limpiar_caches():
    for funcion in (leer_todos_los_registros, obtener_info_alumno_por_correo,
                    compilar_asistencias_grupo_tutor, obtener_resumen_asistencia_alumno):
        try:
            funcion.clear()
        except Exception:
            pass

def _limpiar_widgets():
    for k in [k for k in list(st.session_state.keys()) if str(k).startswith(PREFIJO_WIDGET)]:
        del st.session_state[k]

def _contar_historial(engine, nombre, grupo):
    df = _leer(engine, f'''
        SELECT
          (SELECT count(*) FROM "conducta_registros"
            WHERE LOWER(TRIM("Alumno")) = :n AND TRIM(SPLIT_PART("Grupo", '(', 1)) = :g) AS conducta,
          (SELECT count(*) FROM "asistencia_registros"
            WHERE LOWER(TRIM("Alumno")) = :n AND {GRUPO_DE_CLASE} = :g) AS asistencia,
          (SELECT count(*) FROM "calif_notas"
            WHERE LOWER(TRIM("Alumno")) = :n AND {GRUPO_DE_CLASE} = :g) AS notas
    ''', {"n": nombre.lower(), "g": grupo})
    fila = df.iloc[0] if not df.empty else {}
    return {k: int(fila.get(k, 0) or 0) for k in ("conducta", "asistencia", "notas")}


# =================================================================
# OPERACIONES EN LA BASE (una transacción cada una)
# =================================================================
def _ejecutar_cambio(engine, al, destino, area_destino, mover_conducta, motivo, realizado_por):
    ident = _identidad(al)
    with engine.begin() as conn:
        res = conn.execute(
            text(f'UPDATE "alumnos" SET "Grupo_Base" = :destino, "Área" = :area WHERE {WHERE_ALUMNO}'),
            {**ident, "grupo_actual": al["Grupo"], "destino": destino, "area": area_destino},
        )
        if res.rowcount != 1:
            raise ValueError(
                f"se esperaba 1 alumno y coincidieron {res.rowcount}. Revisa que no esté duplicado en la tabla de alumnos."
            )

        conducta_original = {}
        if mover_conducta:
            previas = conn.execute(
                text('''SELECT incidencia_id, "Grupo" FROM "conducta_registros"
                        WHERE LOWER(TRIM("Alumno")) = :nombre AND TRIM(SPLIT_PART("Grupo", '(', 1)) = :origen
                        FOR UPDATE'''),
                {"nombre": al["Nombre"].lower(), "origen": al["Grupo"]},
            ).fetchall()
            conducta_original = {str(i): g for i, g in previas}
            if conducta_original:
                conn.execute(
                    text('UPDATE "conducta_registros" SET "Grupo" = :destino WHERE incidencia_id = ANY(:ids)'),
                    {"destino": destino, "ids": [int(i) for i in conducta_original]},
                )

        conn.execute(
            text('''INSERT INTO "alumnos_movimientos"
                      (alumno_id, apellido_paterno, apellido_materno, nombres, nombre_completo,
                       grupo_origen, grupo_destino, area_origen, area_destino,
                       conducta_original, motivo, realizado_por)
                    VALUES (:id, :ap, :am, :nom, :nombre, :origen, :destino, :area_origen, :area_destino,
                            CAST(:conducta AS jsonb), :motivo, :por)'''),
            {**ident, "nombre": al["Nombre"], "origen": al["Grupo"], "destino": destino,
             "area_origen": _valor(al["Área"]), "area_destino": area_destino,
             "conducta": json.dumps(conducta_original), "motivo": motivo, "por": realizado_por},
        )
    return len(conducta_original)

def _deshacer_cambio(engine, mov_id, realizado_por):
    with engine.begin() as conn:
        m = conn.execute(
            text('SELECT * FROM "alumnos_movimientos" WHERE id = :id AND revertido_en IS NULL FOR UPDATE'),
            {"id": int(mov_id)},
        ).mappings().first()
        if m is None:
            raise ValueError("ese cambio ya se había deshecho.")

        res = conn.execute(
            text(f'UPDATE "alumnos" SET "Grupo_Base" = :destino, "Área" = :area WHERE {WHERE_ALUMNO}'),
            {"id": m["alumno_id"], "ap": m["apellido_paterno"], "am": m["apellido_materno"], "nom": m["nombres"],
             "grupo_actual": m["grupo_destino"], "destino": m["grupo_origen"], "area": m["area_origen"]},
        )
        if res.rowcount != 1:
            raise ValueError(
                f"{m['nombre_completo']} ya no está en {m['grupo_destino']} (quizá lo cambiaron otra vez). No se deshizo nada."
            )

        for inc_id, grupo_anterior in (m["conducta_original"] or {}).items():
            # Solo regresa las incidencias que siguen en el grupo destino
            conn.execute(
                text('UPDATE "conducta_registros" SET "Grupo" = :g WHERE incidencia_id = :i AND "Grupo" = :dest'),
                {"g": grupo_anterior, "i": int(inc_id), "dest": m["grupo_destino"]},
            )

        conn.execute(
            text('UPDATE "alumnos_movimientos" SET revertido_en = now(), revertido_por = :por WHERE id = :id'),
            {"por": realizado_por, "id": int(mov_id)},
        )
    return m["nombre_completo"], m["grupo_origen"]


# =================================================================
# CALLBACKS DE LOS BOTONES (leen los valores vigentes de los widgets)
# =================================================================
def _al_confirmar_cambio(engine, al, permitidos, realizado_por, k):
    destino = st.session_state.get(f"{k}_destino")
    motivo = " ".join(str(st.session_state.get(f"{k}_motivo", "")).split())
    mover_conducta = bool(st.session_state.get(f"{k}_conducta", True))
    area_sel = st.session_state.get(f"{k}_area")
    area_original = _valor(al["Área"])
    area_actual_txt = area_original if area_original else SIN_AREA
    if area_sel is None or area_sel == area_actual_txt:
        area_destino = area_original
    else:
        area_destino = None if area_sel == SIN_AREA else area_sel

    if al["Grupo"] not in permitidos or destino not in permitidos or destino == al["Grupo"]:
        st.session_state["cg_aviso"] = ("error", "🚨 No se hizo el cambio: el grupo destino no es válido.")
        return
    if len(motivo) < 5:
        st.session_state["cg_aviso"] = ("error", "🚨 No se hizo el cambio: escribe el motivo.")
        return
    try:
        n_conducta = _ejecutar_cambio(engine, al, destino, area_destino, mover_conducta, motivo, realizado_por)
    except ValueError as e:
        st.session_state["cg_aviso"] = ("error", f"🚨 No se hizo el cambio: {e}")
        return
    except Exception:
        logging.exception("Error al cambiar de grupo")
        st.session_state["cg_aviso"] = ("error", "🚨 No se hizo el cambio por un error de conexión. Intenta de nuevo.")
        return

    _limpiar_caches()
    _limpiar_widgets()
    extra = f" Su expediente de conducta ({n_conducta} incidencia(s)) se fue con él." if n_conducta else ""
    st.session_state["cg_aviso"] = ("success", f"✅ {al['Nombre']} cambió de {al['Grupo']} a {destino}.{extra}")

def _al_deshacer(engine, realizado_por):
    mov_id = st.session_state.get(f"{PREFIJO_WIDGET}deshacer_sel")
    if mov_id is None:
        return
    try:
        nombre, grupo = _deshacer_cambio(engine, mov_id, realizado_por)
    except ValueError as e:
        st.session_state["cg_aviso"] = ("error", f"🚨 No se deshizo el cambio: {e}")
        return
    except Exception:
        logging.exception("Error al deshacer cambio de grupo")
        st.session_state["cg_aviso"] = ("error", "🚨 No se deshizo el cambio por un error de conexión. Intenta de nuevo.")
        return
    _limpiar_caches()
    _limpiar_widgets()
    st.session_state["cg_aviso"] = ("success", f"↩️ Cambio deshecho: {nombre} regresó a {grupo}.")


# =================================================================
# SECCIONES DEL PANEL
# =================================================================
def _seccion_mover(engine, df, permitidos, realizado_por):
    grupos_con_alumnos = sorted(set(df["Grupo"]), key=_orden_grupo)
    c_grupo, c_buscar = st.columns([1, 2])
    grupo_filtro = c_grupo.selectbox("Grupo actual", ["Todos"] + grupos_con_alumnos, key=f"{PREFIJO_WIDGET}filtro")
    busqueda = c_buscar.text_input("Buscar por nombre, correo o ID", key=f"{PREFIJO_WIDGET}buscar")

    candidatos = df if grupo_filtro == "Todos" else df[df["Grupo"] == grupo_filtro]
    if busqueda.strip():
        palabras = _sin_acentos(busqueda).split()
        candidatos = candidatos[candidatos["_busqueda"].apply(lambda h: all(p in h for p in palabras))]
    if candidatos.empty:
        st.info("No hay alumnos con ese filtro. Prueba con otro grupo o con menos palabras.")
        return

    etiquetas = dict(zip(candidatos["_clave"], candidatos["Nombre"] + " (" + candidatos["Grupo"] + ")"))
    clave = st.selectbox(
        "Alumno", list(etiquetas), format_func=etiquetas.get, index=None,
        placeholder=f"Elige entre {len(etiquetas)} alumno(s)", key=f"{PREFIJO_WIDGET}alumno",
    )
    if clave is None:
        return

    al = df[df["_clave"] == clave].iloc[0]
    k = f"{PREFIJO_WIDGET}{hashlib.md5(clave.encode()).hexdigest()[:10]}"

    with st.container(border=True):
        st.markdown(f"#### {al['Nombre']}")
        area_txt = f", área {al['Área']}" if _valor(al["Área"]) else ""
        st.caption(f"Está en **{al['Grupo']}**{area_txt}. ID {_valor(al['ID']) or 'no registrado'}, "
                   f"correo {_valor(al['correo']) or 'no registrado'}.")

        opciones_destino = [g for g in permitidos if g != al["Grupo"]]
        destino = st.selectbox("Cambiar al grupo", opciones_destino, index=None,
                               placeholder="Elige el grupo nuevo", key=f"{k}_destino")
        if destino is None:
            return

        areas = sorted({a for a in df["Área"].map(_valor).dropna() if a.strip()})
        if areas:
            opciones_area = [SIN_AREA] + areas
            area_actual_txt = _valor(al["Área"]) or SIN_AREA
            st.selectbox("Área en el grupo nuevo", opciones_area,
                         index=opciones_area.index(area_actual_txt) if area_actual_txt in opciones_area else 0,
                         key=f"{k}_area", help="Solo importa en los grupos que se dividen por área.")

        conteos = _contar_historial(engine, al["Nombre"], al["Grupo"])
        mover_conducta = st.checkbox(
            f"Llevar su expediente de conducta al {destino} ({conteos['conducta']} incidencia(s))",
            value=True, key=f"{k}_conducta",
            help="Si lo desmarcas, sus reportes se quedan en el grupo anterior y ni su nuevo tutor ni él los verán.",
        )
        motivo = st.text_input("Motivo del cambio", max_chars=120, key=f"{k}_motivo",
                               placeholder="Ej. Solicitud de los padres, reacomodo de grupos")

        conducta_txt = (f"sus {conteos['conducta']} incidencia(s) de conducta pasan al {destino}"
                        if mover_conducta else f"sus {conteos['conducta']} incidencia(s) de conducta se quedan en el {al['Grupo']}")
        st.info(
            f"**Qué va a pasar:** {al['Nombre']} sale de las listas del {al['Grupo']} y entra a las del {destino}; "
            f"{conducta_txt}. Sus {conteos['asistencia']} registro(s) de asistencia y {conteos['notas']} calificación(es) "
            f"se quedan guardados en las clases del {al['Grupo']}: no se borra nada, y en el {destino} empieza sin faltas "
            f"ni calificaciones."
        )

        cambia_grado = _grado(al["Grupo"]) != _grado(destino)
        grado_ok = True
        if cambia_grado:
            st.warning(f"⚠️ Este cambio también lo pasa de {_grado(al['Grupo'])}° a {_grado(destino)}°.")
            grado_ok = st.checkbox("Sí, el cambio de grado es correcto", key=f"{k}_grado")

        confirmado = st.checkbox("Revisé los datos", key=f"{k}_confirmar")
        listo = confirmado and grado_ok and len(" ".join(motivo.split())) >= 5
        if not listo:
            st.caption("Para continuar escribe el motivo y marca «Revisé los datos».")
        st.button(
            "🔀 Cambiar de grupo", type="primary", disabled=not listo, key=f"{k}_boton",
            on_click=_al_confirmar_cambio, args=(engine, al.to_dict(), permitidos, realizado_por, k),
        )

def _seccion_historial(engine, permitidos, realizado_por):
    df_h = _leer(engine, '''
        SELECT id, fecha, nombre_completo, grupo_origen, grupo_destino, motivo,
               realizado_por, revertido_en, revertido_por
        FROM "alumnos_movimientos" ORDER BY fecha DESC LIMIT 300
    ''')
    if not df_h.empty:
        df_h = df_h[df_h["grupo_origen"].isin(permitidos) | df_h["grupo_destino"].isin(permitidos)]
    if df_h.empty:
        st.info("Todavía no hay cambios de grupo registrados.")
        return

    def _fmt(ts):
        return pd.Timestamp(ts).tz_convert(ZONA).strftime("%d/%m/%Y %H:%M") if pd.notna(ts) else ""

    vista = pd.DataFrame({
        "Fecha": df_h["fecha"].map(_fmt),
        "Alumno": df_h["nombre_completo"],
        "De": df_h["grupo_origen"],
        "A": df_h["grupo_destino"],
        "Motivo": df_h["motivo"],
        "Hecho por": df_h["realizado_por"],
        "Estado": [f"Deshecho el {_fmt(r)} por {p}" if pd.notna(r) else "Vigente"
                   for r, p in zip(df_h["revertido_en"], df_h["revertido_por"])],
    })
    st.dataframe(vista, hide_index=True, use_container_width=True, height=min(400, 38 * (len(vista) + 1)))

    vigentes = df_h[df_h["revertido_en"].isna()]
    if vigentes.empty:
        return
    st.markdown("#### Deshacer un cambio")
    etiquetas = {int(r.id): f"{_fmt(r.fecha)}: {r.nombre_completo}, de {r.grupo_origen} a {r.grupo_destino}"
                 for r in vigentes.itertuples()}
    sel = st.selectbox("Cambio a deshacer", list(etiquetas), format_func=etiquetas.get, index=None,
                       placeholder="Elige un cambio", key=f"{PREFIJO_WIDGET}deshacer_sel")
    if sel is None:
        return
    st.caption("El alumno regresa a su grupo y área anteriores, y las incidencias que se movieron vuelven a ese grupo.")
    confirmado = st.checkbox("Sí, quiero deshacerlo", key=f"{PREFIJO_WIDGET}deshacer_ok")
    st.button("↩️ Deshacer cambio", disabled=not confirmado, key=f"{PREFIJO_WIDGET}deshacer_btn",
              on_click=_al_deshacer, args=(engine, realizado_por))


# =================================================================
# PANEL PRINCIPAL
# =================================================================
def renderizar_panel_cambio_grupo(correo_usuario, correo_real, rol, area):
    st.header("🔀 Cambio de Grupo")

    if str(rol).strip().lower() not in ROLES_PERMITIDOS:
        st.error("⛔ Solo coordinación y dirección pueden cambiar alumnos de grupo.")
        return

    aviso = st.session_state.pop("cg_aviso", None)
    if aviso:
        getattr(st, aviso[0])(aviso[1])

    realizado_por = correo_usuario if correo_usuario == correo_real else f"{correo_usuario} (vía {correo_real})"
    engine = obtener_engine_sql()

    try:
        existe = bool(_leer(engine, "SELECT to_regclass('public.alumnos_movimientos') IS NOT NULL AS existe")["existe"].iloc[0])
    except Exception:
        logging.exception("No se pudo revisar la bitácora de cambios")
        existe = False
    if not existe:
        st.error("⚙️ Falta la bitácora de cambios (tabla alumnos_movimientos). Corre cambio_grupo.sql en el SQL Editor de Supabase y recarga.")
        return

    df = _leer(engine, '''
        SELECT "ID", "Apellido Paterno", "Apellido Materno", "Nombres", "correo", "Área",
               TRIM("Grupo_Base") AS "Grupo"
        FROM "alumnos"
        ORDER BY TRIM("Grupo_Base"), "Apellido Paterno", "Apellido Materno", "Nombres"
    ''')
    df_asig = _leer(engine, '''
        SELECT DISTINCT TRIM(SPLIT_PART("Grupo", '(', 1)) AS grupo
        FROM "asignaciones" WHERE COALESCE(TRIM("Grupo"), '') <> ''
    ''')
    if df.empty:
        st.info("La tabla de alumnos está vacía.")
        return

    df["Grupo"] = df["Grupo"].map(lambda g: _valor(g) or "")
    df["Nombre"] = [_nombre(_valor(a), _valor(b), _valor(c))
                    for a, b, c in zip(df["Apellido Paterno"], df["Apellido Materno"], df["Nombres"])]
    df["_clave"] = [json.dumps([_valor(i), _valor(a), _valor(b), _valor(c), g])
                    for i, a, b, c, g in zip(df["ID"], df["Apellido Paterno"], df["Apellido Materno"], df["Nombres"], df["Grupo"])]
    df["_busqueda"] = [_sin_acentos(f"{n} {_valor(c) or ''} {_valor(i) or ''}")
                       for n, c, i in zip(df["Nombre"], df["correo"], df["ID"])]

    todos = set(df["Grupo"]) | (set(df_asig["grupo"].map(_valor).dropna()) if not df_asig.empty else set())
    todos = sorted({g for g in todos if g}, key=_orden_grupo)
    permitidos = _grupos_permitidos(todos, rol, area)
    if not permitidos:
        st.warning("No hay grupos de tu sección para administrar.")
        return
    if len(permitidos) < len(todos):
        st.caption(f"Puedes mover alumnos entre los grupos de tu sección: {', '.join(permitidos)}.")

    df_perm = df[df["Grupo"].isin(permitidos)]

    tab_mover, tab_historial = st.tabs(["🔀 Cambiar de grupo", "🕑 Historial y deshacer"])
    with tab_mover:
        _seccion_mover(engine, df_perm, permitidos, realizado_por)
    with tab_historial:
        _seccion_historial(engine, permitidos, realizado_por)