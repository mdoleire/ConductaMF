# paneles/tutor.py
import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import gspread

from config import (
    FILE_ASIGNACIONES, 
    FILE_ALUMNOS, 
    FILE_ASISTENCIA, 
    PERIODOS_LECTIVOS,
    SUPER_USUARIOS_WHITELIST
)
from database import (
    leer_datos, 
    leer_todos_los_registros, 
    obtener_lista_alumnos, 
    leer_todas_las_asignaciones
)
from calculadora import format_calif, calcular_calificacion_progresiva

def renderizar_panel_tutor(gc, usuario, nombre_prof):
    st.header(f"🧑‍🏫 Panel de Tutoría: {nombre_prof}")
    
    usuario = str(usuario).lower().strip()
    es_superusuario = usuario in SUPER_USUARIOS_WHITELIST
    
    # 1. Buscar los grupos tutelados
    df_asig = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
    
    if df_asig.empty or 'Usuario_Profesor' not in df_asig.columns:
        st.warning("⚠️ No se encontró la estructura de asignaciones.")
        return

    df_asig['Usuario_Profesor'] = df_asig['Usuario_Profesor'].astype(str).str.lower().str.strip()
    if 'Materia' in df_asig.columns:
        df_asig['Materia'] = df_asig['Materia'].astype(str).str.strip()
    if 'Grupo' in df_asig.columns:
        df_asig['Grupo'] = df_asig['Grupo'].astype(str).str.strip()

    if es_superusuario:
        mis_grupos_tutor = df_asig[df_asig['Materia'] == 'Tutor']['Grupo'].unique().tolist()
        if not mis_grupos_tutor:
            mis_grupos_tutor = df_asig['Grupo'].unique().tolist()
    else:
        mis_grupos_tutor = df_asig[(df_asig['Usuario_Profesor'] == usuario) & (df_asig['Materia'] == 'Tutor')]['Grupo'].unique().tolist()
    
    if not mis_grupos_tutor:
        st.warning("⚠️ No tienes ningún grupo asignado bajo la materia 'Tutor'.")
        return
        
    grupo_sel = st.selectbox("Grupo de Tutoría:", mis_grupos_tutor)
    
    fila_grupo = df_asig[df_asig['Grupo'] == grupo_sel]
    nivel_grupo = fila_grupo['Nivel'].iloc[0] if not fila_grupo.empty and 'Nivel' in fila_grupo.columns else "Preparatoria"
    
    st.markdown("---")
    
    modo_tutor = st.radio(
        "Perspectiva de Análisis:", 
        ["👥 Visión General del Grupo (Por Mes)", "👤 Expediente por Alumno (Detallado)"], 
        horizontal=True
    )
    st.markdown("---")
    
    # =================================================================
    # COMPILACIÓN DE DATOS (CONDUCTA + ASISTENCIA)
    # =================================================================
    with st.spinner("Recuperando registros integrales..."):
        df_full = leer_todos_los_registros(gc)
        
        if not df_full.empty and 'Grupo' in df_full.columns:
            df_full['Grupo'] = df_full['Grupo'].astype(str).str.strip()
            
        df_grupo_conducta = df_full[df_full['Grupo'] == grupo_sel].copy() if not df_full.empty else pd.DataFrame()
        if not df_grupo_conducta.empty:
            df_grupo_conducta['Fecha_DT'] = pd.to_datetime(df_grupo_conducta['Fecha'], errors='coerce')
        
        # Lectura segura de asistencias
        df_asist_plana = pd.DataFrame()
        try:
            doc_asist = gc.open(FILE_ASISTENCIA)
            hojas = doc_asist.worksheets()
            sufijo_grupo = f" - {grupo_sel.strip()}"
            hojas_grupo = [h for h in hojas if h.title.strip().endswith(sufijo_grupo)]
            
            list_melted = []
            for h in hojas_grupo:
                try:
                    datos = h.get_all_values()
                    if len(datos) > 1:
                        cols = datos[0]
                        df_temp = pd.DataFrame(datos[1:], columns=cols)
                        materia = h.title.replace(sufijo_grupo, "").strip()
                        
                        fechas_cols = [c for c in cols if c != 'Alumno']
                        if fechas_cols:
                            df_melt = df_temp.melt(id_vars=['Alumno'], value_vars=fechas_cols, var_name='Fecha', value_name='Falta')
                            df_melt['Materia'] = materia
                            df_melt['Categoría'] = 'Asistencia'
                            df_melt['Profesor'] = 'Control de Asistencia'
                            df_melt['Puntos_Descontados'] = 0
                            df_melt['Observaciones'] = ''
                            list_melted.append(df_melt)
                except Exception:
                    continue
            
            if list_melted:
                df_asist_plana = pd.concat(list_melted, ignore_index=True)
                df_asist_plana = df_asist_plana[df_asist_plana['Falta'].isin(['🔴 Falta', '🟡 Retardo'])]
                
                if not df_asist_plana.empty:
                    df_asist_plana['Fecha_DT'] = pd.to_datetime(df_asist_plana['Fecha'], format='%d-%m-%Y', errors='coerce')
                    df_asist_plana['Fecha'] = df_asist_plana['Fecha_DT'].dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
            
        if not df_asist_plana.empty and not df_grupo_conducta.empty:
            columnas_comunes = ['Fecha', 'Alumno', 'Profesor', 'Materia', 'Categoría', 'Falta', 'Observaciones', 'Puntos_Descontados', 'Fecha_DT']
            for col in columnas_comunes:
                if col not in df_asist_plana.columns: df_asist_plana[col] = None
                if col not in df_grupo_conducta.columns: df_grupo_conducta[col] = None
            
            df_unificado = pd.concat([df_grupo_conducta[columnas_comunes], df_asist_plana[columnas_comunes]], ignore_index=True)
        elif not df_asist_plana.empty:
            df_unificado = df_asist_plana.copy()
        else:
            df_unificado = df_grupo_conducta.copy()

    if df_unificado.empty:
        df_unificado = pd.DataFrame(columns=['Fecha', 'Alumno', 'Profesor', 'Materia', 'Categoría', 'Falta', 'Observaciones', 'Puntos_Descontados', 'Fecha_DT'])

    # =================================================================
    # MODO 1: RESUMEN MENSUAL GRUPAL
    # =================================================================
    if modo_tutor == "👥 Visión General del Grupo (Por Mes)":
        st.subheader(f"📊 Resumen del Grupo: {grupo_sel}")
        
        if df_unificado.empty:
            st.success(f"✨ El grupo {grupo_sel} no presenta incidencias registradas.")
            return
            
        meses_dict = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
        meses_disponibles = sorted(df_unificado['Fecha_DT'].dt.month.dropna().unique().tolist())
        nombres_meses = [meses_dict[m] for m in meses_disponibles if m in meses_dict]
        
        if not nombres_meses:
            st.info("Sin registros con fechas válidas para agrupar.")
            return
            
        mes_sel = st.selectbox("Selecciona Mes:", nombres_meses)
        mes_num = [k for k, v in meses_dict.items() if v == mes_sel][0]
        
        df_mes = df_unificado[df_unificado['Fecha_DT'].dt.month == mes_num].copy()
        
        if df_mes.empty:
            st.success(f"Sin registros en el mes de {mes_sel}.")
        else:
            c1, c2, c3 = st.columns(3)
            total_conducta = len(df_mes[df_mes['Categoría'] != 'Asistencia'])
            total_faltas = len(df_mes[df_mes['Falta'] == '🔴 Falta'])
            total_retardos = len(df_mes[df_mes['Falta'] == '🟡 Retardo'])
            
            c1.metric("Reportes Disciplinarios", total_conducta)
            c2.metric("Inasistencias Registradas", total_faltas)
            c3.metric("Retardos Registrados", total_retardos)
            
            st.markdown(f"### Desglose Mensual: {mes_sel}")
            cols_mostrar = ['Fecha', 'Alumno', 'Materia', 'Categoría', 'Falta', 'Puntos_Descontados']
            st.dataframe(df_mes[cols_mostrar].sort_values('Fecha', ascending=False), use_container_width=True, hide_index=True)
            
            csv_data = df_mes[cols_mostrar].to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "📥 Descargar Reporte Grupal (CSV)",
                data=csv_data,
                file_name=f"Reporte_Tutor_{grupo_sel}_{mes_sel}.csv",
                mime="text/csv"
            )

    # =================================================================
    # MODO 2: EXPEDIENTE INDIVIDUAL
    # =================================================================
    else:
        grupo_limpio = grupo_sel.split("(")[0].strip()
        try:
            opc_alumnos = obtener_lista_alumnos(gc, FILE_ALUMNOS, grupo_limpio)
        except Exception:
            opc_alumnos = []

        if not opc_alumnos:
            st.warning(f"No se localizaron alumnos para la pestaña '{grupo_limpio}'.")
            return            
            
        alumno_sel = st.selectbox("Selecciona Estudiante:", ["Seleccione..."] + opc_alumnos)
        
        if alumno_sel == "Seleccione...":
            st.info("👈 Selecciona a un alumno para desplegar su expediente unificado.")
            return
            
        st.subheader(f"📄 Expediente Disciplinario: {alumno_sel}")
        
        tipo_reporte = st.radio("Ventana temporal:", ["Mensual", "Por Periodo Lectivo"], horizontal=True)
        
        df_unificado['Alumno_Norm'] = df_unificado['Alumno'].astype(str).str.strip().str.lower()
        df_alumno = df_unificado[df_unificado['Alumno_Norm'] == alumno_sel.lower().strip()].copy()
        
        if df_alumno.empty:
            st.success(f"✨ **{alumno_sel}** tiene un expediente impecable (Sin incidencias ni inasistencias).")
            return
            
        df_filtrado = pd.DataFrame()
        nombre_archivo = f"Expediente_{alumno_sel.replace(' ', '_')}"
        
        if tipo_reporte == "Mensual":
            meses_dict = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
            meses_disponibles = sorted(df_alumno['Fecha_DT'].dt.month.dropna().unique().tolist())
            nombres_meses = [meses_dict[m] for m in meses_disponibles if m in meses_dict]
            
            if not nombres_meses:
                st.info("Sin fechas reconocidas para este estudiante.")
                return
                
            mes_sel_nombre = st.selectbox("Selecciona Mes:", nombres_meses)
            mes_num = [k for k, v in meses_dict.items() if v == mes_sel_nombre][0]
            df_filtrado = df_alumno[df_alumno['Fecha_DT'].dt.month == mes_num].copy()
            nombre_archivo += f"_{mes_sel_nombre}.csv"
            
        else:
            hoy = datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None)
            periodos = PERIODOS_LECTIVOS.get(nivel_grupo, PERIODOS_LECTIVOS.get("Preparatoria", []))
            pers = [p for p in periodos if datetime.strptime(p['inicio'], '%Y-%m-%d') <= hoy]
            
            if not pers:
                st.info(f"No hay periodos lectivos activos para {nivel_grupo}.")
                return
                
            per_sel = st.selectbox("Selecciona Periodo:", [p['nombre'] for p in pers])
            p_inf = next(p for p in pers if p['nombre'] == per_sel)
            df_filtrado = df_alumno[(df_alumno['Fecha_DT'] >= p_inf['inicio']) & (df_alumno['Fecha_DT'] <= p_inf['fin'])].copy()
            nombre_archivo += f"_{per_sel}.csv"
            
        if df_filtrado.empty:
            st.success(f"✨ Sin incidencias en el periodo seleccionado para **{alumno_sel}**.")
        else:
            df_conducta_pura = df_filtrado[df_filtrado['Categoría'] != 'Asistencia']
            faltas_totales = len(df_filtrado[df_filtrado['Falta'] == '🔴 Falta'])
            retardos_totales = len(df_filtrado[df_filtrado['Falta'] == '🟡 Retardo'])

            calificacion_final, total_descuento = calcular_calificacion_progresiva(df_conducta_pura)
            color_calif = format_calif(calificacion_final)
            
            c_res1, c_res2, c_res3, c_res4 = st.columns(4)
            c_res1.metric("Calificación Conducta", color_calif.split(" ")[1], delta=f"-{total_descuento:.1f} pts", delta_color="inverse")
            c_res2.info(f"Semáforo: **{color_calif.split(' ')[0]}**")            
            c_res3.metric("🔴 Faltas", faltas_totales)
            c_res4.metric("🟡 Retardos", retardos_totales)
            
            st.markdown("### Expediente Detallado")
            cols_mostrar = ['Fecha', 'Materia', 'Categoría', 'Falta', 'Observaciones', 'Puntos_Descontados']
            st.dataframe(df_filtrado[cols_mostrar].sort_values('Fecha', ascending=False), use_container_width=True, hide_index=True)
            
            csv_data = df_filtrado[cols_mostrar].to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "📥 Descargar Expediente (CSV)",
                data=csv_data,
                file_name=nombre_archivo,
                mime="text/csv",
                type="primary"
            )