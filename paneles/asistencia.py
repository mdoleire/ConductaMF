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
    st.header(f"📅 Pase de Lista Diario")
    
    # 1. Buscar materias asignadas
    df_asig = leer_datos(gc, FILE_ASIGNACIONES)
    mis_asig = df_asig[df_asig['Usuario_Profesor'] == usuario]
    if mis_asig.empty:
        st.warning("Sin materias asignadas para pasar lista.")
        return

    c1, c2 = st.columns(2)
    materia = c1.selectbox("Materia:", mis_asig['Materia'].unique(), key="asist_mat")
    grupo = c2.selectbox("Grupo:", mis_asig[mis_asig['Materia'] == materia]['Grupo'].unique(), key="asist_grup")

    st.markdown("---")

    # 2. Obtener la lista inteligente de alumnos
    try:
        alumnos = obtener_lista_alumnos(gc, FILE_ALUMNOS, grupo)
    except Exception:
        alumnos = []

    if not alumnos:
        st.warning(f"No se encontraron alumnos registrados para el grupo {grupo}.")
        return

    # Creamos un nombre de pestaña único, ej: "Matemáticas - 5°B"
    nombre_pestana = f"{materia} - {grupo}"
    fecha_hoy = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%d-%m-%Y")

    # 3. Leer el historial en formato de "Matriz" (Columnas = Fechas)
    try:
        df_historial = leer_datos(gc, FILE_ASISTENCIA, nombre_pestana)
    except Exception:
        df_historial = pd.DataFrame()

    # Si la pestaña es nueva, iniciamos con la columna de alumnos
    if df_historial.empty or 'Alumno' not in df_historial.columns:
        df_historial = pd.DataFrame({"Alumno": alumnos})

    # BLOQUEO DE SEGURIDAD: Evitar doble pase de lista
    if fecha_hoy in df_historial.columns:
        st.info(f"✅ Ya pasaste lista para **{nombre_pestana}** el día de hoy ({fecha_hoy}).")
        st.dataframe(df_historial[['Alumno', fecha_hoy]], hide_index=True, use_container_width=True)
        return

    # 4. Calcular Estadísticas (contando hacia atrás en las columnas)
    stats = {}
    columnas_fechas = [c for c in df_historial.columns if c != 'Alumno']
    total_clases = len(columnas_fechas)

    for al in alumnos:
        if total_clases > 0 and al in df_historial['Alumno'].values:
            fila_alumno = df_historial[df_historial['Alumno'] == al].iloc[0]
            faltas = (fila_alumno[columnas_fechas] == '🔴 Falta').sum()
            retardos = (fila_alumno[columnas_fechas] == '🟡 Retardo').sum()
            pct = (faltas / total_clases) * 100
            stats[al] = f"{pct:.1f}% ({faltas}F, {retardos}R)"
        else:
            stats[al] = "0.0% (0F, 0R)"

    # 5. Armar la tabla visual interactiva
    df_view = pd.DataFrame({
        "Alumno": alumnos,
        "Asistencia": ["✅ Presente"] * len(alumnos),
        "Historial Acumulado": [stats[al] for al in alumnos]
    })

    st.markdown(f"### 📋 Lista de {grupo} ({materia})")
    st.caption("💡 Haz clic en '✅ Presente' para cambiar el estatus. Al guardar, se añadirá una nueva columna en Excel.")

    df_editado = st.data_editor(
        df_view,
        column_config={
            "Alumno": st.column_config.TextColumn("Alumno", disabled=True),
            "Asistencia": st.column_config.SelectboxColumn(
                "Asistencia de Hoy",
                options=["✅ Presente", "🟡 Retardo", "🔴 Falta"],
                required=True,
            ),
            "Historial Acumulado": st.column_config.TextColumn("Historial Acumulado", disabled=True)
        },
        hide_index=True,
        use_container_width=True,
        key=f"editor_{materia}_{grupo}"
    )

    # 6. Procesar y Guardar como Matriz
    if st.button("💾 Guardar Asistencia", type="primary"):
        with st.spinner(f"Agregando columna del {fecha_hoy} a Google Drive..."):
            try:
                doc = gc.open(FILE_ASISTENCIA)
            except gspread.exceptions.SpreadsheetNotFound:
                st.error(f"⚠️ No se encontró el archivo '{FILE_ASISTENCIA}'.")
                st.stop()

            try:
                ws = doc.worksheet(nombre_pestana)
            except gspread.exceptions.WorksheetNotFound:
                ws = doc.add_worksheet(title=nombre_pestana, rows="100", cols="50")

            # Hacemos una copia de la matriz actual
            df_actualizado = df_historial.copy()

            # Truco de magia: Si entró un alumno nuevo a mitad de ciclo, lo agregamos a las filas
            alumnos_existentes = df_actualizado['Alumno'].tolist() if 'Alumno' in df_actualizado.columns else []
            nuevos_alumnos = [a for a in alumnos if a not in alumnos_existentes]
            if nuevos_alumnos:
                df_nuevos = pd.DataFrame({"Alumno": nuevos_alumnos})
                df_actualizado = pd.concat([df_actualizado, df_nuevos], ignore_index=True)
                df_actualizado = df_actualizado.sort_values('Alumno').reset_index(drop=True)

            # Mapeamos lo que el profesor seleccionó en la pantalla hacia una nueva columna con la fecha de hoy
            asistencia_dict = dict(zip(df_editado['Alumno'], df_editado['Asistencia']))
            df_actualizado[fecha_hoy] = df_actualizado['Alumno'].map(asistencia_dict)
            
            # Limpiamos huecos vacíos para que Google Sheets no marque error
            df_actualizado = df_actualizado.fillna("")

            # Sobreescribimos la pestaña con la nueva tabla completa (es rapidísimo)
            ws.clear()
            ws.update([df_actualizado.columns.values.tolist()] + df_actualizado.values.tolist())
            
            leer_datos.clear() # Limpiamos la memoria caché para que se actualice al instante
            
            st.success(f"✅ Asistencia registrada. ¡Se agregó la columna '{fecha_hoy}' en tu Excel!")
            time.sleep(2)
            st.rerun()
