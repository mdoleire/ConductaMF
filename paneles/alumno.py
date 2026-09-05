# paneles/alumno.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import FILE_REGISTROS, FILE_ALUMNOS, PERIODOS_LECTIVOS
from database import (
    leer_todos_los_registros, 
    obtener_info_alumno_por_correo, 
    obtener_resumen_asistencia_alumno
)

def renderizar_panel_alumno(gc, correo_alumno):
    st.markdown("## 🎓 Portal del Estudiante")
    
    # 1. Identificar al estudiante de manera segura
    info_estudiante = obtener_info_alumno_por_correo(gc, FILE_ALUMNOS, correo_alumno)
    
    if not info_estudiante:
        st.error(f"⛔ No se localizó un expediente asociado a la cuenta: **{correo_alumno}**")
        st.info("Por favor, acude a Coordinación para verificar tu alta institucional.")
        
        # Botón de escape para evitar bloqueos
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔙 Salir / Iniciar sesión con otra cuenta"):
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()
            
        st.stop()
        
    nombre_alumno = info_estudiante["Nombre"]
    grupo_alumno = info_estudiante["Grupo"]
    
    col_saludo, col_cerrar = st.columns([4, 1])
    with col_saludo:
        st.markdown(f"Bienvenido, **{nombre_alumno}** | Grupo: **{grupo_alumno}**")
    with col_cerrar:
        if st.button("🔒 Salir", type="secondary"):
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()

    st.markdown("---")

    tab_conducta, tab_asistencia = st.tabs(["🛡️ Mis Registros de Conducta", "📅 Inasistencias y Derecho a Examen"])

    # -------------------------------------------------------------
    # SECCIÓN CONDUCTA
    # -------------------------------------------------------------
    with tab_conducta:
        df_global = leer_todos_los_registros(gc)
        
        if df_global.empty or 'Alumno' not in df_global.columns:
            df_mi_conducta = pd.DataFrame()
        else:
            df_mi_conducta = df_global[df_global['Alumno'].astype(str).str.strip().str.lower() == nombre_alumno.lower()].copy()

        if df_mi_conducta.empty:
            st.success("🌟 Tienes un expediente limpio. No registras ninguna incidencia disciplinaria.")
        else:
            df_mi_conducta['Fecha'] = pd.to_datetime(df_mi_conducta['Fecha'], errors='coerce')
            puntos_totales = pd.to_numeric(df_mi_conducta['Puntos_Descontados'], errors='coerce').fillna(0).sum()
            
            c_met1, c_met2 = st.columns(2)
            c_met1.metric("Incidencias Reportadas", f"{len(df_mi_conducta)}")
            c_met2.metric("Puntos Descontados", f"- {puntos_totales:.1f} pts")
            
            filtro_lapso = st.radio("Ventana de visualización:", ["Esta Semana", "Este Mes", "Por Periodo Lectivo", "Historial Completo"], horizontal=True)
            
            hoy = datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None)
            
            if filtro_lapso == "Esta Semana":
                fecha_corte = hoy - timedelta(days=7)
                df_mostrar = df_mi_conducta[df_mi_conducta['Fecha'] >= fecha_corte]
            elif filtro_lapso == "Este Mes":
                df_mostrar = df_mi_conducta[(df_mi_conducta['Fecha'].dt.month == hoy.month) & (df_mi_conducta['Fecha'].dt.year == hoy.year)]
            elif filtro_lapso == "Por Periodo Lectivo":
                nivel_clave = "Preparatoria" if ("4°" in grupo_alumno or "5°" in grupo_alumno or "6°" in grupo_alumno) else "Secundaria"
                periodos = PERIODOS_LECTIVOS.get(nivel_clave, [])
                opciones_p = [p['nombre'] for p in periodos]
                sel_p = st.selectbox("Selecciona Periodo:", opciones_p)
                p_datos = next(p for p in periodos if p['nombre'] == sel_p)
                df_mostrar = df_mi_conducta[(df_mi_conducta['Fecha'] >= p_datos['inicio']) & (df_mi_conducta['Fecha'] <= p_datos['fin'])]
            else:
                df_mostrar = df_mi_conducta

            if df_mostrar.empty:
                st.info(f"Sin incidencias registradas para el filtro: {filtro_lapso}.")
            else:
                cols_visibles = [c for c in ['Fecha', 'Materia', 'Categoría', 'Falta', 'Observaciones', 'Puntos_Descontados'] if c in df_mostrar.columns]
                df_mostrar_view = df_mostrar[cols_visibles].sort_values(by="Fecha", ascending=False).copy()
                df_mostrar_view['Fecha'] = df_mostrar_view['Fecha'].dt.strftime('%d/%m/%Y %H:%M')
                st.dataframe(df_mostrar_view, use_container_width=True, hide_index=True)

    # -------------------------------------------------------------
    # SECCIÓN ASISTENCIA
    # -------------------------------------------------------------
    with tab_asistencia:
        st.markdown("### Estado de Asistencias por Materia")
        st.caption("Conforme a los Artículos 19, 38 y las tablas de inasistencias del Acuerdo de Convivencia Escolar.")
        
        df_asistencias_alumno = obtener_resumen_asistencia_alumno(gc, nombre_alumno, grupo_alumno)
        
        if df_asistencias_alumno.empty:
            st.info("Aún no hay listas de asistencia activas para tu grupo.")
        else:
            st.dataframe(df_asistencias_alumno, use_container_width=True, hide_index=True)
            
            # Alertas tempranas preventivas
            alerta_riesgo = df_asistencias_alumno[df_asistencias_alumno['Faltas Efectivas'] >= (df_asistencias_alumno['Límite Permitido'] - 1)]
            if not alerta_riesgo.empty:
                st.warning("⚠️ **Atención:** Te encuentras en el límite o has superado el máximo de inasistencias permitidas en una o más materias. Consulta con tu Coordinación de Etapa.")