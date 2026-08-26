# paneles/tutor.py
import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

# Importamos desde las otras piezas del sistema
from config import FILE_ASIGNACIONES, FILE_ALUMNOS, PERIODOS_LECTIVOS
from calculadora import format_calif, calcular_calificacion_progresiva
from database import leer_datos, leer_todos_los_registros, obtener_lista_alumnos

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
    
    df_full = leer_todos_los_registros(gc)
    if df_full.empty:
        st.warning("La base de datos institucional está vacía.")
        return

    # Aislamos toda la data del grupo seleccionado para que el tutor no vea otros salones
    df_grupo_completo = df_full[df_full['Grupo'] == grupo_sel].copy()

    # =================================================================
    # MODO 1: RESUMEN GRUPAL (NUEVO)
    # =================================================================
    if modo_tutor == "👥 Visión General del Grupo (Por Mes)":
        st.subheader(f"📊 Reporte Grupal: {grupo_sel}")
        
        if df_grupo_completo.empty:
            st.success(f"✨ ¡Excelente! El grupo {grupo_sel} no tiene ninguna incidencia registrada en todo el ciclo.")
            return
            
        df_grupo_completo['Fecha_DT'] = pd.to_datetime(df_grupo_completo['Fecha'], errors='coerce')
        meses_dict = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
        
        # Obtenemos solo los meses donde realmente hubo reportes
        meses_disponibles = sorted(df_grupo_completo['Fecha_DT'].dt.month.dropna().unique().tolist())
        nombres_meses = [meses_dict[m] for m in meses_disponibles]
        
        if not nombres_meses:
            st.info("No hay registros con un formato de fecha válido.")
            return
            
        mes_sel = st.selectbox("Selecciona el Mes a consultar:", nombres_meses)
        mes_num = [k for k, v in meses_dict.items() if v == mes_sel][0]
        
        df_mes = df_grupo_completo[df_grupo_completo['Fecha_DT'].dt.month == mes_num].copy()
        
        if df_mes.empty:
            st.success(f"No hay incidencias para el grupo en el mes de {mes_sel}.")
        else:
            # Métricas rápidas para el tutor
            c1, c2 = st.columns(2)
            c1.metric("Total de Incidencias en el Mes", len(df_mes))
            
            # Agrupamos para descubrir quién tiene más reportes este mes
            alumnos_top = df_mes.groupby('Alumno').size().reset_index(name='Reportes').sort_values('Reportes', ascending=False)
            if not alumnos_top.empty:
                c2.metric("Alumno con más reportes", f"{alumnos_top.iloc[0]['Alumno']} ({alumnos_top.iloc[0]['Reportes']})")
            
            st.markdown(f"### 📋 Desglose de Incidencias del Grupo ({mes_sel})")
            # Agregamos la columna 'Alumno' a la vista para saber quién hizo qué
            cols_mostrar = ['Fecha', 'Alumno', 'Profesor', 'Materia', 'Categoría', 'Falta', 'Puntos_Descontados']
            st.dataframe(df_mes[cols_mostrar].sort_values('Fecha', ascending=False), use_container_width=True, hide_index=True)
            
            csv_data = df_mes[cols_mostrar].to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 Descargar Reporte Grupal (CSV)",
                data=csv_data,
                file_name=f"Reporte_Grupal_{grupo_sel}_{mes_sel}.csv",
                mime="text/csv",
                type="primary"
            )

    # =================================================================
    # MODO 2: EXPEDIENTE POR ALUMNO (EL QUE YA TENÍAS)
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
        st.info("👈 Selecciona un alumno para generar su reporte conductual individual.")
        return
            
        st.subheader(f"📄 Generador de Reporte: {alumno_sel}")
        
        tipo_reporte = st.radio("Elige el rango de tiempo:", ["Mensual", "Por Periodo Lectivo"], horizontal=True)
        df_alumno = df_grupo_completo[df_grupo_completo['Alumno'] == alumno_sel].copy()
        
        if df_alumno.empty:
            st.success(f"✨ ¡Excelente noticia! **{alumno_sel}** no tiene ninguna incidencia registrada en todo el ciclo.")
            return
            
        df_alumno['Fecha_DT'] = pd.to_datetime(df_alumno['Fecha'], errors='coerce')
        df_filtrado = pd.DataFrame()
        nombre_archivo_descarga = f"Reporte_Conducta_{alumno_sel.replace(' ', '_')}"
        
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
            st.success(f"✨ **{alumno_sel}** no tiene incidencias en el rango seleccionado.")
        else:
            calificacion_final, total_descuento = calcular_calificacion_progresiva(df_filtrado)
            color_calif = format_calif(calificacion_final)
            
            c_res1, c_res2 = st.columns(2)
            c_res1.metric(
                label="Calificación de Conducta (Periodo/Mes)", 
                value=color_calif.split(" ")[1], 
                delta=f"-{total_descuento:.1f} pts de sanción", 
                delta_color="inverse"
            )
            c_res2.info(f"Semáforo Visual: **{color_calif.split(' ')[0]}**")            
            st.markdown("### 📋 Desglose de Incidencias")
            cols_mostrar = ['Fecha', 'Profesor', 'Materia', 'Categoría', 'Falta', 'Observaciones', 'Puntos_Descontados']
            st.dataframe(df_filtrado[cols_mostrar].sort_values('Fecha', ascending=False), use_container_width=True, hide_index=True)
            
            csv_data = df_filtrado[cols_mostrar].to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 Descargar Reporte (Excel / CSV)",
                data=csv_data,
                file_name=nombre_archivo_descarga,
                mime="text/csv",
                type="primary"
            )
