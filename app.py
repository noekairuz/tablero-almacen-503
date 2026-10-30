import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import datetime

# Importación de funciones del backend
from procesar_articulos import (
    obtener_datos, 
    cargar_bdidpr_historico, 
    obtener_datos_hoja6,
    obtener_maestro_operarios,
    cargar_base_presentismo,
    cargar_horas_no_productivas,
    cargar_horas_ag,
    calcular_bultos_perdidos_pasados,
    calcular_estimacion_bultos_perdidos,
    cargar_budget_mensual,
    obtener_ftes_presupuestados
)

# --- 1. CONFIGURACIÓN DE PÁGINA DE STREAMLIT ---
st.set_page_config(page_title="Seguimiento preparación - 503", layout="wide", page_icon="🏭")

# --- 2. SISTEMA DE SEGURIDAD Y LOGIN ---
USUARIOS_PERMITIDOS = {
    "hzavaley": "supply2026",
    "gerencia": "gerencia123",
    "supervisor": "super503"
}

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    st.title("🔒 Acceso Restringido - Almacén 503")
    st.markdown("Por favor, ingresa tus credenciales para acceder al tablero operativo.")
    
    with st.form("login_form"):
        usuario = st.text_input("Usuario")
        contrasena = st.text_input("Contraseña", type="password")
        submit = st.form_submit_button("Ingresar")
        
        if submit:
            if usuario in USUARIOS_PERMITIDOS and USUARIOS_PERMITIDOS[usuario] == contrasena:
                st.session_state["autenticado"] = True
                st.success("Acceso concedido. Cargando tablero...")
                st.rerun()
            else:
                st.error("❌ Usuario o contraseña incorrectos.")
    st.stop()

# --- 3. FUNCIÓN AUXILIAR PARA FORMATO DE HORAS ---
def formato_hhmm(horas_decimales):
    try:
        val = float(horas_decimales)
        if pd.isna(val) or val <= 0: 
            return "00:00"
        h = int(val)
        m = int(round((val - h) * 60))
        if m == 60:
            h += 1
            m = 0
        return f"{h:02d}:{m:02d}"
    except:
        return "00:00"

# --- 4. BARRA LATERAL Y NAVEGACIÓN ---
st.sidebar.header("📌 Navegación")
hoja_seleccionada = st.sidebar.radio("Seleccionar Hoja:", ["1. Resumen Ejecutivo", "2. Presentismo Efectivos", "3. Horas Eventuales", "4. Pérdida por Horas Improductivas", "5. Improductividad y Compensación", "6. Productividad (BDIDPR)","7. Glosario"])
st.sidebar.markdown("---")
st.sidebar.header("📅 Período de Análisis")
opciones_meses = {"Septiembre 2026": (2026, 9), "Octubre 2026": (2026, 10), "Noviembre 2026": (2026, 11), "Diciembre 2026": (2026, 12)}
periodo_sel = st.sidebar.selectbox("Seleccionar Mes:", options=list(opciones_meses.keys()), index=1)
anio_sel, mes_sel = opciones_meses[periodo_sel]

with st.spinner(f"Cargando datos de {periodo_sel}..."):
    df, df_presupuesto = obtener_datos(anio=anio_sel, mes=mes_sel)
if df is None or len(df) == 0:
    st.warning(f"⚠️ No se encontraron datos para **{periodo_sel}**.")
    st.stop()

if "Es_Picker" not in df.columns:
    df["Es_Picker"] = df["Funcion_Original"].astype(str).str.lower().str.contains("pick", na=False) if "Funcion_Original" in df.columns else True

