# paneles/calificaciones.py
import streamlit as st
import pandas as pd
import gspread
import uuid
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    FILE_ASIGNACIONES, 
    FILE_ALUMNOS, 
    FILE_CALIFICACIONES, 
    PERIODOS_LECTIVOS, 
    SUPER_USUARIOS_WHITELIST
)
from database import (
    leer_datos, 
    obtener_lista_alumnos, 
    leer_todas_las_asignaciones
)

# 🎨 SEMÁFORO EN ESCALA DE 100 PUNTOS (ESTÁNDAR GOOGLE CLASSROOM)
def format_calif_100(val):
    if val >= 90.0: return f"🟢 {val:.1f}"
    if val >= 70.0: return f"🟡 {val:.1f}"
    return f"🔴 {val:.1f}"

def renderizar_panel_calificaciones(gc, usuario, nombre_prof):
    st.header(f"📊 Calificador Académico: {nombre_prof}")
    
    usuario = str(usuario).lower().strip()
    es_superusuario = usuario in SUPER_USUARIOS_WHITELIST
    
    # 1. Cargar asignaciones
    df_asig = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
    if df_asig.empty or 'Usuario_Profesor' not in df_asig.columns:
        st.warning("⚠️ No se encontró la estructura de asignaciones docentes.")
        return
        
    df_asig['Usuario_Profesor'] = df_asig['Usuario_Profesor'].astype(str).str.lower().str.strip()
    df_asig['Materia'] = df_asig['Materia'].astype(str).str.strip()
    df_asig['Grupo'] = df_asig['Grupo'].astype(str).str.strip()
    
    if es_superusuario:
        mis_asig = df_asig.copy()
    else:
        mis_asig = df_asig[df_asig['Usuario_Profesor'] == usuario]
        
    if mis_asig.empty:
        st.warning("⚠️ No tienes materias asignadas para calificar.")
        return
        
    niveles = sorted(mis_asig['Nivel'].unique().tolist())
    if len(niveles) > 1:
        nivel_sel = st.radio("Sección Escolar:", niveles, horizontal=True)
        mis_asig = mis_asig[mis_asig['Nivel'] == nivel_sel]
    else:
        nivel_sel = niveles[0]

    c1, c2, c3 = st.columns(3)
    materia_sel = c1.selectbox("Materia:", mis_asig['Materia'].unique(), key="calif_mat")
    grupos_de_esta_materia = mis_asig[mis_asig['Materia'] == materia_sel]['Grupo'].unique().tolist()
    grupo_sel = c2.selectbox("Grupo activo:", grupos_de_esta_materia, key="calif_grup")
    
    nivel_key = "Secundaria" if "secundaria" in str(nivel_sel).lower() else "Preparatoria"
    periodos_disponibles = [p["nombre"] for p in PERIODOS_LECTIVOS.get(nivel_key, [])]
    periodo_sel = c3.selectbox("Periodo de Evaluación:", periodos_disponibles, key="calif_per")
    
    clase_id = f"{materia_sel} - {grupo_sel}"
    st.markdown("---")
    
    # =================================================================
    # 2. PONDERACIONES / CRITERIOS
    # =================================================================
    df_pond_todas = leer_datos(gc, FILE_CALIFICACIONES, "Ponderaciones")
    if not df_pond_todas.empty:
        df_pond_todas.columns = df_pond_todas.columns.str.strip()
        
    if not df_pond_todas.empty and 'Clase' in df_pond_todas.columns and 'Rubro' in df_pond_todas.columns:
        df_pond_todas['Clase'] = df_pond_todas['Clase'].astype(str).str.strip()
        df_pond_todas['Periodo'] = df_pond_todas['Periodo'].astype(str).str.strip()
        pond_actual = df_pond_todas[(df_pond_todas['Clase'] == clase_id) & (df_pond_todas['Periodo'] == periodo_sel)]
    else:
        pond_actual = pd.DataFrame()
        
    if pond_actual.empty:
        st.warning(f"⚠️ No has configurado los criterios de evaluación para **{clase_id}** en el **{periodo_sel}**.")
        
        # Opción de clonar
        idx_actual = periodos_disponibles.index(periodo_sel) if periodo_sel in periodos_disponibles else 0
        if idx_actual > 0 and not df_pond_todas.empty and 'Clase' in df_pond_todas.columns:
            periodo_anterior = periodos_disponibles[idx_actual - 1]
            pond_ant = df_pond_todas[(df_pond_todas['Clase'] == clase_id) & (df_pond_todas['Periodo'] == periodo_anterior)]
            if not pond_ant.empty:
                if st.button(f"📋 Copiar ponderaciones del {periodo_anterior}", type="secondary"):
                    with st.spinner("Clonando criterios..."):
                        doc_calif = gc.open(FILE_CALIFICACIONES)
                        ws_p = doc_calif.worksheet("Ponderaciones")
                        filas_clon = [[clase_id, periodo_sel, r['Rubro'], r['Porcentaje']] for _, r in pond_ant.iterrows()]
                        ws_p.append_rows(filas_clon)
                        leer_datos.clear()
                        st.success("✅ Criterios copiados exitosamente.")
                        time.sleep(1)
                        st.rerun()

        st.markdown("##### 📝 Define tus Criterios de Evaluación")
        criterios_base = pd.DataFrame([
            {"Categoría / Rubro": "Exámenes", "Porcentaje (%)": 40},
            {"Categoría / Rubro": "Tareas y Trabajos", "Porcentaje (%)": 30},
            {"Categoría / Rubro": "Proyectos e Investigación", "Porcentaje (%)": 20},
            {"Categoría / Rubro": "Participación y Asistencia", "Porcentaje (%)": 10},
        ])
        
        df_criterios_edit = st.data_editor(
            criterios_base,
            num_rows="dynamic",
            column_config={
                "Categoría / Rubro": st.column_config.TextColumn("Categoría / Rubro", required=True),
                "Porcentaje (%)": st.column_config.NumberColumn("Porcentaje (%)", min_value=1, max_value=100, step=5, required=True)
            },
            use_container_width=True,
            hide_index=True,
            key=f"editor_pond_{clase_id}_{periodo_sel}"
        )
        
        suma_porcentajes = int(df_criterios_edit["Porcentaje (%)"].fillna(0).sum())
        todas_mis_clases = sorted(list(set([f"{r['Materia']} - {r['Grupo']}" for _, r in mis_asig.iterrows()])))
        
        st.markdown("##### 👥 Aplicar estos mismos criterios a:")
        clases_destino_pond = st.multiselect(
            "Selecciona las materias/salones que compartirán esta ponderación:",
            options=todas_mis_clases,
            default=[clase_id]
        )
        
        c_status, c_save_btn = st.columns([3, 2])
        with c_status:
            if suma_porcentajes == 100:
                st.success(f"Suma total: **{suma_porcentajes}%** ✅ (Listo para guardar)")
            else:
                st.error(f"Suma total: **{suma_porcentajes}%** ❌ (Debe dar 100%)")
                
        with c_save_btn:
            if st.button("💾 Guardar Criterios de Evaluación", type="primary", use_container_width=True):
                if suma_porcentajes != 100:
                    st.error("🚨 La suma debe ser exactamente 100%.")
                elif not clases_destino_pond:
                    st.error("🚨 Selecciona al menos una materia/salón.")
                else:
                    with st.spinner("Guardando en la nube..."):
                        try:
                            doc_calif = gc.open(FILE_CALIFICACIONES)
                            ws_p = doc_calif.worksheet("Ponderaciones")
                            all_vals = ws_p.get_all_values()
                            if not all_vals:
                                ws_p.append_row(["Clase", "Periodo", "Rubro", "Porcentaje"])
                            
                            lote_p = []
                            for target_clase in clases_destino_pond:
                                for _, fila in df_criterios_edit.iterrows():
                                    r_nom = str(fila["Categoría / Rubro"]).strip()
                                    r_pct = int(fila["Porcentaje (%)"])
                                    if r_nom:
                                        lote_p.append([target_clase, periodo_sel, r_nom, r_pct])
                                        
                            ws_p.append_rows(lote_p)
                            leer_datos.clear()
                            st.success(f"✅ Criterios configurados para {len(clases_destino_pond)} clase(s).")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e_save:
                            if "200" in str(e_save):
                                leer_datos.clear()
                                st.success("✅ Criterios guardados exitosamente.")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"Error al guardar: {e_save}")
        st.stop()
        
    rubros_pesos = dict(zip(pond_actual['Rubro'], pond_actual['Porcentaje']))
    
    col_t1, col_t2 = st.columns([4, 1])
    with col_t1:
        cols_badge = st.columns(len(rubros_pesos))
        for i, (rubro, pct) in enumerate(rubros_pesos.items()):
            cols_badge[i].metric(rubro, f"{pct}%")
    with col_t2:
        if st.button("⚙️ Modificar", help="Borra los criterios actuales para reconfigurarlos", use_container_width=True):
            doc_calif = gc.open(FILE_CALIFICACIONES)
            ws_p = doc_calif.worksheet("Ponderaciones")
            all_vals = ws_p.get_all_values()
            nuevas_filas = [r for r in all_vals if len(r) > 1 and not (r[0] == clase_id and r[1] == periodo_sel)]
            ws_p.clear()
            ws_p.append_rows([["Clase", "Periodo", "Rubro", "Porcentaje"]] + nuevas_filas)
            leer_datos.clear()
            st.rerun()
        
    st.markdown("---")
    
    # =================================================================
    # 3. CREACIÓN DE ACTIVIDAD (ESCALA 100)
    # =================================================================
    with st.popover("➕ Nueva Actividad / Tarea", use_container_width=True):
        st.markdown("### Crear Actividad de Evaluación (Escala 100)")
        
        nombre_actividad = st.text_input("Nombre de la Actividad:", placeholder="Ej. Examen 1 - Leyes de Newton")
        rubro_actividad = st.selectbox("Categoría a la que pertenece:", list(rubros_pesos.keys()))
        puntos_max = st.number_input("Puntos Máximos:", min_value=10.0, max_value=100.0, value=100.0, step=10.0)
        
        st.markdown("##### 👥 Asignar a grupos:")
        grupos_seleccionados_tarea = st.multiselect(
            "Grupos que realizarán esta actividad:",
            options=grupos_de_esta_materia,
            default=[grupo_sel]
        )
        
        if st.button("🚀 Crear y Asignar Actividad", type="primary", use_container_width=True):
            if not nombre_actividad.strip():
                st.error("⚠️ Asigna un nombre a la actividad.")
            elif not grupos_seleccionados_tarea:
                st.error("⚠️ Selecciona al menos un grupo.")
            else:
                with st.spinner("Creando actividad..."):
                    try:
                        doc_calif = gc.open(FILE_CALIFICACIONES)
                        ws_act = doc_calif.worksheet("Actividades")
                        all_acts = ws_act.get_all_values()
                        headers_act = ["ID_Actividad", "Clase", "Periodo", "Nombre_Actividad", "Rubro", "Puntos_Max", "Fecha_Creacion"]
                        if not all_acts:
                            ws_act.append_row(headers_act)
                        
                        lote_actividades = []
                        fecha_creacion = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d")
                        for g in grupos_seleccionados_tarea:
                            id_act = f"ACT-{uuid.uuid4().hex[:6].upper()}"
                            clase_target = f"{materia_sel} - {g}"
                            lote_actividades.append([
                                id_act, clase_target, periodo_sel, nombre_actividad.strip(), rubro_actividad, puntos_max, fecha_creacion
                            ])
                            
                        ws_act.append_rows(lote_actividades)
                        leer_datos.clear()
                        st.success(f"✅ Actividad creada para {len(grupos_seleccionados_tarea)} grupo(s).")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e_act:
                        if "200" in str(e_act):
                            leer_datos.clear()
                            st.success("✅ Actividad creada exitosamente.")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"Error al crear actividad: {e_act}")

    # =================================================================
    # 4. MATRIZ DE CALIFICACIONES (ESCALA 100 Y CÁLCULO PROPORCIONAL)
    # =================================================================
    try:
        grupo_limpio = grupo_sel.split("(")[0].strip()
        alumnos_clase = obtener_lista_alumnos(gc, FILE_ALUMNOS, grupo_limpio)
    except Exception:
        alumnos_clase = []
        
    if not alumnos_clase:
        st.warning(f"No hay alumnos registrados en la lista de '{grupo_limpio}'.")
        return
        
    df_act_todas = leer_datos(gc, FILE_CALIFICACIONES, "Actividades")
    if not df_act_todas.empty and 'Clase' in df_act_todas.columns:
        df_act_todas['Clase'] = df_act_todas['Clase'].astype(str).str.strip()
        df_act_todas['Periodo'] = df_act_todas['Periodo'].astype(str).str.strip()
        mis_actividades = df_act_todas[(df_act_todas['Clase'] == clase_id) & (df_act_todas['Periodo'] == periodo_sel)]
    else:
        mis_actividades = pd.DataFrame()
        
    if mis_actividades.empty:
        st.info("💡 Aún no has agregado ninguna actividad evaluativa en este periodo. Haz clic en **'➕ Nueva Actividad / Tarea'** arriba.")
        return

    df_notas_todas = leer_datos(gc, FILE_CALIFICACIONES, "Calificaciones")
    if not df_notas_todas.empty and 'Clase' in df_notas_todas.columns:
        df_notas_todas['Clase'] = df_notas_todas['Clase'].astype(str).str.strip()
        mis_notas = df_notas_todas[df_notas_todas['Clase'] == clase_id]
    else:
        mis_notas = pd.DataFrame()

    datos_matriz = {"Alumno": alumnos_clase}
    actividades_cols = []
    
    for _, act in mis_actividades.iterrows():
        id_act = str(act['ID_Actividad']).strip()
        col_nombre = f"{act['Nombre_Actividad']} ({act['Rubro']})"
        p_max = float(act.get('Puntos_Max', 100.0))
        actividades_cols.append((id_act, col_nombre, act['Rubro'], p_max))
        
        # Leemos notas existentes de la nube
        notas_act = mis_notas[mis_notas['ID_Actividad'] == id_act] if not mis_notas.empty else pd.DataFrame()
        dicc_notas = dict(zip(notas_act['Alumno'].astype(str).str.strip(), pd.to_numeric(notas_act['Nota'], errors='coerce').fillna(0.0))) if not notas_act.empty else {}
        
        datos_matriz[col_nombre] = [float(dicc_notas.get(str(al).strip(), 0.0)) for al in alumnos_clase]

    df_editable = pd.DataFrame(datos_matriz)
    
    # 🧮 CÁLCULO PROPORCIONAL DE PROMEDIOS (ESTILO GOOGLE CLASSROOM)
    # Solo evalúa los rubros que REALMENTE tienen tareas creadas
    rubros_con_tareas = list(set([r for _, _, r, _ in actividades_cols]))
    peso_total_evaluado = sum(float(rubros_pesos.get(r, 0.0)) for r in rubros_con_tareas)
    
    promedios_calculados = []
    for idx, row in df_editable.iterrows():
        desglose_por_rubro = {r: [] for r in rubros_con_tareas}
        
        for id_act, col_nom, rubro, p_max in actividades_cols:
            val_nota = float(row.get(col_nom, 0.0))
            # Normalizamos cada tarea a base 100
            nota_base_100 = (val_nota / p_max) * 100.0 if p_max > 0 else 0.0
            desglose_por_rubro[rubro].append(nota_base_100)
            
        puntos_acumulados = 0.0
        for rubro, lista_notas in desglose_por_rubro.items():
            pct_rubro = float(rubros_pesos.get(rubro, 0.0))
            prom_rubro = (sum(lista_notas) / len(lista_notas)) if lista_notas else 0.0
            puntos_acumulados += (prom_rubro * (pct_rubro / 100.0))
            
        # Ponderación proporcional: normaliza sobre el peso activo
        if peso_total_evaluado > 0:
            promedio_periodo_alumno = (puntos_acumulados / (peso_total_evaluado / 100.0))
        else:
            promedio_periodo_alumno = 0.0
            
        promedios_calculados.append(round(promedio_periodo_alumno, 1))

    df_editable['Promedio Periodo'] = [format_calif_100(p) for p in promedios_calculados]
    
    config_editor = {
        "Alumno": st.column_config.TextColumn("Alumno", disabled=True),
        "Promedio Periodo": st.column_config.TextColumn("Promedio Periodo (Base 100)", disabled=True)
    }
    for _, col_nom, _, p_max in actividades_cols:
        config_editor[col_nom] = st.column_config.NumberColumn(
            col_nom, min_value=0.0, max_value=float(p_max), step=1.0, format="%.1f", required=True
        )

    st.subheader("📝 Captura de Calificaciones (Base 100)")
    df_resultado = st.data_editor(
        df_editable,
        column_config=config_editor,
        use_container_width=True,
        hide_index=True,
        key=f"ed_calif_{clase_id}_{periodo_sel}"
    )

    col_save, col_dl = st.columns([1, 1])
    with col_save:
        if st.button("💾 Guardar Calificaciones", type="primary", use_container_width=True):
            with st.spinner("Guardando calificaciones en la nube..."):
                try:
                    doc_calif = gc.open(FILE_CALIFICACIONES)
                    ws_notas = doc_calif.worksheet("Calificaciones")
                    
                    all_vals_notas = ws_notas.get_all_values()
                    headers_notas = ["ID_Actividad", "Clase", "Alumno", "Nota"]
                    
                    # Conservamos notas de otras clases
                    if len(all_vals_notas) > 1:
                        filas_otras = [r for r in all_vals_notas[1:] if len(r) > 1 and str(r[1]).strip() != clase_id]
                    else:
                        filas_otras = []
                    
                    filas_nuevas = []
                    for _, r in df_resultado.iterrows():
                        al_nombre = str(r['Alumno']).strip()
                        for id_act, col_nom, _, _ in actividades_cols:
                            nota_val = float(r.get(col_nom, 0.0))
                            filas_nuevas.append([id_act, clase_id, al_nombre, nota_val])
                    
                    # Matriz limpia consolidada
                    matriz_final = [headers_notas] + filas_otras + filas_nuevas
                    
                    # Sobrescritura directa desde A1 sin usar .clear()
                    ws_notas.update(range_name="A1", values=matriz_final)
                    
                    leer_datos.clear()
                    st.success("✅ Calificaciones guardadas exitosamente en la nube.")
                    time.sleep(1)
                    st.rerun()
                except Exception as e_grades:
                    if "200" in str(e_grades):
                        leer_datos.clear()
                        st.success("✅ Calificaciones guardadas exitosamente.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"Error al guardar notas: {e_grades}")
                
    with col_dl:
        csv_boleta = df_resultado.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 Descargar Boleta del Grupo (CSV)",
            data=csv_boleta,
            file_name=f"Calificaciones_{clase_id}_{periodo_sel}.csv",
            mime="text/csv",
            use_container_width=True
        )