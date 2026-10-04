# paneles/calificaciones.py
import streamlit as st
import pandas as pd
import uuid
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import text

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
    leer_todas_las_asignaciones,
    obtener_engine_sql
)

# 🎨 SEMÁFORO EN ESCALA 100 (GOOGLE CLASSROOM)
def format_calif_100(val):
    if val >= 90.0: return f"🟢 {val:.1f}"
    if val >= 70.0: return f"🟡 {val:.1f}"
    return f"🔴 {val:.1f}"

def renderizar_panel_calificaciones(gc, usuario, nombre_prof):
    st.header(f"📊 Calificador Académico: {nombre_prof}")
    
    usuario = str(usuario).lower().strip()
    es_superusuario = usuario in SUPER_USUARIOS_WHITELIST
    engine = obtener_engine_sql()
    
    # 1. Cargar asignaciones docentes
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
        st.warning("⚠️ Sin materias asignadas para calificar.")
        return
        
    niveles = sorted(mis_asig['Nivel'].unique().tolist())
    if len(niveles) > 1:
        nivel_sel = st.radio("Sección Escolar:", niveles, horizontal=True)
        mis_asig = mis_asig[mis_asig['Nivel'] == nivel_sel]
    else:
        nivel_sel = niveles[0]

    # Selectores: Materia, Grupo y Periodo
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
    # 2. PONDERACIONES / CRITERIOS (CONEXIÓN SQL SUPABASE)
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
        
    # Si no están configuradas las ponderaciones
    if pond_actual.empty:
        st.warning(f"⚠️ No has configurado los criterios de evaluación para **{clase_id}** en el **{periodo_sel}**.")
        
        # Opción A: Clonar del periodo anterior
        idx_actual = periodos_disponibles.index(periodo_sel) if periodo_sel in periodos_disponibles else 0
        if idx_actual > 0 and not df_pond_todas.empty and 'Clase' in df_pond_todas.columns:
            periodo_anterior = periodos_disponibles[idx_actual - 1]
            pond_ant = df_pond_todas[(df_pond_todas['Clase'] == clase_id) & (df_pond_todas['Periodo'] == periodo_anterior)]
            if not pond_ant.empty:
                if st.button(f"📋 Copiar ponderaciones del {periodo_anterior}", type="secondary"):
                    with st.spinner("Clonando criterios en Supabase..."):
                        with engine.begin() as conn:
                            for _, r in pond_ant.iterrows():
                                conn.execute(
                                    text('INSERT INTO "calif_ponderaciones" ("Clase", "Periodo", "Rubro", "Porcentaje") VALUES (:c, :p, :r, :pct)'),
                                    {"c": clase_id, "p": periodo_sel, "r": r['Rubro'], "pct": int(r['Porcentaje'])}
                                )
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
                    st.error("🚨 Selecciona al menos una clase.")
                else:
                    with st.spinner("Guardando en Supabase..."):
                        try:
                            with engine.begin() as conn:
                                for target_clase in clases_destino_pond:
                                    # Borramos anteriores de ese periodo en Supabase
                                    conn.execute(
                                        text('DELETE FROM "calif_ponderaciones" WHERE "Clase" = :c AND "Periodo" = :p'),
                                        {"c": target_clase, "p": periodo_sel}
                                    )
                                    for _, fila in df_criterios_edit.iterrows():
                                        r_nom = str(fila["Categoría / Rubro"]).strip()
                                        r_pct = int(fila["Porcentaje (%)"])
                                        if r_nom:
                                            conn.execute(
                                                text('INSERT INTO "calif_ponderaciones" ("Clase", "Periodo", "Rubro", "Porcentaje") VALUES (:c, :p, :r, :pct)'),
                                                {"c": target_clase, "p": periodo_sel, "r": r_nom, "pct": r_pct}
                                            )
                            leer_datos.clear()
                            st.success(f"✅ Criterios guardados para {len(clases_destino_pond)} clase(s).")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e_p:
                            st.error(f"Error al guardar: {e_p}")
        st.stop()
        
    rubros_pesos = dict(zip(pond_actual['Rubro'], pond_actual['Porcentaje']))
    
    # Visualización de los criterios configurados
    col_t1, col_t2 = st.columns([4, 1])
    with col_t1:
        cols_badge = st.columns(len(rubros_pesos))
        for i, (rubro, pct) in enumerate(rubros_pesos.items()):
            cols_badge[i].metric(rubro, f"{pct}%")
            
    # ✅ FIX DEFINITIVO BOTÓN MODIFICAR (EJECUCIÓN SQL DIRECTA)
    with col_t2:
        if st.button("⚙️ Modificar Criterios", help="Borra las ponderaciones actuales para reeditarlas", use_container_width=True):
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text('DELETE FROM "calif_ponderaciones" WHERE "Clase" = :c AND "Periodo" = :p'),
                        {"c": clase_id, "p": periodo_sel}
                    )
                leer_datos.clear()
                st.success("✅ Criterios eliminados. Ya puedes reconfigurarlos.")
                time.sleep(1)
                st.rerun()
            except Exception as e_mod:
                st.error(f"Error al modificar criterios: {e_mod}")
        
    st.markdown("---")
    
    # =================================================================
    # 3. ACCIONES DE ACTIVIDADES: CREAR, SINCRONIZAR Y ELIMINAR
    # =================================================================
    # Consultamos las actividades existentes de esta clase y periodo
    df_act_todas = leer_datos(gc, FILE_CALIFICACIONES, "Actividades")
    if not df_act_todas.empty and 'Clase' in df_act_todas.columns:
        df_act_todas['Clase'] = df_act_todas['Clase'].astype(str).str.strip()
        df_act_todas['Periodo'] = df_act_todas['Periodo'].astype(str).str.strip()
        mis_actividades = df_act_todas[(df_act_todas['Clase'] == clase_id) & (df_act_todas['Periodo'] == periodo_sel)]
    else:
        mis_actividades = pd.DataFrame()

    # Fila de 3 botones de acción equilibrados
    col_btn_act1, col_btn_act2, col_btn_act3 = st.columns(3)
    
    # --- BOTÓN 1: CREAR ACTIVIDAD MANUAL ---
    with col_btn_act1:
        with st.popover("➕ Nueva Tarea Manual", use_container_width=True):
            st.markdown("### Crear Actividad Manual")
            nombre_actividad = st.text_input("Nombre de la Actividad:", placeholder="Ej. Tarea 1 - Ley de Ohm")
            rubro_actividad = st.selectbox("Categoría a la que pertenece:", list(rubros_pesos.keys()))
            puntos_max = st.number_input("Puntos Máximos:", min_value=10.0, max_value=100.0, value=100.0, step=10.0)
            
            st.markdown("##### 👥 Asignar a grupos:")
            grupos_seleccionados_tarea = st.multiselect("Grupos a los que aplica:", options=grupos_de_esta_materia, default=[grupo_sel])
            
            if st.button("🚀 Crear y Asignar Actividad", type="primary", use_container_width=True):
                if not nombre_actividad.strip():
                    st.error("⚠️ Asigna un nombre a la actividad.")
                elif not grupos_seleccionados_tarea:
                    st.error("⚠️ Selecciona al menos un grupo.")
                else:
                    with st.spinner("Creando en Supabase..."):
                        try:
                            fecha_creacion = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d")
                            with engine.begin() as conn:
                                for g in grupos_seleccionados_tarea:
                                    id_act = f"ACT-{uuid.uuid4().hex[:6].upper()}"
                                    clase_target = f"{materia_sel} - {g}"
                                    conn.execute(
                                        text('''INSERT INTO "calif_actividades" ("ID_Actividad", "Clase", "Periodo", "Nombre_Actividad", "Rubro", "Puntos_Max", "Fecha_Creacion")
                                                VALUES (:id, :c, :p, :nom, :rub, :pmax, :fec)'''),
                                        {"id": id_act, "c": clase_target, "p": periodo_sel, "nom": nombre_actividad.strip(), "rub": rubro_actividad, "pmax": puntos_max, "fec": fecha_creacion}
                                    )
                            leer_datos.clear()
                            st.success(f"✅ Actividad creada para {len(grupos_seleccionados_tarea)} grupo(s).")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e_act:
                            st.error(f"Error al crear: {e_act}")

   # --- BOTÓN 2: SINCRONIZAR TODO DESDE CLASSROOM (MULTICATEGORÍA AUTOMÁTICA) ---
    with col_btn_act2:
        with st.popover("🔄 Sincronizar Classroom", use_container_width=True):
            st.markdown("### 🎓 Conexión con Google Classroom")
            token_google = st.session_state.get("access_token")
            
            if not token_google:
                st.warning("⚠️ No se detectó sesión de Classroom activa. Cierra sesión e inicia nuevamente aceptando los permisos.")
            else:
                st.caption("Esta herramienta descarga automáticamente **todas las tareas y exámenes de todas las categorías** con sus calificaciones.")
                
                try:
                    headers_cr = {"Authorization": f"Bearer {token_google}"}
                    res_c = requests.get("https://classroom.googleapis.com/v1/courses?teacherId=me&courseStates=ACTIVE", headers=headers_cr).json()
                    cursos_cr = res_c.get("courses", [])
                    
                    if not cursos_cr:
                        st.info("No se encontraron cursos activos en Google Classroom.")
                    else:
                        dict_cursos = {f"{c['name']} ({c.get('section', 'General')})": c['id'] for c in cursos_cr}
                        curso_seleccionado_label = st.selectbox("Selecciona la clase en Classroom:", list(dict_cursos.keys()))
                        id_curso_elegido = dict_cursos[curso_seleccionado_label]
                        
                        if st.button("🚀 Sincronizar Todo (Todas las Categorías y Notas)", type="primary", use_container_width=True):
                            with st.spinner("Descargando tareas, categorías y notas de Classroom a Supabase..."):
                                # 1. Consultamos el curso para extraer sus categorías oficiales de Classroom
                                res_curso_det = requests.get(f"https://classroom.googleapis.com/v1/courses/{id_curso_elegido}", headers=headers_cr).json()
                                cats_cr = res_curso_det.get("gradeCategories", [])
                                mapa_cats_cr = {c["id"]: c.get("name", "Tareas y Trabajos") for c in cats_cr}

                                # 2. Descargar todas las tareas (CourseWork)
                                res_w = requests.get(f"https://classroom.googleapis.com/v1/courses/{id_curso_elegido}/courseWork", headers=headers_cr).json()
                                tareas_cr = res_w.get("courseWork", [])
                                
                                if not tareas_cr:
                                    st.warning("Ese curso en Classroom no tiene tareas creadas.")
                                else:
                                    # 3. Padrón oficial de alumnos para cruzar por Correo Institucional
                                    df_alumnos_db = pd.read_sql('SELECT * FROM "alumnos"', engine)
                                    df_alumnos_db.columns = df_alumnos_db.columns.str.strip()
                                    col_correo_db = next((c for c in df_alumnos_db.columns if 'correo' in c.lower()), 'Correo')
                                    
                                    mapa_email_a_oficial = {}
                                    for _, al_row in df_alumnos_db.iterrows():
                                        c_inst = str(al_row.get(col_correo_db, '')).lower().strip()
                                        nom_of = str(al_row.get('Nombre Completo', '')).strip()
                                        if c_inst and nom_of:
                                            mapa_email_a_oficial[c_inst] = nom_of

                                    # 4. Alumnos de Classroom (IDs y Correos)
                                    res_st = requests.get(f"https://classroom.googleapis.com/v1/courses/{id_curso_elegido}/students", headers=headers_cr).json()
                                    mapa_userid_a_nombre = {}
                                    for s in res_st.get("students", []):
                                        u_id = s.get("userId")
                                        prof = s.get("profile", {})
                                        email_cr = str(prof.get("emailAddress", "")).lower().strip()
                                        nombre_cr = str(prof.get("name", {}).get("fullName", "")).strip()
                                        
                                        if email_cr in mapa_email_a_oficial:
                                            mapa_userid_a_nombre[u_id] = mapa_email_a_oficial[email_cr]
                                        else:
                                            nombre_encontrado = None
                                            palabras_cr = set(nombre_cr.lower().replace("'", "").split())
                                            for nom_of in alumnos_clase:
                                                palabras_of = set(nom_of.lower().replace("'", "").split())
                                                if len(palabras_cr.intersection(palabras_of)) >= 2:
                                                    nombre_encontrado = nom_of
                                                    break
                                            mapa_userid_a_nombre[u_id] = nombre_encontrado or nombre_cr
                                    
                                    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
                                    total_notas_descargadas = 0
                                    
                                    with engine.begin() as conn:
                                        for t in tareas_cr:
                                            id_act_cr = f"CR-{t['id']}"
                                            nom_t = t.get("title", "Sin Título")
                                            p_max_t = float(t.get("maxPoints", 100.0))
                                            
                                            # 🏷️ ASIGNACIÓN AUTOMÁTICA DE CATEGORÍA DESDE CLASSROOM:
                                            cat_id_t = t.get("gradeCategoryId")
                                            if cat_id_t and cat_id_t in mapa_cats_cr:
                                                rubro_detectado = mapa_cats_cr[cat_id_t]
                                            else:
                                                # Inferencia inteligente si no tenía categoría en Classroom
                                                nom_low = nom_t.lower()
                                                if any(w in nom_low for w in ["examen", "evalua", "quiz", "prueba"]):
                                                    rubro_detectado = "Exámenes"
                                                elif any(w in nom_low for w in ["proyect", "investig", "practic"]):
                                                    rubro_detectado = "Proyectos e Investigación"
                                                else:
                                                    rubro_detectado = "Tareas y Trabajos"
                                            
                                            # Emparejamos con los rubros configurados en la app
                                            rubro_final = rubro_detectado
                                            for r_existente in rubros_pesos.keys():
                                                if rubro_detectado.lower() in r_existente.lower() or r_existente.lower() in rubro_detectado.lower():
                                                    rubro_final = r_existente
                                                    break
                                            
                                            # Guardar / Actualizar Actividad en Supabase
                                            conn.execute(
                                                text('''INSERT INTO "calif_actividades" ("ID_Actividad", "Clase", "Periodo", "Nombre_Actividad", "Rubro", "Puntos_Max", "Fecha_Creacion")
                                                        VALUES (:id, :c, :p, :nom, :rub, :pmax, :fec)
                                                        ON CONFLICT ("ID_Actividad") DO UPDATE SET "Nombre_Actividad" = EXCLUDED."Nombre_Actividad", "Rubro" = EXCLUDED."Rubro", "Puntos_Max" = EXCLUDED."Puntos_Max"'''),
                                                {"id": id_act_cr, "c": clase_id, "p": periodo_sel, "nom": nom_t, "rub": rubro_final, "pmax": p_max_t, "fec": fecha_hoy}
                                            )
                                            
                                            # Descargar Notas de cada Alumno (Borradores y Oficiales)
                                            res_sub = requests.get(f"https://classroom.googleapis.com/v1/courses/{id_curso_elegido}/courseWork/{t['id']}/studentSubmissions", headers=headers_cr).json()
                                            for sub in res_sub.get("studentSubmissions", []):
                                                u_id = sub.get("userId")
                                                nom_alm = mapa_userid_a_nombre.get(u_id)
                                                
                                                nota_asignada = sub.get("assignedGrade")
                                                if nota_asignada is None:
                                                    nota_asignada = sub.get("draftGrade")
                                                
                                                if nom_alm and nota_asignada is not None:
                                                    conn.execute(
                                                        text('''INSERT INTO "calif_notas" ("ID_Actividad", "Clase", "Alumno", "Nota")
                                                                VALUES (:id, :c, :alm, :nota)
                                                                ON CONFLICT ("ID_Actividad", "Alumno") DO UPDATE SET "Nota" = EXCLUDED."Nota"'''),
                                                        {"id": id_act_cr, "c": clase_id, "alm": nom_alm, "nota": float(nota_asignada)}
                                                    )
                                                    total_notas_descargadas += 1
                                                    
                                    leer_datos.clear()
                                    st.success(f"🎉 ¡Éxito! Se importaron {len(tareas_cr)} tareas y {total_notas_descargadas} calificaciones en todas sus categorías correspondientes.")
                                    time.sleep(1)
                                    st.rerun()
                except Exception as e_cr:
                    st.error(f"Error con Classroom: {e_cr}")
                    
    # --- ✅ BOTÓN 3 NUEVO: ELIMINAR ACTIVIDAD ---
    with col_btn_act3:
        with st.popover("🗑️ Eliminar Actividad", use_container_width=True):
            st.markdown("### Eliminar Tarea o Examen")
            if mis_actividades.empty:
                st.info("No hay actividades registradas en este periodo para eliminar.")
            else:
                st.warning("⚠️ **Atención:** Al eliminar una actividad, se borrarán también todas las calificaciones que los alumnos tengan en ella.")
                
                dict_acts_del = {
                    f"{r['Nombre_Actividad']} ({r['Rubro']})": str(r['ID_Actividad']).strip()
                    for _, r in mis_actividades.iterrows()
                }
                
                act_a_borrar_lbl = st.selectbox("Selecciona la actividad a eliminar:", list(dict_acts_del.keys()), key="sel_act_del")
                id_act_a_borrar = dict_acts_del[act_a_borrar_lbl]
                
                confirmar_borrado = st.checkbox("Confirmo que deseo borrar esta actividad y sus notas", key="chk_conf_del_act")
                
                if st.button("🗑️ Borrar Definitivamente", type="secondary", disabled=not confirmar_borrado, use_container_width=True):
                    with st.spinner("Eliminando actividad y calificaciones de Supabase..."):
                        try:
                            with engine.begin() as conn:
                                # 1. Borramos notas de los alumnos asociadas a esa actividad
                                conn.execute(
                                    text('DELETE FROM "calif_notas" WHERE "ID_Actividad" = :id AND "Clase" = :c'),
                                    {"id": id_act_a_borrar, "c": clase_id}
                                )
                                # 2. Borramos la actividad del catálogo
                                conn.execute(
                                    text('DELETE FROM "calif_actividades" WHERE "ID_Actividad" = :id AND "Clase" = :c'),
                                    {"id": id_act_a_borrar, "c": clase_id}
                                )
                            leer_datos.clear()
                            st.success(f"✅ Actividad '{act_a_borrar_lbl}' eliminada exitosamente.")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e_del:
                            st.error(f"Error al eliminar actividad: {e_del}")

    st.markdown("---")
    
    # =================================================================
    # 4. MATRIZ DE CALIFICACIONES (ESCALA 100)
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
        st.info("💡 Aún no hay actividades en este periodo. Crea una manual o sincroniza desde Google Classroom arriba.")
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
        
        notas_act = mis_notas[mis_notas['ID_Actividad'] == id_act] if not mis_notas.empty else pd.DataFrame()
        dicc_notas = dict(zip(notas_act['Alumno'].astype(str).str.strip(), pd.to_numeric(notas_act['Nota'], errors='coerce').fillna(0.0))) if not notas_act.empty else {}
        
        datos_matriz[col_nombre] = [float(dicc_notas.get(str(al).strip(), 0.0)) for al in alumnos_clase]

    df_editable = pd.DataFrame(datos_matriz)
    
    # Cálculo proporcional en base 100
    rubros_con_tareas = list(set([r for _, _, r, _ in actividades_cols]))
    peso_total_evaluado = sum(float(rubros_pesos.get(r, 0.0)) for r in rubros_con_tareas)
    
    promedios_calculados = []
    for idx, row in df_editable.iterrows():
        desglose_por_rubro = {r: [] for r in rubros_con_tareas}
        
        for id_act, col_nom, rubro, p_max in actividades_cols:
            val_nota = float(row.get(col_nom, 0.0))
            nota_base_100 = (val_nota / p_max) * 100.0 if p_max > 0 else 0.0
            desglose_por_rubro[rubro].append(nota_base_100)
            
        puntos_acumulados = 0.0
        for rubro, lista_notas in desglose_por_rubro.items():
            pct_rubro = float(rubros_pesos.get(rubro, 0.0))
            prom_rubro = (sum(lista_notas) / len(lista_notas)) if lista_notas else 0.0
            puntos_acumulados += (prom_rubro * (pct_rubro / 100.0))
            
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
            with st.spinner("Guardando en Supabase..."):
                try:
                    with engine.begin() as conn:
                        for _, r in df_resultado.iterrows():
                            al_nombre = str(r['Alumno']).strip()
                            for id_act, col_nom, _, _ in actividades_cols:
                                nota_val = float(r.get(col_nom, 0.0))
                                conn.execute(
                                    text('''INSERT INTO "calif_notas" ("ID_Actividad", "Clase", "Alumno", "Nota")
                                            VALUES (:id, :c, :alm, :nota)
                                            ON CONFLICT ("ID_Actividad", "Alumno") DO UPDATE SET "Nota" = EXCLUDED."Nota"'''),
                                    {"id": id_act, "c": clase_id, "alm": al_nombre, "nota": nota_val}
                                )
                    leer_datos.clear()
                    st.success("✅ Calificaciones guardadas exitosamente en Supabase.")
                    time.sleep(1)
                    st.rerun()
                except Exception as e_grades:
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