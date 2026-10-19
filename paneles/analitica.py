# paneles/analitica.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import PERIODOS_LECTIVOS
from calculadora import format_calif, calcular_calificacion_progresiva

# ==========================================
# 🌟 FUNCIÓN PARA LA VENTANA EMERGENTE (POP-UP)
# ==========================================
@st.dialog("📄 Detalle de Observaciones", width="large")
def mostrar_popup_detalles(df_filtrado, alumno, materia, grupo):
    st.markdown(f"#### 👨‍🎓 {alumno}")
    st.markdown(f"**📚 Materia:** {materia} | **🏫 Grupo:** {grupo}")
    st.markdown("---")
    
    # Filtramos la base de datos cruda para sacar solo los reportes de este alumno en esta materia
    df_detalle = df_filtrado[
        (df_filtrado['Alumno'] == alumno) & 
        (df_filtrado['Materia'] == materia) & 
        (df_filtrado['Grupo'] == grupo)
    ].copy()
    
    if df_detalle.empty:
        st.info("Este registro no tiene observaciones detalladas.")
    else:
        # Mostramos las columnas clave para el director
        cols_clave = ['Fecha', 'Profesor', 'Falta', 'Observaciones', 'Puntos_Descontados']
        cols_existentes = [c for c in cols_clave if c in df_detalle.columns]
        
        st.dataframe(
            df_detalle[cols_existentes].sort_values('Fecha', ascending=False), 
            hide_index=True, 
            use_container_width=True
        )
        
        if st.button("Cerrar Ventana", use_container_width=True):
            st.rerun()

