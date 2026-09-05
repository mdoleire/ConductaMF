# paneles/docente.py
import streamlit as st
import pandas as pd
import json
import time
import gspread
from datetime import datetime
from zoneinfo import ZoneInfo
import google.generativeai as genai

from config import (
    FILE_ALUMNOS, 
    FILE_ASIGNACIONES, 
    FILE_REGISTROS, 
    FILE_ASISTENCIA,
    CATALOGO_SANCIONES, 
    SUPER_USUARIOS_WHITELIST
)
from database import (
    leer_datos, 
    leer_todos_los_registros, 
    obtener_lista_alumnos, 
    obtener_dataframe_alumnos,
    leer_todas_las_asignaciones
)
from paneles.analitica import mostrar_tablero_analitico

st.markdown("""
    <style>
    div[data-baseweb="select"] > div {
        white-space: normal !important;
        word-wrap: break-word !important;
    }
    ul[role="listbox"] li {
        white-space: normal !important;
        word-wrap: break-word !important;
        height: auto !important;
        padding-top: 10px !important;
        padding-bottom: 10px !important;
    }
    </style>
""", unsafe_allow_html=True)

def renderizar_panel_docente(gc, usuario, nombre_prof):
    st.header(f"🛡️ Panel Docente: {nombre_prof}")
    
    if "form_reset" not in st.session_state:
        st.session_state["form_reset"] = 0
    if "ia_closed_state" not in st.session_state:
        st.session_state["ia_closed_state"] = 0
        
    usuario = str(usuario).lower().strip()
    es_superusuario = usuario in SUPER_USUARIOS_WHITELIST
        
    with st.expander("📝 Registro de Incidencia", expanded=True):
        reporte_pasillo = st.checkbox("🚨 ¿Es un reporte de pasillo / fuera de clase?", key=f"pasillo_{st.session_state.form_reset}")
        st.markdown("---")
        
        materia = "Pasillo / Inst. General"
        grupo_final = []
        alumnos_final = ["General (Ver observaciones)"] 
        
        # --- CASO 1: REPORTE DE PASILLO ---
        if reporte_pasillo:
            c1, c2, c3 = st.columns(3)
            nivel = c1.selectbox("Nivel:", ["Secundaria", "Preparatoria"], key=f"niv_{st.session_state.form_reset}")
            opciones_grados = ["1°", "2°", "3°"] if nivel == "Secundaria" else ["4°", "5°", "6°"]
            
            grados_sel = c2.multiselect("Grado(s):", opciones_grados, key=f"grad_{st.session_state.form_reset}")
            
            grupos_disponibles = []
            df_asig_global = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
            
            if not df_asig_global.empty and 'Grupo' in df_asig_global.columns:
                df_asig_global['Grupo'] = df_asig_global['Grupo'].astype(str).str.strip()
                todos_los_grupos = df_asig_global['Grupo'].dropna().unique().tolist()
                
                if grados_sel:
                    for grad_individual in grados_sel:
                        numero_grado = grad_individual.replace("°", "") 
                        grupos_del_grado = [g for g in todos_los_grupos if g.startswith(f"{numero_grado}°")]
                        grupos_disponibles.extend(grupos_del_grado)
                    grupos_disponibles = sorted(list(set(grupos_disponibles)))
            else:
                if grados_sel:
                    for grad_individual in grados_sel:
                        grupos_disponibles.extend([f"{grad_individual}A", f"{grad_individual}B"])
                    grupos_disponibles = sorted(grupos_disponibles)
            
            grupos_sel = c3.multiselect("Grupo(s) implicado(s):", grupos_disponibles, key=f"grups_p_{st.session_state.form_reset}")
            grupo_final = grupos_sel
            
            alumnos_por_grupo_seleccionados = []
            if grupos_sel:
                st.markdown("**Selecciona a los alumnos involucrados por salón:**")
                pestanas = st.tabs(grupos_sel) 
                
                for idx, g_sel in enumerate(grupos_sel):
                    with pestanas[idx]:
                        try:
                            lista_grupo = obtener_lista_alumnos(gc, FILE_ALUMNOS, g_sel.strip())
                            if lista_grupo:
                                sel_alumnos = st.multiselect(
                                    f"Implicados de {g_sel}:", 
                                    lista_grupo, 
                                    key=f"al_{g_sel}_{st.session_state.form_reset}"
                                )
                                if sel_alumnos:
                                    for nombre in sel_alumnos:
                                        alumnos_por_grupo_seleccionados.append((g_sel, nombre))
                            else:
                                st.warning(f"⚠️ No hay alumnos listos en {g_sel}")
                        except Exception:
                            st.warning(f"⚠️ No se encontró la base de datos para {g_sel}")
                
                if alumnos_por_grupo_seleccionados:
                    alumnos_final = [nombre for _, nombre in alumnos_por_grupo_seleccionados]

        # --- CASO 2: REPORTE EN CLASE ---
        else:
            df_asig = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
            
            if df_asig.empty or 'Usuario_Profesor' not in df_asig.columns:
                st.warning("⚠️ No se encontró la estructura correcta en el archivo de asignaciones.")
                return
                
            df_asig['Usuario_Profesor'] = df_asig['Usuario_Profesor'].astype(str).str.lower().str.strip()
            df_asig['Materia'] = df_asig['Materia'].astype(str).str.strip()
            df_asig['Grupo'] = df_asig['Grupo'].astype(str).str.strip()
            
            if es_superusuario:
                mis_asig = df_asig.copy()
                st.info("👑 Modo Super Usuario: Acceso completo a grupos y materias.")
            else:
                mis_asig = df_asig[df_asig['Usuario_Profesor'] == usuario]
            
            if mis_asig.empty: 
                st.warning("Sin materias asignadas para tu usuario actual.")
                return            

            # Separación de Niveles
            niveles_prof = sorted(mis_asig['Nivel'].unique().tolist())
            if len(niveles_prof) > 1:
                nivel_elegido = st.radio("Sección:", niveles_prof, horizontal=True, key=f"nav_niv_{st.session_state.form_reset}")
                mis_asig = mis_asig[mis_asig['Nivel'] == nivel_elegido]

            # FILTRO POR DÍA EN CURSO (CON DESBLOQUEO MANUAL)
            hoy_cdmx = datetime.now(ZoneInfo("America/Mexico_City"))
            dia_semana_map = {0: "Lunes", 1: "Martes", 2: "Miercoles", 3: "Jueves", 4: "Viernes"}
            nombre_dia_hoy = dia_semana_map.get(hoy_cdmx.weekday(), "Fin de semana")

            ver_todas = st.toggle("🔓 Mostrar todas las materias (Fuera del horario de hoy)", key=f"tog_mat_{st.session_state.form_reset}")
            
            mis_asig_filtradas = mis_asig.copy()
            if not ver_todas and not es_superusuario and hoy_cdmx.weekday() in dia_semana_map:
                try:
                    df_conf = leer_datos(gc, FILE_ASISTENCIA, "Configuracion")
                    if not df_conf.empty and 'Clase' in df_conf.columns and nombre_dia_hoy in df_conf.columns:
                        clases_hoy = df_conf[pd.to_numeric(df_conf[nombre_dia_hoy], errors='coerce').fillna(0) > 0]['Clase'].tolist()
                        materias_validas = []
                        for _, r in mis_asig.iterrows():
                            tag = f"{r['Materia']} - {r['Grupo']}"
                            if tag in clases_hoy or tag not in df_conf['Clase'].values:
                                materias_validas.append(r['Materia'])
                        if materias_validas:
                            mis_asig_filtradas = mis_asig[mis_asig['Materia'].isin(materias_validas)]
                except Exception:
                    pass
                       
            c1, c2 = st.columns(2)
            materia = c1.selectbox("Materia:", mis_asig_filtradas['Materia'].unique(), key=f"mat_select_{st.session_state.form_reset}")
            grupo = c2.selectbox("Grupo:", mis_asig_filtradas[mis_asig_filtradas['Materia'] == materia]['Grupo'].unique(), key=f"grup_select_{st.session_state.form_reset}")
            grupo_final = [grupo]
            
            captura_multiple = st.checkbox("Habilitar registro múltiple", key=f"check_mult_{st.session_state.form_reset}")
            
            try:
                grupo_base = grupo.split("(")[0].strip()
                df_alumnos_crudo = obtener_dataframe_alumnos(gc, FILE_ALUMNOS, grupo_base)
                
                # Filtrado por Áreas (Preparatoria)
                if df_alumnos_crudo is not None and not df_alumnos_crudo.empty:
                    if 'Área' in df_alumnos_crudo.columns:
                        texto_busqueda = f"{materia} {grupo}".upper()
                        
                        if "ÁREA 1" in texto_busqueda or "ÁREA I " in texto_busqueda or "ÁREA I)" in texto_busqueda:
                            df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo['Área'] == 'Área 1']
                        elif "ÁREA 2" in texto_busqueda or "ÁREA II" in texto_busqueda:
                            df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo['Área'] == 'Área 2']
                        elif "ÁREA 3" in texto_busqueda or "ÁREA III" in texto_busqueda:
                            df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo['Área'] == 'Área 3']
                        elif "ÁREA 4" in texto_busqueda or "ÁREA IV" in texto_busqueda:
                            df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo['Área'] == 'Área 4']
                    
                    nombres = df_alumnos_crudo['Nombre Completo'].replace('', pd.NA).dropna()
                    opc = sorted(nombres.unique().tolist())
                else:
                    opc = []
                    
                if not opc:
                    st.warning(f"La pestaña '{grupo_base}' no tiene alumnos registrados para esta especialidad.")
            except Exception as e:
                opc = []
                st.error(f"Falta la pestaña '{grupo_base}' en el archivo de Alumnos: {e}")
            
            if not captura_multiple:
                alumnos_sel_raw = st.selectbox("Alumno:", ["Seleccione..."] + opc, key=f"indiv_{st.session_state.form_reset}")
                alumnos_final = [alumnos_sel_raw] if alumnos_sel_raw != "Seleccione..." else []
            else:
                alumnos_final = st.multiselect("Alumnos:", opc, key=f"grup_{st.session_state.form_reset}")

        st.markdown("---")
        
        key_cat_recomendada = f"ia_cat_{st.session_state.form_reset}"
        key_fal_recomendada = f"ia_fal_{st.session_state.form_reset}"

        if key_cat_recomendada not in st.session_state:
            st.session_state[key_cat_recomendada] = list(CATALOGO_SANCIONES.keys())[0]
        if key_fal_recomendada not in st.session_state:
            st.session_state[key_fal_recomendada] = None

        # =================================================================
        # ASISTENTE DE CLASIFICACIÓN CON IA (GEMINI BLINDADO)
        # =================================================================
        popover_key = f"pop_ia_{st.session_state.form_reset}_{st.session_state.ia_closed_state}"
        
        with st.popover("🪄 Usar Asistente de Clasificación (IA)", use_container_width=True, key=popover_key):
            st.markdown("### 🪄 Clasificación Inteligente")
            st.caption("Escribe los hechos ocurridos. La IA seleccionará la categoría y falta correspondientes en el formulario.")
            
            relato_incidencia = st.text_area(
                "Descripción de los hechos:",
                placeholder="Ejemplo: El alumno utilizó el celular durante la explicación y no atendió las indicaciones...",
                key=f"relato_ia_{st.session_state.form_reset}"
            )

            if st.button("🪄 Clasificar Hechos", type="primary", key=f"btn_ia_{st.session_state.form_reset}"):
                if not relato_incidencia.strip():
                    st.warning("⚠️ Redacta los hechos antes de solicitar la clasificación.")
                else:
                    try:
                        api_key_gemini = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("gemini_api_key")
                        if not api_key_gemini:
                            for k in st.secrets.keys():
                                sec = st.secrets[k]
                                if isinstance(sec, dict):
                                    api_key_gemini = sec.get("GEMINI_API_KEY") or sec.get("gemini_api_key")
                                    if api_key_gemini: break
                        
                        if not api_key_gemini:
                            st.error("🔑 Llave de API no configurada en los secretos de la aplicación.")
                        else:
                            genai.configure(api_key=api_key_gemini)
                            
                            instrucciones_ia = f"""
                            Eres un asistente de disciplina escolar del Colegio Miraflores.
                            Tu función es clasificar estrictamente el relato dentro de las opciones de este catálogo oficial:
                            {json.dumps(CATALOGO_SANCIONES, ensure_ascii=False, indent=2)}

                            Reglas obligatorias:
                            1. Devuelve ÚNICA Y EXCLUSIVAMENTE un JSON plano con estas claves exactas:
                            {{"categoria": "Nombre de la Categoría", "falta": "Nombre de la Falta"}}
                            2. Respeta con exactitud las mayúsculas, acentos y signos del catálogo.
                            """
                            
                            modelo = genai.GenerativeModel(
                                model_name='gemini-3.6-flash',
                                system_instruction=instrucciones_ia,
                                generation_config={"response_mime_type": "application/json"}
                            )
                            
                            with st.spinner("Analizando hechos con IA..."):
                                respuesta_api = modelo.generate_content(relato_incidencia)
                                datos_clasificados = json.loads(respuesta_api.text.strip())
                                
                                cat_ia = datos_clasificados.get("categoria")
                                fal_ia = datos_clasificados.get("falta")
                                
                                if cat_ia in CATALOGO_SANCIONES and fal_ia in CATALOGO_SANCIONES[cat_ia]:
                                    st.session_state[key_cat_recomendada] = cat_ia
                                    st.session_state[key_fal_recomendada] = fal_ia
                                    st.session_state[f"cat_{st.session_state.form_reset}"] = cat_ia
                                    
                                    puntos_falta = CATALOGO_SANCIONES[cat_ia][fal_ia]["puntos"]
                                    st.session_state[f"falta_{st.session_state.form_reset}"] = f"{fal_ia} ({puntos_falta} pt)"
                                    st.session_state[f"obs_prefill_{st.session_state.form_reset}"] = relato_incidencia
                                else:
                                    st.warning("⚠️ La falta sugerida no coincidió exactamente con el catálogo oficial.")
                    
                    except Exception as e:
                        st.error(f"⚠️ El clasificador no está disponible temporalmente: {e}")

            if st.session_state[key_fal_recomendada]:
                cat_sug = st.session_state[key_cat_recomendada]
                fal_sug = st.session_state[key_fal_recomendada]
                st.success(f"✅ Sugerencia: **{cat_sug}** ➔ **{fal_sug}**.")
                
                if st.button("Cerrar Ventana", type="secondary", key=f"close_ia_{st.session_state.form_reset}", use_container_width=True):
                    st.session_state["ia_closed_state"] += 1
                    st.rerun()
        
        # --- MENÚS DE SELECCIÓN DE FALTA ---
        c_cat, c_fal = st.columns([1, 2])
        lista_categorias = list(CATALOGO_SANCIONES.keys())
        try:
            indice_categoria_defecto = lista_categorias.index(st.session_state[key_cat_recomendada])
        except ValueError:
            indice_categoria_defecto = 0
            
        with c_cat:
            categoria = st.selectbox(
                "Categoría:", 
                lista_categorias, 
                index=indice_categoria_defecto, 
                key=f"cat_{st.session_state.form_reset}"
            )
            
        dict_faltas = CATALOGO_SANCIONES[categoria]
        opciones_visuales = [f"{nombre} ({datos['puntos']} pt)" for nombre, datos in dict_faltas.items()]
        
        indice_falta_defecto = 0
        if st.session_state[key_fal_recomendada]:
            for index_opcion, texto_opcion in enumerate(opciones_visuales):
                if texto_opcion.startswith(st.session_state[key_fal_recomendada]):
                    indice_falta_defecto = index_opcion
                    break
                    
        with c_fal:
            falta_seleccionada_visual = st.selectbox(
                "Falta cometida:", 
                opciones_visuales, 
                index=indice_falta_defecto, 
                key=f"falta_{st.session_state.form_reset}"
            )
            
        falta_original = falta_seleccionada_visual.split(" (")[0]
        redaccion_inicial = st.session_state.get(f"obs_prefill_{st.session_state.form_reset}", "")
        
        obs = st.text_area(
            "Observaciones y detalles de lo ocurrido:", 
            value=redaccion_inicial,
            key=f"obs_{st.session_state.form_reset}"
        )

        # --- GUARDADO EN BASE DE DATOS ---
        if st.button("💾 Guardar Registro", type="primary"):
            if reporte_pasillo and not grupo_final:
                st.error("⚠️ Selecciona al menos un grupo implicado en el reporte.")
                st.stop()
            elif not reporte_pasillo and not alumnos_final:
                st.error("⚠️ Selecciona al menos un alumno.")
                st.stop()
                
            info_falta = dict_faltas.get(falta_original)
            p = info_falta["puntos"] if info_falta else 0
            s = info_falta["semaforo"] if info_falta else "Gris"
            
            f = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d %H:%M:%S")
            lote = []
            
            if reporte_pasillo:
                if alumnos_por_grupo_seleccionados:
                    for g_real, al_limpio in alumnos_por_grupo_seleccionados:
                        lote.append([f, nombre_prof, materia, g_real, al_limpio, categoria, falta_original, obs, p, s])
                else:
                    for g in grupo_final:
                        lote.append([f, nombre_prof, materia, g, "General (Ver observaciones)", categoria, falta_original, obs, p, s])
            else:
                for g in grupo_final:
                    for al in alumnos_final:
                        lote.append([f, nombre_prof, materia, g, al, categoria, falta_original, obs, p, s])
            
            doc = gc.open(FILE_REGISTROS)
            clase_id = "Reportes_Pasillo" if reporte_pasillo else f"{materia} - {grupo_final[0]}"
            
            try:
                ws = doc.worksheet(clase_id)
            except gspread.exceptions.WorksheetNotFound:
                ws = doc.add_worksheet(title=clase_id, rows="1000", cols="10")
                ws.append_row(["Fecha", "Profesor", "Materia", "Grupo", "Alumno", "Categoría", "Falta", "Observaciones", "Puntos_Descontados", "Es_Grave"])
            
            ws.append_rows(lote)
            leer_todos_los_registros.clear()
            
            st.session_state.form_reset += 1
            st.success("✅ Incidencia guardada con éxito en la base de datos.")
            time.sleep(1)
            st.rerun()

    st.markdown("---")
    st.subheader("📈 Analítica de Conducta")
    df_full = leer_todos_los_registros(gc)
    
    if es_superusuario:
        df_doc = df_full
        titulo_tablero = "Reportes Globales Institucionales"
    else:
        df_doc = df_full[df_full['Profesor'] == nombre_prof] if not df_full.empty else df_full
        titulo_tablero = "Mis Reportes Docentes"
        
    mostrar_tablero_analitico(df_doc, titulo_tablero, modo_descarga=True)