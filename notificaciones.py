import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import streamlit as st
import pandas as pd
from datetime import datetime

# ==========================================
# PLANTILLAS HTML
# ==========================================
PLANTILLA_BASE = """
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
    <div style="background-color: #0B1B3D; color: white; padding: 15px 20px; text-align: center; border-bottom: 4px solid #C5A059;">
        <h2 style="margin: 0; letter-spacing: 1px;">COLEGIO MIRAFLORES</h2>
    </div>
    <div style="padding: 30px 20px; color: #2C3E50; font-size: 15px; line-height: 1.6;">
        <p style="text-align: right; color: #7F8C8D;">Fecha: {fecha}</p>
        {cuerpo_mensaje}
        <br><br>
        <p>Le enviamos un cordial saludo.</p>
    </div>
</div>
"""

CUERPO_PADRES_GRAVE = """
<p><strong>Estimados padres de familia,</strong></p>
<p>Por medio de la presente le informamos que su hijo(a) <strong>{alumno}</strong> tuvo la siguiente conducta:</p>
<div style="background-color: #F4F6F9; padding: 12px; border-left: 4px solid #0B1B3D; margin: 15px 0;">
    <em>"{conducta}"</em>
</div>
<p>Como establece el Acuerdo General, esto constituye una falta grave. Por lo tanto, se hace acreedor(a) a un 5 en conducta en la materia de <strong>{materia}</strong>.</p>
<p>Esperamos que esta medida esté acompañada de una reflexión acerca de su comportamiento y contemos con su apoyo para que esto no vuelva a suceder.</p>
"""

CUERPO_TUTOR_GRAVE = """
<p><strong>Estimado tutor y coordinador de sección,</strong></p>
<p>Por medio de la presente le informamos que su alumno(a) <strong>{alumno}</strong> tuvo la siguiente conducta:</p>
<div style="background-color: #F4F6F9; padding: 12px; border-left: 4px solid #0B1B3D; margin: 15px 0;">
    <em>"{conducta}"</em>
</div>
<p>Como establece el Acuerdo General, esto constituye una falta grave en la materia de <strong>{materia}</strong>.</p>
<p>Esperamos contar con su oportuno seguimiento para evitar que esta situación se repita, dar contención y tratar el tema con el alumno.</p>
"""

CUERPO_PASILLO = """
<p><strong>Estimado tutor,</strong></p>
<p>Por medio de la presente le informamos que el alumno(a) <strong>{alumno}</strong> tuvo la siguiente conducta:</p>
<div style="background-color: #F4F6F9; padding: 12px; border-left: 4px solid #C5A059; margin: 15px 0;">
    <em>"{conducta}"</em>
</div>
<p>Este incidente ocurrió en: <strong>{lugar}</strong>.</p>
<p>Esperamos contar con su oportuno seguimiento para evitar que esta situación se repita, dar contención y tratar el tema con el alumno.</p>
"""

# ==========================================
# MOTOR DE ENVÍO
# ==========================================
def enviar_correo(destinatarios, asunto, cuerpo_html):
    remitente = st.secrets["smtp"]["email_sender"]
    password = st.secrets["smtp"]["email_password"]
    
    if not destinatarios: 
        st.warning("⚠️ La lista de destinatarios está vacía. Revisa que el alumno tenga correos registrados en la hoja.")
        return
    
    msg = MIMEMultipart()
    msg['From'] = remitente
    msg['To'] = ", ".join(destinatarios)
    msg['Subject'] = asunto
    msg.attach(MIMEText(PLANTILLA_BASE.format(fecha=datetime.now().strftime("%d/%m/%Y"), cuerpo_mensaje=cuerpo_html), 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        server.send_message(msg)
        server.quit()
        st.toast("📧 ¡Correo enviado exitosamente!", icon="✉️")
    except Exception as e:
        st.error(f"🚨 Error SMTP detallado: {e}")

def procesar_notificaciones_conducta(df_alumnos, reporte_pasillo, alumno, materia, falta, observaciones):
    # Buscar correos en la base de datos
    alumno_data = df_alumnos[df_alumnos['Nombre Completo'] == alumno]
    if alumno_data.empty: return
    
    # Extracción segura de los tres posibles correos
    correo_al = str(alumno_data['correo'].iloc[0]).strip() if 'correo' in alumno_data.columns and pd.notna(alumno_data['correo'].iloc[0]) else ""
    correo_tut1 = str(alumno_data['correo_tutor'].iloc[0]).strip() if 'correo_tutor' in alumno_data.columns and pd.notna(alumno_data['correo_tutor'].iloc[0]) else ""
    correo_tut2 = str(alumno_data['correo_tutor2'].iloc[0]).strip() if 'correo_tutor2' in alumno_data.columns and pd.notna(alumno_data['correo_tutor2'].iloc[0]) else ""
    
    texto_conducta = f"{falta} - {observaciones}"
    
    if reporte_pasillo:
        cuerpo = CUERPO_PASILLO.format(alumno=alumno, conducta=texto_conducta, lugar=materia)
        # Se envía a ambos tutores si existen
        dest_pasillo = [c for c in [correo_tut1, correo_tut2] if c]
        if dest_pasillo:
            enviar_correo(dest_pasillo, f"Aviso de Incidencia (Pasillo/Patio) - {alumno}", cuerpo)
    else:
        # Correo a Padres (ambos tutores) y Alumno
        dest_padres = [c for c in [correo_al, correo_tut1, correo_tut2] if c]
        if dest_padres:
            cuerpo_padres = CUERPO_PADRES_GRAVE.format(alumno=alumno, conducta=texto_conducta, materia=materia)
            enviar_correo(dest_padres, f"Aviso de Falta Grave - {alumno}", cuerpo_padres)