# paneles/analitica.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import PERIODOS_LECTIVOS
from calculadora import format_calif

# ==========================================
# 4. COMPONENTE ANALÍTICO MULTI-FILTRO
# ==========================================
def mostrar_tablero_analitico(df, titulo_contexto, modo_descarga=True):
    if df.empty:
        st.info("No hay datos registrados con los filtros seleccionados.")
        return

    df['Fecha'] = pd.to_datetime(df['Fecha'])
    t_sem, t_mes, t_per = st.tabs(["📅 Semanal", "🗓️ Mensual", "🎓 Periodo Lectivo"])

    with t_sem:
        df_s = df[df['Fecha'] >= (datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None) - timedelta(days=7))].copy()
        if not df_s.empty:
            st.dataframe(df_s.sort_values(['Grupo', 'Alumno']), use_container_width=True, hide_index=True)
        else:
            st.success("Sin reportes esta semana.")

    with t_mes:
        df_m = df[df['Fecha'].dt.month == datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None).month].copy()
        if not df_m.empty:
            res = df_m.groupby(['Grupo', 'Alumno', 'Falta']).size().reset_index(name='Veces')
            st.dataframe(res.sort_values(['Grupo', 'Alumno']), use_container_width=True, hide_index=True)
        else:
            st.info("Sin registros este mes.")

    with t_per:
        hoy = datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None)
        
        # ✨ NUEVO: Extraemos y aplanamos todos los periodos del diccionario
        todos_los_periodos = []
        if isinstance(PERIODOS_LECTIVOS, dict):
            for nivel, periodos in PERIODOS_LECTIVOS.items():
                for p in periodos:
                    p_copia = p.copy()
                    # Le añadimos el nivel al nombre para que el director sepa cuál está viendo
                    p_copia['nombre_mostrar'] = f"{p['nombre']} ({nivel})"
                    todos_los_periodos.append(p_copia)
        else:
            # Respaldo por si regresa a ser lista en el futuro
            for p in PERIODOS_LECTIVOS:
                p_copia = p.copy()
                p_copia['nombre_mostrar'] = p['nombre']
                todos_los_periodos.append(p_copia)
        
        # Filtramos solo los periodos que ya comenzaron
        pers = [p for p in todos_los_periodos if datetime.strptime(p['inicio'], '%Y-%m-%d') <= hoy]
        
        if not pers:
            st.info("No hay periodos activos hasta el día de hoy.")
        else:
            sel_p = st.selectbox(f"Periodo ({titulo_contexto}):", [p['nombre_mostrar'] for p in pers], index=len(pers)-1, key=f"per_{titulo_contexto}")
            p_inf = next(p for p in pers if p['nombre_mostrar'] == sel_p)
            
            df_p = df[(df['Fecha'] >= p_inf['inicio']) & (df['Fecha'] <= p_inf['fin'])].copy()
            if not df_p.empty:
                df_p['Puntos_Descontados'] = pd.to_numeric(df_p['Puntos_Descontados'], errors='coerce').fillna(0)
                boleta = df_p.groupby(['Grupo', 'Alumno'])['Puntos_Descontados'].sum().reset_index()
                boleta['Promedio'] = (10 + (boleta['Puntos_Descontados'] / 5)).clip(0, 10)
                boleta['Calificación'] = boleta['Promedio'].apply(format_calif)
                
                st.dataframe(boleta[['Grupo', 'Alumno', 'Calificación']].sort_values(['Grupo', 'Alumno']), use_container_width=True, hide_index=True)
                if modo_descarga:
                    st.download_button("📥 Descargar Excel", boleta.to_csv(index=False).encode('utf-8'), f"Reporte_{sel_p}.csv")
            else:
                st.success("Sin incidencias en el periodo.")
