# paneles/coordinador.py
import streamlit as st
import pandas as pd

from config import FILE_ASIGNACIONES
from database import leer_todos_los_registros, leer_todas_las_asignaciones
from paneles.analitica import mostrar_tablero_analitico

def renderizar_panel_coordinador(gc, area_coordinador):
    # Limpiamos el área para evitar errores por espacios accidentales
    area_coordinador_limpia = str(area_coordinador).strip()
    
    st.subheader(f"📋 Monitoreo de Coordinación: Área de {area_coordinador_limpia}")
    
    df_incidencias = leer_todos_los_registros(gc)
    
    # 🚀 CAMBIO CLAVE: Usamos la función optimizada con caché que recorre todas las pestañas
    df_asig = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
    
    if df_asig.empty:
        st.error("No se pudo cargar el archivo de asignaciones docentes.")
        return

    # Limpiamos los títulos de las columnas por seguridad
    df_asig.columns = df_asig.columns.str.strip()

    if 'Area' in df_asig.columns and 'Materia' in df_asig.columns:
        # Limpiamos los datos de las columnas para asegurar la coincidencia
        df_asig['Area'] = df_asig['Area'].astype(str).str.strip()
        df_asig['Materia'] = df_asig['Materia'].astype(str).str.strip()
        
        materias_del_area = df_asig[df_asig['Area'] == area_coordinador_limpia]['Materia'].unique().tolist()
    else:
        st.error("Estructura de columnas incorrecta en la plantilla docente.")
        return

    if df_incidencias.empty:
        st.info("No se han reportado incidencias en el sistema de forma global.")
    else:
        # Limpiamos la columna de materia en incidencias antes de cruzar
        if 'Materia' in df_incidencias.columns:
            df_incidencias['Materia'] = df_incidencias['Materia'].astype(str).str.strip()
            
        df_coordinacion = df_incidencias[df_incidencias['Materia'].isin(materias_del_area)]
        
        if df_coordinacion.empty:
            st.warning(f"Sin incidencias registradas en el área de {area_coordinador_limpia}.")
        else:
            st.write(f"Incidencias encontradas en tu coordinación: **{len(df_coordinacion)}**")
            columnas_coordinador = [col for col in ['Fecha', 'Profesor', 'Materia', 'Grupo', 'Alumno', 'Categoría', 'Falta', 'Observaciones', 'Puntos_Descontados'] if col in df_coordinacion.columns]
            
            if 'Fecha' in df_coordinacion.columns:
                df_coordinacion = df_coordinacion.sort_values(by='Fecha', ascending=False)
                
            st.dataframe(df_coordinacion[columnas_coordinador], use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.subheader("📊 Analítica del Departamento")
            mostrar_tablero_analitico(df_coordinacion, f"Coordinación {area_coordinador_limpia}", modo_descarga=True)
