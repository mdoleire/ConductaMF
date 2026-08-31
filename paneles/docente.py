# paneles/docente.py
import streamlit as st
import pandas as pd
import json
import time
import gspread
from datetime import datetime
from zoneinfo import ZoneInfo
import google.generativeai as genai

from config import FILE_ALUMNOS, FILE_ASIGNACIONES, FILE_REGISTROS, CATALOGO_SANCIONES
from database import leer_datos, leer_todos_los_registros, obtener_lista_alumnos, leer_todas_las_asignaciones
from paneles.analitica import mostrar_tablero_analitico

def renderizar_panel_docente(gc, usuario, nombre_prof):
    st.header(f"🛡️ Panel Docente: {nombre_prof}")
    
    if "form_reset" not in st.session_state:
        st.session_state["form_reset"] = 0
    if "ia_closed_state" not in st.session_state:
        st.session_state["ia_closed_state"] = 0
        
    usuario = str(usuario).lower().strip()
        
    with st.expander("📝 Registro de Incidencia", expanded=True):
        reporte_pasillo = st.checkbox("🚨 ¿Es un reporte de pasillo / fuera de clase?", key=f"pasillo_{st.session_state.form_reset}")
        st.markdown("---")
        
        materia = "Pasillo / Inst. General"
        grupo_final = []
        alumnos_final = ["General (Ver observaciones)"] 
        
        # --- SELECCIÓN DE ALUMNOS (PASILLO O GRUPO CLASE) ---
        if reporte_pasillo:
            c1, c2, c3 = st.columns(3)
            nivel = c1.selectbox("Nivel:", ["Secundaria", "Preparatoria"], key=f"niv_{st.session_state.form_reset}")
            opciones_grados = ["1°", "2°", "3°"] if nivel == "Secundaria" else ["4°", "5°", "6°"]
            
            grados_sel = c2.multiselect("Grado(s):", opciones_grados, key=f"grad_{st.session_state.form_reset}")
            
            grupos_disponibles = []
            df_asig_global = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
            
            if not df_asig_global.empty and 'Grupo' in df_asig_global.columns:
                # Limpieza de espacios invisibles en los grupos
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
                pestañas = st.tabs(grupos_sel) 
                
                for idx, g_sel in enumerate(grupos_sel):
                    with pestañas[idx]:
                        try:
                            # Limpieza del nombre del grupo antes de buscar la pestaña
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
        else:
            df_asig = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
            
            if df_asig.empty or 'Usuario_Profesor' not in df_asig.columns:
                st.warning("⚠️ No se encontró la estructura correcta en el archivo de asignaciones.")
                return
                
            # Limpieza extrema de datos para emparejar correctamente
            df_asig['Usuario_Profesor'] = df_asig['Usuario_Profesor'].astype(str).str.lower().str.strip()
            df_asig['Materia'] = df_asig['Materia'].astype(str).str.strip()
            df_asig['Grupo'] = df_asig['Grupo'].astype(str).str.strip()
            
            mis_asig = df_asig[df_asig['Usuario_Profesor'] == usuario]
            
            if mis_asig.empty: 
                st.warning("Sin materias asignadas para tu usuario actual.")
                return
            
            # --- ✨ NUEVO: SEPARACIÓN DE NIVELES (PREPA / SECUNDARIA) ---
            st.markdown("##### 🏫 Selecciona tu Nivel Escolar")
            niveles_prof = sorted(mis_asig['Nivel'].unique().tolist())
            
            if len(niveles_prof) > 1:
                nivel_elegido = st.radio("Cambiar entre secciones:", niveles_prof, horizontal=True, key=f"nav_niv_{st.session_state.form_reset}")
                mis_asig = mis_asig[mis_asig['Nivel'] == nivel_elegido]
            else:
                st.info(f"Nivel detectado: **{niveles_prof[0]}**")
                
            st.markdown("<br>", unsafe_allow_html=True)
            
            c1, c2 = st.columns(2)
            materia = c1.selectbox("Materia:", mis_asig['Materia'].unique())
            grupo = c2.selectbox("Grupo:", mis_asig[mis_asig['Materia'] == materia]['Grupo'].unique())
            grupo_final = [grupo]
            
            c1, c2 = st.columns(2)
            materia = c1.selectbox("Materia:", mis_asig['Materia'].unique())
            grupo = c2.selectbox("Grupo:", mis_asig[mis_asig['Materia'] == materia]['Grupo'].unique())
            grupo_final = [grupo]
            
            captura_multiple = st.checkbox("Habilitar registro múltiple", key=f"check_mult_{st.session_state.form_reset}")
            
            try:
                # Aseguramos que no haya espacios al enviar el nombre de la pestaña
                opc = obtener_lista_alumnos(gc, FILE_ALUMNOS, grupo.strip())
                if not opc:
                    st.warning(f"La pestaña '{grupo}' no tiene alumnos registrados con el formato correcto.")
            except Exception:
                opc = []
                st.error(f"Falta la pestaña '{grupo}' en el archivo de Alumnos")
            
            if not captura_multiple:
                alumnos_sel_raw = st.selectbox("Alumno:", ["Seleccione..."] + opc, key=f"indiv_{st.session_state.form_reset}")
                alumnos_final = [alumnos_sel_raw] if alumnos_sel_raw != "Seleccione..." else []
            else:
                alumnos_final = st.multiselect("Alumnos:", opc, key=f"grup_{st.session_state.form_reset}")

        st.markdown("---")
        
        # Claves de control de estado dinámico para la IA ligados al ciclo del formulario
        key_cat_recomendada = f"ia_cat_{st.session_state.form_reset}"
        key_fal_recomendada = f"ia_fal_{st.session_state.form_reset}"

        if key_cat_recomendada not in st.session_state:
            st.session_state[key_cat_recomendada] = list(CATALOGO_SANCIONES.keys())[0]
        if key_fal_recomendada not in st.session_state:
            st.session_state[key_fal_recomendada] = None

        # =================================================================
        # 🪄 BOTÓN FLOTANTE (POPOVER) - ASISTENTE DE CLASIFICACIÓN CON IA
        # =================================================================
        popover_key = f"pop_ia_{st.session_state.form_reset}_{st.session_state.ia_closed_state}"
        
        with st.popover("🪄 Usar Asistente de Clasificación (IA)", use_container_width=True, key=popover_key):
            st.markdown("### 🪄 Clasificación Inteligente")
            st.write("Redacta la situación abajo. La IA configurará automáticamente la categoría y falta correspondientes en el formulario de fondo.")
            
            relato_incidencia = st.text_area(
                "Describe lo sucedido con tus propias palabras:",
                placeholder="Ejemplo: El alumno llegó tarde y comenzó a distraer a sus compañeros...",
                key=f"relato_ia_{st.session_state.form_reset}",
                help="Describe detalladamente los hechos y haz clic en Clasificar."
            )

            if st.button("🪄 Clasificar Hechos", type="primary", key=f"btn_ia_{st.session_state.form_reset}"):
                if not relato_incidencia.strip():
                    st.warning("⚠️ Por favor, redacta los hechos antes de solicitar la clasificación.")
                else:
                    try:
                        api_key_gemini = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("gemini_api_key")
                        if not api_key_gemini:
                            for seccion_key in st.secrets.keys():
                                contenido_seccion = st.secrets[seccion_key]
                                if isinstance(contenido_seccion, dict) or hasattr(contenido_seccion, "get"):
                                    api_key_gemini = contenido_seccion.get("GEMINI_API_KEY") or contenido_seccion.get("gemini_api_key")
                                    if api_key_gemini:
                                        break
                        
                        if not api_key_gemini:
                            st.error("🔑 Error: No se localizó la llave 'GEMINI_API_KEY' en la configuración.")
                        else:
                            genai.configure(api_key=api_key_gemini)
                            modelo_gemini = genai.GenerativeModel('gemini-3.5-flash')
                            
                            prompt_sistema = f"""
                            Eres un asistente de disciplina del Colegio Miraflores. Analiza la siguiente descripción de incidencia y clasifícala estrictamente dentro de las opciones de nuestro catálogo oficial.
                            
                            CATÁLOGO DE INCIDENCIAS:
                            {json.dumps(CATALOGO_SANCIONES, ensure_ascii=False, indent=2)}
                            
                            INCIDENCIA REPORTADA:
                            "{relato_incidencia}"
                            
                            INSTRUCCIONES:
                            1. Identifica qué "Categoría" y qué "Falta" específica del catálogo se asocian mejor al relato.
                            2. Debes responder EXCLUSIVAMENTE en formato JSON plano con la siguiente estructura exacta:
                            {{
                                "categoria": "Nombre Exacto de la Categoría",
                                "falta": "Nombre Exacto de la Falta"
                            }}
                            
                            Asegúrate de respetar de forma estricta los acentos, mayúsculas y la ortografía del catálogo oficial provisto. No agregues bloques de código como ```json ni texto adicional.
                            """
                            
                            with st.spinner("🪄 Analizando hechos con Inteligencia Artificial..."):
                                respuesta_api = modelo_gemini.generate_content(
                                    prompt_sistema,
                                    generation_config={"response_mime_type": "application/json"}
                                )
                                
                                datos_clasificados = json.loads(respuesta_api.text.strip())
                                cat_ia = datos_clasificados.get("categoria")
                                fal_ia = datos_clasificados.get("falta")
                                
                                if cat_ia in CATALOGO_SANCIONES:
                                    st.session_state[key_cat_recomendada] = cat_ia
                                    if fal_ia in CATALOGO_SANCIONES[cat_ia]:
                                        st.session_state[key_fal_recomendada] = fal_ia
                                        
                                        # FORZAR ACTUALIZACIÓN INMEDIATA DE LOS SELECTORES DE FONDO
                                        st.session_state[f"cat_{st.session_state.form_reset}"] = cat_ia
                                        
                                        puntos_falta = CATALOGO_SANCIONES[cat_ia][fal_ia]["puntos"]
                                        st.session_state[f"falta_{st.session_state.form_reset}"] = f"{fal_ia} ({puntos_falta} pt)"
                                        
                                        # Auto-actualizamos las observaciones de fondo
                                        st.session_state[f"obs_prefill_{st.session_state.form_reset}"] = relato_incidencia
                                    else:
                                        st.session_state[key_fal_recomendada] = None
                                else:
                                    st.warning("⚠️ La sugerencia de la IA no coincidió exactamente con el catálogo oficial.")
                    
                    except Exception as e:
                        st.error(f"⚠️ El clasificador automático no se encuentra disponible.")
                        st.info(f"Detalle técnico: {e}")

            if st.session_state[key_fal_recomendada]:
                cat_sug = st.session_state[key_cat_recomendada]
                fal_sug = st.session_state[key_fal_recomendada]
                
                st.success(f"✅ ¡Clasificado con éxito! Sugerencia: **{cat_sug}** ➔ **{fal_sug}**.")
                
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("❌ Cerrar Ventana", type="secondary", key=f"close_ia_{st.session_state.form_reset}", use_container_width=True):
                    st.session_state["ia_closed_state"] += 1
                    st.rerun()
        
        # --- MENÚS EN CASCADA DE FALTAS ---
        c_cat, c_fal = st.columns(2)
        
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
            "Redacción final de lo sucedido (Observaciones):", 
            value=redaccion_inicial,
            key=f"obs_{st.session_state.form_reset}"
        )

        # --- PROCESAMIENTO DEL GUARDADO ---
        if st.button("Guardar Registro", type="primary"):
            if reporte_pasillo and not grupo_final:
                st.error("⚠️ Por favor, seleccione al menos un grupo implicado en el reporte de pasillo.")
                st.stop()
            elif not reporte_pasillo and not alumnos_final:
                st.error("⚠️ Por favor, seleccione al menos un alumno.")
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
            st.success("✅ Incidencia registrada exitosamente en la base de datos.")
            time.sleep(1)
            st.rerun()

    st.markdown("---")
    st.subheader("📈 Mi Analítica")
    df_full = leer_todos_los_registros(gc)
    df_doc = df_full[df_full['Profesor'] == nombre_prof] if not df_full.empty else df_full
    mostrar_tablero_analitico(df_doc, "Mis Reportes", modo_descarga=False)