# ==========================================
# 4. COMPONENTE ANALÍTICO MULTI-FILTRO
# ==========================================
def mostrar_tablero_analitico(df, titulo_contexto, modo_descarga=True):
    if df.empty:
        st.info("No hay datos registrados con los filtros seleccionados.")
        return

    df['Fecha'] = pd.to_datetime(df['Fecha'])
    t_sem, t_mes, t_per = st.tabs(["📅 Semanal", "🗓️ Mensual", "🎓 Periodo Lectivo"])

    # --- PESTAÑA SEMANAL ---
    with t_sem:
        df_s = df[df['Fecha'] >= (datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None) - timedelta(days=7))].copy()
        if not df_s.empty:
            cols_visibles = [c for c in ['Fecha', 'Alumno', 'Grupo', 'Materia', 'Categoría', 'Falta', 'Observaciones', 'Puntos_Descontados'] if c in df_s.columns]
            st.dataframe(df_s[cols_visibles].sort_values(['Fecha'], ascending=False), use_container_width=True, hide_index=True)
        else:
            st.success("Sin reportes esta semana.")

    # --- PESTAÑA MENSUAL ---
    with t_mes:
        df_m = df[df['Fecha'].dt.month == datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None).month].copy()
        if not df_m.empty:
            cols_visibles = [c for c in ['Fecha', 'Alumno', 'Grupo', 'Materia', 'Categoría', 'Falta', 'Observaciones', 'Puntos_Descontados'] if c in df_m.columns]
            st.dataframe(df_m[cols_visibles].sort_values(['Fecha'], ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("Sin registros este mes.")

    # --- PESTAÑA DE PERIODO (DONDE ESTÁ LA BOLETA) ---
    with t_per:
        hoy = datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None)
        
        todos_los_periodos = []
        if isinstance(PERIODOS_LECTIVOS, dict):
            for nivel, periodos in PERIODOS_LECTIVOS.items():
                for p in periodos:
                    p_copia = p.copy()
                    p_copia['nombre_mostrar'] = f"{p['nombre']} ({nivel})"
                    todos_los_periodos.append(p_copia)
        else:
            for p in PERIODOS_LECTIVOS:
                p_copia = p.copy()
                p_copia['nombre_mostrar'] = p['nombre']
                todos_los_periodos.append(p_copia)
        
        pers = [p for p in todos_los_periodos if datetime.strptime(p['inicio'], '%Y-%m-%d') <= hoy]
        
        if not pers:
            st.info("No hay periodos activos hasta el día de hoy.")
        else:
            sel_p = st.selectbox(f"Periodo ({titulo_contexto}):", [p['nombre_mostrar'] for p in pers], index=len(pers)-1, key=f"per_{titulo_contexto}")
            p_inf = next(p for p in pers if p['nombre_mostrar'] == sel_p)
            
            df_p = df[(df['Fecha'] >= p_inf['inicio']) & (df['Fecha'] <= p_inf['fin'])].copy()
            if not df_p.empty:
                
                # Agrupamos la calificación matemáticamente
                boleta_data = []
                for (g, mat, al), df_alumno in df_p.groupby(['Grupo', 'Materia', 'Alumno']):
                    prom, _ = calcular_calificacion_progresiva(df_alumno)
                    boleta_data.append({
                        'Grupo': g, 
                        'Materia': mat, 
                        'Alumno': al, 
                        'Promedio': prom
                    })
                
                boleta = pd.DataFrame(boleta_data)
                boleta['Calificación'] = boleta['Promedio'].apply(format_calif)
                
                # 1. Dibujar la tabla general
                st.dataframe(
                    boleta[['Grupo', 'Materia', 'Alumno', 'Calificación']].sort_values(['Grupo', 'Materia', 'Alumno']), 
                    use_container_width=True, 
                    hide_index=True
                )
                
                # =======================================================
                # 🔍 INSPECTOR INTELIGENTE (Botón para abrir el Pop-Up)
                # =======================================================
                st.markdown("---")
                st.markdown("#### 🔍 Inspeccionar Reportes Detallados")
                st.caption("Selecciona un alumno de la tabla superior para leer las observaciones de su comportamiento.")
                
                # Creamos un diccionario rápido para emparejar el selector con la base de datos
                dict_opciones = {f"{r['Grupo']} | {r['Materia']} | {r['Alumno']} ({r['Calificación']})": i for i, r in boleta.iterrows()}
                
                c_sel, c_btn = st.columns([3, 1])
                with c_sel:
                    registro_elegido = st.selectbox(
                        "Selecciona un alumno:", 
                        ["Seleccione..."] + list(dict_opciones.keys()), 
                        key=f"sel_det_{titulo_contexto}"
                    )
                with c_btn:
                    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                    if st.button("👁️ Abrir Observaciones", use_container_width=True, type="primary"):
                        if registro_elegido != "Seleccione...":
                            idx_elegido = dict_opciones[registro_elegido]
                            fila_seleccionada = boleta.iloc[idx_elegido]
                            
                            # Llamamos a la función mágica que dibuja el pop-up
                            mostrar_popup_detalles(df_p, fila_seleccionada['Alumno'], fila_seleccionada['Materia'], fila_seleccionada['Grupo'])
                        else:
                            st.warning("Selecciona un registro primero.")
                
                if modo_descarga:
                    st.markdown("---")
                    def texto_semaforo_excel(val):
                        if val >= 9.0: return "Verde (Aprobado)"
                        if val >= 7.0: return "Amarillo (En Riesgo)"
                        return "Rojo (Reprobado)"

                    df_excel = boleta[['Grupo', 'Materia', 'Alumno', 'Promedio']].copy()
                    df_excel['Estado'] = df_excel['Promedio'].apply(texto_semaforo_excel)
                    df_excel = df_excel.sort_values(['Grupo', 'Materia', 'Alumno'])
                    
                    st.download_button(
                        "📥 Descargar Resumen General a Excel", 
                        df_excel.to_csv(index=False).encode('utf-8-sig'), 
                        f"Reporte_{sel_p}.csv",
                        mime="text/csv"
                    )
            else:
                st.success("Sin incidencias en el periodo.")