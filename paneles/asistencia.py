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

    # 2. Obtener la lista inteligente (inmune a errores)
    try:
        alumnos = obtener_lista_alumnos(gc, FILE_ALUMNOS, grupo)
    except Exception:
        alumnos = []

    if not alumnos:
        st.warning(f"No se encontraron alumnos registrados para el grupo {grupo}.")
        return

    # 3. Leer historial para calcular porcentajes (%)
    historial = pd.DataFrame()
    try:
        df_historial = leer_datos(gc, FILE_ASISTENCIA, "General")
        if not df_historial.empty:
            historial = df_historial[(df_historial['Materia'] == materia) & (df_historial['Grupo'] == grupo)]
    except Exception:
        pass # Si el archivo o pestaña no existe aún, no pasa nada

    # 4. Lógica Matemática de Faltas
    stats = {}
    fecha_hoy = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d")
    
    if not historial.empty:
        total_clases = historial['Fecha'].nunique() # Cuenta los días únicos que has pasado lista
        
        # Bloqueo de seguridad: Evitar pase de lista doble el mismo día
        ya_paso = historial[historial['Fecha'] == fecha_hoy]
        if not ya_paso.empty:
            st.info(f"✅ Ya pasaste lista para **{materia} - {grupo}** el día de hoy.")
            return

        for al in alumnos:
            faltas_al = len(historial[(historial['Alumno'] == al) & (historial['Estatus'] == '🔴 Falta')])
            retardos_al = len(historial[(historial['Alumno'] == al) & (historial['Estatus'] == '🟡 Retardo')])
            pct = (faltas_al / total_clases) * 100 if total_clases > 0 else 0
            stats[al] = f"{pct:.1f}% ({faltas_al}F, {retardos_al}R)"
    else:
        # Si es la primera vez que se usa el sistema
        for al in alumnos:
            stats[al] = "0.0% (0F, 0R)"

    # 5. Armar la tabla visual
    df_view = pd.DataFrame({
        "Alumno": alumnos,
        "Asistencia": ["✅ Presente"] * len(alumnos), # <-- El prellenado mágico
        "Historial Acumulado": [stats[al] for al in alumnos]
    })

    st.markdown(f"### 📋 Lista de {grupo} ({materia})")
    st.caption("💡 Haz clic en '✅ Presente' para cambiar el estatus de un alumno. Los porcentajes se calculan con base en las clases impartidas hasta hoy.")

    # El editor interactivo
    df_editado = st.data_editor(
        df_view,
        column_config={
            "Alumno": st.column_config.TextColumn("Alumno", disabled=True),
            "Asistencia": st.column_config.SelectboxColumn(
                "Asistencia de Hoy",
                help="Selecciona Presente, Retardo o Falta",
                options=["✅ Presente", "🟡 Retardo", "🔴 Falta"],
                required=True,
            ),
            "Historial Acumulado": st.column_config.TextColumn("Historial Acumulado", disabled=True)
        },
        hide_index=True,
        use_container_width=True,
        key=f"editor_{materia}_{grupo}"
    )

    # 6. Procesar y Guardar
    if st.button("💾 Guardar Asistencia", type="primary"):
        lote = []
        for _, row in df_editado.iterrows():
            lote.append([fecha_hoy, nombre_prof, materia, grupo, row['Alumno'], row['Asistencia']])

        with st.spinner("Sincronizando con Google Drive..."):
            try:
                doc = gc.open(FILE_ASISTENCIA)
            except gspread.exceptions.SpreadsheetNotFound:
                st.error(f"⚠️ No se encontró el archivo '{FILE_ASISTENCIA}' en tu Google Drive.")
                st.stop()

            try:
                ws = doc.worksheet("General")
            except gspread.exceptions.WorksheetNotFound:
                # Si es la primera vez, crea la pestaña y los encabezados automáticamente
                ws = doc.add_worksheet(title="General", rows="1000", cols="6")
                ws.append_row(["Fecha", "Profesor", "Materia", "Grupo", "Alumno", "Estatus"])
            
            ws.append_rows(lote)
            st.success("✅ Asistencia registrada correctamente. Calculando nuevos porcentajes...")
            time.sleep(2)
            st.rerun()
