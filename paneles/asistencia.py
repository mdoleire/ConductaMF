# paneles/asistencia.py
import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import gspread
import time

from config import FILE_ASIGNACIONES, FILE_ALUMNOS, FILE_ASISTENCIA
from database import leer_datos, obtener_lista_alumnos

def renderizar_panel_asistencia(gc, usuario, nombre_prof):
    st.header(f"📅 Pase de Lista y Edición")
    
    # 1. Buscar materias asignadas
    df_asig = leer_datos(gc, FILE_ASIGNACIONES)
    mis_asig = df_asig[df_asig['Usuario_Profesor'] == usuario]
    if mis_asig.empty:
        st.warning("Sin materias asignadas para pasar lista.")
        return

    # Ajustamos las columnas para hacerle espacio al selector de fecha
    c1, c2, c3 = st.columns([2, 2, 1.5])
    materia = c1.selectbox("Materia:", mis_asig['Materia'].unique(), key="asist_mat")
    grupo = c2.selectbox("Grupo:", mis_asig[mis_asig['Materia'] == materia]['Grupo'].unique(), key="asist_grup")
    
    # --- NUEVO: Selector de Fecha ---
    fecha_input = c3.date_input("Fecha de clase:", datetime.now(ZoneInfo("America/Mexico_City")))
    fecha_str = fecha_input.strftime("%d-%m-%Y")

    st.markdown("---")

    # 2. Obtener la lista inteligente de alumnos
    try:
        alumnos = obtener_lista_alumnos(gc, FILE_ALUMNOS, grupo)
    except Exception:
        alumnos = []

    if not alumnos:
        st.warning(f"No se encontraron alumnos registrados para el grupo {grupo}.")
        return

    nombre_pestana = f"{materia} - {grupo}"

    # 3. Leer el historial en formato de "Matriz"
    try:
        df_historial = leer_datos(gc, FILE_ASISTENCIA, nombre_pestana)
    except Exception:
        df_historial = pd.DataFrame()

    if df_historial.empty or 'Alumno' not in df_historial.columns:
        df_historial = pd.DataFrame({"Alumno": alumnos})

    # 4. Calcular Estadísticas
    stats = {}
    columnas_fechas = [c for c in df_historial.columns if c != 'Alumno']
    total_clases = len(columnas_fechas)

    for al in alumnos:
        if total_clases > 0 and al in df_historial['Alumno'].values:
            fila_alumno = df_historial[df_historial['Alumno'] == al].iloc[0]
            faltas = (fila_alumno[columnas_fechas] == '🔴 Falta').sum()
            retardos = (fila_alumno[columnas_fechas] == '🟡 Retardo').sum()
            pct = (faltas / total_clases) * 100 if total_clases > 0 else 0
            stats[al] = f"{pct:.1f}% ({faltas}F, {retardos}R)"
        else:
            stats[al] = "0.0% (0F, 0R)"

    # --- NUEVO: Inteligencia de Carga Previa ---
    if fecha_str in df_historial.columns:
        st.info(f"📝 **Modo Edición:** Estás modificando la asistencia guardada previamente para el día **{fecha_str}**.")
        # Cruzamos los datos del Excel con la lista actual
        valores_previos = dict(zip(df_historial['Alumno'], df_historial[fecha_str]))
        col_asistencia = [valores_previos.get(al, "✅ Presente") if pd.notna(valores_previos.get(al)) and valores_previos.get(al) != "" else "✅ Presente" for al in alumnos]
    else:
        st.info(f"✨ **Nuevo Registro:** Pasando lista para el **{fecha_str}**.")
        col_asistencia = ["✅ Presente"] * len(alumnos)

    # 5. Armar la tabla visual interactiva
    df_view = pd.DataFrame({
        "Alumno": alumnos,
        "Asistencia": col_asistencia,
        "Historial Acumulado": [stats[al] for al in alumnos]
    })

    st.markdown(f"### 📋 Lista de {grupo} ({materia})")

    df_editado = st.data_editor(
        df_view,
        column_config={
            "Alumno": st.column_config.TextColumn("Alumno", disabled=True),
            "Asistencia": st.column_config.SelectboxColumn(
                "Asistencia",
                options=["✅ Presente", "🟡 Retardo", "🔴 Falta"],
                required=True,
            ),
            "Historial Acumulado": st.column_config.TextColumn("Historial Acumulado", disabled=True)
        },
        hide_index=True,
        use_container_width=True,
        key=f"editor_{materia}_{grupo}_{fecha_str}"
    )

    # 6. Procesar y Guardar
    if st.button("💾 Guardar Asistencia", type="primary"):
        with st.spinner(f"Guardando registro del {fecha_str}..."):
            try:
                doc = gc.open(FILE_ASISTENCIA)
            except gspread.exceptions.SpreadsheetNotFound:
                st.error(f"⚠️ No se encontró el archivo '{FILE_ASISTENCIA}'.")
                st.stop()

            try:
                ws = doc.worksheet(nombre_pestana)
            except gspread.exceptions.WorksheetNotFound:
                ws = doc.add_worksheet(title=nombre_pestana, rows="100", cols="50")

            df_actualizado = df_historial.copy()

            # Asegurar que no se pierdan los alumnos nuevos
            alumnos_existentes = df_actualizado['Alumno'].tolist() if 'Alumno' in df_actualizado.columns else []
            nuevos_alumnos = [a for a in alumnos if a not in alumnos_existentes]
            if nuevos_alumnos:
                df_nuevos = pd.DataFrame({"Alumno": nuevos_alumnos})
                df_actualizado = pd.concat([df_actualizado, df_nuevos], ignore_index=True)
                df_actualizado = df_actualizado.sort_values('Alumno').reset_index(drop=True)

            # Escribir o sobreescribir la columna de la fecha seleccionada
            asistencia_dict = dict(zip(df_editado['Alumno'], df_editado['Asistencia']))
            df_actualizado[fecha_str] = df_actualizado['Alumno'].map(asistencia_dict)
            
            df_actualizado = df_actualizado.fillna("")

            ws.clear()
            ws.update([df_actualizado.columns.values.tolist()] + df_actualizado.values.tolist())
            
            leer_datos.clear()
            
            st.success(f"✅ ¡Asistencia del {fecha_str} guardada correctamente!")
            time.sleep(1.5)
            st.rerun()
