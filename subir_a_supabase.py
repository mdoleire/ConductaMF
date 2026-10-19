# subir_a_supabase.py
import sqlite3
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

URL_SUPABASE = (
    st.secrets.get("DATABASE_URL") or 
    st.secrets.get("database_url") or 
    st.secrets.get("URL_SUPABASE") or 
    st.secrets.get("SUPABASE_URL")
)

if URL_SUPABASE.startswith("postgres://"):
    URL_SUPABASE = URL_SUPABASE.replace("postgres://", "postgresql+psycopg2://", 1)
elif URL_SUPABASE.startswith("postgresql://") and not URL_SUPABASE.startswith("postgresql+psycopg2://"):
    URL_SUPABASE = URL_SUPABASE.replace("postgresql://", "postgresql+psycopg2://", 1)

def subir_base_a_la_nube():
    print("=" * 60)
    print("🚀 SUBIENDO 'MIRAFLORES.DB' A SUPABASE CON BLINDAJE DE SEGURIDAD...")
    print("=" * 60)

    conn_sqlite = sqlite3.connect('miraflores.db')
    
    # 🛡️ Conexión cifrada obligatoria (SSL/TLS)
    engine_supabase = create_engine(
        URL_SUPABASE,
        connect_args={"sslmode": "require"}
    )
    
    tablas_df = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", conn_sqlite)
    
    for nombre_tabla in tablas_df['name']:
        print(f"📦 Subiendo tabla '{nombre_tabla}'...")
        df = pd.read_sql(f'SELECT * FROM "{nombre_tabla}"', conn_sqlite)
        
        # Si ya existía una columna incidencia_id estática de pruebas previas, la limpiamos para que sea SERIAL real
        if nombre_tabla == "conducta_registros" and "incidencia_id" in df.columns:
            df = df.drop(columns=["incidencia_id"])
        elif nombre_tabla == "calif_actividades" and not df.empty and "ID_Actividad" in df.columns:
            df = df.drop_duplicates(subset=["ID_Actividad"], keep="last")
        elif nombre_tabla == "calif_notas" and not df.empty and {"ID_Actividad", "Alumno"}.issubset(df.columns):
            df = df.drop_duplicates(subset=["ID_Actividad", "Alumno"], keep="last")

        # 1. Subimos la tabla a Supabase
        df.to_sql(nombre_tabla, engine_supabase, if_exists='replace', index=False)
        
        # 2. 🛡️ CIBERSEGURIDAD Y LLAVES ÚNICAS REQUERIDAS POR CALIFICACIONES.PY
        with engine_supabase.begin() as conn_pg:
            if nombre_tabla == "conducta_registros":
                conn_pg.execute(text('ALTER TABLE public."conducta_registros" ADD COLUMN incidencia_id SERIAL PRIMARY KEY;'))
            elif nombre_tabla == "calif_actividades":
                conn_pg.execute(text('ALTER TABLE public."calif_actividades" ADD CONSTRAINT uq_calif_act UNIQUE ("ID_Actividad");'))
            elif nombre_tabla == "calif_notas":
                conn_pg.execute(text('ALTER TABLE public."calif_notas" ADD CONSTRAINT uq_calif_notas UNIQUE ("ID_Actividad", "Alumno");'))
            
            conn_pg.execute(text(f'ALTER TABLE public."{nombre_tabla}" ENABLE ROW LEVEL SECURITY;'))
            conn_pg.execute(text(f'REVOKE ALL ON TABLE public."{nombre_tabla}" FROM anon, authenticated;'))
            
        print(f"   ✅ Tabla '{nombre_tabla}' subida y blindada con RLS ({len(df)} filas).")
        
    conn_sqlite.close()
    print("\n" + "=" * 60)
    print("🎉 ¡ÉXITO TOTAL! Toda tu escuela vive segura en Supabase.")
    print("=" * 60)

if __name__ == "__main__":
    subir_base_a_la_nube()