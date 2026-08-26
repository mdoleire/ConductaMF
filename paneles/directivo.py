# paneles/directivo.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from database import leer_todos_los_registros
from paneles.analitica import mostrar_tablero_analitico

def renderizar_panel_directivo(gc):
    st.header("📊 Inteligencia Institucional (Directivo)")
    df_full = leer_todos_los_registros(gc)
    
    if df_full.empty:
        st.info("Base de datos de registros vacía.")
        return

    df_pasillo = df_full[df_full['Materia'] == "Pasillo / Inst. General"]
    if not df_pasillo.empty:
        df_pasillo['Fecha_DT'] = pd.to_datetime(df_pasillo['Fecha'], errors='coerce')
        hoy = datetime.now(ZoneInfo("America/Mexico_City"))
        limite_tiempo = hoy - timedelta(days=1)
        alertas_recientes = df_pasillo[df_pasillo['Fecha_DT'] >= limite_tiempo.replace(tzinfo=None)]
        
        if not alertas_recientes.empty:
            num_alertas = len(alertas_recientes)
            if st.session_state.get("memoria_alertas_pasillo") != num_alertas:
                st.toast(f"🚨 Tienes {num_alertas} reporte(s) de pasillo reciente(s).", icon="🚨")
                st.session_state["memoria_alertas_pasillo"] = num_alertas
            
            st.warning(f"🔔 **ALERTAS PRIORITARIAS:** Se han registrado {num_alertas} incidencias fuera de clase en las últimas 24 horas.")
            with st.expander("👀 Ver Detalles de Reportes de Pasillo", expanded=True):
                cols_alerta = ["Fecha", "Profesor", "Grupo", "Alumno", "Falta", "Observaciones"]
                cols_validas = [c for c in cols_alerta if c in alertas_recientes.columns]
                st.dataframe(alertas_recientes[cols_validas].sort_values(by="Fecha", ascending=False), use_container_width=True, hide_index=True)
        else:
            st.session_state["memoria_alertas_pasillo"] = 0

    with st.expander("🔍 Filtros de Búsqueda Avanzada", expanded=False):
        f1, f2, f3, f4 = st.columns(4)
        df_f = df_full.copy()
        
        grados = ["Todos"] + sorted(df_f['Grado'].astype(str).unique().tolist())
        sel_grado = f1.selectbox("Filtrar Grado:", grados)
        if sel_grado != "Todos":
            df_f = df_f[df_f['Grado'].astype(str) == sel_grado]
            
        grupos = ["Todos"] + sorted(df_f['Grupo'].astype(str).unique().tolist())
        sel_grupo = f2.selectbox("Filtrar Grupo:", grupos)
        if sel_grupo != "Todos":
            df_f = df_f[df_f['Grupo'].astype(str) == sel_grupo]
            
        profs = ["Todos"] + sorted(df_f['Profesor'].astype(str).unique().tolist())
        sel_prof = f3.selectbox("Filtrar Profesor:", profs)
        if sel_prof != "Todos":
            df_f = df_f[df_f['Profesor'].astype(str) == sel_prof]
            
        mats = ["Todos"] + sorted(df_f['Materia'].astype(str).unique().tolist())
        idx_mat = 1 if (len(mats) == 2 and sel_prof != "Todos") else 0
        sel_mat = f4.selectbox("Filtrar Materia:", mats, index=idx_mat)
        if sel_mat != "Todos":
            df_f = df_f[df_f['Materia'].astype(str) == sel_mat]

    mostrar_tablero_analitico(df_f, "Institucional")