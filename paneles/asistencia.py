# paneles/asistencia.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import gspread
import time

from config import FILE_ASIGNACIONES, FILE_ALUMNOS, FILE_ASISTENCIA
from database import leer_datos, obtener_lista_alumnos, leer_todas_las_asignaciones

def renderizar_panel_asistencia(gc, usuario, nombre_prof):
    st.header(f"📅 Gestión de Asistencia")
    
    # 1. Buscar materias asignadas (Soporte multinivel)
    df_asig = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
    mis_asig = df_asig[df_asig['Usuario_Profesor'] == usuario]
    if mis_asig.empty:
        st.warning("Sin materias asignadas para pasar lista.")
        return

    modo_vista = st.radio("Selecciona la acción a realizar:", 
                          ["📝 Pasar Lista / Editar Día", "📊 Vista Histórica del Grupo"], 
                          horizontal=True)

    st.markdown("---")

    # --- Layout de 3 columnas para alinear el interruptor a la derecha ---
    c1, c2, c3 = st.columns([3, 3, 2])
    materia = c1.selectbox("Materia:", mis_asig['Materia'].unique(), key="asist_mat")
    grupo = c2.selectbox("Grupo:", mis_asig[mis_asig['Materia'] == materia]['Grupo'].unique(), key="asist_grup")
    
    with c3:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        # Le asignamos un "key" (llave) en la memoria para poder controlarlo desde el botón "X"
        mostrar_edicion = st.toggle("⚙️ Modificar horario", key="toggle_edicion")
    
    # 2. Obtener la lista de alumnos
    try:
        alumnos = obtener_lista_alumnos(gc, FILE_ALUMNOS, grupo)
    except Exception:
        alumnos = []

    if not alumnos:
        st.warning(f"No se encontraron alumnos registrados para el grupo {grupo}.")
        return

    nombre_pestana = f"{materia} - {grupo}"

    # ========================================================
    # 🚀 MOTOR DE CONFIGURACIÓN DE HORARIOS
    # ========================================================
    try:
        df_config = leer_datos(gc, FILE_ASISTENCIA, "Configuracion")
    except Exception:
        df_config = pd.DataFrame(columns=["Clase", "Lunes", "Martes", "Miercoles", "Jueves", "Viernes"])

    config_actual = pd.DataFrame()
    if not df_config.empty and 'Clase' in df_config.columns:
        config_actual = df_config[df_config['Clase'] == nombre_pestana]

    v_lun, v_mar, v_mie, v_jue, v_vie = 0, 0, 0, 0, 0
    if not config_actual.empty:
        v_lun = int(config_actual.iloc[0]['Lunes'])
        v_mar = int(config_actual.iloc[0]['Martes'])
        v_mie = int(config_actual.iloc[0]['Miercoles'])
        v_jue = int(config_actual.iloc[0]['Jueves'])
        v_vie = int(config_actual.iloc[0]['Viernes'])

    if config_actual.empty:
        st.info(f"⚙️ **Configuración Inicial requerida para {nombre_pestana}**")
        st.write("Antes de pasar lista, define el horario de esta materia para calcular correctamente las faltas.")
        mostrar_formulario = True
        detener_app = True
    else:
        # Leemos el estado del interruptor desde la memoria
        mostrar_formulario = st.session_state.get("toggle_edicion", False)
        detener_app = False

    # Si está encendido (o si es nuevo), mostramos el panel
    if mostrar_formulario:
        with st.container():
            # --- NUEVO: Botón de Cerrar (X) visible solo si NO es configuración inicial ---
            if not config_actual.empty:
                c_vacio, c_cerrar = st.columns([8, 2])
                with c_cerrar:
                    if st.button("❌ Cerrar", use_container_width=True):
                        # Apagamos el interruptor en la memoria y recargamos
                        st.session_state.toggle_edicion = False
                        st.rerun()

            with st.form(f"form_horario_{nombre_pestana}"):
                st.write("Indica cuántas horas de clase tienes cada día (0 = No hay clase, 1 = Sencilla, 2 = Doble):")
                
                c_lun, c_mar, c_mie, c_jue, c_vie = st.columns(5)
                h_lun = c_lun.number_input("Lunes", min_value=0, max_value=4, value=v_lun)
                h_mar = c_mar.number_input("Martes", min_value=0, max_value=4, value=v_mar)
                h_mie = c_mie.number_input("Miérc.", min_value=0, max_value=4, value=v_mie)
                h_jue = c_jue.number_input("Jueves", min_value=0, max_value=4, value=v_jue)
                h_vie = c_vie.number_input("Viernes", min_value=0, max_value=4, value=v_vie)

                if st.form_submit_button("💾 Guardar Horario", type="primary"):
                    if sum([h_lun, h_mar, h_mie, h_jue, h_vie]) == 0:
                        st.error("⚠️ Debes asignar al menos 1 hora de clase a la semana.")
                    else:
                        with st.spinner("Actualizando configuración en Google Drive..."):
                            doc = gc.open(FILE_ASISTENCIA)
                            try:
                                ws_conf = doc.worksheet("Configuracion")
                            except gspread.exceptions.WorksheetNotFound:
                                ws_conf = doc.add_worksheet(title="Configuracion", rows="100", cols="6")
                                ws_conf.append_row(["Clase", "Lunes", "Martes", "Miercoles", "Jueves", "Viernes"])

                            if config_actual.empty:
                                nueva_fila = pd.DataFrame([[nombre_pestana, h_lun, h_mar, h_mie, h_jue, h_vie]], columns=["Clase", "Lunes", "Martes", "Miercoles", "Jueves", "Viernes"])
                                df_actualizado = pd.concat([df_config, nueva_fila], ignore_index=True)
                            else:
                                df_actualizado = df_config.copy()
                                idx = df_actualizado[df_actualizado['Clase'] == nombre_pestana].index
                                df_actualizado.loc[idx, ['Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes']] = [h_lun, h_mar, h_mie, h_jue, h_vie]
                            
                            df_actualizado = df_actualizado.fillna("")
                            ws_conf.clear()
                            ws_conf.update([df_actualizado.columns.values.tolist()] + df_actualizado.values.tolist())
                            
                            # Al guardar exitosamente, también apagamos el panel
                            st.session_state.toggle_edicion = False
                            leer_datos.clear() 
                            st.success("✅ Horario actualizado con éxito.")
                            time.sleep(1.5)
                            st.rerun()
                            
    if detener_app:
        return

    # Diccionario de pesos del horario (Fines de semana apagados)
    horario_clase = {
        0: v_lun, 1: v_mar, 2: v_mie, 3: v_jue, 4: v_vie,
        5: 0, # Sábado apagado
        6: 0  # Domingo apagado
    }

    # ========================================================
    # 3. LEER EL HISTORIAL Y CALCULAR FALTAS PONDERADAS
    # ========================================================
    try:
        df_historial = leer_datos(gc, FILE_ASISTENCIA, nombre_pestana)
    except Exception:
        df_historial = pd.DataFrame()

    if df_historial.empty or 'Alumno' not in df_historial.columns:
        df_historial = pd.DataFrame({"Alumno": alumnos})

    columnas_fechas = [c for c in df_historial.columns if c != 'Alumno']
    
    total_horas_impartidas = 0
    peso_fechas = {} 
    
    for col_fecha in columnas_fechas:
        try:
            dia_semana = datetime.strptime(col_fecha, "%d-%m-%Y").weekday()
            horas_ese_dia = horario_clase.get(dia_semana, 1)
            if horas_ese_dia == 0: horas_ese_dia = 1 
            
            peso_fechas[col_fecha] = horas_ese_dia
            total_horas_impartidas += horas_ese_dia
        except:
            peso_fechas[col_fecha] = 1
            total_horas_impartidas += 1

    stats = {}
    faltas_dict = {}
    retardos_dict = {}
    
    for al in alumnos:
        if total_horas_impartidas > 0 and al in df_historial['Alumno'].values:
            fila_alumno = df_historial[df_historial['Alumno'] == al].iloc[0]
            faltas_ponderadas = 0
            retardos_ponderados = 0
            
            for col_f in columnas_fechas:
                estado = fila_alumno[col_f]
                peso = peso_fechas[col_f] 
                
                if estado == '🔴 Falta':
                    faltas_ponderadas += peso
                elif estado == '🟡 Retardo':
                    retardos_ponderados += peso
            
            pct = (faltas_ponderadas / total_horas_impartidas) * 100
            stats[al] = f"{pct:.1f}%"
            faltas_dict[al] = faltas_ponderadas
            retardos_dict[al] = retardos_ponderados
        else:
            stats[al] = "0.0%"
            faltas_dict[al] = 0
            retardos_dict[al] = 0

    # ========================================================
    # MODO 1: PASE DE LISTA Y EDICIÓN
    # ========================================================
    if modo_vista == "📝 Pasar Lista / Editar Día":
        
        dias_espanol = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
        fechas_validas = []
        etiquetas_fechas = {} 
        
        hoy = datetime.now(ZoneInfo("America/Mexico_City"))
        
        for i in range(30): 
            fecha_eval = hoy - timedelta(days=i)
            dia_semana = fecha_eval.weekday()
            
            if horario_clase.get(dia_semana, 0) > 0:
                f_str = fecha_eval.strftime("%d-%m-%Y")
                fechas_validas.append(f_str)
                etiquetas_fechas[f_str] = f"{dias_espanol[dia_semana]} {f_str}"
                
        if not fechas_validas:
            f_str = hoy.strftime("%d-%m-%Y")
            fechas_validas = [f_str]
            etiquetas_fechas[f_str] = f"{dias_espanol[hoy.weekday()]} {f_str}"

        fecha_str = st.selectbox(
            "📅 Selecciona la fecha de la clase:", 
            fechas_validas,
            format_func=lambda x: etiquetas_fechas[x]
        )
        
        fecha_sel_dt = datetime.strptime(fecha_str, "%d-%m-%Y")
        dia_semana_actual = fecha_sel_dt.weekday()
        
        if horario_clase.get(dia_semana_actual) == 2:
            st.info("⏱️ **Dato:** Este día es de clase doble. Las inasistencias contarán como 2 faltas.")

        st.markdown("<br>", unsafe_allow_html=True)
        
        if fecha_str in df_historial.columns:
            st.info(f"📝 **Modo Edición:** Modificando asistencia del **{fecha_str}**.")
            valores_previos = dict(zip(df_historial['Alumno'], df_historial[fecha_str]))
            col_asistencia = [valores_previos.get(al, "✅ Presente") if pd.notna(valores_previos.get(al)) and valores_previos.get(al) != "" else "✅ Presente" for al in alumnos]
        else:
            st.info(f"✨ **Nuevo Registro:** Pasando lista para el **{fecha_str}**.")
            col_asistencia = ["✅ Presente"] * len(alumnos)

        df_view = pd.DataFrame({
            "Alumno": alumnos,
            "Asistencia": col_asistencia,
            "% Inasistencia": [stats[al] for al in alumnos],
            "Faltas Acum.": [faltas_dict[al] for al in alumnos],
            "Retardos Acum.": [retardos_dict[al] for al in alumnos]
        })

        st.markdown(f"### 📋 Lista de {grupo} ({materia})")

        df_editado = st.data_editor(
            df_view,
            column_config={
                "Alumno": st.column_config.TextColumn("Alumno", disabled=True),
                "Asistencia": st.column_config.SelectboxColumn(
                    "Asistencia",
                    options=["✅ Presente", "🟡 Retardo", "🔴 Falta"],
                    required=True,
                ),
                "% Inasistencia": st.column_config.TextColumn("% Inasistencia", disabled=True),
                "Faltas Acum.": st.column_config.NumberColumn("Faltas", disabled=True),
                "Retardos Acum.": st.column_config.NumberColumn("Retardos", disabled=True)
            },
            hide_index=True,
            use_container_width=True,
            key=f"editor_{materia}_{grupo}_{fecha_str}"
        )

        if st.button("💾 Guardar Asistencia", type="primary"):
            with st.spinner(f"Guardando registro del {fecha_str}..."):
                try:
                    doc = gc.open(FILE_ASISTENCIA)
                except gspread.exceptions.SpreadsheetNotFound:
                    st.error(f"⚠️ No se encontró el archivo '{FILE_ASISTENCIA}'.")
                    st.stop()

                try:
                    ws = doc.worksheet(nombre_pestana)
                except gspread.exceptions.WorksheetNotFound:
                    ws = doc.add_worksheet(title=nombre_pestana, rows="100", cols="50")

                df_actualizado = df_historial.copy()
                
                alumnos_existentes = df_actualizado['Alumno'].tolist() if 'Alumno' in df_actualizado.columns else []
                nuevos_alumnos = [a for a in alumnos if a not in alumnos_existentes]
                if nuevos_alumnos:
                    df_nuevos = pd.DataFrame({"Alumno": nuevos_alumnos})
                    df_actualizado = pd.concat([df_actualizado, df_nuevos], ignore_index=True)
                    df_actualizado = df_actualizado.sort_values('Alumno').reset_index(drop=True)

                asistencia_dict = dict(zip(df_editado['Alumno'], df_editado['Asistencia']))
                df_actualizado[fecha_str] = df_actualizado['Alumno'].map(asistencia_dict)
                
                df_actualizado = df_actualizado.fillna("")

                ws.clear()
                ws.update([df_actualizado.columns.values.tolist()] + df_actualizado.values.tolist())
                
                leer_datos.clear()
                
                st.success(f"✅ ¡Asistencia del {fecha_str} guardada correctamente!")
                time.sleep(1.5)
                st.rerun()

    # ========================================================
    # MODO 2: VISTA HISTÓRICA
    # ========================================================
    else:
        st.markdown(f"### 📈 Historial Completo de {grupo} ({materia})")
        
        if df_historial.empty or len(columnas_fechas) == 0:
            st.info("Aún no hay registros de asistencia guardados para esta materia y grupo.")
            return

        df_mostrar = pd.DataFrame({"Alumno": df_historial["Alumno"]})
        
        df_mostrar["% Faltas"] = df_mostrar["Alumno"].map(stats)
        df_mostrar["Total Faltas"] = df_mostrar["Alumno"].map(faltas_dict)
        df_mostrar["Total Retardos"] = df_mostrar["Alumno"].map(retardos_dict)
        
        for col in columnas_fechas:
            df_mostrar[col] = df_historial[col]
        
        st.dataframe(df_mostrar, use_container_width=True, hide_index=True)
        
        csv_data = df_mostrar.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 Descargar Matriz de Asistencia (CSV)",
            data=csv_data,
            file_name=f"Asistencia_{materia}_{grupo}.csv",
            mime="text/csv",
            type="primary"
        )
