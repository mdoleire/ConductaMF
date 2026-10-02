# subir_a_supabase.py
import sqlite3
import pandas as pd
import streamlit as st

from sqlalchemy import create_engine

# 1. PEGA AQUÍ TU CADENA DE CONEXIÓN DE SUPABASE (Con tu contraseña real):
URL_SUPABASE = st.secrets["DATABASE_URL"]

def subir_base_a_la_nube():
    print("=" * 60)
    print("🚀 SUBIENDO 'MIRAFLORES.DB' A TU SERVIDOR DE SUPABASE...")
    print("=" * 60)

    # Conexión a SQLite local
    conn_sqlite = sqlite3.connect('miraflores.db')
    
    # Conexión a PostgreSQL en Supabase
    engine_supabase = create_engine(URL_SUPABASE)
    
    # Obtenemos la lista de todas tus tablas locales
    tablas_df = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", conn_sqlite)
    
    for nombre_tabla in tablas_df['name']:
        print(f"📦 Subiendo tabla '{nombre_tabla}'...")
        # Leemos de SQLite local
        df = pd.read_sql(f"SELECT * FROM [{nombre_tabla}]", conn_sqlite)
        
        # Subimos a Supabase en la nube
        df.to_sql(nombre_tabla, engine_supabase, if_exists='replace', index=False)
        print(f"   ✅ Tabla '{nombre_tabla}' subida con éxito ({len(df)} filas).")
        
    conn_sqlite.close()
    print("\n" + "=" * 60)
    print("🎉 ¡ÉXITO TOTAL! Toda tu escuela ya vive en la nube de Supabase.")
    print("=" * 60)

if __name__ == "__main__":
    subir_base_a_la_nube()