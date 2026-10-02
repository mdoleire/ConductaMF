# paneles/alumno.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import text

from config import FILE_REGISTROS, FILE_ALUMNOS, PERIODOS_LECTIVOS
from database import (
    leer_todos_los_registros, 
    obtener_info_alumno_por_correo, 
    obtener_resumen_asistencia_alumno,
    obtener_engine_sql,
    format_calif
)

def format_calif_100(val):
    if val >= 90.0: return f"🟢 {val:.1f}"
    if val >= 70.0: return f"🟡 {val:.1f}"
    return f"🔴 {val:.1f}"

def renderizar_panel_alumno(gc, correo_alumno):
    st.markdown("## 🎓 Portal del Estudiante")
    
    info_estudiante = obtener_info_alumno_por_correo(gc, FILE_ALUMNOS, correo_alumno)
    
    if not info_estudiante:
        st.error("⛔ Expediente no localizado. Consulta a Coordinación.")
        st.stop()
        
    nombre_alumno = info_estudiante["Nombre"]
    grupo_alumno = info_estudiante["Grupo"]
    alumno_id_seguro = info_estudiante["ID"]
    
    col_saludo, col_cerrar = st.columns([4, 1])
    with col_saludo:
        st.markdown(f"Bienvenido, **{nombre_alumno}** | Grupo: **{grupo_alumno}**")
    with col_cerrar:
        if st.button("🔒 Salir", type="secondary"):
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()

    st.markdown("---")
    
    # 3 PESTAÑAS: Conducta, Asistencia y Calificaciones Académicas
    tab_conducta, tab_asistencia, tab_calificaciones = st.tabs([
        "🛡️ Mis Registros de Conducta", 
        "📅 Inasistencias y Derecho a Examen",
        "📚 Mis Calificaciones Académicas"
    ])

    # =============================================================
    # 1. PESTAÑA CONDUCTA
    # =============================================================
    with tab_conducta:
        df_global = leer_todos_los_registros(gc)
        if df_global.empty:
            df_mi_conducta = pd.DataFrame()
        else:
            if 'alumno_id' in df_global.columns and alumno_id_seguro:
                df_mi_conducta = df_global[df_global['alumno_id'].astype(str) == str(alumno_id_seguro)].copy()
            else:
                df_mi_conducta = df_global[
                    (df_global['Alumno'].astype(str).str.strip().str.lower() == nombre_alumno.lower()) &
                    (df_global['Grupo'].astype(str).str.strip().str.lower() == grupo_alumno.lower())
                ].copy()

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
                df_mostrar = df_mi_conducta[df_mi_conducta['Fecha'] >= (hoy - timedelta(days=7))]
            elif filtro_lapso == "Este Mes":
                df_mostrar = df_mi_conducta[(df_mi_conducta['Fecha'].dt.month == hoy.month) & (df_mi_conducta['Fecha'].dt.year == hoy.year)]
            elif filtro_lapso == "Por Periodo Lectivo":
                nivel_clave = "Preparatoria" if any(g in grupo_alumno for g in ["4°", "5°", "6°"]) else "Secundaria"
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

    # =============================================================
    # 2. PESTAÑA ASISTENCIA
    # =============================================================
    with tab_asistencia:
        st.markdown("### Estado de Asistencias por Materia")
        df_asistencias_alumno = obtener_resumen_asistencia_alumno(gc, nombre_alumno, grupo_alumno)
        if df_asistencias_alumno.empty:
            st.info("Aún no hay listas de asistencia activas para tu grupo.")
        else:
            st.dataframe(df_asistencias_alumno, use_container_width=True, hide_index=True)

    # =============================================================
    # 3. 📚 PESTAÑA CALIFICACIONES ACADÉMICAS (GOOGLE CLASSROOM / SUPABASE)
    # =============================================================
    with tab_calificaciones:
        st.markdown("### 📚 Calificaciones Académicas")
        
        nivel_clave = "Preparatoria" if any(g in grupo_alumno for g in ["4°", "5°", "6°"]) else "Secundaria"
        periodos_nivel = PERIODOS_LECTIVOS.get(nivel_clave, [])
        
        # Selector de Periodo para consultar
        nombres_periodos = [p["nombre"] for p in periodos_nivel]
        periodo_consulta = st.selectbox("Selecciona el Periodo:", nombres_periodos, key="al_per_calif")
        info_p = next(p for p in periodos_nivel if p["nombre"] == periodo_consulta)
        
        # Determinamos si el periodo está activo o ya cerró
        hoy_fecha = datetime.now(ZoneInfo("America/Mexico_City")).date()
        fecha_fin_periodo = datetime.strptime(info_p["fin"], "%Y-%m-%d").date()
        
        periodo_cerrado = hoy_fecha > fecha_fin_periodo
        
        # Consultamos las notas y ponderaciones del alumno desde Supabase
        engine = obtener_engine_sql()
        query_califs = text('''
            SELECT 
                n."Clase", 
                n."Nota", 
                a."Nombre_Actividad", 
                a."Rubro", 
                a."Puntos_Max",
                p."Porcentaje"
            FROM "calif_notas" n
            JOIN "calif_actividades" a ON n."ID_Actividad" = a."ID_Actividad"
            LEFT JOIN "calif_ponderaciones" p ON (n."Clase" = p."Clase" AND a."Periodo" = p."Periodo" AND a."Rubro" = p."Rubro")
            WHERE LOWER(TRIM(n."Alumno")) = :alm AND a."Periodo" = :per
        ''')
        
        df_mis_califs = pd.read_sql(query_califs, engine, params={"alm": nombre_alumno.lower().strip(), "per": periodo_consulta})
        
        if df_mis_califs.empty:
            st.info(f"💡 No hay calificaciones registradas para el **{periodo_consulta}** todavía.")
        else:
            # Agrupamos por Materia para calcular el promedio ponderado
            for clase_nombre, df_materia in df_mis_califs.groupby("Clase"):
                materia_limpia = clase_nombre.split(" - ")[0].strip()
                
                # 🏷️ REGLA OFICIAL DE TÍTULOS:
                if periodo_cerrado:
                    titulo_tarjeta = f"Calificación de {periodo_consulta} - {materia_limpia}"
                    estado_badge = "🔒 Periodo Cerrado (Final)"
                else:
                    titulo_tarjeta = f"Calificación Parcial de {materia_limpia}"
                    estado_badge = "⏳ En curso (Parcial)"
                
                # Cálculo de promedio ponderado base 100
                desglose_rubros = {}
                pesos_rubros = {}
                
                for _, r in df_materia.iterrows():
                    rubro = r["Rubro"]
                    pct = float(r["Porcentaje"] or 0)
                    nota = float(r["Nota"])
                    p_max = float(r["Puntos_Max"] or 100.0)
                    nota_100 = (nota / p_max) * 100.0 if p_max > 0 else 0.0
                    
                    if rubro not in desglose_rubros:
                        desglose_rubros[rubro] = []
                        pesos_rubros[rubro] = pct
                    desglose_rubros[rubro].append(nota_100)
                    
                peso_evaluado = sum(pesos_rubros.values())
                puntos_acum = 0.0
                for rubro, lista_notas in desglose_rubros.items():
                    prom_rubro = sum(lista_notas) / len(lista_notas)
                    puntos_acum += prom_rubro * (pesos_rubros[rubro] / 100.0)
                    
                promedio_final = (puntos_acum / (peso_evaluado / 100.0)) if peso_evaluado > 0 else 0.0
                promedio_final = round(promedio_final, 1)
                
                # Despliegue visual para el estudiante
                with st.container():
                    c_card1, c_card2 = st.columns([3, 1])
                    with c_card1:
                        st.subheader(titulo_tarjeta)
                        st.caption(f"Estado: {estado_badge}")
                    with c_card2:
                        st.metric("Promedio", f"{promedio_final} pts", delta=format_calif_100(promedio_final))
                        
                    # Detalle desplegable de las tareas de esa materia
                    with st.expander("👀 Ver desglose de tareas y exámenes"):
                        df_view_materia = df_materia[["Nombre_Actividad", "Rubro", "Nota", "Puntos_Max"]].copy()
                        df_view_materia.columns = ["Actividad", "Categoría", "Tu Calificación", "Puntos Máximos"]
                        st.dataframe(df_view_materia, use_container_width=True, hide_index=True)
                        
                st.markdown("---")