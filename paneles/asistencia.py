# paneles/asistencia.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time
import logging

from config import (
    FILE_ASIGNACIONES, 
    FILE_ALUMNOS, 
    FILE_ASISTENCIA, 
    SUPER_USUARIOS_WHITELIST, 
    PERIODOS_LECTIVOS
)
from database import (
    leer_datos, 
    obtener_lista_alumnos, 
    obtener_dataframe_alumnos, 
    leer_todas_las_asignaciones,
    obtener_conexion_sql
)

def renderizar_panel_asistencia(gc, usuario, nombre_prof):
    
    def obtener_materia_teorica(nombre_materia):
        diccionario_fusion = {
            "lab física": "Física",
            "laboratorio de química": "Química", 
            "lab química": "Química",
            "laboratorio de biología": "Biología 1", 
            "lab biología": "Biología 1",
            "laboratorio de física iii": "Física III", 
            "lab física iii": "Física III",
            "laboratorio de química iii": "Química III", 
            "lab química iii": "Química III",
            "laboratorio de biología iv": "Biología IV", 
            "lab biología iv": "Biología IV",
            "laboratorio de lab física iv a i": "Física IV A I", 
            "lab física iv a i": "Física IV A I",
            "laboratorio de lab física iv a ii": "Física IV A II", 
            "lab física iv a ii": "Física IV A II",
            "laboratorio de lab química iv a i": "Química IV A I", 
            "lab química iv a i": "Química IV A I",
            "laboratorio de lab química iv a ii": "Química IV A II", 
            "lab química iv a ii": "Química IV A II"
        }
        limpio = str(nombre_materia).lower().strip().replace("  ", " ")
        return diccionario_fusion.get(limpio, str(nombre_materia).strip())

    st.header("📅 Gestión de Asistencia")
    
    if "modo_edicion_horario" not in st.session_state:
        st.session_state.modo_edicion_horario = False
        
    usuario = str(usuario).lower().strip()
    es_superusuario = usuario in SUPER_USUARIOS_WHITELIST
    
    hoy_cdmx = datetime.now(ZoneInfo("America/Mexico_City"))
    dia_num_hoy = hoy_cdmx.weekday()
    dias_espanol = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    nombre_dia_hoy = dias_espanol.get(dia_num_hoy)
    # 🛡️ Las columnas de asistencia_config van sin acento ("Miercoles")
    columna_dia_hoy = {0: "Lunes", 1: "Martes", 2: "Miercoles", 3: "Jueves", 4: "Viernes"}.get(dia_num_hoy)

    MODO_PASAR = "📝 Pasar Lista del Día"
    MODO_PENDIENTES = "🗓️ Días sin Lista"
    MODO_HISTORICO = "📊 Vista Histórica del Grupo (Modificar Asistencia)"

    def ir_a_pendientes():
        st.session_state["modo_asist"] = MODO_PENDIENTES

    modo_vista = st.radio(
        "Acción:",
        [MODO_PASAR, MODO_PENDIENTES, MODO_HISTORICO],
        horizontal=True,
        key="modo_asist"
    )
    st.markdown("---")

    habilitar_historico = False
    if modo_vista == MODO_PASAR:
        habilitar_historico = st.toggle("🔓 Modificar asistencia de días anteriores (Mostrar todas las materias)")

    if modo_vista == "📝 Pasar Lista del Día" and not habilitar_historico:
        if dia_num_hoy in [5, 6]:
            st.warning(f"☕ **Hoy es {nombre_dia_hoy}. No hay clases programadas en fin de semana.**")
            st.info("💡 Para revisar o modificar inasistencias de días anteriores, activa el interruptor de arriba.")
            return  

    df_asig = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
    if df_asig.empty or 'Usuario_Profesor' not in df_asig.columns:
        st.warning("⚠️ No se encontró la estructura correcta en el archivo de asignaciones.")
        return
        
    df_asig['Usuario_Profesor'] = df_asig['Usuario_Profesor'].astype(str).str.lower().str.strip()
    df_asig['Materia'] = df_asig['Materia'].astype(str).str.strip()
    df_asig['Grupo'] = df_asig['Grupo'].astype(str).str.strip()
    
    if es_superusuario:
        mis_asig = df_asig.copy()
    else:
        mis_asig = df_asig[df_asig['Usuario_Profesor'] == usuario]
    
    if mis_asig.empty:
        st.warning("Sin materias asignadas para pasar lista.")
        return

    niveles_prof = sorted(mis_asig['Nivel'].unique().tolist())
    if len(niveles_prof) > 1:
        nivel_elegido = st.radio("🏫 Nivel Escolar:", niveles_prof, horizontal=True)
        mis_asig = mis_asig[mis_asig['Nivel'] == nivel_elegido]
    elif len(niveles_prof) == 1:
        nivel_elegido = niveles_prof[0]
    else:
        nivel_elegido = "Preparatoria"

    try:
        df_config = leer_datos(gc, FILE_ASISTENCIA, "Configuracion")
    except Exception:
        df_config = pd.DataFrame(columns=["Clase", "Lunes", "Martes", "Miercoles", "Jueves", "Viernes"])

    materias_filtradas = mis_asig.copy()

    if modo_vista == "📝 Pasar Lista del Día" and not habilitar_historico and not es_superusuario:
        if not df_config.empty and 'Clase' in df_config.columns and columna_dia_hoy in df_config.columns:
            clases_hoy = df_config[pd.to_numeric(df_config[columna_dia_hoy], errors='coerce').fillna(0) > 0]['Clase'].tolist()
            materias_hoy = []
            for _, r in mis_asig.iterrows():
                mat_base = obtener_materia_teorica(r['Materia'])
                tag = f"{mat_base} - {r['Grupo']}"
                
                if tag in clases_hoy or tag not in df_config['Clase'].values:
                    materias_hoy.append(r['Materia'])
            
            if materias_hoy:
                materias_filtradas = mis_asig[mis_asig['Materia'].isin(materias_hoy)]
            else:
                st.success(f"☕ **Hoy {nombre_dia_hoy} no tienes ninguna clase asignada en tu horario.**")
                st.info("💡 Activa el interruptor arriba para modificar días anteriores.")
                return

    c1, c2, c3 = st.columns([3, 3, 2])
    materia_seleccionada = c1.selectbox("Materia:", materias_filtradas['Materia'].unique(), key="asist_mat")
    materia = obtener_materia_teorica(materia_seleccionada)
    grupo = c2.selectbox("Grupo:", materias_filtradas[materias_filtradas['Materia'] == materia_seleccionada]['Grupo'].unique(), key="asist_grup")
    
    with c3:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if not st.session_state.modo_edicion_horario:
            if st.button("⚙️ Modificar horario", use_container_width=True):
                st.session_state.modo_edicion_horario = True
                st.rerun()

    try:
        grupo_limpio = grupo.split("(")[0].strip()
        df_alumnos_crudo = obtener_dataframe_alumnos(gc, FILE_ALUMNOS, grupo_limpio)
        
        if df_alumnos_crudo is not None and not df_alumnos_crudo.empty:
            col_area = 'area_academica' if 'area_academica' in df_alumnos_crudo.columns else ('Área' if 'Área' in df_alumnos_crudo.columns else None)
            if col_area:
                texto_busqueda = f"{materia} {grupo}".upper()
                if "ÁREA 1" in texto_busqueda or "ÁREA I" in texto_busqueda:
                    df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo[col_area].astype(str).str.upper().str.contains('1|I|CIENCIAS', na=False)]
                elif "ÁREA 2" in texto_busqueda or "ÁREA II" in texto_busqueda:
                    df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo[col_area].astype(str).str.upper().str.contains('2|II', na=False)]
                elif "ÁREA 3" in texto_busqueda or "ÁREA III" in texto_busqueda:
                    df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo[col_area].astype(str).str.upper().str.contains('3|III|HUMANIDADES', na=False)]
                elif "ÁREA 4" in texto_busqueda or "ÁREA IV" in texto_busqueda:
                    df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo[col_area].astype(str).str.upper().str.contains('4|IV', na=False)]
            if 'Nombre Completo' in df_alumnos_crudo.columns:
                nombres = df_alumnos_crudo['Nombre Completo'].replace(r'^nan nan nan$|^nan$|^$', pd.NA, regex=True).dropna()
                alumnos = sorted(nombres.unique().tolist())
            else:
                alumnos = obtener_lista_alumnos(gc, FILE_ALUMNOS, grupo_limpio)
        else:
            alumnos = []
    except Exception as e:
        alumnos = []
        st.error(f"Error al obtener alumnos: {e}")
        
    if not alumnos:
        st.warning(f"No se encontraron alumnos registrados para el grupo '{grupo_limpio}'.")
        return

    nombre_pestana = f"{materia} - {grupo}"
    config_actual = pd.DataFrame()
    if not df_config.empty and 'Clase' in df_config.columns:
        config_actual = df_config[df_config['Clase'] == nombre_pestana]

    v_lun, v_mar, v_mie, v_jue, v_vie = 0, 0, 0, 0, 0
    if not config_actual.empty:
        v_lun = int(config_actual.iloc[0].get('Lunes', 0))
        v_mar = int(config_actual.iloc[0].get('Martes', 0))
        v_mie = int(config_actual.iloc[0].get('Miercoles', 0))
        v_jue = int(config_actual.iloc[0].get('Jueves', 0))
        v_vie = int(config_actual.iloc[0].get('Viernes', 0))

    if config_actual.empty:
        st.info(f"⚙️ Configuración requerida para {nombre_pestana}")
        mostrar_formulario = True
        detener_app = True
    else:
        mostrar_formulario = st.session_state.modo_edicion_horario
        detener_app = False

    if mostrar_formulario:
        with st.container():
            if not config_actual.empty:
                _, c_cerrar = st.columns([8, 2])
                with c_cerrar:
                    if st.button("❌ Cerrar", use_container_width=True):
                        st.session_state.modo_edicion_horario = False
                        st.rerun()

            with st.form(f"form_horario_{nombre_pestana}"):
                st.write("Horas de clase por día (0 = Sin clase, 1 = Sencilla, 2 = Doble):")
                c_lun, c_mar, c_mie, c_jue, c_vie = st.columns(5)
                h_lun = c_lun.number_input("Lunes", 0, 4, v_lun)
                h_mar = c_mar.number_input("Martes", 0, 4, v_mar)
                h_mie = c_mie.number_input("Miérc.", 0, 4, v_mie)
                h_jue = c_jue.number_input("Jueves", 0, 4, v_jue)
                h_vie = c_vie.number_input("Viernes", 0, 4, v_vie)

                if st.form_submit_button("💾 Guardar Horario", type="primary"):
                    if sum([h_lun, h_mar, h_mie, h_jue, h_vie]) == 0:
                        st.error("⚠️ Asigna al menos 1 hora de clase a la semana.")
                    else:
                        conn = obtener_conexion_sql()
                        try:
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM [asistencia_config] WHERE [Clase] = ?", (nombre_pestana,))
                            # 🛡️ Columnas entre corchetes (el wrapper las convierte en "Clase", "Lunes"...).
                            # Sin comillas, Postgres las pasaba a minúsculas y el INSERT fallaba.
                            cursor.execute(
                                "INSERT INTO [asistencia_config] ([Clase], [Lunes], [Martes], [Miercoles], [Jueves], [Viernes]) VALUES (?, ?, ?, ?, ?, ?)",
                                (nombre_pestana, int(h_lun), int(h_mar), int(h_mie), int(h_jue), int(h_vie))
                            )
                            conn.commit()
                            st.session_state.modo_edicion_horario = False
                            leer_datos.clear()
                            st.success("✅ Horario actualizado correctamente en la base de datos.")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e_h:
                            conn.rollback()
                            logging.exception(e_h)
                            st.error("🚨 No se pudo guardar el horario. Intenta de nuevo.")
                        finally:
                            conn.close()
    if detener_app:
        return

    dias_semana_clase = sum([v_lun, v_mar, v_mie, v_jue, v_vie])
    horario_clase = {0: v_lun, 1: v_mar, 2: v_mie, 3: v_jue, 4: v_vie, 5: 0, 6: 0}

    # ========================================================
    # 🛡️ LÓGICA DE DETECCIÓN AUTOMÁTICA DE PERIODO
    # ========================================================
    st.markdown("---")
    
    nivel_key = "Secundaria" if "secundaria" in nivel_elegido.lower() else "Preparatoria"
    periodos_nivel = PERIODOS_LECTIVOS.get(nivel_key, [])
    
    periodo_actual_nombre = "1° Periodo"
    idx_periodo = 0
    fecha_evaluacion = hoy_cdmx.date()

    if periodos_nivel:
        for i, p in enumerate(periodos_nivel):
            fin_periodo = datetime.strptime(p["fin"], "%Y-%m-%d").date()
            if fecha_evaluacion <= fin_periodo:
                periodo_actual_nombre = p["nombre"]
                idx_periodo = i
                break
        else:
            periodo_actual_nombre = periodos_nivel[-1]["nombre"]
            idx_periodo = len(periodos_nivel) - 1

    if "secundaria" in nivel_elegido.lower():
        opciones_asistencia = ["✅ Presente", "🔴 Falta"]
        opciones_hist = ["✅ Presente", "🔴 Falta", "⚪ Sin Clase", ""]
        limites_tabla = {1: [2, 2, 3], 2: [3, 4, 5], 3: [5, 6, 7], 4: [6, 8, 10], 5: [8, 10, 12]}
    else:
        opciones_asistencia = ["✅ Presente", "🟡 Retardo", "🔴 Falta"]
        opciones_hist = ["✅ Presente", "🟡 Retardo", "🔴 Falta", "⚪ Sin Clase", ""]
        limites_tabla = {1: [2, 2, 2, 2, 2], 2: [4, 3, 4, 4, 4], 3: [5, 5, 4, 5, 5], 4: [7, 7, 6, 7, 7], 5: [9, 9, 7, 9, 9]}

    limites_fila = limites_tabla.get(dias_semana_clase, [99, 99, 99, 99, 99])
    limite_faltas = limites_fila[idx_periodo] if idx_periodo < len(limites_fila) else limites_fila[-1]

    # Cargar datos de la clase actual
    try:
        df_historial = leer_datos(gc, FILE_ASISTENCIA, nombre_pestana)
    except Exception:
        df_historial = pd.DataFrame()

    if df_historial.empty or 'Alumno' not in df_historial.columns:
        df_historial = pd.DataFrame({"Alumno": alumnos})

    def clave_orden_fecha(col_nombre):
        try:
            f_limpia = col_nombre.split(" (")[0].strip()
            dt = datetime.strptime(f_limpia, "%d-%m-%Y")
            prioridad = 1 if "(S1)" in col_nombre else (2 if "(S2)" in col_nombre else 0)
            return (dt, prioridad)
        except Exception:
            return (datetime.min, 0)

    columnas_fechas = [c for c in df_historial.columns if c != 'Alumno']
    columnas_fechas.sort(key=clave_orden_fecha)
    
    peso_fechas = {}
    for col_f in columnas_fechas:
        if "(S1)" in col_f or "(S2)" in col_f:
            peso_fechas[col_f] = 1
        else:
            try:
                fecha_limpia = col_f.split(" (")[0]
                d_sem = datetime.strptime(fecha_limpia, "%d-%m-%Y").weekday()
                peso_fechas[col_f] = horario_clase.get(d_sem, 1) or 1
            except Exception:
                peso_fechas[col_f] = 1

    # 3. Inicialización y cálculo de faltas por alumno (RESETEO POR PERIODO)
    faltas_dict = {}
    retardos_dict = {}
    faltas_efectivas_dict = {}
    derecho_examen_dict = {}
    
    inicio_p_actual = datetime.strptime(periodos_nivel[idx_periodo]["inicio"], "%Y-%m-%d").date()
    fin_p_actual = datetime.strptime(periodos_nivel[idx_periodo]["fin"], "%Y-%m-%d").date()

    for al in alumnos:
        if al in df_historial['Alumno'].values:
            fila_al = df_historial[df_historial['Alumno'] == al].iloc[0]
            
            f_real = 0
            r_real = 0
            
            for col_fecha in columnas_fechas:
                try:
                    fecha_limpia = col_fecha.split(" (")[0]
                    fecha_col_dt = datetime.strptime(fecha_limpia, "%d-%m-%Y").date()
                    
                    if inicio_p_actual <= fecha_col_dt <= fin_p_actual:
                        estatus_celda = str(fila_al[col_fecha])
                        if estatus_celda == '🔴 Falta':
                            f_real += 1
                        elif estatus_celda == '🟡 Retardo':
                            r_real += 1
                except Exception:
                    pass 
            
            f_efec = f_real + (r_real // 3)
            
            faltas_dict[al] = f_real
            retardos_dict[al] = r_real
            faltas_efectivas_dict[al] = f_efec
            
            if f_efec > limite_faltas:
                derecho_examen_dict[al] = "❌ SIN DERECHO"
            elif f_efec == limite_faltas:
                derecho_examen_dict[al] = "🚨 LÍMITE ALCANZADO"
            elif f_efec == (limite_faltas - 1) and limite_faltas > 1:
                derecho_examen_dict[al] = "⚠️ EN RIESGO (-1 falta)"
            else:
                derecho_examen_dict[al] = "✅ SÍ"
        else:
            faltas_dict[al], retardos_dict[al], faltas_efectivas_dict[al] = 0, 0, 0
            derecho_examen_dict[al] = "✅ SÍ"

    # =================================================================
    # 🗓️ DÍAS CON CLASE SIN LISTA (CALENDARIO VS ASISTENCIA)
    # =================================================================
    def calcular_dias_sin_lista(desde):
        """Días con clase según el horario, desde `desde` hasta AYER, sin ningún registro
        (ni lista ni motivo). Hoy no cuenta: se atiende en "Pasar Lista del Día"."""
        registradas = {c.split(" (")[0].strip() for c in columnas_fechas}
        pendientes = []
        curr = desde
        while curr < hoy_cdmx.date():
            if horario_clase.get(curr.weekday(), 0) > 0:
                f_str = curr.strftime("%d-%m-%Y")
                if f_str not in registradas:
                    pendientes.append(f_str)
            curr += timedelta(days=1)
        return pendientes

    def guardar_columnas(registros):
        """registros = {columna_fecha: {alumno: estatus}}. Reemplaza esas fechas en una sola transacción."""
        conn = obtener_conexion_sql()
        try:
            cursor = conn.cursor()
            for col_f, por_alumno in registros.items():
                cursor.execute("DELETE FROM [asistencia_registros] WHERE [Clase] = ? AND [Fecha] = ?", (nombre_pestana, col_f))
                lote = [(nombre_pestana, al, col_f, est) for al, est in por_alumno.items()]
                if lote:
                    cursor.executemany('INSERT INTO [asistencia_registros] ("Clase", "Alumno", "Fecha", "Estatus") VALUES (?, ?, ?, ?)', lote)
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logging.exception(e)
            st.error("🚨 No se pudo guardar. Intenta de nuevo.")
            return False
        finally:
            conn.close()

    def etiqueta_dia(f_str):
        return f"{dias_espanol[datetime.strptime(f_str, '%d-%m-%Y').weekday()]} {f_str}"

    inicio_p_dt = datetime.strptime(periodos_nivel[idx_periodo]["inicio"], "%Y-%m-%d").date()
    fechas_pendientes = calcular_dias_sin_lista(inicio_p_dt)

    # =================================================================
    # MODO: DÍAS SIN LISTA (REGISTRAR MOTIVO O LA LISTA OLVIDADA)
    # =================================================================
    if modo_vista == MODO_PENDIENTES:
        st.markdown(f"### 🗓️ Días sin lista: {materia} - {grupo}")
        st.caption("Días en los que tu horario marca clase de esta materia y todavía no hay lista ni motivo registrado (hasta ayer).")

        incluir_anteriores = st.checkbox("Incluir periodos anteriores del ciclo", key=f"pend_ant_{nombre_pestana}")
        if incluir_anteriores:
            st.caption("⚠️ Registrar faltas en un periodo ya cerrado puede cambiar el derecho a examen de ese periodo.")
            desde = datetime.strptime(periodos_nivel[0]["inicio"], "%Y-%m-%d").date()
        else:
            desde = inicio_p_dt
        pendientes = calcular_dias_sin_lista(desde)

        if not pendientes:
            st.success("🎉 No tienes días pendientes en esta materia.")
            return

        st.warning(f"Tienes **{len(pendientes)}** día(s) pendiente(s).")
        tabla_pend = pd.DataFrame({
            "Fecha": pendientes,
            "Día": [dias_espanol[datetime.strptime(f, "%d-%m-%Y").weekday()] for f in pendientes],
            "Horas de clase": [horario_clase.get(datetime.strptime(f, "%d-%m-%Y").weekday(), 0) for f in pendientes],
        })
        alto_tabla = {"height": 280} if len(pendientes) > 7 else {}
        st.dataframe(tabla_pend, hide_index=True, use_container_width=True, **alto_tabla)

        fecha_sel = st.selectbox("📅 Día a resolver:", pendientes, format_func=etiqueta_dia, key=f"pend_fecha_{nombre_pestana}")
        horas_dia = horario_clase.get(datetime.strptime(fecha_sel, "%d-%m-%Y").weekday(), 1)
        sufijo_key = f"{nombre_pestana}_{fecha_sel}"

        OPC_CLASE = "✅ Sí hubo clase: se me pasó tomar lista"
        OPC_SUSPENSION = "🏛️ No hubo clase: suspensión oficial"
        OPC_MISA = "⛪ No hubo clase: misa"
        OPC_OTRO = "📝 No hubo clase: otro motivo"
        que_paso = st.radio("¿Qué pasó ese día?", [OPC_CLASE, OPC_SUSPENSION, OPC_MISA, OPC_OTRO], key=f"pend_que_{sufijo_key}")

        if que_paso == OPC_CLASE:
            columnas_destino = [fecha_sel]
            if horas_dia >= 2:
                estructura = st.radio(
                    "Ese día tu horario marca clase doble. ¿Cómo la registras?",
                    ["🕒 Bloque continuo (una sola lista)", "👥 Dos módulos (lista S1 y lista S2)", "1️⃣ Solo primer módulo (S1)", "2️⃣ Solo segundo módulo (S2)"],
                    key=f"pend_estr_{sufijo_key}"
                )
                if "Dos módulos" in estructura:
                    columnas_destino = [f"{fecha_sel} (S1)", f"{fecha_sel} (S2)"]
                elif "primer" in estructura:
                    columnas_destino = [f"{fecha_sel} (S1)"]
                elif "segundo" in estructura:
                    columnas_destino = [f"{fecha_sel} (S2)"]

            st.caption("Todos aparecen como presentes: cambia solo a quienes faltaron o llegaron tarde.")
            df_pend = pd.DataFrame({"Alumno": alumnos})
            config_pend = {"Alumno": st.column_config.TextColumn("Alumno", disabled=True)}
            for col_d in columnas_destino:
                df_pend[col_d] = "✅ Presente"
                config_pend[col_d] = st.column_config.SelectboxColumn(col_d, options=opciones_asistencia, required=True)
            df_pend_editado = st.data_editor(
                df_pend, column_config=config_pend, hide_index=True, use_container_width=True,
                key=f"pend_ed_{sufijo_key}_{'_'.join(columnas_destino)}"
            )

            if st.button(f"💾 Guardar lista del {etiqueta_dia(fecha_sel)}", type="primary", key=f"pend_guardar_lista_{sufijo_key}"):
                registros = {col_d: dict(zip(df_pend_editado["Alumno"], df_pend_editado[col_d])) for col_d in columnas_destino}
                if guardar_columnas(registros):
                    leer_datos.clear()
                    st.success(f"✅ Lista del {etiqueta_dia(fecha_sel)} guardada.")
                    time.sleep(1)
                    st.rerun()
        else:
            if que_paso == OPC_OTRO:
                motivo = st.text_input(
                    "Motivo (obligatorio):", placeholder="Ej. Simulacro, ceremonia, salida escolar",
                    max_chars=60, key=f"pend_motivo_{sufijo_key}"
                )
                etiqueta = " ".join(motivo.split())
            else:
                base = "Suspensión oficial" if que_paso == OPC_SUSPENSION else "Misa"
                detalle = st.text_input(
                    "Detalle (opcional):",
                    placeholder="Ej. Día de la Revolución" if que_paso == OPC_SUSPENSION else "Ej. Inicio de ciclo escolar",
                    max_chars=40, key=f"pend_detalle_{sufijo_key}"
                )
                detalle = " ".join(detalle.split())
                etiqueta = f"{base}: {detalle}" if detalle else base

            if not etiqueta:
                st.info("✍️ Escribe el motivo para poder registrarlo.")
            else:
                estatus_sin_clase = f"⚪ Sin Clase ({etiqueta})"
                st.caption(f"Se registrará **{estatus_sin_clase}** para los {len(alumnos)} alumnos. No cuenta como falta y el día deja de aparecer como pendiente.")
                if st.button("💾 Registrar día sin clase", type="primary", key=f"pend_guardar_sc_{sufijo_key}"):
                    if guardar_columnas({fecha_sel: {al: estatus_sin_clase for al in alumnos}}):
                        leer_datos.clear()
                        st.success(f"✅ {etiqueta_dia(fecha_sel)} quedó registrado como sin clase.")
                        time.sleep(1)
                        st.rerun()
        return

    # =================================================================
    # MODO 1: PASE DE LISTA DEL DÍA
    # =================================================================
    if modo_vista == "📝 Pasar Lista del Día":
        st.info(f"💡 Frecuencia: **{dias_semana_clase} horas/semana**. Evaluando **{periodo_actual_nombre}** (Límite: **{limite_faltas} faltas** | 3 Retardos = 1 Falta).")
        if fechas_pendientes and not habilitar_historico:
            c_aviso, c_ir = st.columns([3, 1])
            c_aviso.warning(f"⚠️ Hay **{len(fechas_pendientes)}** día(s) del periodo actual con clase según tu horario y sin lista.")
            c_ir.button("🗓️ Resolver ahora", on_click=ir_a_pendientes, use_container_width=True, key="btn_ir_pend")
        
        alumnos_sin_derecho = [al for al, est in derecho_examen_dict.items() if est == "❌ SIN DERECHO"]
        alumnos_en_riesgo = [al for al, est in derecho_examen_dict.items() if "RIESGO" in est or "LÍMITE" in est]
        if alumnos_sin_derecho:
            st.error(f"🚫 **ALUMNOS SIN DERECHO:** {', '.join(alumnos_sin_derecho)} (Superaron el límite de {limite_faltas} faltas).")
        if alumnos_en_riesgo:
            st.warning(f"⚠️ **EN RIESGO PREVENTIVO:** {', '.join(alumnos_en_riesgo)}.")

        fechas_disponibles_pase = []
        etiquetas_pase = {}
        
        # 1. SIEMPRE AGREGAMOS 'HOY' SI LE TOCA CLASE
        if horario_clase.get(dia_num_hoy, 0) > 0:
            f_hoy_str = hoy_cdmx.strftime("%d-%m-%Y")
            fechas_disponibles_pase.append(f_hoy_str)
            etiquetas_pase[f_hoy_str] = f"Hoy ({nombre_dia_hoy}) {f_hoy_str}"
            
        # 2. ¿EL MAESTRO ENCENDIÓ EL INTERRUPTOR HISTÓRICO?
        # 🛡️ Antes solo se ofrecían los últimos 44 días, así que no se podía registrar el inicio
        # del periodo anterior. Ahora se elige el periodo y aparecen todos sus días de clase.
        if habilitar_historico:
            nombres_periodos_pase = [p["nombre"] for p in periodos_nivel]
            c_per, c_todos = st.columns([2, 1])
            periodo_pase = c_per.selectbox("Periodo:", nombres_periodos_pase, index=idx_periodo,
                                           key=f"periodo_pase_{nombre_pestana}")
            incluir_fuera_horario = c_todos.checkbox(
                "Incluir días fuera de mi horario", key=f"fuera_horario_{nombre_pestana}",
                help="Útil si tu horario cambió durante el ciclo.")
            p_pase = next(p for p in periodos_nivel if p["nombre"] == periodo_pase)
            inicio_pase = datetime.strptime(p_pase["inicio"], "%Y-%m-%d").date()
            fin_pase = min(datetime.strptime(p_pase["fin"], "%Y-%m-%d").date(), hoy_cdmx.date())
            registradas_pase = {c.split(" (")[0].strip() for c in columnas_fechas}

            fecha_eval = fin_pase   # del más reciente al más antiguo
            while fecha_eval >= inicio_pase:
                dia_sem = fecha_eval.weekday()
                tiene_clase = dias_semana_clase == 0 or horario_clase.get(dia_sem, 0) > 0
                if dia_sem < 5 and (tiene_clase or incluir_fuera_horario):
                    f_str = fecha_eval.strftime("%d-%m-%Y")
                    if f_str not in fechas_disponibles_pase:
                        fechas_disponibles_pase.append(f_str)
                        estado_dia = "✅ con lista" if f_str in registradas_pase else "⚠️ sin lista"
                        etiquetas_pase[f_str] = f"{dias_espanol[dia_sem]} {f_str} ({estado_dia})"
                fecha_eval -= timedelta(days=1)
            if fin_pase < inicio_pase:
                st.info(f"El {periodo_pase} todavía no empieza.")
        
        # 3. Los días pasados sin lista se resuelven en "🗓️ Días sin Lista" (motivo o lista olvidada)

        # 4. ¿HAY FECHAS PARA MOSTRAR?
        if not fechas_disponibles_pase:
            if habilitar_historico:
                st.warning("⚠️ No se encontraron fechas de clase en el historial.")
            elif fechas_pendientes:
                st.info(f"📅 Hoy ({nombre_dia_hoy}) no hay clase de esta materia según tu horario.")
            else:
                st.success(f"🎉 **Estás al corriente con todas tus clases registradas hasta el día de hoy.**")
            return

        fecha_str = st.selectbox("📅 Fecha de clase a registrar/modificar:", fechas_disponibles_pase, format_func=lambda x: etiquetas_pase[x])
        dia_seleccionado = datetime.strptime(fecha_str, "%d-%m-%Y").weekday()
        horas_ese_dia = horario_clase.get(dia_seleccionado, 1)

        if horas_ese_dia >= 2:
            tipo_sesion = st.radio(
                "¿Cómo registrarás la clase doble de hoy?",
                ["🕒 Bloque Continuo (Sesión de 2 horas)", "1️⃣ Primer Módulo (1 hora)", "2️⃣ Segundo Módulo (1 hora)"],
                horizontal=True
            )
            if "Primer" in tipo_sesion:
                col_fecha_final = f"{fecha_str} (S1)"
                st.info("ℹ️ Cada inasistencia contará como **1 falta**.")
            elif "Segundo" in tipo_sesion:
                col_fecha_final = f"{fecha_str} (S2)"
                st.info("ℹ️ Cada inasistencia contará como **1 falta**.")
            else:
                col_fecha_final = f"{fecha_str}"
                st.warning("⚠️ **ATENCIÓN: Registrando Bloque Continuo (2 horas).** Una inasistencia computará como **2 faltas reglamentarias**.")
        else:
            col_fecha_final = fecha_str

        if col_fecha_final in df_historial.columns:
            valores_previos = dict(zip(df_historial['Alumno'], df_historial[col_fecha_final]))
            sin_clase_previo = next((str(v) for v in valores_previos.values() if str(v).startswith("⚪")), None)
            if sin_clase_previo:
                st.info(f"ℹ️ Este día está registrado como **{sin_clase_previo}**. Si guardas esta lista, se reemplaza.")
            col_asist = [
                v if (pd.notna(v) and v != "" and not str(v).startswith("⚪")) else "✅ Presente"
                for v in (valores_previos.get(al) for al in alumnos)
            ]
        else:
            col_asist = ["✅ Presente"] * len(alumnos)

        df_view = pd.DataFrame({
            "Alumno": alumnos,
            "Asistencia": col_asist,
            "Faltas Reales": [faltas_dict[al] for al in alumnos],
            "Retardos": [retardos_dict[al] for al in alumnos],
            "Faltas Efectivas": [faltas_efectivas_dict[al] for al in alumnos],
            "Derecho Examen": [derecho_examen_dict[al] for al in alumnos]
        })

        col_config = {
            "Alumno": st.column_config.TextColumn("Alumno", disabled=True),
            "Asistencia": st.column_config.SelectboxColumn("Asistencia", options=opciones_asistencia, required=True),
            "Faltas Reales": st.column_config.NumberColumn("Faltas", disabled=True),
            "Faltas Efectivas": st.column_config.NumberColumn("Efectivas", disabled=True),
            "Derecho Examen": st.column_config.TextColumn("Derecho", disabled=True)
        }
        if "secundaria" in nivel_elegido.lower():
            col_config["Retardos"] = None
        else:
            col_config["Retardos"] = st.column_config.NumberColumn("Retardos", disabled=True)

        df_editado = st.data_editor(
            df_view,
            column_config=col_config,
            hide_index=True,
            use_container_width=True,
            key=f"ed_{materia}_{grupo}_{col_fecha_final}"
        )

        if st.button("💾 Guardar Asistencia", type="primary"):
            with st.spinner(f"Guardando asistencia del {col_fecha_final}..."):
                mapeo_asist = dict(zip(df_editado['Alumno'], df_editado['Asistencia']))
                conn = obtener_conexion_sql()
                guardado = False
                try:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM [asistencia_registros] WHERE [Clase] = ? AND [Fecha] = ?", (nombre_pestana, col_fecha_final))

                    lote_insert = [(nombre_pestana, al, col_fecha_final, mapeo_asist.get(al, "✅ Presente")) for al in alumnos]
                    cursor.executemany('INSERT INTO [asistencia_registros] ("Clase", "Alumno", "Fecha", "Estatus") VALUES (?, ?, ?, ?)', lote_insert)
                    conn.commit()
                    guardado = True
                except Exception as e:
                    conn.rollback()
                    logging.exception(e)
                    st.error("🚨 No se pudo guardar la asistencia. Tus cambios siguen en la tabla; intenta de nuevo.")
                finally:
                    conn.close()

                # 🛡️ Antes el mensaje de éxito y el rerun se ejecutaban aunque el guardado fallara
                if guardado:
                    leer_datos.clear()
                    st.success("✅ Asistencia guardada correctamente.")
                    time.sleep(1)
                    st.rerun()

    # =================================================================
    # MODO 2: VISTA HISTÓRICA DEL GRUPO (MODIFICAR ASISTENCIA)
    # =================================================================
    else:
        st.markdown(f"### 📈 Historial y Modificación: {grupo} ({materia})")
        st.caption("Edita cualquier celda directamente en la tabla. Los totales se recalcularán automáticamente.")
        
        if fechas_pendientes:
            c_aviso, c_ir = st.columns([3, 1])
            c_aviso.warning(f"⚠️ Hay **{len(fechas_pendientes)}** día(s) del periodo actual con clase según tu horario y sin lista.")
            c_ir.button("🗓️ Resolver ahora", on_click=ir_a_pendientes, use_container_width=True, key="btn_ir_pend_hist")

        # 2. 🛡️ SELECTOR DE PERIODO PARA LA TABLA HISTÓRICA
        nombres_periodos_hist = ["Ver Historial Completo (Todos los periodos)"] + [p['nombre'] for p in periodos_nivel]
        periodo_hist_sel = st.selectbox("📅 Mostrar datos del:", nombres_periodos_hist, index=idx_periodo + 1)
        
        columnas_fechas_filtradas = []
        if periodo_hist_sel == "Ver Historial Completo (Todos los periodos)":
            columnas_fechas_filtradas = columnas_fechas
        else:
            p_inf = next(p for p in periodos_nivel if p['nombre'] == periodo_hist_sel)
            inicio_p = datetime.strptime(p_inf['inicio'], "%Y-%m-%d").date()
            fin_p = datetime.strptime(p_inf['fin'], "%Y-%m-%d").date()
            
            for col_f in columnas_fechas:
                try:
                    fecha_limpia = col_f.split(" (")[0]
                    fecha_col_dt = datetime.strptime(fecha_limpia, "%d-%m-%Y").date()
                    if inicio_p <= fecha_col_dt <= fin_p:
                        columnas_fechas_filtradas.append(col_f)
                except:
                    pass

        if df_historial.empty or len(columnas_fechas_filtradas) == 0:
            st.info(f"💡 No hay asistencias registradas en la selección actual ({periodo_hist_sel}).")
            return

        # 3. RECALCULAR MÉTRICAS SOLO PARA EL PERIODO SELECCIONADO
        faltas_hist_dict = {}
        retardos_hist_dict = {}
        efectivas_hist_dict = {}
        derecho_hist_dict = {}

        if periodo_hist_sel == "Ver Historial Completo (Todos los periodos)":
            limite_hist = 999 
        else:
            idx_sel = nombres_periodos_hist.index(periodo_hist_sel) - 1
            limites_fila = limites_tabla.get(dias_semana_clase, [99, 99, 99, 99, 99])
            limite_hist = limites_fila[idx_sel] if idx_sel < len(limites_fila) else limites_fila[-1]

        for al in alumnos:
            if al in df_historial['Alumno'].values:
                fila_al = df_historial[df_historial['Alumno'] == al].iloc[0]
                
                f_real = sum(1 for c in columnas_fechas_filtradas if str(fila_al[c]) == '🔴 Falta')
                r_real = sum(1 for c in columnas_fechas_filtradas if str(fila_al[c]) == '🟡 Retardo')
                f_efec = f_real + (r_real // 3)
                
                faltas_hist_dict[al] = f_real
                retardos_hist_dict[al] = r_real
                efectivas_hist_dict[al] = f_efec
                
                if f_efec > limite_hist: derecho_hist_dict[al] = "❌ SIN DERECHO"
                elif f_efec == limite_hist: derecho_hist_dict[al] = "🚨 LÍMITE ALCANZADO"
                elif f_efec == (limite_hist - 1) and limite_hist > 1: derecho_hist_dict[al] = "⚠️ EN RIESGO"
                else: derecho_hist_dict[al] = "✅ SÍ"
            else:
                faltas_hist_dict[al], retardos_hist_dict[al], efectivas_hist_dict[al] = 0, 0, 0
                derecho_hist_dict[al] = "✅ SÍ"

        df_mostrar = pd.DataFrame({"Alumno": df_historial["Alumno"]})
        
        if periodo_hist_sel != "Ver Historial Completo (Todos los periodos)":
            df_mostrar["Derecho Examen"] = df_mostrar["Alumno"].map(derecho_hist_dict)
            
        df_mostrar["Faltas Efectivas"] = df_mostrar["Alumno"].map(efectivas_hist_dict)
        df_mostrar["Faltas Reales"] = df_mostrar["Alumno"].map(faltas_hist_dict)
        
        if "secundaria" not in nivel_elegido.lower():
            df_mostrar["Retardos"] = df_mostrar["Alumno"].map(retardos_hist_dict)
            
        for col in columnas_fechas_filtradas:
            df_mostrar[col] = df_historial[col]
            
        config_cols_hist = {
            "Alumno": st.column_config.TextColumn("Alumno", disabled=True),
            "Derecho Examen": st.column_config.TextColumn("Derecho", disabled=True),
            "Faltas Efectivas": st.column_config.NumberColumn("Efectivas", disabled=True),
            "Faltas Reales": st.column_config.NumberColumn("Faltas", disabled=True),
            "Retardos": st.column_config.NumberColumn("Retardos", disabled=True)
        }
        # 🛡️ Los estatus con motivo ("⚪ Sin Clase (Misa)") no están en la lista fija; se agregan
        valores_en_tabla = set()
        for col in columnas_fechas_filtradas:
            valores_en_tabla.update(str(v) for v in df_mostrar[col].dropna().unique() if str(v).strip())
        opciones_hist_tabla = opciones_hist + sorted(valores_en_tabla - set(opciones_hist))
        for col in columnas_fechas_filtradas:
            config_cols_hist[col] = st.column_config.SelectboxColumn(col, options=opciones_hist_tabla, required=False)

        st.info("💡 Puedes editar la asistencia de cualquier día directamente en esta tabla. Los totales se recalcularán al guardar.")
        df_editado_hist = st.data_editor(
            df_mostrar,
            column_config=config_cols_hist,
            use_container_width=True,
            hide_index=True,
            key=f"ed_hist_{materia}_{grupo}_{periodo_hist_sel}"
        )
        
        c_h1, c_h2 = st.columns([1, 1])
        with c_h1:
            if st.button("💾 Guardar Cambios Históricos", type="primary", use_container_width=True):
                with st.spinner("Actualizando base de datos..."):
                    conn = obtener_conexion_sql()
                try:
                    cursor = conn.cursor()
                    
                    for col_f in columnas_fechas_filtradas:
                        cursor.execute("DELETE FROM [asistencia_registros] WHERE [Clase] = ? AND [Fecha] = ?", (nombre_pestana, col_f))
                    
                    lote_hist = []
                    for _, r in df_editado_hist.iterrows():
                        al_nom = r['Alumno']
                        for col_f in columnas_fechas_filtradas:
                            # 🛡️ Una celda borrada llega como None; antes se guardaba el texto "None"
                            val_celda = r.get(col_f, "")
                            val_estatus = "" if pd.isna(val_celda) else str(val_celda).strip()
                            if val_estatus != "":
                                lote_hist.append((nombre_pestana, al_nom, col_f, val_estatus))
                                
                    cursor.executemany('INSERT INTO [asistencia_registros] ("Clase", "Alumno", "Fecha", "Estatus") VALUES (?, ?, ?, ?)', lote_hist)
                    conn.commit()
                finally:
                    conn.close() 
                
                leer_datos.clear()
                st.success("✅ Cambios históricos guardados correctamente.")
                time.sleep(1)
                st.rerun()
                    
        with c_h2:
            df_export_asist = df_mostrar.copy()
            remplazos_excel = {
                "✅ Presente": "Presente", "🔴 Falta": "Falta", "🟡 Retardo": "Retardo",
                "⚪ Sin Clase": "Sin Clase", "⚪ Descartado": "Descartado",
                "✅ SÍ": "SÍ", "❌ NO": "NO", "❌ SIN DERECHO": "SIN DERECHO",
                "🚨 LÍMITE ALCANZADO": "LÍMITE ALCANZADO", "⚠️ EN RIESGO": "EN RIESGO"
            }
            for col in df_export_asist.columns:
                df_export_asist[col] = df_export_asist[col].replace(remplazos_excel)
                
            st.download_button(
                "📥 Descargar Matriz CSV",
                df_export_asist.to_csv(index=False).encode('utf-8-sig'),
                f"Asistencia_{materia}_{grupo}_{periodo_hist_sel}.csv",
                mime="text/csv",
                use_container_width=True
            )