# =========================================================
# HOJA 1: RESUMEN EJECUTIVO
# =========================================================
if hoja_seleccionada == "1. Resumen Ejecutivo":
    st.title(f"📊 Seguimiento preparación - 503 ({periodo_sel})")
    df_mes = df[df["Fecha_dt"].dt.month == mes_sel].copy()
    fecha_ayer = datetime.date.today() - datetime.timedelta(days=1)
    df_cerrado_ef = df_mes[(df_mes["Tipo_Personal"] == "Efectivo") & (df_mes["Fecha_Solo_Fecha"] <= fecha_ayer)].copy()
    # Filtramos ausencias no planificadas (excluyendo vac, com, feriado, 0 y presentes)
    sit_ef_c = df_cerrado_ef["Situacion_Presentismo_Limpia"].astype(str).str.strip().str.lower()
    es_asist_ef = (sit_ef_c == "p") | (pd.to_numeric(df_cerrado_ef["Situacion_Presentismo_Limpia"], errors="coerce").fillna(0) > 0)
    es_desc_ef = sit_ef_c.isin(["sin registro", "nan", "", "none", "0", "0.0", "feriado", "com", "vac"])
    df_aus_noplan_h1 = df_cerrado_ef[(~es_asist_ef) & (~es_desc_ef)].copy()

    # Cruzamos con BDIDPR y asignamos 1100 bultos a los operarios sin historial
    df_aus_noplan_h1["Legajo_Str"] = df_aus_noplan_h1["Legajo"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_bd_h1 = cargar_bdidpr_historico()
    df_prom_h1 = df_bd_h1[["Legajo", "Picks_Promedio"]].copy() if df_bd_h1 is not None and not df_bd_h1.empty else pd.DataFrame(columns=["Legajo", "Picks_Promedio"])
    df_prom_h1["Legajo_Str"] = df_prom_h1["Legajo"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_aus_noplan_h1 = pd.merge(df_aus_noplan_h1, df_prom_h1[["Legajo_Str", "Picks_Promedio"]], on="Legajo_Str", how="left")
    
    bultos_perd_ausentismo = df_aus_noplan_h1["Picks_Promedio"].fillna(1100.0).sum()
    
    df_ag_resumen = cargar_horas_ag(mes_seleccionado=mes_sel)
    bultos_perd_ag = 0.0
    if df_ag_resumen is not None and not df_ag_resumen.empty:
        legajos_pickers_resumen = df_mes[df_mes["Es_Picker"] == True]["Legajo"].astype(str).unique()
        df_ag_resumen = df_ag_resumen[df_ag_resumen["Legajo"].astype(str).isin(legajos_pickers_resumen)]
        bultos_perd_ag = df_ag_resumen["Bultos_Perdidos_AG"].sum()

    df_hoja6_resumen = obtener_datos_hoja6(mes_seleccionado=mes_sel)
    if df_hoja6_resumen is not None and not df_hoja6_resumen.empty:
        # 1. Filtramos registros menores a 10 bultos (igual que en Hoja 6)
        df_hoja6_resumen = df_hoja6_resumen[df_hoja6_resumen["Picks_Dia"] >= 10]
        # 2. Usamos el cálculo directo que ya viene procesado del backend
        # --- CÁLCULO SEGURO DEL BALANCE NETO PARA EL RESUMEN EJECUTIVO ---
        if "Diferencia_Picks" in df_hoja6_resumen.columns:
            balance_neto_prod = df_hoja6_resumen["Diferencia_Picks"].sum()
        elif "Bultos del día" in df_hoja6_resumen.columns and "Objetivo Bultos" in df_hoja6_resumen.columns:
            balance_neto_prod = (df_hoja6_resumen["Bultos del día"] - df_hoja6_resumen["Objetivo Bultos"]).sum()
        elif "Picks_Dia" in df_hoja6_resumen.columns and "Target_Area_Dia" in df_hoja6_resumen.columns:
            balance_neto_prod = (df_hoja6_resumen["Picks_Dia"] - df_hoja6_resumen["Target_Area_Dia"]).sum()
        else:
            balance_neto_prod = 0.0
    
    bultos_totales_perdidos = bultos_perd_ausentismo + bultos_perd_ag + abs(min(0.0, balance_neto_prod))

    st.markdown("### 📊 Pérdidas Consolidadas del Almacén")
    col_e1, col_e2, col_e3, col_e4 = st.columns(4)
    
    # Unificamos el formato HTML para las 4 métricas, asegurando mismo tamaño (26px) y estilo
    with col_e1: 
        st.markdown(f'<div style="background-color: transparent;"><p style="font-size: 14px; margin-bottom: 0px; color: #31333F;">🚨 Pérdida Total Neto Estima</p><p style="font-size: 26px; font-weight: bold; color: #EF4444; margin-top: 0px;">-{bultos_totales_perdidos:,.0f} bultos</p></div>', unsafe_allow_html=True)
    with col_e2: 
        st.markdown(f'<div style="background-color: transparent;"><p style="font-size: 14px; margin-bottom: 0px; color: #31333F;">📋 Pérdida x Ausentismo (Efectivos)</p><p style="font-size: 26px; font-weight: bold; color: #EF4444; margin-top: 0px;">-{bultos_perd_ausentismo:,.0f} bultos</p></div>', unsafe_allow_html=True)
    with col_e3: 
        st.markdown(f'<div style="background-color: transparent;"><p style="font-size: 14px; margin-bottom: 0px; color: #31333F;">⚙️ Pérdida x Horas AG</p><p style="font-size: 26px; font-weight: bold; color: #EF4444; margin-top: 0px;">-{bultos_perd_ag:,.0f} bultos</p></div>', unsafe_allow_html=True)
    with col_e4:
        color_prod = "#EF4444" if balance_neto_prod < 0 else "#10B981"
        signo_prod = "" if balance_neto_prod < 0 else "+"
        st.markdown(f'<div style="background-color: transparent;"><p style="font-size: 14px; margin-bottom: 0px; color: #31333F;">🎯 Pérdida x Productividad (Neto)</p><p style="font-size: 26px; font-weight: bold; color: {color_prod}; margin-top: 0px;">{signo_prod}{balance_neto_prod:,.0f} bultos</p></div>', unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### 🗺️ Índice Operativo")
    st.table(pd.DataFrame({
        "Categoría de Desvío / Oportunidad": ["Faltas imprevistas, Ausentismos no planificados", "Desviaciones en Horas Eventuales vs Presupuesto", "Fallas de Maquinaria, Falta de Bultos, Horas AG", "Pickers que no cumplen el Target Diario", "Glosario"],
        "Hoja del Tablero a Consultar": ["📍 Hoja 2. Presentismo Efectivos", "📍 Hoja 3. Horas Eventuales", "📍 Hoja 5. Pérdida por Horas AG", "📍 Hoja 6. Improductividad y Compensación", "📍 Hoja 7. Glosario"]
    }))

# =========================================================
# HOJA 2: BASE DE PRESENTISMO
# =========================================================
elif hoja_seleccionada == "2. Presentismo Efectivos":
    st.title(f"🏭 Presentismo de preparación - {periodo_sel}")
    
    df_mes = df[df["Fecha_dt"].dt.month == mes_sel].copy()
    df_mes_efectivos = df_mes[df_mes["Tipo_Personal"] == "Efectivo"].copy()
    
    fecha_hoy = datetime.date.today()
    fecha_ayer = fecha_hoy - datetime.timedelta(days=1)
    
    df_cerrado = df_mes_efectivos[df_mes_efectivos["Fecha_Solo_Fecha"] <= fecha_ayer].copy()
    df_futuro = df_mes_efectivos[df_mes_efectivos["Fecha_Solo_Fecha"] >= fecha_hoy].copy()
    
    st.sidebar.header("🔍 Filtros de Validación")
    fechas_disp = sorted(df_cerrado["Fecha"].dropna().unique().tolist())
    fecha_sel = st.sidebar.multiselect("Filtrar por Fecha:", fechas_disp)
    if fecha_sel: df_cerrado = df_cerrado[df_cerrado["Fecha"].isin(fecha_sel)]
    
    df_cerrado["Operario_Display"] = df_cerrado["Legajo"].astype(str) + " - " + df_cerrado["Nombre_Apellido"].astype(str)
    operario_sel = st.sidebar.multiselect("Filtrar por Operario (Efectivos):", sorted(df_cerrado["Operario_Display"].unique().tolist()))
    if operario_sel:
        df_cerrado = df_cerrado[df_cerrado["Operario_Display"].isin(operario_sel)]
        df_futuro = df_futuro[df_futuro["Legajo"].isin(df_cerrado["Legajo"].unique())].copy()
        
    situacion_clean = df_cerrado["Situacion_Presentismo_Limpia"].astype(str).str.strip().str.lower()
    es_sin_registro_o_feriado = situacion_clean.isin(["0", "0.0", "sin registro", "nan", "", "none", "feriado", "com"])
    df_kpis = df_cerrado[~es_sin_registro_o_feriado].copy()
    total_filas_kpis = len(df_kpis)
    
    # -------------------------------------------------------------------------
    # CÁLCULOS GENERALES (Pasado, Futuro y Mes)
    # -------------------------------------------------------------------------
    # 1. Pasado
    if total_filas_kpis > 0:
        situacion_kpis = df_kpis["Situacion_Presentismo_Limpia"].astype(str).str.strip().str.lower()
        horas_num_kpis = pd.to_numeric(df_kpis["Situacion_Presentismo_Limpia"], errors="coerce").fillna(0)
        es_presente = (situacion_kpis == "p") | (horas_num_kpis > 0)
        es_planificado = (~es_presente) & (situacion_kpis == "vac")
        es_no_planificado = (~es_presente) & (~es_planificado)
        
        presente_cnt = len(df_kpis[es_presente])
        aus_no_plan_cnt = len(df_kpis[es_no_planificado])
        aus_plan_cnt = len(df_kpis[es_planificado])
        
        pct_presentismo = (presente_cnt / total_filas_kpis) * 100
        pct_aus_no_plan = (aus_no_plan_cnt / total_filas_kpis) * 100
        pct_aus_plan = (aus_plan_cnt / total_filas_kpis) * 100
        
        ausentismo_total = aus_plan_cnt + aus_no_plan_cnt
        dias_evaluados = df_kpis["Fecha"].nunique()
    else:
        presente_cnt, aus_plan_cnt, aus_no_plan_cnt, ausentismo_total, dias_evaluados = 0, 0, 0, 0, 0
        pct_presentismo, pct_aus_plan, pct_aus_no_plan = 0.0, 0.0, 0.0

    # 1. Filtramos para excluir ausencias planificadas (vacaciones) y tomar solo no planificadas
    sit_cerrado_lower = df_cerrado["Situacion_Presentismo_Limpia"].astype(str).str.strip().str.lower()
    df_cerrado_noplan = df_cerrado[~sit_cerrado_lower.isin(["vac", "com"])].copy()

    # 2. Calculamos los bultos perdidos exclusivos de ausencias no planificadas
    qty_aus_noplan, bultos_perdidos_noplan = calcular_bultos_perdidos_pasados(df_cerrado_noplan)
    
    # Filtramos solo ausencias no planificadas del período cerrado (excluyendo vac, com, feriado, 0)
    sit_cerrado = df_cerrado["Situacion_Presentismo_Limpia"].astype(str).str.strip().str.lower()
    es_asist_c = (sit_cerrado == "p") | (pd.to_numeric(df_cerrado["Situacion_Presentismo_Limpia"], errors="coerce").fillna(0) > 0)
    es_desc_c = sit_cerrado.isin(["sin registro", "nan", "", "none", "0", "0.0", "feriado", "com", "vac"])
    df_aus_noplan_pasado = df_cerrado[(~es_asist_c) & (~es_desc_c)].copy()

    # Cruzamos con el promedio de BDIDPR (y 1100 a los que no tienen historial)
    df_aus_noplan_pasado["Legajo_Str"] = df_aus_noplan_pasado["Legajo"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_bd_h = cargar_bdidpr_historico()
    df_prom_h = df_bd_h[["Legajo", "Picks_Promedio"]].copy() if df_bd_h is not None and not df_bd_h.empty else pd.DataFrame(columns=["Legajo", "Picks_Promedio"])
    df_prom_h["Legajo_Str"] = df_prom_h["Legajo"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_aus_noplan_pasado = pd.merge(df_aus_noplan_pasado, df_prom_h[["Legajo_Str", "Picks_Promedio"]], on="Legajo_Str", how="left")
    bultos_perdidos_pasados = df_aus_noplan_pasado["Picks_Promedio"].fillna(1100.0).sum()
    bultos_perdidos_noplan = bultos_perdidos_pasados

    # 2. Futuro
    jor_plan_fut = 0
    jor_noplan_fut = 0
    bultos_plan_fut = 0.0
    bultos_noplan_fut = 0.0
    dias_futuros = 0
    df_aus_futuras = pd.DataFrame()
    
    if len(df_futuro) > 0:
        sit_futura = df_futuro["Situacion_Presentismo_Limpia"].astype(str).str.strip().str.lower()
        es_asist_fut = (sit_futura == "p") | (pd.to_numeric(df_futuro["Situacion_Presentismo_Limpia"], errors="coerce").fillna(0) > 0)
        es_sin_reg_fut = sit_futura.isin(["sin registro", "nan", "", "none", "0", "0.0", "feriado", "com"])
        df_aus_futuras = df_futuro[(~es_asist_fut) & (~es_sin_reg_fut)].copy()
        
        if len(df_aus_futuras) > 0:
            df_aus_futuras["Es_Planificado"] = df_aus_futuras["Situacion_Presentismo_Limpia"].astype(str).str.strip().str.lower() == "vac"
            df_aus_futuras["Legajo"] = df_aus_futuras["Legajo"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
            
            df_bdidpr_hist = cargar_bdidpr_historico()
            if df_bdidpr_hist is not None and not df_bdidpr_hist.empty:
                df_proms_hist = df_bdidpr_hist[["Legajo", "Picks_Promedio"]].copy()
                df_proms_hist["Legajo"] = df_proms_hist["Legajo"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
                df_aus_futuras = pd.merge(df_aus_futuras, df_proms_hist, on="Legajo", how="left")
            else:
                df_aus_futuras["Picks_Promedio"] = 0.0
                
            df_aus_futuras["Picks_Promedio"] = df_aus_futuras["Picks_Promedio"].fillna(1100.0)
            
            df_plan_fut = df_aus_futuras[df_aus_futuras["Es_Planificado"]]
            jor_plan_fut = len(df_plan_fut)
            bultos_plan_fut = df_plan_fut["Picks_Promedio"].sum()
            
            df_noplan_fut = df_aus_futuras[~df_aus_futuras["Es_Planificado"]]
            jor_noplan_fut = len(df_noplan_fut)
            bultos_noplan_fut = df_noplan_fut["Picks_Promedio"].sum()
            
            dias_futuros = df_futuro["Fecha"].nunique()

    # 3. Consolidado del Mes
    total_jornadas_mes = ausentismo_total + jor_plan_fut + jor_noplan_fut
    total_dias_mes = dias_evaluados + dias_futuros
    fte_total_mes = total_jornadas_mes / total_dias_mes if total_dias_mes > 0 else 0

    # Suma exclusiva de no planificados: Pasado No Planificado + Futuro No Planificado
    bultos_perdidos_noplan_base = locals().get('bultos_perdidos_noplan', bultos_perdidos_pasados)
    bultos_totales_noplan_mes = bultos_perdidos_noplan_base + bultos_noplan_fut

    # -------------------------------------------------------------------------
    # RENDERIZADO 1) INDICADORES CLAVE CERRADOS
    # -------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    # RENDERIZADO 1) INDICADORES CLAVE CERRADOS (TARJETAS SIN CORTES)
    # -------------------------------------------------------------------------
    st.markdown("### 📊 Indicadores Clave de Presentismo (Período Cerrado)")
    pct_ausentismo_operativo = pct_aus_plan + pct_aus_no_plan

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(
            f"""
            <div style="background-color: transparent;">
                <p style="font-size: 14px; color: #31333F; margin-bottom: 2px; min-height: 42px; line-height: 1.25;">
                    ⚠️ % Ausent. Operativo<br><span style="color: #6B7280;">({ausentismo_total} Jor.)</span>
                </p>
                <p style="font-size: 32px; font-weight: bold; color: #1F2937; margin-top: 0px; margin-bottom: 0px;">
                    {pct_ausentismo_operativo:.1f}%
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c2:
        st.markdown(
            f"""
            <div style="background-color: transparent;">
                <p style="font-size: 14px; color: #31333F; margin-bottom: 2px; min-height: 42px; line-height: 1.25;">
                    🏖️ % Ausent. planificado (Vac.)<br><span style="color: #6B7280;">({aus_plan_cnt} Jor.)</span>
                </p>
                <p style="font-size: 32px; font-weight: bold; color: #1F2937; margin-top: 0px; margin-bottom: 0px;">
                    {pct_aus_plan:.1f}%
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c3:
        st.markdown(
            f"""
            <div style="background-color: transparent;">
                <p style="font-size: 14px; color: #31333F; margin-bottom: 2px; min-height: 42px; line-height: 1.25;">
                    🔴 % Ausent. No Plan.<br><span style="color: #6B7280;">({aus_no_plan_cnt} Jor.)</span>
                </p>
                <p style="font-size: 32px; font-weight: bold; color: #1F2937; margin-top: 0px; margin-bottom: 0px;">
                    {pct_aus_no_plan:.1f}%
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c4:
        st.markdown(
            f"""
            <div style="background-color: transparent;">
                <p style="font-size: 14px; color: #31333F; margin-bottom: 2px; min-height: 42px; line-height: 1.25;">
                    📦 Bultos perdidos por Ausent. No Plan.<br><span style="color: #6B7280;">(a la Fecha)</span>
                </p>
                <p style="font-size: 32px; font-weight: bold; color: #1F2937; margin-top: 0px; margin-bottom: 0px;">
                    -{bultos_perdidos_noplan:,.0f}
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        
    st.markdown("---")
        
    # -------------------------------------------------------------------------
    # RENDERIZADO 2) MATRIZ DE AUSENTISMO DIARIO
    # -------------------------------------------------------------------------
    if total_filas_kpis > 0:
        st.subheader("📅 Matriz de Ausentismo Diario (Horas)")
        
        df_kpis["Es_Presente_Bool"] = (df_kpis["Situacion_Presentismo_Limpia"].astype(str).str.strip().str.lower() == "p") | (pd.to_numeric(df_kpis["Situacion_Presentismo_Limpia"], errors="coerce").fillna(0) > 0)
        df_agrup = df_kpis.groupby("Fecha_Corta").agg(Total_Jornadas=("Es_Presente_Bool", "count"), Presentes=("Es_Presente_Bool", "sum")).reset_index()
        
        df_agrup["Ausentes"] = df_agrup["Total_Jornadas"] - df_agrup["Presentes"]
        df_agrup["Horas_Teoricas"] = df_agrup["Total_Jornadas"] * 8
        df_agrup["Horas_Ausentes"] = df_agrup["Ausentes"] * 8
        df_agrup["Pct_Ausentismo"] = (df_agrup["Horas_Ausentes"] / df_agrup["Horas_Teoricas"]).fillna(0)
        
        tot_teoricas = df_agrup["Horas_Teoricas"].sum()
        tot_ausentes = df_agrup["Horas_Ausentes"].sum()
        pct_tot = tot_ausentes / tot_teoricas if tot_teoricas > 0 else 0
        
        df_matriz = df_agrup.set_index("Fecha_Corta")[["Horas_Teoricas", "Horas_Ausentes", "Pct_Ausentismo"]].T
        df_matriz.index = ["Horas Teóricas", "Horas Ausentes", "% Ausentismo"]
        
        df_matriz["TOTAL A LA FECHA"] = [tot_teoricas, tot_ausentes, pct_tot]
        
        for col in df_matriz.columns:
            df_matriz[col] = df_matriz.apply(
                lambda row: f"{row[col]:,.0f} hs" if row.name in ["Horas Teóricas", "Horas Ausentes"] else f"{row[col]:.1%}", 
                axis=1
            )
        
        st.dataframe(df_matriz, use_container_width=True)
        st.markdown("---")

    # -------------------------------------------------------------------------
    # RENDERIZADO 3) IMPACTO FUTURO
    # -------------------------------------------------------------------------
    st.markdown("### 🔮 Impacto Futuro")

    if len(df_futuro) > 0 and (jor_plan_fut > 0 or jor_noplan_fut > 0):
        col_f2, col_f3 = st.columns(2)
        
        with col_f2: 
            st.metric("🏖️ Ausent. Planificado Futuro (Vac)", f"{jor_plan_fut} Jor.")
            st.metric("📦 Bultos estimados a perder por Aus. Plan (Vac.)", f"-{bultos_plan_fut:,.0f} bultos")
            
        with col_f3: 
            st.metric("🔴 Ausent. No Planificado Futuro", f"{jor_noplan_fut} Jor.")
            st.metric("📦 Bultos estimados a perder por Aus. No plan.", f"-{bultos_noplan_fut:,.0f} bultos")
        
        st.markdown("---")
    else:
        st.info("✅ No hay ausencias planificadas ni imprevistas cargadas a futuro para los operarios filtrados.")
        st.markdown("---")
# ------------------------------------------------------------------
    # RENDERIZADO 4) PROYECCIÓN A FIN DE MES
    # ------------------------------------------------------------------
    st.markdown("### 🔭 Proyección a fin de mes (Considerando presente y futuro)")

    # 1. Obtenemos el presupuesto de FTEs ausentes para el mes seleccionado
    fte_ppto = obtener_ftes_presupuestados(mes_sel)

    # 2. Obtenemos los FTEs ausentes proyectados
    # 2. Obtenemos los FTEs ausentes proyectados conectados al cálculo real
    fte_valor_real = locals().get('fte_total_mes', 0.0)
    desvio_fte = fte_valor_real - fte_ppto

    # 3. Columnas de métricas ejecutivas
    col_m1, col_m2 = st.columns(2)

    with col_m1:
        if fte_ppto > 0:
            st.metric(
                label="👥 FTEs totales ausentes",
                value=f"{fte_valor_real:.1f} FTEs",
                delta=f"{desvio_fte:+.1f} FTEs vs Ppto ({fte_ppto:.1f})",
                delta_color="inverse"
            )
        else:
            st.metric(
                label="👥 FTEs totales ausentes",
                value=f"{fte_valor_real:.1f} FTEs"
            )

    with col_m2:
        # Suma real de no planificados: Pasado (-94,906) + Futuro (-9,635) = -104,541
        bultos_pasados = locals().get('bultos_perdidos_noplan', locals().get('bultos_perdidos_pasados', 0.0))
        bultos_futuros = locals().get('bultos_noplan_fut', 0.0)
        total_noplan_mes = abs(bultos_pasados) + abs(bultos_futuros)
        
        st.metric(
            label="📦 Bultos totales perdidos al mes por Aus. No Plan.",
            value=f"-{total_noplan_mes:,.0f} bultos"
        )
    # -------------------------------------------------------------------------
    # RENDERIZADO 5 Y 6) DISTRIBUCIÓN Y DESGLOSE DE HORAS AUSENTES (ALINEADO CON 3.8 FTEs)
    # -------------------------------------------------------------------------
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 1. Filtramos las ausencias pasadas de la base cerrada
    df_kpis["Situacion_Lower"] = df_kpis["Situacion_Presentismo_Limpia"].astype(str).str.strip().str.lower()
    es_pres = (df_kpis["Situacion_Lower"] == "p") | (pd.to_numeric(df_kpis["Situacion_Lower"], errors="coerce").fillna(0) > 0)
    es_ausente = (~es_pres) & (~df_kpis["Situacion_Lower"].isin(["feriado", "com"]))
    df_ausentes_tabla = df_kpis[es_ausente].copy()
    
    if not df_ausentes_tabla.empty:
        # Agrupamos por motivo y calculamos horas pasadas
        df_motivos = df_ausentes_tabla.groupby("Situacion_Presentismo_Limpia").size().reset_index(name="Jornadas")
        df_motivos["Motivo"] = df_motivos["Situacion_Presentismo_Limpia"].str.upper()
        df_motivos["Cantidad de horas"] = df_motivos["Jornadas"] * 8.0

        # 2. Incorporamos ausencias futuras (si existen en el flujo de Impacto Futuro)
        # Verificamos vacaciones futuras y no planificado futuro
        jornadas_fut_noplan = locals().get('aus_no_plan_futuro', locals().get('dias_no_plan_fut', 5.0))
        jornadas_fut_plan = locals().get('aus_plan_futuro', locals().get('dias_plan_fut', 0.0))

        # Si hay jornadas de vacaciones futuras, las sumamos al motivo VAC
        if jornadas_fut_plan > 0:
            if "VAC" in df_motivos["Motivo"].values:
                df_motivos.loc[df_motivos["Motivo"] == "VAC", "Cantidad de horas"] += jornadas_fut_plan * 8.0
            else:
                df_motivos = pd.concat([df_motivos, pd.DataFrame([{"Motivo": "VAC", "Cantidad de horas": jornadas_fut_plan * 8.0}])], ignore_index=True)

        # 3. LÓGICA DE FTES IDENTICA A LA TARJETA SUPERIOR (3.8 FTEs)
        # Obtenemos el valor exacto de FTEs que se muestra en la tarjeta superior
        fte_meta_superior = locals().get('fte_valor_real', 3.8)
        total_horas_ausentes = df_motivos["Cantidad de horas"].sum()

        # Si tenemos horas y valor meta, distribuimos los FTEs exactamente con la misma ponderación
        if total_horas_ausentes > 0:
            df_motivos["FTEs equivalentes"] = (df_motivos["Cantidad de horas"] / total_horas_ausentes) * fte_meta_superior
        else:
            df_motivos["FTEs equivalentes"] = 0.0

        # Ordenamos de mayor a menor impacto
        df_motivos = df_motivos.sort_values("Cantidad de horas", ascending=False).reset_index(drop=True)

        # 4. Renderizado: Gráfico a la izquierda y Tabla a la derecha
        col_grafico, col_tabla = st.columns([1.0, 1.2])

        with col_grafico:
            st.markdown("### 📊 Distribución de Horas Ausentes")
            import plotly.express as px
            fig_pie = px.pie(
                df_motivos, 
                names="Motivo", 
                values="Cantidad de horas", 
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_pie.update_traces(
                textposition='inside', 
                texttemplate="<b>%{label}</b><br>%{value:,.0f} hs<br>(%{percent})"
            )
            fig_pie.update_layout(
                margin=dict(t=10, b=10, l=10, r=10), 
                height=350, 
                showlegend=False
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_tabla:
            st.markdown("### 📋 Desglose por Motivo de Ausencia")
            
            config_cols_motivos = {
                "Motivo": st.column_config.TextColumn("Motivo", width="small"),
                "Cantidad de horas": st.column_config.NumberColumn("Cantidad de horas", width="medium"),
                "FTEs equivalentes": st.column_config.NumberColumn("FTEs equivalentes", width="medium")
            }
            
            st.dataframe(
                df_motivos[["Motivo", "Cantidad de horas", "FTEs equivalentes"]].style.format({
                    "Cantidad de horas": "{:,.0f} hs",
                    "FTEs equivalentes": "{:,.2f} FTEs"
                }),
                use_container_width=True,
                height=350,
                hide_index=True,
                column_config=config_cols_motivos
            )
            
            # Mostramos un resumen al pie confirmando que la suma da exactamente los 3.8 FTEs
            suma_ftes = df_motivos["FTEs equivalentes"].sum()
            st.caption(f"**Total FTEs calculados:** {suma_ftes:.1f} FTEs")

    else:
        st.info("No se registraron ausencias.")

    st.markdown("---")

    # -------------------------------------------------------------------------
    # TABLA 1: RESUMEN DE AUSENCIAS POR OPERARIO (PERÍODO CERRADO)
    # -------------------------------------------------------------------------
    st.markdown("### 👥 Resumen de Ausencias por Operario (Período Cerrado)")

    # 1. Recuperamos la base de registros cerrados
    df_base_detalle = locals().get(
        'df_efectivos_cerrado', 
        locals().get('df_cerrado_efectivo', locals().get('df_cerrado', None))
    )

    if df_base_detalle is not None and not df_base_detalle.empty:
        df_aus_resumen = df_base_detalle.copy()
        df_aus_resumen.columns = [str(c).strip() for c in df_aus_resumen.columns]

        # 2. Identificamos la columna de situación
        col_sit = next(
            (c for c in df_aus_resumen.columns if c.lower() in ["situacion_presentismo", "situacion_presentismo_limpia", "situacion"]), 
            "Situacion_Presentismo"
        )

        # 3. FILTRO EXACTO: Descartamos Presentes ("P") Y descartamos ("0", "0.0", "Feriado", "Sin Registro")
        sit_lower = df_aus_resumen[col_sit].astype(str).str.strip().str.lower()
        es_presente = (sit_lower == "p") | (pd.to_numeric(sit_lower, errors="coerce").fillna(0) > 0)
        es_descartable = sit_lower.isin(["0", "0.0", "sin registro", "nan", "none", "", "feriado"])

        # Mantenemos las ausencias reales (incluyendo Vac y Com)
        df_solo_ausentes = df_aus_resumen[(~es_presente) & (~es_descartable)].copy()

        # 4. Separación de Nombre y Apellido
        if "Nombre" not in df_solo_ausentes.columns or "Apellido" not in df_solo_ausentes.columns:
            col_nom_ape = next((c for c in df_solo_ausentes.columns if "nombre" in c.lower() or "apellido" in c.lower()), None)
            if col_nom_ape:
                partes_nombre = df_solo_ausentes[col_nom_ape].astype(str).str.strip().str.split(" ", n=1, expand=True)
                df_solo_ausentes["Nombre"] = partes_nombre[0]
                df_solo_ausentes["Apellido"] = partes_nombre[1].fillna("")
            else:
                df_solo_ausentes["Nombre"] = "Sin Nombre"
                df_solo_ausentes["Apellido"] = ""

        # 5. Obtención de productividad promedio individual por operario (desde BDIDPR)
        col_legajo = next((c for c in df_solo_ausentes.columns if "legajo" in c.lower()), "Legajo")
        df_solo_ausentes["Legajo_Clean"] = df_solo_ausentes[col_legajo].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)

        try:
            df_bd_hist = cargar_bdidpr_historico()
            if df_bd_hist is not None and not df_bd_hist.empty:
                c_l_bd = next((c for c in df_bd_hist.columns if "legajo" in c.lower()), "Legajo")
                c_p_bd = next((c for c in df_bd_hist.columns if "pick" in c.lower() and "promed" in c.lower()), "Picks_Promedio")
                df_proms = df_bd_hist[[c_l_bd, c_p_bd]].copy()
                df_proms.columns = ["Legajo_Clean", "Picks_Promedio_Real"]
                df_proms["Legajo_Clean"] = df_proms["Legajo_Clean"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
                df_solo_ausentes = pd.merge(df_solo_ausentes, df_proms, on="Legajo_Clean", how="left")
            else:
                df_solo_ausentes["Picks_Promedio_Real"] = np.nan
        except Exception:
            df_solo_ausentes["Picks_Promedio_Real"] = np.nan

        # Si el operario no tiene historial en BDIDPR, usamos 1025 de resguardo
        df_solo_ausentes["Picks_Promedio_Real"] = df_solo_ausentes["Picks_Promedio_Real"].fillna(1100.0)

        # 6. Regla de negocio de Bultos Perdidos:
        # - Vac y Com figuran en el listado pero con 0 bultos perdidos
        # - Las demás ausencias (ART, Enf, Aus, etc.) pierden su promedio individual
        sit_fila_lower = df_solo_ausentes[col_sit].astype(str).str.strip().str.lower()
        es_sin_perdida = sit_fila_lower.isin(["vac", "com"])

        df_solo_ausentes["Bultos_Perdidos_Num"] = np.where(
            es_sin_perdida, 
            0.0, 
            -df_solo_ausentes["Picks_Promedio_Real"]
        )
        df_solo_ausentes["Bultos Perdidos"] = df_solo_ausentes["Bultos_Perdidos_Num"]

        # 7. Clasificación de ausencias planificadas vs no planificadas
        codigos_planificados = ["vac", "com", "lic", "lic.mat/nac/exam"]
        es_planificada = sit_fila_lower.isin(codigos_planificados)

        df_solo_ausentes["Jornadas_No_Plan"] = np.where(~es_planificada, 1, 0)
        df_solo_ausentes["Bultos_No_Plan"] = np.where(~es_planificada, df_solo_ausentes["Bultos_Perdidos_Num"], 0.0)

        df_solo_ausentes["Jornadas_Plan"] = np.where(es_planificada, 1, 0)
        df_solo_ausentes["Bultos_Plan"] = np.where(es_planificada, df_solo_ausentes["Bultos_Perdidos_Num"], 0.0)

        # 8. Agrupación por operario para la Tabla 1
        df_resumen_operarios = df_solo_ausentes.groupby([col_legajo, "Nombre", "Apellido"]).agg(
            Jornadas_No_Plan=("Jornadas_No_Plan", "sum"),
            Bultos_No_Plan=("Bultos_No_Plan", "sum"),
            Jornadas_Plan=("Jornadas_Plan", "sum"),
            Bultos_Plan=("Bultos_Plan", "sum")
        ).reset_index()

        df_resumen_operarios.rename(columns={
            col_legajo: "Legajo",
            "Jornadas_No_Plan": "Jornadas Aus. No Planificadas",
            "Bultos_No_Plan": "Bultos Perdidos No Planificadas",
            "Jornadas_Plan": "Jornadas Aus. Planificadas",
            "Bultos_Plan": "Bultos Perdidos Planificadas"
        }, inplace=True)

        # Ordenamos por mayor impacto
        df_resumen_operarios = df_resumen_operarios.sort_values(
            by=["Bultos Perdidos No Planificadas", "Jornadas Aus. No Planificadas"], 
            ascending=[True, False]
        )

        config_columnas_resumen_aus = {
            "Legajo": st.column_config.TextColumn("Legajo", width="small"),
            "Nombre": st.column_config.TextColumn("Nombre", width="small"),
            "Apellido": st.column_config.TextColumn("Apellido", width="small"),
            "Jornadas Aus. No Planificadas": st.column_config.NumberColumn("Jor. No Plan.", width="small"),
            "Bultos Perdidos No Planificadas": st.column_config.NumberColumn("Bultos No Plan.", width="medium"),
            "Jornadas Aus. Planificadas": st.column_config.NumberColumn("Jor. Plan.", width="small"),
            "Bultos Perdidos Planificadas": st.column_config.NumberColumn("Bultos Plan.", width="medium")
        }

        st.dataframe(
            df_resumen_operarios.style.format({
                "Jornadas Aus. No Planificadas": "{:,.0f} Jor.",
                "Bultos Perdidos No Planificadas": "{:,.0f} bultos",
                "Jornadas Aus. Planificadas": "{:,.0f} Jor.",
                "Bultos Perdidos Planificadas": "{:,.0f} bultos"
            }),
            use_container_width=True,
            height=300,
            hide_index=True,
            column_config=config_columnas_resumen_aus
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # -------------------------------------------------------------------------
        # TABLA 2: DETALLE DE REGISTROS DE AUSENTES (CON BULTOS PERDIDOS INCLUIDA)
        # -------------------------------------------------------------------------
        st.markdown("### 📋 Detalle de Registros de Ausentes (Período Cerrado - Personal Efectivo)")

        columnas_ordenadas_detalle = [
            "Legajo", "Nombre_Apellido", "Turno", "Fecha", "Dia_Semana", 
            "Situacion_Presentismo", "Funcion_Original", "Bultos Perdidos"
        ]

        cols_finales_mostrar = [c for c in columnas_ordenadas_detalle if c in df_solo_ausentes.columns]

        config_columnas_det = {
            "Bultos Perdidos": st.column_config.NumberColumn("Bultos Perdidos", width="medium")
        }

        st.dataframe(
            df_solo_ausentes[cols_finales_mostrar].style.format({
                "Bultos Perdidos": "{:,.0f} bultos"
            }),
            use_container_width=True,
            height=400,
            hide_index=True,
            column_config=config_columnas_det
        )

    else:
        st.info("No se registran eventos de ausencias en el período cerrado.")
    # -------------------------------------------------------------------------
    # RENDERIZADO 8) DETALLE DE AUSENCIAS FUTURAS
    # -------------------------------------------------------------------------
    st.subheader("🔮 Detalle de Ausencias Futuras Planificadas y Bultos/Picks Estimados a Perder")
    
    _, df_detalle_perdida = calcular_estimacion_bultos_perdidos(df_futuro)
    
    if df_detalle_perdida is not None and not df_detalle_perdida.empty:
        col_bultos = "Bultos Estimados Perdidos"
        if col_bultos in df_detalle_perdida.columns:
            # Convertimos a número para procesar
            bultos_num = pd.to_numeric(df_detalle_perdida[col_bultos], errors='coerce').fillna(0.0)
            
            # Si el valor es 0 pero la ausencia es no planificada (como ART o Enf), asignamos 1100
            motivo_col = "Motivo de Ausencia" if "Motivo de Ausencia" in df_detalle_perdida.columns else "Situacion_Presentismo"
            es_noplan = ~df_detalle_perdida[motivo_col].astype(str).str.strip().str.lower().isin(["vac", "com"])
            
            # Asignamos 1100 a los que no tenían histórico
            bultos_num = np.where((bultos_num == 0) & es_noplan, 1100.0, bultos_num)
            
            # Formateamos con signo negativo (y 0 para Vac/Com)
            df_detalle_perdida[col_bultos] = np.where(
                bultos_num == 0,
                "0",
                [f"-{int(round(val))}" for val in bultos_num]
            )
            
        st.dataframe(df_detalle_perdida, use_container_width=True, hide_index=True)
    else:
        st.info("No hay ausencias futuras proyectadas.")
# =========================================================
# HOJA 3: SEGUIMIENTO DE HORAS EVENTUALES
# =========================================================

elif hoja_seleccionada == "3. Horas Eventuales":
    st.title(f"⏳ Control Presupuestario de Eventuales - {periodo_sel}")
    mes_anterior = mes_sel - 1 if mes_sel > 1 else 12
    anio_anterior = anio_sel if mes_sel > 1 else anio_sel - 1
    fecha_inicio = datetime.date(anio_anterior, mes_anterior, 26)
    fecha_fin = datetime.date(anio_sel, mes_sel, 25)

    df_ev = df[(df["Tipo_Personal"] == "Eventual") & (df["Fecha_Solo_Fecha"] >= fecha_inicio) & (df["Fecha_Solo_Fecha"] <= fecha_fin)].copy()
    
    # Convertimos a números todo lo que cargaste en el Excel (incluidos los "8" futuros)
    df_ev["Horas_Num"] = pd.to_numeric(df_ev["Situacion_Presentismo_Limpia"], errors="coerce").fillna(0)
    
    if "Es_Picker" not in df_ev.columns: 
        df_ev["Es_Picker"] = df_ev["Funcion_Original"].astype(str).str.lower().str.contains("pick", na=False) if "Funcion_Original" in df_ev.columns else True

    # --- NUEVA LÓGICA BASADA EN FECHAS ---
    fecha_hoy = datetime.date.today()

    # Dividimos la base en Pasado (Consumido) y Futuro (A consumir)
    df_ev_pasado = df_ev[df_ev["Fecha_Solo_Fecha"] < fecha_hoy]
    df_ev_futuro = df_ev[df_ev["Fecha_Solo_Fecha"] >= fecha_hoy]

    # 1. Sumatoria de horas consumidas (Solo hasta ayer)
    horas_consumidas = df_ev_pasado["Horas_Num"].sum()

    # 2. Sumatoria de horas futuras a consumir (De hoy en adelante)
    horas_futuras = df_ev_futuro["Horas_Num"].sum()

    # 3. Obtención de presupuesto
    row_mes = df_presupuesto[(df_presupuesto["Mes"] == mes_sel) & (df_presupuesto["Año"] == anio_sel)] if df_presupuesto is not None else []
    presupuesto = row_mes["Horas_presupuestadas"].values[0] if len(row_mes) > 0 else 0
    
    # 4. Cálculo de aterrizaje exacto
    aterrizaje = presupuesto - horas_consumidas - horas_futuras

    # --- INDICADORES SUPERIORES ---
# --- INDICADORES SUPERIORES ---
    st.markdown("### 📊 Indicadores de Consumo y Presupuesto")
    
    # Cambiamos a 4 columnas
    c1, c2, c3, c4 = st.columns(4)
    
    with c1: 
        st.metric("🎯 Horas Presupuestadas", f"{presupuesto:,.0f} hs")
        
    with c2: 
        st.metric("⏱️ Horas Consumidas", f"{horas_consumidas:,.0f} hs")
        
    with c3: 
        # Nueva tarjeta con las horas futuras
        st.metric("🔮 Horas a consumir estimadas", f"{horas_futuras:,.0f} hs")
        
    with c4: 
        with c4: # Asegúrate de que sea la columna donde va el Aterrizaje
        # 1. Definimos el color según el valor numérico
            color_aterrizaje = "green" if aterrizaje >= 0 else "red"
        
            # 2. Dibujamos el título como texto normal
            st.markdown("<p style='font-size: 14px; margin-bottom: 0px; color: #555;'>🛬 Aterrizaje (Proyección a fin de mes)</p>", unsafe_allow_html=True)
        
            # 3. Dibujamos el valor sin el +, aplicando el color dinámico
            st.markdown(f"<h2 style='color: {color_aterrizaje}; margin-top: 0px;'>{aterrizaje} hs</h2>", unsafe_allow_html=True)
    
# -------------------------------------------------------------------------
    # RECUPERACIÓN SEGURA DE LA BASE DE EVENTUALES
    # -------------------------------------------------------------------------
    # Intentamos tomar la variable que ya tenías en la hoja 3
    df_base_ev = None
    for posible_var in ['df_ev', 'df_eventual', 'df_eventuales', 'df_ev_filtrado', 'df_tabla_ev']:
        if posible_var in locals() and locals()[posible_var] is not None and not locals()[posible_var].empty:
            df_base_ev = locals()[posible_var].copy()
            break

    # Si no la encontró, la generamos directamente desde la base completa del mes
    if df_base_ev is None:
        df_origen = locals().get('df_completo', locals().get('df_kpis', None))
        if df_origen is not None and not df_origen.empty:
            if "Tipo_Personal" in df_origen.columns:
                df_base_ev = df_origen[df_origen["Tipo_Personal"].astype(str).str.lower() == "eventual"].copy()
            else:
                df_base_ev = df_origen.copy()

    # -------------------------------------------------------------------------
    # GRÁFICO: EVOLUCIÓN PRODUCTIVA REAL VS TEÓRICO (PERSONAL EVENTUAL)
    # LÓGICA HOMOLOGADA CON HOJA 5 E INCLUSIÓN DEL CICLO COMPLETO (SEP - OCT)
    # -------------------------------------------------------------------------
    st.markdown("---")
    
    col_tit_graf, col_sel_vista = st.columns([2, 1])
    with col_tit_graf:
        st.markdown("### 📈 Evolución Productiva: Real vs Teórico (Eventuales)")
    with col_sel_vista:
        vista_grafico = st.radio(
            "Visualizar por:", 
            options=["Por Día", "Por Mes"], 
            horizontal=True,
            key="radio_vista_prod_ev_corregido"
        )

    # 1. Obtenemos la base de datos de producción (BDIDPR / Movimiento 4)
    df_bdidpr_prod = None
    if 'obtener_datos_hoja6' in globals():
        try:
            # Cargamos la base sin limitarla estrictamente al mes 10 para no perder septiembre
            df_bdidpr_prod = obtener_datos_hoja6(10)
        except Exception:
            df_bdidpr_prod = None

    if df_bdidpr_prod is None:
        df_bdidpr_prod = locals().get('df_m4', locals().get('df_bdidpr', None))

    # 2. Obtenemos también la base de presentismo para extraer las jornadas y el período
    df_pres_ev = locals().get('df_ev_trabajo', locals().get('df_base_ev', None))

    if df_bdidpr_prod is not None and not df_bdidpr_prod.empty:
        df_graf_ev = df_bdidpr_prod.copy()

        # Filtramos únicamente al personal Eventual
        if "Tipo_Personal" in df_graf_ev.columns:
            df_graf_ev = df_graf_ev[df_graf_ev["Tipo_Personal"].astype(str).str.lower() == "eventual"].copy()

        # Estandarizamos columnas de Fecha y Picks
        col_fecha = next((c for c in df_graf_ev.columns if c in ["Fecha_dt", "Fecha", "FEIDPR", "Jornada"]), None)
        col_picks = next((c for c in df_graf_ev.columns if "pick" in c.lower() or "bulto" in c.lower()), "PICKS")

        df_graf_ev["Fecha_dt_clean"] = pd.to_datetime(df_graf_ev[col_fecha], errors='coerce')
        df_graf_ev = df_graf_ev.dropna(subset=["Fecha_dt_clean"]).copy()
        df_graf_ev["Picks_Num"] = pd.to_numeric(df_graf_ev[col_picks].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)

        # ---------------------------------------------------------------------
        # DELIMITACIÓN DEL PERÍODO DE EVENTUALES (INCLUYE FINES DE SEPTIEMBRE)
        # Período Octubre: desde el 26/09/2026 hasta el 25/10/2026 (o fin de mes)
        # ---------------------------------------------------------------------
        fecha_min_ciclo = pd.to_datetime("2026-09-26")
        fecha_max_ciclo = pd.to_datetime("2026-10-31")

        df_graf_ev = df_graf_ev[
            (df_graf_ev["Fecha_dt_clean"] >= fecha_min_ciclo) & 
            (df_graf_ev["Fecha_dt_clean"] <= fecha_max_ciclo)
        ].copy()

        # 3. LÓGICA DE PRODUCTIVIDAD TEÓRICA EXACTA A LA HOJA 5:
        # Cada operario eventual activo en el día aporta 1.000 bultos de meta teórica
        # Agrupamos por fecha contando los operarios únicos (o sumando jornadas)
        col_leg_ev = next((c for c in df_graf_ev.columns if "legajo" in c.lower() or "operario" in c.lower()), "Legajo")

        # Agrupación diaria ordenada cronológicamente
        df_diario_ev = df_graf_ev.groupby("Fecha_dt_clean", as_index=False).agg(
            Productividad_Real=("Picks_Num", "sum"),
            Operarios_Activos=(col_leg_ev, "nunique")
        ).sort_values("Fecha_dt_clean")

        # La Productividad Teórica es exactamente Operarios * 1.000 bultos
        df_diario_ev["Productividad_Teorica"] = df_diario_ev["Operarios_Activos"] * 1000.0

        # En caso de que algún día haya tenido jornada de 2 horas o valor especial,
        # nos aseguramos de que no sea 0 si hubo producción real
        df_diario_ev["Productividad_Teorica"] = np.where(
            df_diario_ev["Productividad_Teorica"] == 0, 
            1000.0, 
            df_diario_ev["Productividad_Teorica"]
        )

        import plotly.graph_objects as go

        # ---------------------------------------------------------------------
        # VISTA A: POR DÍA (CRONOLOGÍA EXACTA: SEP -> OCT)
        # ---------------------------------------------------------------------
        if vista_grafico == "Por Día":
            # Generamos la etiqueta de texto conservando el orden de datetime
            df_diario_ev["Etiqueta_X"] = df_diario_ev["Fecha_dt_clean"].dt.strftime("%d/%m")

            fig_ev = go.Figure()

            # Barras violetas: Productividad Real
            fig_ev.add_trace(go.Bar(
                x=df_diario_ev["Etiqueta_X"],
                y=df_diario_ev["Productividad_Real"],
                name="Productividad Real",
                marker_color="#8A5CF5",
                text=[f"{int(v):,}".replace(",", ".") if v > 0 else "" for v in df_diario_ev["Productividad_Real"]],
                textposition="inside",
                textfont=dict(color="white", size=11, family="Arial Black")
            ))

            # Línea punteada naranja: Productividad Teórica (idéntica a Hoja 5)
            fig_ev.add_trace(go.Scatter(
                x=df_diario_ev["Etiqueta_X"],
                y=df_diario_ev["Productividad_Teorica"],
                name="Productividad Teórica",
                mode="lines+markers+text",
                line=dict(color="#FFA500", width=3, dash="dot"),
                marker=dict(size=8, color="#FFA500"),
                text=[f"{int(v):,}".replace(",", ".") for v in df_diario_ev["Productividad_Teorica"]],
                textposition="top center",
                textfont=dict(color="#FFA500", size=10, family="Arial Black")
            ))

            fig_ev.update_layout(
                height=380,
                margin=dict(t=20, b=20, l=20, r=20),
                plot_bgcolor="white",
                paper_bgcolor="white",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(showgrid=False, linecolor="#E5E7EB", type="category"),
                yaxis=dict(showgrid=True, gridcolor="#F3F4F6", zeroline=False),
                bargap=0.25
            )

            st.plotly_chart(fig_ev, use_container_width=True)

        # ---------------------------------------------------------------------
        # VISTA B: POR MES (CONSOLIDADO MENSUAL)
        # ---------------------------------------------------------------------
        else:
            df_diario_ev["Periodo_Mes"] = df_diario_ev["Fecha_dt_clean"].dt.to_period("M")
            df_mensual_ev = df_diario_ev.groupby("Periodo_Mes", as_index=False).agg(
                Productividad_Real=("Productividad_Real", "sum"),
                Productividad_Teorica=("Productividad_Teorica", "sum")
            ).sort_values("Periodo_Mes")

            mapa_nombres = {9: "Septiembre (Cierre)", 10: "Octubre 2026"}
            df_mensual_ev["Etiqueta_Mes"] = df_mensual_ev["Periodo_Mes"].apply(
                lambda p: mapa_nombres.get(p.month, f"{p.month}/{p.year}")
            )

            fig_mes = go.Figure()

            # Barras violetas mensuales
            fig_mes.add_trace(go.Bar(
                x=df_mensual_ev["Etiqueta_Mes"],
                y=df_mensual_ev["Productividad_Real"],
                name="Productividad Real",
                marker_color="#8A5CF5",
                text=[f"{int(v):,}".replace(",", ".") for v in df_mensual_ev["Productividad_Real"]],
                textposition="inside",
                textfont=dict(color="white", size=13, family="Arial Black")
            ))

            # Línea punteada naranja mensual
            fig_mes.add_trace(go.Scatter(
                x=df_mensual_ev["Etiqueta_Mes"],
                y=df_mensual_ev["Productividad_Teorica"],
                name="Productividad Teórica",
                mode="lines+markers+text",
                line=dict(color="#FFA500", width=3, dash="dot"),
                marker=dict(size=10, color="#FFA500"),
                text=[f"{int(v):,}".replace(",", ".") for v in df_mensual_ev["Productividad_Teorica"]],
                textposition="top center",
                textfont=dict(color="#FFA500", size=12, family="Arial Black")
            ))

            fig_mes.update_layout(
                height=380,
                margin=dict(t=20, b=20, l=20, r=20),
                plot_bgcolor="white",
                paper_bgcolor="white",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(showgrid=False, linecolor="#E5E7EB"),
                yaxis=dict(showgrid=True, gridcolor="#F3F4F6", zeroline=False),
                bargap=0.35
            )

            st.plotly_chart(fig_mes, use_container_width=True)

    else:
        st.info("No se encontraron registros de productividad en BDIDPR para el personal eventual.")




    # -------------------------------------------------------------------------
    # PROCESAMIENTO Y RENDERIZADO DE TABLAS DE EVENTUALES
    # -------------------------------------------------------------------------
    if df_base_ev is not None and not df_base_ev.empty:
        df_ev_trabajo = df_base_ev.copy()
        df_ev_trabajo.columns = [str(c).strip() for c in df_ev_trabajo.columns]

        # Normalizamos nombres de columnas
        col_leg = next((c for c in df_ev_trabajo.columns if "legajo" in c.lower()), "Legajo")
        col_nom = next((c for c in df_ev_trabajo.columns if "nombre" in c.lower() or "apellido" in c.lower()), "Nombre_Apellido")
        col_turno = next((c for c in df_ev_trabajo.columns if "turno" in c.lower()), "Turno")
        col_func = next((c for c in df_ev_trabajo.columns if "funcion" in c.lower() or "puesto" in c.lower()), "Funcion_Original")
        col_fecha = next((c for c in df_ev_trabajo.columns if "fecha" in c.lower() and "corta" not in c.lower()), "Fecha")

        # Obtenemos las horas diarias registradas
        col_sit = next((c for c in df_ev_trabajo.columns if "situacion" in c.lower()), None)
        if col_sit:
            # En eventuales la situación contiene las horas trabajadas (ej: 8, 8.0)
            df_ev_trabajo["Horas_Dia"] = pd.to_numeric(
                df_ev_trabajo[col_sit].astype(str).str.replace(',', '.'), 
                errors='coerce'
            ).fillna(0.0)
        elif "Horas" in df_ev_trabajo.columns:
            df_ev_trabajo["Horas_Dia"] = pd.to_numeric(
                df_ev_trabajo["Horas"].astype(str).str.replace(',', '.'), 
                errors='coerce'
            ).fillna(0.0)
        else:
            df_ev_trabajo["Horas_Dia"] = 0.0

        # Determinamos período cerrado vs futuro por fecha
        if col_fecha in df_ev_trabajo.columns:
            df_ev_trabajo["Fecha_dt_eval"] = pd.to_datetime(df_ev_trabajo[col_fecha], errors='coerce')
            fecha_corte = locals().get('fecha_corte_real', locals().get('fecha_max_cerrada', None))
            
            if fecha_corte is None:
                # Si no está definida, tomamos como consumidas aquellas con horas > 0
                df_ev_trabajo["Horas_Consumidas"] = df_ev_trabajo["Horas_Dia"]
                df_ev_trabajo["Horas_A_Consumir"] = 0.0
            else:
                fecha_corte_ts = pd.to_datetime(fecha_corte)
                df_ev_trabajo["Horas_Consumidas"] = np.where(df_ev_trabajo["Fecha_dt_eval"] <= fecha_corte_ts, df_ev_trabajo["Horas_Dia"], 0.0)
                df_ev_trabajo["Horas_A_Consumir"] = np.where(df_ev_trabajo["Fecha_dt_eval"] > fecha_corte_ts, df_ev_trabajo["Horas_Dia"], 0.0)
        else:
            df_ev_trabajo["Horas_Consumidas"] = df_ev_trabajo["Horas_Dia"]
            df_ev_trabajo["Horas_A_Consumir"] = 0.0

        # Columnas para agrupar
        cols_grupo = [c for c in [col_leg, col_nom, col_turno, col_func] if c in df_ev_trabajo.columns]

      
        # ---------------------------------------------------------------------
        # TABLA 1: RESUMEN POR OPERARIO
        # ---------------------------------------------------------------------
        st.markdown("### 👥 Resumen por Operario")

        df_resumen_ev = df_ev_trabajo.groupby(cols_grupo, as_index=False).agg(
            Horas_Consumidas=("Horas_Consumidas", "sum"),
            Horas_A_Consumir=("Horas_A_Consumir", "sum")
        )

        # Mapeamos nombres finales de visualización
        mapeo_cols = {
            col_leg: "Legajo",
            col_nom: "Nombre y Apellido",
            col_turno: "Turno",
            col_func: "Función",
            "Horas_Consumidas": "Horas totales consumidas",
            "Horas_A_Consumir": "Horas totales a consumir"
        }
        df_resumen_ev.rename(columns=mapeo_cols, inplace=True)
        df_resumen_ev = df_resumen_ev.sort_values(by="Horas totales consumidas", ascending=False).reset_index(drop=True)

        config_cols_resumen = {
            "Legajo": st.column_config.TextColumn("Legajo", width="small"),
            "Nombre y Apellido": st.column_config.TextColumn("Nombre y Apellido", width="medium"),
            "Turno": st.column_config.TextColumn("Turno", width="small"),
            "Función": st.column_config.TextColumn("Función", width="medium"),
            "Horas totales consumidas": st.column_config.NumberColumn("Horas totales consumidas", width="medium"),
            "Horas totales a consumir": st.column_config.NumberColumn("Horas totales a consumir", width="medium")
        }

        st.dataframe(
            df_resumen_ev.style.format({
                "Horas totales consumidas": "{:,.1f} hs",
                "Horas totales a consumir": "{:,.1f} hs"
            }),
            use_container_width=True,
            height=320,
            hide_index=True,
            column_config=config_cols_resumen
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # ---------------------------------------------------------------------
        # TABLA 2: DETALLE RENOMBRADO
        # ---------------------------------------------------------------------
        st.markdown("### 📋 Detalle de horas consumidas/A consumir por operario y día")

        # 1. Identificamos la columna de situación de presentismo
        col_sit_presentismo = next(
            (c for c in df_ev_trabajo.columns if "situacion" in c.lower()), 
            None
        )

        # 2. Reemplazamos 'Sin Registro' por '0'
        if col_sit_presentismo:
            # Reemplazamos tanto el texto exacto como posibles variantes vacías
            df_ev_trabajo[col_sit_presentismo] = (
                df_ev_trabajo[col_sit_presentismo]
                .astype(str)
                .str.strip()
                .replace({"Sin Registro": "0", "sin registro": "0", "nan": "0", "None": "0", "": "0"})
            )

        # 3. Columnas a presentar en la tabla
        cols_detalle_mostrar = [c for c in [
            col_leg, col_nom, col_turno, col_func, "Fecha", "Fecha_Corta", "Dia_Semana", col_sit_presentismo, "Horas_Dia"
        ] if c and c in df_ev_trabajo.columns]

        # 4. Renderizado de la tabla
        st.dataframe(
            df_ev_trabajo[cols_detalle_mostrar] if cols_detalle_mostrar else df_ev_trabajo,
            use_container_width=True,
            height=400,
            hide_index=True
        )


# =========================================================
# HOJA 4: PRODUCTIVIDAD ACUMULADA HISTÓRICA
# =========================================================
elif hoja_seleccionada == "6. Productividad (BDIDPR)":
    st.title("📦 Tendencia de Productividad por Preparador")
    df_bdidpr = cargar_bdidpr_historico()
    if df_bdidpr is None or len(df_bdidpr) == 0: st.warning("⚠️ No se encontró BDIDPR.")
    else:
        df_prod = pd.merge(df_bdidpr, obtener_maestro_operarios(), on="Legajo", how="left")
        df_prod["Nombre_Apellido"] = df_prod["Nombre_Apellido"].fillna("No Identificado")
        df_tabla = df_prod.rename(columns={"Legajo": "Legajo Operario", "Nombre_Apellido": "Nombre y Apellido", "Jornadas_Pickeo": "Cantidad de Jornadas con Pickeo", "Picks_Promedio": "Picks x DIA Promedio", "Hs_Productivas_Promedio": "Horas Productivas Promedio", "Area_Salida_Principal": "Área de Salida Principal"}).sort_values("Picks x DIA Promedio", ascending=False)
        st.dataframe(df_tabla[["Legajo Operario", "Nombre y Apellido", "Cantidad de Jornadas con Pickeo", "Picks x DIA Promedio", "Horas Productivas Promedio", "Área de Salida Principal"]].style.format({"Cantidad de Jornadas con Pickeo": "{:,.0f}", "Picks x DIA Promedio": "{:,.1f} picks", "Horas Productivas Promedio": "{:,.2f} hs"}), use_container_width=True, height=600)

# =============================================================================
# HOJA 4: HORAS NO PRODUCTIVAS (AG Y NP)
# =============================================================================
# =============================================================================
# HOJA 4: HORAS NO PRODUCTIVAS (AG Y NP) - EXCLUSIVO PICKING
# =============================================================================
# =============================================================================
# HOJA 4: HORAS NO PRODUCTIVAS (AG Y NP) - SOLO PICKING CON IMPUTACIÓN REAL
# =============================================================================
elif any(h in hoja_seleccionada for h in ["4. Horas No Productivas", "4. Pérdida por Horas AG", "4. Pérdida por Horas Improductivas"]):

    st.title("⏱️ Horas No Productivas - Tareas AG y NP")

    # 1. Determinación segura del número de mes seleccionado
    if 'mes_sel' in locals() and isinstance(mes_sel, (int, float)):
        mes_filtro_num = int(mes_sel)
    elif 'periodo_sel' in locals():
        mapa_meses = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
            "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
        }
        mes_filtro_num = next((v for k, v in mapa_meses.items() if k in str(periodo_sel).lower()), 10)
    else:
        mes_filtro_num = 10

    import os
    import pandas as pd
    import numpy as np
    import plotly.express as px
    import procesar_articulos as pa

    # -------------------------------------------------------------------------
    # 2. DICCIONARIO MAESTRO DE NOMBRES Y BASE DE PRESENTISMO
    # -------------------------------------------------------------------------
    mapa_maestro_nombres = {}
    try:
        df_maestro = pa.obtener_maestro_operarios()
        if df_maestro is not None and not df_maestro.empty:
            c_l_m = next((c for c in df_maestro.columns if "legajo" in c.lower()), "Legajo")
            c_n_m = next((c for c in df_maestro.columns if "nombre" in c.lower() or "apellido" in c.lower()), "Nombre_Apellido")
            for _, r in df_maestro[[c_l_m, c_n_m]].dropna().iterrows():
                lk = str(r[c_l_m]).strip().replace(".0", "")
                nv = str(r[c_n_m]).strip()
                if lk and nv and nv.lower() not in ["none", "nan", ""]:
                    mapa_maestro_nombres[lk] = nv
    except Exception:
        pass

    # Carga de presentismo del mes para validar operarios presentes por turno
    df_presentismo_mes = None
    try:
        df_presentismo_mes = pa.cargar_base_presentismo(2026, mes_filtro_num)
        if df_presentismo_mes is not None and not df_presentismo_mes.empty:
            c_l_p = next((c for c in df_presentismo_mes.columns if "legajo" in c.lower()), "Legajo")
            c_n_p = next((c for c in df_presentismo_mes.columns if "nombre" in c.lower() or "apellido" in c.lower()), "Nombre_Apellido")
            for _, r in df_presentismo_mes[[c_l_p, c_n_p]].dropna().iterrows():
                lk = str(r[c_l_p]).strip().replace(".0", "")
                nv = str(r[c_n_p]).strip()
                if lk and nv and lk not in mapa_maestro_nombres and nv.lower() not in ["none", "nan", ""]:
                    mapa_maestro_nombres[lk] = nv
    except Exception:
        pass

    # -------------------------------------------------------------------------
    # 3. CARGA DIRECTA DE HORASAG.CSV
    # -------------------------------------------------------------------------
    carpetas_buscar = [
        "Datos_mensuales",
        os.path.join(os.getcwd(), "Datos_mensuales"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "Datos_mensuales"),
        os.getcwd()
    ]
    ruta_csv_ag = None
    for c in carpetas_buscar:
        if os.path.exists(c) and os.path.isdir(c):
            for arch in os.listdir(c):
                if "horasag" in arch.lower().replace(" ", "").replace("_", "") and arch.lower().endswith(".csv"):
                    ruta_csv_ag = os.path.join(c, arch)
                    break
        if ruta_csv_ag:
            break

    df_ag_raw = pd.DataFrame()
    if ruta_csv_ag and os.path.exists(ruta_csv_ag):
        try:
            df_ag_raw = pd.read_csv(ruta_csv_ag, sep=';', encoding='utf-8-sig', low_memory=False)
            if len(df_ag_raw.columns) == 1:
                df_ag_raw = pd.read_csv(ruta_csv_ag, sep=',', encoding='utf-8-sig', low_memory=False)
        except Exception:
            try:
                df_ag_raw = pd.read_csv(ruta_csv_ag, sep=None, engine='python', encoding='utf-8-sig')
            except Exception:
                pass

    if not df_ag_raw.empty:
        df_ag_raw.columns = [str(c).replace('\ufeff', '').strip() for c in df_ag_raw.columns]

        col_f = next((c for c in df_ag_raw.columns if "fecha" in c.lower() and "marca" not in c.lower()), "Fecha")
        df_ag_raw["Fecha_dt"] = pd.to_datetime(df_ag_raw[col_f], errors='coerce', dayfirst=True)

        if "Mes" in df_ag_raw.columns and not df_ag_raw["Mes"].isna().all():
            df_ag_raw["Mes_Num"] = pd.to_numeric(df_ag_raw["Mes"], errors='coerce').fillna(df_ag_raw["Fecha_dt"].dt.month).fillna(0)
        else:
            df_ag_raw["Mes_Num"] = df_ag_raw["Fecha_dt"].dt.month.fillna(0)

        # Filtro estricto por el mes seleccionado
        df_mes = df_ag_raw[df_ag_raw["Mes_Num"] == mes_filtro_num].copy()

        col_leg = next((c for c in df_mes.columns if "legajo" in c.lower()), "Número de Legajo")
        col_tiempo = next((c for c in df_mes.columns if "tiempo" in c.lower() or "hs" in c.lower()), "Tiempo hs")
        col_tipo = next((c for c in df_mes.columns if "tipo" in c.lower() and "tarea" in c.lower()), "Tipo de tarea")
        col_nom = next((c for c in df_mes.columns if "apellido" in c.lower() or "nombre" in c.lower()), "Apellido y Nombre")
        col_maq = next((c for c in df_mes.columns if "maquina" in c.lower()), "Maquina")

        # Conversión de horas a número
        df_mes["Tiempo_hs_num"] = pd.to_numeric(df_mes[col_tiempo].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)

        # ---------------------------------------------------------------------
        # REGLA 1: EXCLUIR AUTOELEVADORES (SOLO PICKING)
        # ---------------------------------------------------------------------
        es_autoelevador = df_mes[col_maq].astype(str).str.lower().str.contains("autoelevador", na=False)
        df_picking = df_mes[~es_autoelevador].copy()

        # Completar nombres que vinieron válidos en el CSV
        for _, r in df_picking[[col_leg, col_nom]].dropna().iterrows():
            l_str = str(r[col_leg]).strip().replace(".0", "")
            n_str = str(r[col_nom]).strip()
            if l_str and n_str and l_str not in mapa_maestro_nombres and n_str.lower() not in ["none", "nan", ""]:
                mapa_maestro_nombres[l_str] = n_str

        # ---------------------------------------------------------------------
        # REGLA 2: IMPUTACIÓN DE NÓMINA A CADA PREPARADOR CONECTADO ESE DÍA
        # ---------------------------------------------------------------------
        filas_procesadas = []

        # Preparación de filtros sobre presentismo
        col_f_pres = next((c for c in df_presentismo_mes.columns if "fecha" in c.lower() and "corta" not in c.lower()), "Fecha") if df_presentismo_mes is not None else None
        col_t_pres = next((c for c in df_presentismo_mes.columns if "turno" in c.lower()), "Turno") if df_presentismo_mes is not None else None
        col_s_pres = next((c for c in df_presentismo_mes.columns if "situacion" in c.lower()), "Situacion_Presentismo") if df_presentismo_mes is not None else None
        col_l_pres = next((c for c in df_presentismo_mes.columns if "legajo" in c.lower()), "Legajo") if df_presentismo_mes is not None else None
        col_n_pres = next((c for c in df_presentismo_mes.columns if "nombre" in c.lower() or "apellido" in c.lower()), "Nombre_Apellido") if df_presentismo_mes is not None else None

        if df_presentismo_mes is not None and col_f_pres:
            df_presentismo_mes["Fecha_dt_eval"] = pd.to_datetime(df_presentismo_mes[col_f_pres], errors='coerce', dayfirst=True)

        for _, fila in df_picking.iterrows():
            legajo_raw = str(fila[col_leg]).strip().replace(".0", "")
            horas_evento = fila["Tiempo_hs_num"]

            # Si el registro es una parada grupal de Nómina (ej. "Nómina TN", "Nómina TM", "Nómina TT")
            if "NÓMINA" in legajo_raw.upper() or "NOMINA" in legajo_raw.upper():
                turno_evento = "TN" if "TN" in legajo_raw.upper() or "NOCHE" in legajo_raw.upper() else (
                    "TT" if "TT" in legajo_raw.upper() or "TARDE" in legajo_raw.upper() else "TM"
                )

                fecha_evento = fila["Fecha_dt"]
                preparadores_presentes = []

                # Buscamos en presentismo a los preparadores presentes en esa fecha y turno
                if df_presentismo_mes is not None and pd.notna(fecha_evento):
                    m_fecha = df_presentismo_mes["Fecha_dt_eval"].dt.date == fecha_evento.date()
                    
                    # Filtro por turno
                    palabra_turno = "noche" if turno_evento == "TN" else ("tarde" if turno_evento == "TT" else "mañana")
                    m_turno = df_presentismo_mes[col_t_pres].astype(str).str.lower().str.contains(palabra_turno) | df_presentismo_mes[col_t_pres].astype(str).str.upper().str.contains(turno_evento)
                    
                    # Filtro de presentes (que no sea código de falta/vacaciones)
                    codigos_ausencia = ["enf", "art", "susp", "aus c/a", "aus s/a", "vac", "lic", "com"]
                    m_presente = ~df_presentismo_mes[col_s_pres].astype(str).str.strip().str.lower().isin(codigos_ausencia)
                    
                    # Filtro de pickers
                    m_picker = df_presentismo_mes["Es_Picker"] == True if "Es_Picker" in df_presentismo_mes.columns else True

                    sub_presentes = df_presentismo_mes[m_fecha & m_turno & m_presente & m_picker]

                    for _, rp in sub_presentes.iterrows():
                        lid = str(rp[col_l_pres]).strip().replace(".0", "")
                        nom = str(rp[col_n_pres]).strip() if col_n_pres and pd.notna(rp[col_n_pres]) else mapa_maestro_nombres.get(lid, f"Operario {lid}")
                        preparadores_presentes.append((lid, nom))

                # Si no se encontró el detalle de ese día, usamos la dotación estándar del turno de noche
                if not preparadores_presentes:
                    dotacion_tn = [
                        ("200671", "Ocampo Juan"), ("200658", "Ilaqcua Agustin"), ("200666", "Nuñez Nahuel"),
                        ("200667", "Diaz Alan"), ("200674", "Galeano Ulises"), ("200669", "Zurita Tobias"),
                        ("200664", "Medina Diego"), ("200672", "Lencina Walter"), ("32250", "Medina Cristian"),
                        ("28921", "Zalazar Lucas"), ("31846", "Salvatierra Arian"), ("32207", "Villalba Jonathan"),
                        ("32216", "Cardozo Matias")
                    ]
                    dotacion_elegida = dotacion_tn if turno_evento == "TN" else [("31956", "Acosta Bautista Milton"), ("31744", "Operario")]
                    preparadores_presentes = [(l, mapa_maestro_nombres.get(l, n)) for l, n in dotacion_elegida]

                # Imputamos la hora individual a CADA preparador que estuvo presente
                for leg_p, nom_p in preparadores_presentes:
                    d_nueva = fila.to_dict()
                    d_nueva["Legajo_Final"] = str(leg_p)
                    d_nueva["Nombre_Final"] = nom_p
                    d_nueva["Horas_Calculadas"] = horas_evento
                    filas_procesadas.append(d_nueva)

            else:
                # Es un evento individual
                d_ind = fila.to_dict()
                d_ind["Legajo_Final"] = legajo_raw
                nombre_resuelto = mapa_maestro_nombres.get(legajo_raw, None)
                if not nombre_resuelto:
                    n_csv = str(fila.get(col_nom, "")).strip()
                    nombre_resuelto = n_csv if n_csv and n_csv.lower() not in ["none", "nan", ""] else f"Operario {legajo_raw}"
                d_ind["Nombre_Final"] = nombre_resuelto
                d_ind["Horas_Calculadas"] = horas_evento
                filas_procesadas.append(d_ind)

        df_final_picking = pd.DataFrame(filas_procesadas)

        # Limpieza de tipo de tarea y motivos
        df_final_picking["Tipo_Tarea_Clean"] = df_final_picking[col_tipo].fillna("Tarea AG").astype(str).str.strip()

        def resolver_motivo(r):
            tipo_txt = str(r.get("Tipo_Tarea_Clean", "")).upper()
            if "NP" in tipo_txt:
                mot_np = str(r.get("Motivo NP", "Sin Motivo NP")).strip()
                return mot_np if mot_np and mot_np.lower() not in ["nan", "none"] else "Sin Motivo NP"
            mot_ag = str(r.get("Motivo AG", "Sin Motivo AG")).strip()
            return mot_ag if mot_ag and mot_ag.lower() not in ["nan", "none"] else "Sin Motivo AG"

        df_final_picking["Motivo_Clean"] = df_final_picking.apply(resolver_motivo, axis=1)

        # Separación entre AG y NP
        es_ag_mask = df_final_picking["Tipo_Tarea_Clean"].str.contains("AG", case=False, na=False)
        df_final_picking["Horas_AG"] = np.where(es_ag_mask, df_final_picking["Horas_Calculadas"], 0.0)
        df_final_picking["Horas_NP"] = np.where(~es_ag_mask, df_final_picking["Horas_Calculadas"], 0.0)

        # Bultos perdidos a 125 bultos/hora
        target_picks_hora = 125.0
        df_final_picking["Bultos_AG"] = df_final_picking["Horas_AG"] * target_picks_hora
        df_final_picking["Bultos_NP"] = df_final_picking["Horas_NP"] * target_picks_hora

        # ---------------------------------------------------------------------
        # 4. MÉTRICAS SUPERIORES
        # ---------------------------------------------------------------------
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.metric("⏱️ Horas AG (Compensadas)", f"{df_final_picking['Horas_AG'].sum():,.1f} hs")
        with col_m2:
            st.metric("📦 Bultos Perdidos AG", f"-{df_final_picking['Bultos_AG'].sum():,.0f} bultos")
        with col_m3:
            st.metric("🚫 Horas NP (No Pagas)", f"{df_final_picking['Horas_NP'].sum():,.1f} hs")
        with col_m4:
            st.metric("📦 Bultos No Producidos NP", f"-{df_final_picking['Bultos_NP'].sum():,.0f} bultos")

        st.markdown("---")

        # ---------------------------------------------------------------------
        # 5. GRÁFICOS DE DISTRIBUCIÓN POR MOTIVO
        # ---------------------------------------------------------------------
        st.markdown("### 📊 Distribución de Horas por Motivo")
        tab_ag, tab_np = st.tabs(["🏷️ Tareas AG (Compensadas)", "🚫 Tareas NP (No Pagas)"])

        with tab_ag:
            df_g_ag = df_final_picking[es_ag_mask]
            if not df_g_ag.empty:
                df_mot_ag = df_g_ag.groupby("Motivo_Clean", as_index=False)["Horas_AG"].sum()
                df_mot_ag = df_mot_ag[df_mot_ag["Horas_AG"] > 0].sort_values("Horas_AG", ascending=True)
                
                fig_ag = px.bar(
                    df_mot_ag, 
                    x="Horas_AG", 
                    y="Motivo_Clean", 
                    orientation="h", 
                    text_auto=".1f", 
                    color_discrete_sequence=["#3B82F6"]
                )
                fig_ag.update_layout(
                    height=380, 
                    margin=dict(t=20, b=20, l=10, r=20), 
                    xaxis_title="Horas Totales", 
                    yaxis_title="Motivo AG"
                )
                st.plotly_chart(fig_ag, use_container_width=True)
            else:
                st.info("No hay registros de Tareas AG de Picking en este período.")

        with tab_np:
            df_g_np = df_final_picking[~es_ag_mask]
            if not df_g_np.empty:
                df_mot_np = df_g_np.groupby("Motivo_Clean", as_index=False)["Horas_NP"].sum()
                df_mot_np = df_mot_np[df_mot_np["Horas_NP"] > 0].sort_values("Horas_NP", ascending=True)
                
                fig_np = px.bar(
                    df_mot_np, 
                    x="Horas_NP", 
                    y="Motivo_Clean", 
                    orientation="h", 
                    text_auto=".1f", 
                    color_discrete_sequence=["#EF4444"]
                )
                fig_np.update_layout(
                    height=380, 
                    margin=dict(t=20, b=20, l=10, r=20), 
                    xaxis_title="Horas Totales", 
                    yaxis_title="Motivo NP"
                )
                st.plotly_chart(fig_np, use_container_width=True)
            else:
                st.info("No hay registros de Tareas NP de Picking en este período.")

        st.markdown("---")

        # ---------------------------------------------------------------------
        # 6. TABLA RESUMEN POR OPERARIO DE PICKING (CON NOMBRE REAL)
        # ---------------------------------------------------------------------
        st.markdown("### 👥 Resumen por Operario (Horas y Bultos Perdidos)")

        df_resumen_hnp = df_final_picking.groupby(["Legajo_Final", "Nombre_Final"], as_index=False).agg(
            Eventos=("Horas_Calculadas", "count"),
            Horas_AG=("Horas_AG", "sum"),
            Bultos_AG=("Bultos_AG", "sum"),
            Horas_NP=("Horas_NP", "sum"),
            Bultos_NP=("Bultos_NP", "sum")
        )

        df_resumen_hnp["Total_Hs"] = df_resumen_hnp["Horas_AG"] + df_resumen_hnp["Horas_NP"]
        df_resumen_hnp = df_resumen_hnp.sort_values("Total_Hs", ascending=False).drop(columns=["Total_Hs"])

        df_resumen_hnp.rename(columns={
            "Legajo_Final": "Legajo",
            "Nombre_Final": "Nombre y Apellido",
            "Horas_AG": "Horas AG",
            "Bultos_AG": "Bultos AG",
            "Horas_NP": "Horas NP",
            "Bultos_NP": "Bultos NP"
        }, inplace=True)

        config_cols_resumen = {
            "Legajo": st.column_config.TextColumn("Legajo", width="small"),
            "Nombre y Apellido": st.column_config.TextColumn("Nombre y Apellido", width="medium"),
            "Eventos": st.column_config.NumberColumn("Eventos", width="small"),
            "Horas AG": st.column_config.NumberColumn("Horas AG", format="%.1f hs", width="small"),
            "Bultos AG": st.column_config.NumberColumn("Bultos AG", format="-%.0f bultos", width="medium"),
            "Horas NP": st.column_config.NumberColumn("Horas NP", format="%.1f hs", width="small"),
            "Bultos NP": st.column_config.NumberColumn("Bultos NP", format="-%.0f bultos", width="medium")
        }

        st.dataframe(
            df_resumen_hnp.style.format({
                "Horas AG": "{:,.1f} hs",
                "Bultos AG": "-{:,.0f} bultos",
                "Horas NP": "{:,.1f} hs",
                "Bultos NP": "-{:,.0f} bultos"
            }),
            use_container_width=True,
            height=320,
            hide_index=True,
            column_config=config_cols_resumen
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # ---------------------------------------------------------------------
        # 7. TABLA DETALLE DE REGISTROS (SIN 'NONE')
        # ---------------------------------------------------------------------
        st.markdown("### 📋 Detalle de Registros de Horas No Productivas (Solo Picking)")
        df_final_picking["Fecha_Visual"] = df_final_picking["Fecha_dt"].dt.strftime("%d/%m/%Y")

        df_det_tabla = df_final_picking[["Legajo_Final", "Nombre_Final", "Fecha_Visual", col_maq, "Tipo_Tarea_Clean", "Motivo_Clean", "Horas_Calculadas"]].copy()

        df_det_tabla = df_det_tabla.rename(columns={
            "Legajo_Final": "Legajo",
            "Nombre_Final": "Nombre y Apellido",
            "Fecha_Visual": "Fecha",
            col_maq: "Máquina",
            "Tipo_Tarea_Clean": "Tipo Tarea",
            "Motivo_Clean": "Motivo",
            "Horas_Calculadas": "Horas"
        })

        st.dataframe(
            df_det_tabla.style.format({
                "Horas": "{:,.1f} hs"
            }),
            use_container_width=True,
            height=400,
            hide_index=True
        )

    else:
        st.info("No se registraron horas no productivas (AG / NP) para el período seleccionado.")

# =========================================================================
    # HOJA: 5. IMPRODUCTIVIDAD Y COMPENSACIÓN
    # =========================================================================
elif "Improductividad y Compensación" in hoja_seleccionada:
        st.title("5. Improductividad y Compensación")

        import procesar_articulos as pa
        import plotly.graph_objects as go

        # 1. Determinación segura del mes de análisis
        # 1. Determinación segura del mes de análisis (detecta tanto número como texto)
        if 'mes_sel' in locals() and isinstance(mes_sel, (int, float)):
            mes_filtro_num = int(mes_sel)
        else:
            mapa_meses = {
                "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
            }
            texto_mes = str(locals().get('periodo_sel', locals().get('mes_sel', ''))).lower()
            mes_filtro_num = next((num for nom, num in mapa_meses.items() if nom in texto_mes), 10)

        # 2. Carga de datos base (Hoja 6 / BDIDPR)
        df_diario_h6 = pa.obtener_datos_hoja6(mes_seleccionado=mes_filtro_num)

        if df_diario_h6 is not None and not df_diario_h6.empty:
            col_l_base = next((c for c in df_diario_h6.columns if "legajo" in c.lower()), "Legajo")
            df_diario_h6["Legajo_Limpio"] = df_diario_h6[col_l_base].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)

            if "Fecha_dt" in df_diario_h6.columns:
                df_diario_h6["Fecha_Cruce"] = pd.to_datetime(df_diario_h6["Fecha_dt"], errors='coerce').dt.date
            else:
                col_f_dia = next((c for c in df_diario_h6.columns if "fecha" in c.lower()), "Fecha")
                df_diario_h6["Fecha_Cruce"] = pd.to_datetime(df_diario_h6[col_f_dia], errors='coerce', dayfirst=True).dt.date

            # -----------------------------------------------------------------
            # 3. ASIGNACIÓN REAL DEL TURNO DESDE PRESENTISMO
            # -----------------------------------------------------------------
            dict_turnos_reales = {}
            try:
                df_pres_real = pa.cargar_base_presentismo(2026, mes_filtro_num)
                if df_pres_real is not None and not df_pres_real.empty:
                    c_l_p = next((c for c in df_pres_real.columns if "legajo" in c.lower()), "Legajo")
                    c_t_p = next((c for c in df_pres_real.columns if "turno" in c.lower()), "Turno")
                    
                    sub_turnos = df_pres_real[[c_l_p, c_t_p]].dropna().drop_duplicates()
                    sub_turnos[c_l_p] = sub_turnos[c_l_p].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)

                    def normalizar_sigla(val_t):
                        s = str(val_t).strip().upper()
                        if "NOCHE" in s or "TN" in s:
                            return "TN"
                        if "TARDE" in s or "TT" in s:
                            return "TT"
                        return "TM"

                    sub_turnos["Turno_Norm"] = sub_turnos[c_t_p].apply(normalizar_sigla)
                    dict_turnos_reales = dict(zip(sub_turnos[c_l_p], sub_turnos["Turno_Norm"]))
            except Exception:
                dict_turnos_reales = {}

            df_diario_h6["Turno"] = df_diario_h6["Legajo_Limpio"].map(dict_turnos_reales).fillna("TM")

            # -----------------------------------------------------------------
            # 4. FILTROS DE HOJA EN LA BARRA LATERAL (TURNO Y LEGAJO)
            # -----------------------------------------------------------------
            st.sidebar.markdown("---")
            st.sidebar.markdown("### 🔍 Filtros de Hoja")

            turno_filtro = st.sidebar.selectbox(
                "Filtrar por Turno:",
                options=["Todos", "TM", "TT", "TN"],
                index=0,
                key="sb_turno_filtro_h5"
            )

            if turno_filtro != "Todos":
                df_diario_h6 = df_diario_h6[df_diario_h6["Turno"] == turno_filtro].copy()

            legajos_disp = sorted([str(l) for l in df_diario_h6[col_l_base].dropna().unique().tolist() if str(l) != "nan"])
            legajo_filtro = st.sidebar.multiselect(
                "Filtrar por Legajo (Aplica a toda la hoja):",
                options=legajos_disp,
                key="sb_legajo_filtro_h5"
            )

            if legajo_filtro:
                df_diario_h6 = df_diario_h6[df_diario_h6[col_l_base].astype(str).isin(legajo_filtro)].copy()
            # -----------------------------------------------------------------
            # SELECTOR DE GRANULARIDAD: DÍA VS MES
            # -----------------------------------------------------------------
            
            # -----------------------------------------------------------------
            # REGLA FUNDAMENTAL: FILTRAR OPERARIOS CON MENOS DE 10 BULTOS
            # -----------------------------------------------------------------
            col_bultos = next((c for c in df_diario_h6.columns if "bultos del d" in c.lower() or "picks_dia" in c.lower()), "Bultos del día")
            col_obj_bultos = next((c for c in df_diario_h6.columns if "objetivo bultos" in c.lower() or "target_area" in c.lower()), "Objetivo Bultos")

            df_diario_h6["Bultos_Num"] = pd.to_numeric(df_diario_h6[col_bultos].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
            df_diario_h6 = df_diario_h6[df_diario_h6["Bultos_Num"] >= 10].copy()
            df_diario_h6["Obj_Num"] = pd.to_numeric(df_diario_h6[col_obj_bultos].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)

            # -----------------------------------------------------------------
            # 5. SECCIÓN 1: BALANCE NETO DE PRODUCTIVIDAD (CÁLCULO EXACTO)
            # -----------------------------------------------------------------
            if "Diferencia_Picks" in df_diario_h6.columns:
                balance_neto = df_diario_h6["Diferencia_Picks"].sum()
            else:
                balance_neto = (df_diario_h6["Bultos_Num"] - df_diario_h6["Obj_Num"]).sum()

            st.markdown("### 1. Balance Neto de Productividad")
            col_m1, col_m2 = st.columns([1, 3])
            with col_m1:
                st.metric(
                    label="⚖️ Balance Neto (Real vs Teórico)",
                    value=f"{balance_neto:,.0f} bultos"
                )

            # -----------------------------------------------------------------
            # 6. SECCIÓN 2: EVOLUCIÓN PRODUCTIVA (CORREGIDO 'end' EN PLOTLY)
            # -----------------------------------------------------------------
            # =================================================================
            # 2. EVOLUCIÓN PRODUCTIVA: REAL VS TEÓRICO
            # =================================================================
            st.markdown("### 2. Evolución Productiva: Real vs Teórico")

            # Selector exclusivo para este gráfico
            vista_grafico_evo = st.radio(
                "Vista del gráfico:",
                options=["Por Día", "Por Mes"],
                index=0,
                horizontal=True,
                key="radio_vista_evo_h5"
            )
            st.markdown("<br>", unsafe_allow_html=True)

            def render_evolution_chart(df_data, color_bar, color_line, vista_modo="Por Día"):
                if df_data.empty:
                    return go.Figure()

                col_f = next((c for c in df_data.columns if "fecha" in c.lower()), "Fecha")
                col_b = next((c for c in df_data.columns if "bultos del d" in c.lower() or "picks_dia" in c.lower()), "Bultos del día")
                col_o = next((c for c in df_data.columns if "objetivo bultos" in c.lower() or "target_area" in c.lower()), "Objetivo Bultos")

                df_temp = df_data.copy()
                df_temp["B_Num"] = pd.to_numeric(df_temp[col_b].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                df_temp["O_Num"] = pd.to_numeric(df_temp[col_o].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)

                # Definición de la columna de agrupación según el selector
                if vista_modo == "Por Día":
                    if "Fecha_Corta" in df_temp.columns:
                        col_agrup_f = "Fecha_Corta"
                    else:
                        df_temp["Fecha_Str"] = pd.to_datetime(df_temp[col_f], errors='coerce', dayfirst=True).dt.strftime('%d/%m')
                        col_agrup_f = "Fecha_Str"
                    eje_x_nombre = "Fecha"
                else:
                    # Agrupación consolidada de todo el mes
                    nombre_mes = str(locals().get('periodo_sel', f"Mes {mes_filtro_num}"))
                    df_temp["Periodo_Mes"] = nombre_mes
                    col_agrup_f = "Periodo_Mes"
                    eje_x_nombre = "Mes"

                # Agrupamos por la dimensión seleccionada (Día o Mes)
                df_agg = df_temp.groupby(col_agrup_f, as_index=False).agg(
                    Real=("B_Num", "sum"),
                    Teorico=("O_Num", "sum")
                )

                # 1. EXCLUIMOS REGISTROS SIN BULTOS PREPARADOS
                df_agg = df_agg[df_agg["Real"] > 0].copy()

                fig = go.Figure()

                # Barras: números horizontales en blanco en la parte superior interna
                fig.add_trace(go.Bar(
                    x=df_agg[col_agrup_f],
                    y=df_agg["Real"],
                    name="Productividad Real",
                    marker_color=color_bar,
                    text=df_agg["Real"],
                    texttemplate="%{text:,.0f}",
                    textposition="inside",
                    insidetextanchor="end",
                    textangle=0,
                    textfont=dict(color="white", size=11, family="Arial")
                ))

                # Línea de Productividad Teórica: con etiquetas sobre cada punto
                fig.add_trace(go.Scatter(
                    x=df_agg[col_agrup_f],
                    y=df_agg["Teorico"],
                    mode="lines+markers+text",
                    name="Productividad Teórica",
                    text=df_agg["Teorico"],
                    texttemplate="%{text:,.0f}",
                    textposition="top center",
                    textfont=dict(color="#1F2937", size=10, family="Arial"),
                    line=dict(color=color_line, width=2, dash="dot"),
                    marker=dict(size=6, color=color_line)
                ))

                # 2. FORZAMOS EL EJE X COMO CATEGÓRICO
                fig.update_xaxes(type='category')

                fig.update_layout(
                    height=390,
                    margin=dict(t=30, b=20, l=10, r=10),
                    xaxis_title=eje_x_nombre,
                    yaxis_title="Bultos",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                return fig

            tab_evo_gen, tab_evo_ef, tab_evo_ev = st.tabs([
                "🌍 Evolución Personal General",
                "👥 Evolución Personal Efectivo",
                "⏳ Evolución Personal Eventual"
            ])

            tipo_pers_col = next((c for c in df_diario_h6.columns if "tipo" in c.lower() and "personal" in c.lower()), "Tipo_Personal")

            with tab_evo_gen:
                fig_gen = render_evolution_chart(df_diario_h6, "#10B981", "#1F2937", vista_modo=vista_grafico_evo)
                st.plotly_chart(fig_gen, use_container_width=True, key="chart_evo_gen_h5")

            with tab_evo_ef:
                df_ef_chart = df_diario_h6[df_diario_h6[tipo_pers_col].astype(str).str.lower() == "efectivo"] if tipo_pers_col in df_diario_h6.columns else df_diario_h6
                fig_ef = render_evolution_chart(df_ef_chart, "#10B981", "#1F2937", vista_modo=vista_grafico_evo)
                st.plotly_chart(fig_ef, use_container_width=True, key="chart_evo_ef_h5")

            with tab_evo_ev:
                df_ev_chart = df_diario_h6[df_diario_h6[tipo_pers_col].astype(str).str.lower() == "eventual"] if tipo_pers_col in df_diario_h6.columns else df_diario_h6
                fig_ev = render_evolution_chart(df_ev_chart, "#F59E0B", "#1F2937", vista_modo=vista_grafico_evo)
                st.plotly_chart(fig_ev, use_container_width=True, key="chart_evo_ev_h5")

            # -----------------------------------------------------------------
            # 7. CRUCE CON HORAS AG Y TAREAS NP (CON IMPUTACIÓN REAL DE NÓMINA)
            # -----------------------------------------------------------------
            df_tabla = df_diario_h6.copy()

            # Aseguramos la columna de fecha para el cruce (formato date de Python)
            if "Fecha_dt" in df_tabla.columns:
                df_tabla["Fecha_Cruce"] = pd.to_datetime(df_tabla["Fecha_dt"], errors='coerce').dt.date
            else:
                col_f_temp = next((c for c in df_tabla.columns if "fecha" in c.lower()), "Fecha")
                df_tabla["Fecha_Cruce"] = pd.to_datetime(df_tabla[col_f_temp], errors='coerce', dayfirst=True).dt.date

            filas_cruce_expandidas = []
            try:
                # 1. Cargamos el archivo HorasAG.csv
                import os
                carpetas_buscar = [
                    "Datos_mensuales",
                    os.path.join(os.getcwd(), "Datos_mensuales"),
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "Datos_mensuales"),
                    os.getcwd()
                ]
                ruta_csv_ag = None
                for c in carpetas_buscar:
                    if os.path.exists(c) and os.path.isdir(c):
                        for arch in os.listdir(c):
                            if "horasag" in arch.lower().replace(" ", "").replace("_", "") and arch.lower().endswith(".csv"):
                                ruta_csv_ag = os.path.join(c, arch)
                                break
                    if ruta_csv_ag:
                        break

                df_ag_crudo = pd.DataFrame()
                if ruta_csv_ag and os.path.exists(ruta_csv_ag):
                    try:
                        df_ag_crudo = pd.read_csv(ruta_csv_ag, sep=';', encoding='utf-8-sig', low_memory=False)
                        if len(df_ag_crudo.columns) == 1:
                            df_ag_crudo = pd.read_csv(ruta_csv_ag, sep=',', encoding='utf-8-sig', low_memory=False)
                    except Exception:
                        df_ag_crudo = pd.read_csv(ruta_csv_ag, sep=None, engine='python', encoding='utf-8-sig')

                if not df_ag_crudo.empty:
                    df_ag_crudo.columns = [str(c).replace('\ufeff', '').strip() for c in df_ag_crudo.columns]

                    col_f_ag = next((c for c in df_ag_crudo.columns if "fecha" in c.lower() and "marca" not in c.lower()), "Fecha")
                    col_l_ag = next((c for c in df_ag_crudo.columns if "legajo" in c.lower()), "Número de Legajo")
                    col_t_ag = next((c for c in df_ag_crudo.columns if "tiempo" in c.lower() or "hs" in c.lower()), "Tiempo hs")
                    col_tipo_ag = next((c for c in df_ag_crudo.columns if "tipo" in c.lower() and "tarea" in c.lower()), "Tipo de tarea")
                    col_maq_ag = next((c for c in df_ag_crudo.columns if "maquina" in c.lower()), "Maquina")

                    df_ag_crudo["Fecha_dt"] = pd.to_datetime(df_ag_crudo[col_f_ag], errors='coerce', dayfirst=True)
                    df_ag_crudo["Tiempo_Num"] = pd.to_numeric(df_ag_crudo[col_t_ag].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)

                    # Excluimos autoelevadores: solo máquinas de picking
                    es_auto = df_ag_crudo[col_maq_ag].astype(str).str.lower().str.contains("autoelevador", na=False)
                    df_ag_pick = df_ag_crudo[~es_auto].copy()

                    # Evaluamos cada registro de HorasAG
                    for _, fila_ag in df_ag_pick.iterrows():
                        leg_ag_str = str(fila_ag[col_l_ag]).strip().replace(".0", "")
                        hs_val = fila_ag["Tiempo_Num"]
                        fecha_val = fila_ag["Fecha_dt"].date() if pd.notna(fila_ag["Fecha_dt"]) else None
                        es_ag_bool = "AG" in str(fila_ag.get(col_tipo_ag, "AG")).upper()

                        if fecha_val is None or hs_val <= 0:
                            continue

                        # Si es un evento global de Nómina (ej: Nómina TN el 21/10)
                        if "NÓMINA" in leg_ag_str.upper() or "NOMINA" in leg_ag_str.upper():
                            turno_evento = "TN" if "TN" in leg_ag_str.upper() or "NOCHE" in leg_ag_str.upper() else (
                                "TT" if "TT" in leg_ag_str.upper() or "TARDE" in leg_ag_str.upper() else "TM"
                            )

                            # Buscamos en df_tabla a los preparadores presentes en esa fecha y turno
                            pickers_en_turno = df_tabla[
                                (df_tabla["Fecha_Cruce"] == fecha_val) & 
                                (df_tabla["Turno"] == turno_evento)
                            ]["Legajo_Limpio"].unique()

                            for leg_picker in pickers_en_turno:
                                filas_cruce_expandidas.append({
                                    "Legajo_Limpio": str(leg_picker),
                                    "Fecha_Cruce": fecha_val,
                                    "Horas_AG_Num": hs_val if es_ag_bool else 0.0,
                                    "Horas_NP_Num": 0.0 if es_ag_bool else hs_val
                                })
                        else:
                            # Evento individual
                            filas_cruce_expandidas.append({
                                "Legajo_Limpio": leg_ag_str,
                                "Fecha_Cruce": fecha_val,
                                "Horas_AG_Num": hs_val if es_ag_bool else 0.0,
                                "Horas_NP_Num": 0.0 if es_ag_bool else hs_val
                            })
            except Exception:
                pass

            # 2. Agrupamos por operario y fecha consolidando AG y NP
            if filas_cruce_expandidas:
                df_resumen_cruce = pd.DataFrame(filas_cruce_expandidas).groupby(
                    ["Legajo_Limpio", "Fecha_Cruce"], as_index=False
                ).agg({
                    "Horas_AG_Num": "sum",
                    "Horas_NP_Num": "sum"
                })
                df_tabla = pd.merge(df_tabla, df_resumen_cruce, on=["Legajo_Limpio", "Fecha_Cruce"], how="left")

            # Valores por defecto defensivos si no hubo registro
            if "Horas_AG_Num" not in df_tabla.columns: df_tabla["Horas_AG_Num"] = 0.0
            if "Horas_NP_Num" not in df_tabla.columns: df_tabla["Horas_NP_Num"] = 0.0
            df_tabla["Horas_AG_Num"] = df_tabla["Horas_AG_Num"].fillna(0.0)
            df_tabla["Horas_NP_Num"] = df_tabla["Horas_NP_Num"].fillna(0.0)

            # -----------------------------------------------------------------
            # 8. SECCIÓN 3: DESEMPEÑO DÍA POR DÍA (CON CRITERIOS DEL GLOSARIO)
            # -----------------------------------------------------------------
            st.markdown("---")
            st.markdown("### 3. Desempeño Día por Día")

            col_l = next((c for c in df_tabla.columns if "legajo" in c.lower()), "Legajo")
            col_nom = next((c for c in df_tabla.columns if "nombre" in c.lower() or "apellido" in c.lower()), "Nombre_Apellido")
            col_b = next((c for c in df_tabla.columns if "bultos del d" in c.lower() or "picks_dia" in c.lower()), "Bultos del día")
            col_o = next((c for c in df_tabla.columns if "objetivo bultos" in c.lower() or "target_area" in c.lower()), "Objetivo Bultos")
            col_hs = next((c for c in df_tabla.columns if "conexi" in c.lower() or "hs_productivas_dia" in c.lower()), "Horas Conexión")
            col_p = next((c for c in df_tabla.columns if "pérdida de tiempo" in c.lower() or "perdida" in c.lower() or "hs_perdida_dia" in c.lower()), "Pérdida de Tiempo")
            col_area = next((c for c in df_tabla.columns if "área" in c.lower() or "area" in c.lower()), "Áreas (Separadas por /)")

            def a_decimal(val):
                if pd.isna(val) or val is None: return 0.0
                s = str(val).strip()
                if ":" in s:
                    try:
                        p = s.split(":")
                        return float(p[0]) + float(p[1]) / 60.0
                    except: return 0.0
                try: return float(s.replace(',', '.'))
                except: return 0.0

            def a_hhmm(val):
                if pd.isna(val) or val is None: return "00:00"
                s = str(val).strip()
                if ":" in s and len(s) <= 5: return s
                try:
                    num = float(str(val).replace(',', '.'))
                    if num <= 0: return "00:00"
                    m = int(round(num * 60))
                    return f"{m//60:02d}:{m%60:02d}"
                except: return "00:00"

            df_tabla["Hs_Con_Dec"] = df_tabla[col_hs].apply(a_decimal)
            df_tabla["Horas Conexión"] = df_tabla["Hs_Con_Dec"].apply(a_hhmm)
            df_tabla["Pérdida de Tiempo"] = df_tabla[col_p].apply(a_hhmm)

            # Picks/hora a la izquierda de Bultos del día
            df_tabla["Picks/hora"] = np.where(df_tabla["Hs_Con_Dec"] > 0, df_tabla["Bultos_Num"] / df_tabla["Hs_Con_Dec"], 0.0)

            df_tabla["Horas AG"] = df_tabla["Horas_AG_Num"].apply(a_hhmm)
            df_tabla["Horas NP"] = df_tabla["Horas_NP_Num"].apply(a_hhmm)

            # -----------------------------------------------------------------
            # INICIALIZACIÓN DEFENSIVA PARA EVITAR KEYERROR
            # -----------------------------------------------------------------
            if "Bultos_Perdidos_AG" not in df_tabla.columns:
                df_tabla["Bultos_Perdidos_AG"] = 0.0

            if "Bultos_Perdidos_NP" not in df_tabla.columns:
                df_tabla["Bultos_Perdidos_NP"] = 0.0

            if "Horas_AG_Num" not in df_tabla.columns:
                df_tabla["Horas_AG_Num"] = 0.0

            if "Horas_NP_Num" not in df_tabla.columns:
                df_tabla["Horas_NP_Num"] = 0.0

            # -----------------------------------------------------------------
            # CÁLCULO DE BULTOS PERDIDOS (AG Y NP)
            # -----------------------------------------------------------------
            tasa_p = np.where(df_tabla["Picks/hora"] > 0, df_tabla["Picks/hora"], 125.0)

            df_tabla["Bultos Perdidos AG"] = np.where(
                (df_tabla["Bultos_Perdidos_AG"] == 0) & (df_tabla["Horas_AG_Num"] > 0),
                df_tabla["Horas_AG_Num"] * tasa_p,
                df_tabla["Bultos_Perdidos_AG"]
            )

            df_tabla["Bultos Perdidos NP"] = np.where(
                (df_tabla["Bultos_Perdidos_NP"] == 0) & (df_tabla["Horas_NP_Num"] > 0),
                df_tabla["Horas_NP_Num"] * tasa_p,
                df_tabla["Bultos_Perdidos_NP"]
            )

            # Regla de conexión del Glosario:
            # - Área 22: 05:40 hs = 5.6667 hs
            # - Resto de áreas: 06:40 hs = 6.6667 hs
            def calcular_obj_hs_glosario(area_str):
                a_str = str(area_str).strip()
                if a_str == "22":
                    return 5.0 + 40.0 / 60.0  # 5.6667 hs
                return 6.0 + 40.0 / 60.0      # 6.6667 hs

            df_tabla["Obj_Hs_Conexion"] = df_tabla[col_area].apply(calcular_obj_hs_glosario)

            columnas_completas = [
                "Legajo",
                "Nombre_Apellido",
                "Turno",
                "Fecha",
                "Áreas (Separadas por /)",
                "Objetivo Bultos",
                "Picks/hora",            # <-- A la izquierda de Bultos del día
                "Bultos del día",
                "Horas Conexión",
                "Pérdida de Tiempo",
                "Horas AG",
                "Bultos Perdidos AG",
                "Horas NP",
                "Bultos Perdidos NP"
            ]
            cols_existentes = [c for c in columnas_completas if c in df_tabla.columns]

            def estilo_semaforo(row):
                estilos = pd.Series('', index=row.index)
                # Bultos del día: Verde si cumple/supera Objetivo, Rojo si no llega
                try:
                    b_v = float(str(row["Bultos del día"]).replace(',', '.'))
                    o_v = float(str(row["Objetivo Bultos"]).replace(',', '.'))
                    if b_v >= o_v and o_v > 0:
                        estilos["Bultos del día"] = 'background-color: #D1FAE5; color: #065F46; font-weight: bold;'
                    else:
                        estilos["Bultos del día"] = 'background-color: #FEE2E2; color: #DC2626; font-weight: bold;'
                except: pass

                # Horas de conexión: Rojo si es menor a 05:40 hs en Área 22 o menor a 06:40 hs en otras áreas
                try:
                    s_con = str(row["Horas Conexión"]).strip()
                    if ":" in s_con:
                        p = s_con.split(":")
                        horas_reales = float(p[0]) + float(p[1]) / 60.0
                        
                        # Meta oficial: 05:40 hs (5.6667 hs) en Área 22 y 06:40 hs (6.6667 hs) en las demás
                        area_txt = str(row.get("Áreas (Separadas por /)", "")).strip()
                        meta_hs = (5.0 + 40.0 / 60.0) if area_txt == "22" else (6.0 + 40.0 / 60.0)
                        
                        # Semáforo: Verde si cumple o supera la meta, Rojo si no llega
                        if horas_reales >= meta_hs:
                            estilos["Horas Conexión"] = 'background-color: #D1FAE5; color: #065F46; font-weight: bold;'
                        else:
                            estilos["Horas Conexión"] = 'background-color: #FEE2E2; color: #DC2626; font-weight: bold;'
                except:
                    pass
                return estilos

            cfg_cols = {
                "Legajo": st.column_config.TextColumn("Legajo", width="small"),
                "Nombre_Apellido": st.column_config.TextColumn("Nombre_Apellido", width="medium"),
                "Turno": st.column_config.TextColumn("Turno", width="small"),
                "Fecha": st.column_config.TextColumn("Fecha", width="small"),
                "Áreas (Separadas por /)": st.column_config.TextColumn("Áreas (Separadas por /)", width="small"),
                "Objetivo Bultos": st.column_config.NumberColumn("Objetivo Bultos", format="%d", width="small"),
                "Picks/hora": st.column_config.NumberColumn("Picks/hora", format="%.1f", width="small"),
                "Bultos del día": st.column_config.NumberColumn("Bultos del día", format="%d", width="small"),
                "Horas Conexión": st.column_config.TextColumn("Horas Conexión", width="small"),
                "Pérdida de Tiempo": st.column_config.TextColumn("Pérdida de Tiempo", width="small"),
                "Horas AG": st.column_config.TextColumn("Horas AG", width="small"),
                "Bultos Perdidos AG": st.column_config.NumberColumn("Bultos Perdidos AG", format="-%d", width="medium"),
                "Horas NP": st.column_config.TextColumn("Horas NP", width="small"),
                "Bultos Perdidos NP": st.column_config.NumberColumn("Bultos Perdidos NP", format="-%d", width="medium"),
            }

            tab_ef, tab_ev = st.tabs(["👥 Personal Efectivo", "⏳ Personal Eventual"])

            with tab_ef:
                df_sub_ef = df_tabla[df_tabla[tipo_pers_col].astype(str).str.lower() == "efectivo"].copy()
                if not df_sub_ef.empty:
                    st.dataframe(
                        df_sub_ef[cols_existentes].style.apply(estilo_semaforo, axis=1).format({
                            "Picks/hora": "{:,.1f}",
                            "Bultos Perdidos AG": "-{:,.0f}" if (df_sub_ef["Bultos Perdidos AG"] > 0).any() else "{:,.0f}",
                            "Bultos Perdidos NP": "-{:,.0f}" if (df_sub_ef["Bultos Perdidos NP"] > 0).any() else "{:,.0f}"
                        }),
                        use_container_width=True,
                        height=450,
                        hide_index=True,
                        column_config=cfg_cols
                    )
                else:
                    st.info("No hay datos para Personal Efectivo con los filtros seleccionados.")

            with tab_ev:
                df_sub_ev = df_tabla[df_tabla[tipo_pers_col].astype(str).str.lower() == "eventual"].copy()
                if not df_sub_ev.empty:
                    st.dataframe(
                        df_sub_ev[cols_existentes].style.apply(estilo_semaforo, axis=1).format({
                            "Picks/hora": "{:,.1f}",
                            "Bultos Perdidos AG": "-{:,.0f}" if (df_sub_ev["Bultos Perdidos AG"] > 0).any() else "{:,.0f}",
                            "Bultos Perdidos NP": "-{:,.0f}" if (df_sub_ev["Bultos Perdidos NP"] > 0).any() else "{:,.0f}"
                        }),
                        use_container_width=True,
                        height=450,
                        hide_index=True,
                        column_config=cfg_cols
                    )
                else:
                    st.info("No hay datos para Personal Eventual con los filtros seleccionados.")

            # -----------------------------------------------------------------
            # 9. SECCIÓN 4: TOP OPERARIOS CON MENOR DESEMPEÑO
            # -----------------------------------------------------------------
            st.markdown("### 4. Top Operarios con Menor Desempeño")

            df_tabla["Cumple_Bultos"] = (df_tabla["Bultos_Num"] >= df_tabla["Obj_Num"]) & (df_tabla["Obj_Num"] > 0)
            df_tabla["Cumple_HS"] = df_tabla["Hs_Con_Dec"] >= df_tabla["Obj_Hs_Conexion"]

            def calc_top(df_sub):
                if df_sub.empty:
                    return pd.DataFrame()
                grp = df_sub.groupby([col_l, col_nom, "Turno"], as_index=False).agg(
                    Total_Jornadas=("Bultos del día", "count"),
                    Jornadas_con_bultos_OBJ=("Cumple_Bultos", "sum"),
                    Jornadas_con_HS_OBJ=("Cumple_HS", "sum"),
                    Picks_Hora_Prom=("Picks/hora", "mean")
                )
                grp["%Jornadas>=OBJ Bultos"] = np.where(grp["Total_Jornadas"] > 0, (grp["Jornadas_con_bultos_OBJ"] / grp["Total_Jornadas"]) * 100, 0.0)
                grp["%Jornadas>=OBJ HS"] = np.where(grp["Total_Jornadas"] > 0, (grp["Jornadas_con_HS_OBJ"] / grp["Total_Jornadas"]) * 100, 0.0)
                grp = grp.sort_values(["%Jornadas>=OBJ Bultos", "Picks_Hora_Prom"], ascending=True)
                grp.rename(columns={
                    col_l: "Legajo",
                    col_nom: "Nombre y apellido",
                    "Jornadas_con_bultos_OBJ": "Jornadas con bultos>OBJ",
                    "Jornadas_con_HS_OBJ": "Jornadas con HS>OBJ",
                    "Picks_Hora_Prom": "Picks/hora"
                }, inplace=True)
                return grp

            def estilo_top(df_sub):
                estilos = pd.DataFrame('', index=df_sub.index, columns=df_sub.columns)
                for c in ["%Jornadas>=OBJ Bultos", "%Jornadas>=OBJ HS"]:
                    if c in df_sub.columns:
                        for i in df_sub.index:
                            try:
                                # Limpiamos y convertimos el porcentaje a número flotante
                                val_num = float(str(df_sub.loc[i, c]).replace('%', '').replace(',', '.').strip())
                                
                                # Regla: Verde si es >= 80%, Rojo si es < 80%
                                if val_num >= 80.0:
                                    estilos.loc[i, c] = 'background-color: #D1FAE5; color: #065F46; font-weight: bold;'
                                else:
                                    estilos.loc[i, c] = 'background-color: #FEE2E2; color: #DC2626; font-weight: bold;'
                            except Exception:
                                pass
                return estilos

            tab_t_ef, tab_t_ev = st.tabs(["👥 Efectivos - Menor Desempeño", "⏳ Eventuales - Menor Desempeño"])

            with tab_t_ef:
                d_top_ef = calc_top(df_tabla[df_tabla[tipo_pers_col].astype(str).str.lower() == "efectivo"])
                if not d_top_ef.empty:
                    st.dataframe(
                        d_top_ef.style.apply(estilo_top, axis=None).format({
                            "%Jornadas>=OBJ Bultos": "{:.1f}%",
                            "%Jornadas>=OBJ HS": "{:.1f}%",
                            "Picks/hora": "{:,.1f}"
                        }),
                        use_container_width=True,
                        height=400,
                        hide_index=True
                    )
                else:
                    st.info("No hay datos de efectivos para el ranking.")

            with tab_t_ev:
                d_top_ev = calc_top(df_tabla[df_tabla[tipo_pers_col].astype(str).str.lower() == "eventual"])
                if not d_top_ev.empty:
                    st.dataframe(
                        d_top_ev.style.apply(estilo_top, axis=None).format({
                            "%Jornadas>=OBJ Bultos": "{:.1f}%",
                            "%Jornadas>=OBJ HS": "{:.1f}%",
                            "Picks/hora": "{:,.1f}"
                        }),
                        use_container_width=True,
                        height=400,
                        hide_index=True
                    )
                else:
                    st.info("No hay datos de eventuales para el ranking.")
        else:
            st.info("No se encontraron registros de desempeño diario para el período seleccionado.")
# =========================================================
# HOJA 7: GLOSARIO
# =========================================================
elif hoja_seleccionada == "7. Glosario":
    st.title("📖 Glosario y Cuadro de Referencia")
    
    st.markdown("### 📌 Clasificación de Ausentismos")
    col_no_plan, col_plan = st.columns(2)
    
    with col_no_plan:
        st.error(
            "### 🔴 Ausentismo NO Planificado\n"
            "**`Aus C/A`**, **`Aus S/A`**, **`Aus Del`**, **`ART`**, **`Enf`**, **`Susp`** y Resto de Licencias."
        )
        
    with col_plan:
        st.warning(
            "### 🟡 Ausentismo Planificado\n"
            "**`Vac`**: Vacaciones\n\n"
            "*(El franco compensatorio \"Com\" es un derecho de descanso y se excluye del universo de horas teóricas, no computando como falta ni como presente).*"
        )

    st.markdown("---")
    
    # --- NUEVA SECCIÓN: ATERRIZAJE ---
    st.markdown("### 🛬 Aterrizaje (Horas Eventuales)")
    st.markdown(
        """
        Representa la proyección de horas que sobrarán (positivo) o faltarán (negativo) al cierre del mes operativo. Se calcula restándole a las *Horas Presupuestadas* el total de *Horas Consumidas* (hasta el día de ayer) y las *Horas a Consumir Estimadas*. 
        
        Para la estimación futura, se asume que los operarios que actualmente están dados de alta consumirán 8 horas diarias desde hoy hasta lo que resta para que termine el período. Cabe destacar que el cálculo siempre evalúa el período operativo completo; por ejemplo, el mes de Octubre contempla lo cargado desde el 26/09 al 25/10.
        """
    )
    
    st.markdown("---")
    
    st.markdown("### 🎯 Cálculo de Productividad")
    st.markdown(
        """
        **1. Objetivos Base por Área (Jornada Completa):**
        * **Área 11 y 12 (Seco)**: 1,200 bultos/día
        * **Área 21 (Refrigerado)**: 1,275 bultos/día
        * **Área 22 (Congelado)**: 660 bultos/día
        * **Área 23 (Fruta y Verdura)**: 1,200 bultos/día
        * **Área 95 (Baja Rotación / Especial)**: 900 bultos/día
        * **Personal Eventual**: Objetivo fijo de 1,000 bultos/día independientemente del área.
        
        **2. Horas de Conexión Exigibles:**
        * Si trabaja en el **Área 22**, el objetivo de horas es **05:40 hs** (5.66 horas decimales).
        * Si trabaja en **cualquier otra área**, el objetivo es **06:40 hs** (6.66 horas decimales).

        **3. Cálculo Mixto (Ponderación por áreas):**
        Si un operario registra tiempo en más de un área en el mismo día, su objetivo no se divide, sino que se **pondera** en función del tiempo invertido en cada zona.
        
        *Fórmula interna de código:*  
        `(Horas en Área A / Horas Totales del Día) * Objetivo Full Área A + (Horas en Área B / Horas Totales del Día) * Objetivo Full Área B`
        
        *Ejemplo práctico:*  
        Si un operario trabaja 4 horas en total: 2 horas en la 21 (50% de su tiempo) y 2 horas en la 22 (50% de su tiempo). Su objetivo del día será la mitad del objetivo de la 21 más la mitad del objetivo de la 22:  
        `(1275 * 0.50) + (660 * 0.50) = 967.5 bultos exigidos.`
        
        ---
        #### ⚙️ Lógica Oficial:
        * **Objetivo Teórico (Compromiso):** Cada vez que un operario registra actividad en el día, se le asigna el target correspondiente al área donde más bultos o tiempo registró (Área Principal). A los eventuales siempre se les exige 1000 bultos.
        * **Real vs Compromiso:** El tablero calcula el déficit o superávit diario restando directamente los bultos preparados contra este objetivo fijo del área. De esta forma, evaluamos el aporte de volumen puro y duro de cada persona hacia el objetivo del almacén.
        * Si el operario se encuentra ausente, no registra movimientos, por ende no se le genera un target, y tampoco resta en la matriz productiva.
        * **Traslado de Feriados:** Los registros de BDIDPR de los domingos y del feriado 12/10/2026 se unifican matemáticamente con el día hábil siguiente para preservar la consistencia de los objetivos de las jornadas operativas.
        """
    )