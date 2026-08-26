# paneles/tutor.py
import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import gspread

# Importamos desde las otras piezas del sistema
from config import FILE_ASIGNACIONES, FILE_ALUMNOS, FILE_ASISTENCIA, PERIODOS_LECTIVOS
from database import leer_datos, leer_todos_los_registros, obtener_lista_alumnos
from calculadora import format_calif, calcular_calificacion_progresiva

def renderizar_panel_tutor(gc, usuario, nombre_prof):
    st.header(f"🧑‍🏫 Panel de Tutoría: {nombre_prof}")
    
    # 1. Buscar los grupos donde el profesor es "Tutor"
    df_asig = leer_datos(gc, FILE_ASIGNACIONES)
    mis_grupos_tutor = df_asig[(df_asig['Usuario_Profesor'] == usuario) & (df_asig['Materia'] == 'Tutor')]['Grupo'].unique().tolist()
    
    if not mis_grupos_tutor:
        st.warning("⚠️ El sistema no detectó ningún grupo asignado a tu nombre bajo la materia 'Tutor'.")
        return
        
    grupo_sel = st.selectbox("Selecciona tu Grupo de Tutoría:", mis_grupos_tutor)
    
    st.markdown("---")
    
    # --- SELECTOR DE MODO DE VISTA ---
    modo_tutor = st.radio("¿Qué tipo de análisis deseas realizar?", 
                          ["👥 Visión General del Grupo (Por Mes)", "👤 Expediente por Alumno (Detallado)"], 
                          horizontal=True)
    
    st.markdown("---")
    
    # =================================================================
    # 🚀 MOTOR DE FUSIÓN DE DATOS (CONDUCTA + ASISTENCIA)
    # =================================================================
    with st.spinner("Compilando expedientes unificados..."):
        # 1. Traer datos de Conducta
        df_full = leer_todos_los_registros(gc)
        df_grupo_conducta = df_full[df_full['Grupo'] == grupo_sel].copy() if not df_full.empty else pd.DataFrame()
        if not df_grupo_conducta.empty:
            df_grupo_conducta['Fecha_DT'] = pd.to_datetime(df_grupo_conducta['Fecha'], errors='coerce')
        
        # 2. Traer datos de Asistencia (Múltiples pestañas del grupo)
        df_asist_plana = pd.DataFrame()
        try:
            doc_asist = gc.open(FILE_ASISTENCIA)
            hojas = doc_asist.worksheets()
            hojas_grupo = [h for h in hojas if h.title.endswith(f" - {grupo_sel}")]
            
            list_melted = []
            for h in hojas_grupo:
                datos = h.get_all_values()
                if len(datos) > 1:
                    columnas = datos[0]
                    df_temp = pd.DataFrame(datos[1:], columns=columnas)
                    materia = h.title.split(" - ")[0]
                    
                    fechas_cols = [c for c in columnas if c != 'Alumno']
                    if fechas_cols:
                        # Convertimos la matriz en una lista plana de reportes
                        df_melt = df_temp.melt(id_vars=['Alumno'], value_vars=fechas_cols, var_name='Fecha', value_name='Falta')
                        df_melt['Materia'] = materia
                        df_melt['Categoría'] = 'Asistencia'
                        df_melt['Profesor'] = 'Registro Automático'
                        df_melt['Puntos_Descontados'] = 0
                        df_melt['Observaciones'] = ''
                        list_melted.append(df_melt)
            
            if list_melted:
                df_asist_plana = pd.concat(list_melted, ignore_index=True)
                # Filtramos solo las faltas y retardos (Ignoramos cuando vinieron a clase)
                df_asist_plana = df_asist_plana[df_asist_plana['Falta'].isin(['🔴 Falta', '🟡 Retardo'])]
                
                if not df_asist_plana.empty:
                    df_asist_plana['Fecha_DT'] = pd.to_datetime(df_asist_plana['Fecha'], format='%d-%m-%Y', errors='coerce')
                    df_asist_plana['Fecha'] = df_asist_plana['Fecha_DT'].dt.strftime("%Y-%m-%d 00:00:00")
        except Exception:
            pass
            
        # 3. Unificar los DataFrames
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
    # MODO 1: RESUMEN GRUPAL
    # =================================================================
    if modo_tutor == "👥 Visión General del Grupo (Por Mes)":
        st.subheader(f"📊 Reporte Grupal: {grupo_sel}")
        
        if df_unificado.empty:
            st.success(f"✨ ¡Excelente! El grupo {grupo_sel} no tiene incidencias ni faltas registradas.")
            return
            
        meses_dict = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
        meses_disponibles = sorted(df_unificado['Fecha_DT'].dt.month.dropna().unique().tolist())
        nombres_meses = [meses_dict[m] for m in meses_disponibles]
        
        if not nombres_meses:
            st.info("No hay registros con un formato de fecha válido.")
            return
            
        mes_sel = st.selectbox("Selecciona el Mes a consultar:", nombres_meses)
        mes_num = [k for k, v in meses_dict.items() if v == mes_sel][0]
        
        df_mes = df_unificado[df_unificado['Fecha_DT'].dt.month == mes_num].copy()
        
        if df_mes.empty:
            st.success(f"No hay registros para el grupo en el mes de {mes_sel}.")
        else:
            c1, c2, c3 = st.columns(3)
            total_conducta = len(df_mes[df_mes['Categoría'] != 'Asistencia'])
            total_faltas = len(df_mes[df_mes['Falta'] == '🔴 Falta'])
            total_retardos = len(df_mes[df_mes['Falta'] == '🟡 Retardo'])
            
            c1.metric("Incidencias de Conducta", total_conducta)
            c2.metric("Faltas Totales", total_faltas)
            c3.metric("Retardos Totales", total_retardos)
            
            st.markdown(f"### 📋 Desglose Unificado del Grupo ({mes_sel})")
            cols_mostrar = ['Fecha', 'Alumno', 'Materia', 'Categoría', 'Falta', 'Puntos_Descontados']
            st.dataframe(df_mes[cols_mostrar].sort_values('Fecha', ascending=False), use_container_width=True, hide_index=True)
            
            csv_data = df_mes[cols_mostrar].to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 Descargar Reporte Integral (CSV)",
                data=csv_data,
                file_name=f"Reporte_Integral_{grupo_sel}_{mes_sel}.csv",
                mime="text/csv",
                type="primary"
            )

    # =================================================================
    # MODO 2: EXPEDIENTE POR ALUMNO
    # =================================================================
    else:
        try:
            opc_alumnos = obtener_lista_alumnos(gc, FILE_ALUMNOS, grupo_sel)
        except Exception:
            opc_alumnos = []
            st.error(f"Falta la pestaña '{grupo_sel}' en el archivo de alumnos.")

        if not opc_alumnos:
            st.warning("No se encontraron alumnos en este grupo.")
            return            
            
        alumno_sel = st.selectbox("Selecciona al Alumno:", ["Seleccione..."] + opc_alumnos)
        
        if alumno_sel == "Seleccione...":
            st.info("👈 Selecciona un alumno para generar su expediente unificado.")
            return
            
        st.subheader(f"📄 Expediente Integral: {alumno_sel}")
        
        tipo_reporte = st.radio("Elige el rango de tiempo:", ["Mensual", "Por Periodo Lectivo"], horizontal=True)
        df_alumno = df_unificado[df_unificado['Alumno'] == alumno_sel].copy()
        
        if df_alumno.empty:
            st.success(f"✨ ¡Excelente noticia! **{alumno_sel}** tiene un expediente impecable (Sin faltas ni reportes).")
            return
            
        df_filtrado = pd.DataFrame()
        nombre_archivo_descarga = f"Expediente_{alumno_sel.replace(' ', '_')}"
        
        if tipo_reporte == "Mensual":
            meses_dict = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
            meses_disponibles = sorted(df_alumno['Fecha_DT'].dt.month.dropna().unique().tolist())
            nombres_meses = [meses_dict[m] for m in meses_disponibles]
            
            if not nombres_meses:
                st.info("No hay registros válidos con fecha reconocida.")
                return
                
            mes_sel_nombre = st.selectbox("Selecciona el Mes a reportar:", nombres_meses)
            mes_num = [k for k, v in meses_dict.items() if v == mes_sel_nombre][0]
            
            df_filtrado = df_alumno[df_alumno['Fecha_DT'].dt.month == mes_num].copy()
            nombre_archivo_descarga += f"_{mes_sel_nombre}.csv"
            
        else:
            hoy = datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None)
            pers = [p for p in PERIODOS_LECTIVOS if datetime.strptime(p['inicio'], '%Y-%m-%d') <= hoy]
            nombres_pers = [p['nombre'] for p in pers]
            
            if not nombres_pers:
                st.info("Aún no hay periodos activos configurados.")
                return
                
            per_sel = st.selectbox("Selecciona el Periodo Lectivo:", nombres_pers)
            p_inf = next(p for p in pers if p['nombre'] == per_sel)
            
            df_filtrado = df_alumno[(df_alumno['Fecha_DT'] >= p_inf['inicio']) & (df_alumno['Fecha_DT'] <= p_inf['fin'])].copy()
            nombre_archivo_descarga += f"_{per_sel}.csv"
            
        if df_filtrado.empty:
            st.success(f"✨ **{alumno_sel}** no tiene incidencias ni faltas en el rango seleccionado.")
        else:
            # Separamos los datos para calcular la conducta sin que le afecten las inasistencias
            df_conducta_pura = df_filtrado[df_filtrado['Categoría'] != 'Asistencia']
            faltas_totales = len(df_filtrado[df_filtrado['Falta'] == '🔴 Falta'])
            retardos_totales = len(df_filtrado[df_filtrado['Falta'] == '🟡 Retardo'])

            calificacion_final, total_descuento = calcular_calificacion_progresiva(df_conducta_pura)
            color_calif = format_calif(calificacion_final)
            
            # Ajustamos las cajas de indicadores
            c_res1, c_res2, c_res3, c_res4 = st.columns(4)
            c_res1.metric(
                label="Calificación Conducta", 
                value=color_calif.split(" ")[1], 
                delta=f"-{total_descuento:.1f} pts", 
                delta_color="inverse"
            )
            c_res2.info(f"Semáforo: **{color_calif.split(' ')[0]}**")            
            c_res3.metric("🔴 Faltas Acumuladas", faltas_totales)
            c_res4.metric("🟡 Retardos Acumulados", retardos_totales)
            
            st.markdown("### 📋 Desglose Integral de Expediente")
            cols_mostrar = ['Fecha', 'Materia', 'Categoría', 'Falta', 'Observaciones', 'Puntos_Descontados']
            st.dataframe(df_filtrado[cols_mostrar].sort_values('Fecha', ascending=False), use_container_width=True, hide_index=True)
            
            csv_data = df_filtrado[cols_mostrar].to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 Descargar Expediente (Excel / CSV)",
                data=csv_data,
                file_name=nombre_archivo_descarga,
                mime="text/csv",
                type="primary"
            )
