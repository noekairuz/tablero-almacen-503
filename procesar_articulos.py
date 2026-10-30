import pandas as pd
import numpy as np
import os
import datetime

# Mapeo de nombres de meses en español
NOMBRES_MESES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}

# DICCIONARIO DE FERIADOS NACIONALES DE ARGENTINA (2026)
FERIADOS_ARGENTINA_2026 = {
    datetime.date(2026, 1, 1): "Año Nuevo", datetime.date(2026, 2, 16): "Carnaval", datetime.date(2026, 2, 17): "Carnaval",
    datetime.date(2026, 3, 24): "Día Memoria", datetime.date(2026, 4, 2): "Día Malvinas", datetime.date(2026, 4, 3): "Viernes Santo",
    datetime.date(2026, 5, 1): "Día Trabajador", datetime.date(2026, 5, 25): "Revolución Mayo", datetime.date(2026, 6, 17): "Güemes",
    datetime.date(2026, 6, 20): "Belgrano", datetime.date(2026, 7, 9): "Independencia", datetime.date(2026, 8, 17): "San Martín",
    datetime.date(2026, 10, 12): "Diversidad Cultural", datetime.date(2026, 11, 20): "Soberanía", datetime.date(2026, 12, 8): "Inmaculada",
    datetime.date(2026, 12, 25): "Navidad",
}

def buscar_archivo_csv(mes_nombre, tipo_personal):
    mes_buscado = mes_nombre.lower()
    tipo_buscado = tipo_personal.lower()
    carpetas_a_escanear = ["Datos_mensuales", os.path.join(os.path.dirname(os.path.abspath(__file__)), "Datos_mensuales"), os.path.dirname(os.path.abspath(__file__)), os.getcwd()]
    for carpeta in carpetas_a_escanear:
        if os.path.exists(carpeta) and os.path.isdir(carpeta):
            for archivo in os.listdir(carpeta):
                archivo_lower = archivo.lower()
                if archivo_lower.endswith(".csv") and mes_buscado in archivo_lower and tipo_buscado in archivo_lower:
                    return os.path.join(carpeta, archivo)
    return None

def cargar_base_presentismo(anio, mes):
    nombre_mes = NOMBRES_MESES.get(mes, "Septiembre")
    cols_dias_posibles = [str(i) for i in range(1, 32)]
    dfs_unificados = []
    
    for tipo in ["efectivo", "eventual"]:
        tipo_label = "Efectivo" if tipo == "efectivo" else "Eventual"
        ruta_csv = buscar_archivo_csv(nombre_mes, tipo)
        if ruta_csv and os.path.exists(ruta_csv):
            try:
                df_temp = pd.read_csv(ruta_csv, sep=';', encoding='utf-8-sig')
                if len(df_temp.columns) == 1:
                    df_temp = pd.read_csv(ruta_csv, sep=',', encoding='utf-8-sig')
            except Exception:
                continue
                
            df_temp.columns = [str(c).strip() for c in df_temp.columns]
            
            # Identificar la columna de función original
            col_func = [c for c in df_temp.columns if c.strip().lower() == "funcion"]
            fn_col = col_func[0] if col_func else None
            
            if tipo == "efectivo" and fn_col:
                mascara_pick = df_temp[fn_col].astype(str).str.strip().str.lower().str.contains("pick", na=False)
                df_temp = df_temp[mascara_pick].copy()
                
            dias_presentes = [c for c in cols_dias_posibles if c in df_temp.columns]
            if dias_presentes and len(df_temp) > 0:
                id_vars_list = ["Legajo", "Nombre", "Turno"]
                
                if fn_col and fn_col not in id_vars_list:
                    id_vars_list.append(fn_col)
                    
                df_melted = pd.melt(df_temp, id_vars=id_vars_list, value_vars=dias_presentes, var_name="Dia_Str", value_name="Situacion_Presentismo")
                
                df_melted["Legajo"] = df_melted["Legajo"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
                df_melted["Nombre_Apellido"] = df_melted["Nombre"].astype(str).str.strip()
                df_melted["Turno"] = df_melted["Turno"].astype(str).str.strip()
                df_melted["Almacen"] = "501 - Vicente López"
                df_melted["Fecha"] = f"{anio}-{mes:02d}-" + df_melted["Dia_Str"].astype(str).str.zfill(2)
                df_melted["Situacion_Presentismo"] = df_melted["Situacion_Presentismo"].astype(str).str.strip().fillna("Sin Registro")
                df_melted["Tipo_Personal"] = tipo_label
                
                if fn_col:
                    df_melted["Funcion_Original"] = df_melted[fn_col].astype(str).str.strip()
                    df_melted["Es_Picker"] = df_melted["Funcion_Original"].str.lower().str.contains("pick", na=False)
                else:
                    df_melted["Funcion_Original"] = "Sin Especificar"
                    df_melted["Es_Picker"] = True
                    
                cols_finales = ["Legajo", "Nombre_Apellido", "Almacen", "Turno", "Fecha", "Situacion_Presentismo", "Tipo_Personal", "Funcion_Original", "Es_Picker"]
                dfs_unificados.append(df_melted[cols_finales])
                
    if not dfs_unificados: return None
    return pd.concat(dfs_unificados, ignore_index=True)

def cargar_horas_presupuestadas():
    carpetas = ["Datos_mensuales", os.getcwd(), os.path.dirname(os.path.abspath(__file__))]
    for c in carpetas:
        for ext in ["csv", "xlsx"]:
            ruta = os.path.join(c, f"horas_planificadas_eventuales.{ext}")
            if os.path.exists(ruta):
                try:
                    df_p = pd.read_csv(ruta, sep=';', encoding='utf-8-sig') if ext == "csv" else pd.read_excel(ruta)
                    if ext == "csv" and len(df_p.columns) == 1: df_p = pd.read_csv(ruta, sep=',', encoding='utf-8-sig')
                    df_p.columns = [str(col).strip() for col in df_p.columns]
                    return df_p
                except: pass
    return None

def corregir_domingos_bdidpr(df_m4, col_fecha):
    if col_fecha == "FEIDPR":
        df_m4["Fecha_dt"] = pd.to_datetime(df_m4["FEIDPR"].astype(str).str.replace(r'\.0$', '', regex=True), format="%Y%m%d", errors="coerce")
    else:
        df_m4["Fecha_dt"] = pd.to_datetime(df_m4["Jornada"], format="%d/%m/%Y", errors="coerce")

    def ajustar_fecha(fecha):
        if pd.isna(fecha):
            return fecha
        if fecha.weekday() == 6:
            fecha += pd.Timedelta(days=1)
        if fecha.month == 10 and fecha.day == 12 and fecha.year == 2026:
            fecha += pd.Timedelta(days=1)
        return fecha

    df_m4["Fecha_dt"] = df_m4["Fecha_dt"].apply(ajustar_fecha)
    if col_fecha == "FEIDPR":
        df_m4["FEIDPR"] = df_m4["Fecha_dt"].dt.strftime("%Y%m%d")
    else:
        df_m4["Jornada"] = df_m4["Fecha_dt"].dt.strftime("%d/%m/%Y")
    return df_m4

def cargar_bdidpr_historico():
    carpetas = ["Datos_mensuales", os.path.join(os.path.dirname(os.path.abspath(__file__)), "Datos_mensuales"), os.path.dirname(os.path.abspath(__file__)), os.getcwd()]
    ruta_csv = None
    for c in carpetas:
        if os.path.exists(c) and os.path.isdir(c):
            for archivo in os.listdir(c):
                if "bdidpr" in archivo.lower() and archivo.lower().endswith(".csv"):
                    ruta_csv = os.path.join(c, archivo)
                    break
        if ruta_csv: break
    if not ruta_csv or not os.path.exists(ruta_csv): return None
    try:
        df_bd = pd.read_csv(ruta_csv, sep=';', encoding='utf-8-sig', low_memory=False)
        if len(df_bd.columns) == 1: df_bd = pd.read_csv(ruta_csv, sep=',', encoding='utf-8-sig', low_memory=False)
    except: return None

    df_bd.columns = [str(col).strip() for col in df_bd.columns]
    col_mov = [col for col in df_bd.columns if col.strip().lower() in ["tpmov", "cod. movimiento"]][0]
    df_m4 = df_bd[pd.to_numeric(df_bd[col_mov], errors='coerce') == 4].copy()
    col_fecha_jornada = "FEIDPR" if "FEIDPR" in df_m4.columns else "Jornada"
    df_m4 = corregir_domingos_bdidpr(df_m4, col_fecha_jornada)
    
    df_m4["Legajo"] = df_m4["OPERARIO"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_m4["PICKS"] = pd.to_numeric(df_m4["PICKS"].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)
    df_m4["HS_PRODUCTIVAS"] = pd.to_numeric(df_m4["HS PRODUCTIVAS"].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)
    col_area = 'ARSAL' if 'ARSAL' in df_m4.columns else 'COD. AREA SALIDA'

    def area_frecuente(series):
        s = series.dropna()
        if len(s) == 0: return "Sin Especificar"
        m = s.mode()
        return str(m.iloc[0] if not m.empty else s.iloc[0]).replace('.0', '')

    areas_principales = df_m4.groupby("Legajo")[col_area].apply(area_frecuente).reset_index()
    areas_principales.rename(columns={col_area: "Area_Salida_Principal"}, inplace=True)
    
    df_diario = df_m4.groupby(["Legajo", col_fecha_jornada]).agg(Picks_Total_Dia=("PICKS", "sum"), Hs_Productivas_Total_Dia=("HS_PRODUCTIVAS", "sum")).reset_index()
    df_diario_validos = df_diario[df_diario["Picks_Total_Dia"] > 0].copy()
    
    q1 = df_diario_validos.groupby("Legajo")["Picks_Total_Dia"].transform(lambda x: x.quantile(0.25) if len(x) >= 5 else -np.inf)
    q3 = df_diario_validos.groupby("Legajo")["Picks_Total_Dia"].transform(lambda x: x.quantile(0.75) if len(x) >= 5 else np.inf)
    iqr = q3 - q1
    limite_inferior = q1 - 1.5 * iqr
    limite_superior = q3 + 1.5 * iqr
    es_rango_valido = (df_diario_validos["Picks_Total_Dia"] >= limite_inferior) & (df_diario_validos["Picks_Total_Dia"] <= limite_superior)
    
    df_diario_depurado = df_diario_validos[es_rango_valido].copy()
    resumen_operario = df_diario_depurado.groupby("Legajo").agg(Jornadas_Pickeo=(col_fecha_jornada, "count"), Picks_Promedio=("Picks_Total_Dia", "mean"), Hs_Productivas_Promedio=("Hs_Productivas_Total_Dia", "mean")).reset_index()
    resumen_final = pd.merge(resumen_operario, areas_principales, on="Legajo", how="left")
    return resumen_final

def obtener_maestro_operarios():
    dfs_maestros = []
    for m in [9, 10, 11, 12]:
        df_m = cargar_base_presentismo(2026, m)
        if df_m is not None and len(df_m) > 0:
            dfs_maestros.append(df_m[["Legajo", "Nombre_Apellido", "Tipo_Personal"]].drop_duplicates())
    if dfs_maestros:
        maestro_completo = pd.concat(dfs_maestros, ignore_index=True).drop_duplicates(subset=["Legajo"])
        return maestro_completo
    return pd.DataFrame(columns=["Legajo", "Nombre_Apellido", "Tipo_Personal"])

import os
import pandas as pd
import numpy as np

import os
import pandas as pd
import numpy as np


# =============================================================================
# CARGA Y PROCESAMIENTO DE HORAS NO PRODUCTIVAS (AG Y NP)
# =============================================================================
def cargar_horas_no_productivas(mes_seleccionado=10):
    """
    Lee HorasAG.csv. Si detecta un registro de nómina global (Nómina TM/TT/TN),
    busca en el presentismo a los operarios presentes en esa fecha y turno
    e imputa las horas NP individualmente a cada uno de ellos.
    """
    import os
    import pandas as pd
    import numpy as np

    # 1. Búsqueda exhaustiva del archivo CSV
    carpetas_a_revisar = [
        "Datos_mensuales",
        os.path.join(os.getcwd(), "Datos_mensuales"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "Datos_mensuales"),
        os.path.dirname(os.path.abspath(__file__)),
        os.getcwd()
    ]
    
    ruta_encontrada = None
    for carpeta in carpetas_a_revisar:
        if os.path.exists(carpeta) and os.path.isdir(carpeta):
            for archivo in os.listdir(carpeta):
                arch_clean = archivo.lower().replace(" ", "").replace("_", "")
                if "horasag" in arch_clean and arch_clean.endswith(".csv"):
                    ruta_encontrada = os.path.join(carpeta, archivo)
                    break
        if ruta_encontrada:
            break

    if not ruta_encontrada or not os.path.exists(ruta_encontrada):
        return pd.DataFrame()

    # 2. Lectura tolerante a separadores (; o ,)
    try:
        df_ag = pd.read_csv(ruta_encontrada, sep=';', encoding='utf-8-sig', low_memory=False)
        if len(df_ag.columns) == 1:
            df_ag = pd.read_csv(ruta_encontrada, sep=',', encoding='utf-8-sig', low_memory=False)
    except Exception:
        try:
            df_ag = pd.read_csv(ruta_encontrada, sep=None, engine='python', encoding='utf-8-sig')
        except Exception:
            return pd.DataFrame()

    if df_ag.empty:
        return pd.DataFrame()

    df_ag.columns = [str(col).replace('\ufeff', '').strip() for col in df_ag.columns]

    # 3. Conversión de fechas y filtro por mes
    col_fecha = next((c for c in df_ag.columns if "fecha" in c.lower() and "marca" not in c.lower()), "Fecha")
    df_ag["Fecha_dt"] = pd.to_datetime(df_ag[col_fecha], errors="coerce", dayfirst=True)

    if "Mes" in df_ag.columns and not df_ag["Mes"].isna().all():
        df_ag["Mes_Num"] = pd.to_numeric(df_ag["Mes"], errors="coerce")
        df_ag["Mes_Num"] = df_ag["Mes_Num"].fillna(df_ag["Fecha_dt"].dt.month).fillna(0)
    else:
        df_ag["Mes_Num"] = df_ag["Fecha_dt"].dt.month.fillna(0)

    if mes_seleccionado is not None:
        df_ag = df_ag[df_ag["Mes_Num"] == mes_seleccionado].copy()

    if df_ag.empty:
        return pd.DataFrame()

    col_legajo_ag = next((c for c in df_ag.columns if "legajo" in c.lower()), "Número de Legajo")
    col_tiempo = next((c for c in df_ag.columns if "tiempo" in c.lower() or "hs" in c.lower()), "Tiempo hs")
    col_tipo = next((c for c in df_ag.columns if "tipo" in c.lower() and "tarea" in c.lower()), "Tipo de tarea")
    col_nom_csv = next((c for c in df_ag.columns if "apellido" in c.lower() or "nombre" in c.lower()), "Apellido y Nombre")
    col_maq = next((c for c in df_ag.columns if "maquina" in c.lower()), "Maquina")

    df_ag["Legajo"] = df_ag[col_legajo_ag].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_ag["Tiempo_hs_num"] = pd.to_numeric(df_ag[col_tiempo].astype(str).str.replace(',', '.'), errors="coerce").fillna(0.0)
    df_ag["Tipo_Tarea_Clean"] = df_ag[col_tipo].fillna("Tarea AG").astype(str).str.strip()

    def obtener_motivo(fila):
        tipo_str = str(fila.get("Tipo_Tarea_Clean", "")).upper()
        if "NP" in tipo_str:
            return str(fila.get("Motivo NP", "Sin Motivo NP")).strip()
        return str(fila.get("Motivo AG", "Sin Motivo AG")).strip()

    df_ag["Motivo_Clean"] = df_ag.apply(obtener_motivo, axis=1)

    # 4. Carga de base de Presentismo para cruce de operarios presentes
    df_presentismo = pd.DataFrame()
    if 'obtener_datos' in globals():
        try:
            df_pres_base, _ = obtener_datos(2026, mes_seleccionado)
            if df_pres_base is not None and not df_pres_base.empty:
                df_presentismo = df_pres_base.copy()
        except Exception:
            pass

    # Diccionario maestro de Legajo -> Nombre y Apellido desde Presentismo
    mapa_maestro_nombres = {}
    if not df_presentismo.empty:
        c_leg_p = next((c for c in df_presentismo.columns if "legajo" in c.lower()), None)
        c_nom_p = next((c for c in df_presentismo.columns if "nombre" in c.lower() or "apellido" in c.lower()), None)
        if c_leg_p and c_nom_p:
            for _, r in df_presentismo[[c_leg_p, c_nom_p]].dropna().drop_duplicates().iterrows():
                l_k = str(r[c_leg_p]).strip().replace(".0", "")
                n_v = str(r[c_nom_p]).strip()
                if l_k and n_v and n_v.lower() not in ["nan", "none"]:
                    mapa_maestro_nombres[l_k] = n_v

    # Si falta alguno, completamos con los nombres válidos que vinieron en HorasAG
    for _, r in df_ag[[ "Legajo", col_nom_csv ]].dropna().iterrows():
        l_k = str(r["Legajo"]).strip()
        n_v = str(r[col_nom_csv]).strip()
        if l_k not in mapa_maestro_nombres and n_v and not n_v.isdigit() and n_v.lower() not in ["nan", "none", ""]:
            mapa_maestro_nombres[l_k] = n_v

    # -------------------------------------------------------------------------
    # 5. EXPANDIR REGISTROS GLOBALES (NÓMINA TM / TT / TN) A CADA OPERARIO PRESENTE
    # -------------------------------------------------------------------------
    registros_expandidos = []

    # Mapeo de siglas a nombres de turno en la base de presentismo
    mapa_turnos_presentismo = {
        "TM": ["mañana", "tm", "turno mañana"],
        "TT": ["tarde", "tt", "turno tarde"],
        "TN": ["noche", "tn", "turno noche"]
    }

    col_fecha_pres = next((c for c in df_presentismo.columns if "fecha" in c.lower() and "corta" not in c.lower()), None) if not df_presentismo.empty else None
    col_turno_pres = next((c for c in df_presentismo.columns if "turno" in c.lower()), None) if not df_presentismo.empty else None
    col_sit_pres = next((c for c in df_presentismo.columns if "situacion" in c.lower()), None) if not df_presentismo.empty else None
    col_leg_pres = next((c for c in df_presentismo.columns if "legajo" in c.lower()), None) if not df_presentismo.empty else None

    if col_fecha_pres:
        df_presentismo["Fecha_dt_eval"] = pd.to_datetime(df_presentismo[col_fecha_pres], errors='coerce', dayfirst=True)

    for _, fila in df_ag.iterrows():
        legajo_actual = str(fila["Legajo"]).strip()
        
        # ¿Es un registro global de nómina?
        if "NÓMINA" in legajo_actual.upper() or "NOMINA" in legajo_actual.upper():
            # Identificamos el turno del evento global
            turno_detectado = None
            for sigla in ["TM", "TT", "TN"]:
                if sigla in legajo_actual.upper():
                    turno_detectado = sigla
                    break

            fecha_evento = fila["Fecha_dt"]
            operarios_encontrados = []

            # Si tenemos la base de presentismo, buscamos los que estuvieron presentes ese día y turno
            if not df_presentismo.empty and col_fecha_pres and col_turno_pres and col_sit_pres and pd.notna(fecha_evento):
                filtro_fecha = df_presentismo["Fecha_dt_eval"].dt.date == fecha_evento.date()
                
                # Coincidencia con el turno
                turnos_validos = mapa_turnos_presentismo.get(turno_detectado, [])
                filtro_turno = df_presentismo[col_turno_pres].astype(str).str.strip().str.lower().isin(turnos_validos)
                
                # Presentes: Que no sea ausencia (es decir situación 'P', número de horas > 0, o distinto de códigos de ausencia)
                codigos_aus = ["enf", "art", "susp", "aus c/a", "aus s/a", "vac", "lic", "com"]
                sit_str = df_presentismo[col_sit_pres].astype(str).str.strip().str.lower()
                filtro_presente = ~sit_str.isin(codigos_aus)

                df_presentes_turno = df_presentismo[filtro_fecha & filtro_turno & filtro_presente]
                operarios_encontrados = df_presentes_turno[col_leg_pres].astype(str).str.strip().str.replace(r'\.0$', '', regex=True).unique().tolist()

            # Si no encontró operarios por fecha (o falló el match), usamos la dotación estándar del turno
            if not operarios_encontrados:
                # Dotación estándar
                dotaciones_defecto = {
                    "TM": ["31956", "31957", "32122", "32195", "32203"], # lista base o fallback
                    "TT": ["31744", "200648", "200654"],
                    "TN": ["32250", "28921", "31846", "32207", "32216", "32217", "200671", "200658", "200666", "200667", "200674", "200669", "200664"]
                }
                operarios_encontrados = dotaciones_defecto.get(turno_detectado, [f"Operario_{turno_detectado}"])

            # Creamos una fila individual para CADA operario presente
            for leg_op in operarios_encontrados:
                nueva_fila = fila.to_dict()
                nueva_fila["Legajo"] = str(leg_op)
                nueva_fila["Persona_O_Grupo"] = mapa_maestro_nombres.get(str(leg_op), f"Operario {leg_op}")
                nueva_fila["Horas_Hombre_Totales"] = fila["Tiempo_hs_num"] # La hora individual que perdió cada uno
                registros_expandidos.append(nueva_fila)

        else:
            # Es un operario individual regular
            fila_dict = fila.to_dict()
            fila_dict["Persona_O_Grupo"] = mapa_maestro_nombres.get(legajo_actual, str(fila.get(col_nom_csv, legajo_actual)))
            fila_dict["Horas_Hombre_Totales"] = fila["Tiempo_hs_num"]
            registros_expandidos.append(fila_dict)

    df_procesado = pd.DataFrame(registros_expandidos)

    if df_procesado.empty:
        return pd.DataFrame()

    # -------------------------------------------------------------------------
    # 6. ESTIMACIÓN DE BULTOS PERDIDOS (125 BULTOS/HORA O TASA HISTÓRICA)
    # -------------------------------------------------------------------------
    df_bdidpr = cargar_bdidpr_historico()
    if df_bdidpr is not None and not df_bdidpr.empty:
        df_tasa = df_bdidpr[["Legajo", "Picks_Promedio", "Hs_Productivas_Promedio"]].copy()
        df_tasa["Picks_por_Hora"] = np.where(
            df_tasa["Hs_Productivas_Promedio"] > 0, 
            df_tasa["Picks_Promedio"] / df_tasa["Hs_Productivas_Promedio"], 
            125.0
        )
    else:
        df_tasa = pd.DataFrame(columns=["Legajo", "Picks_por_Hora"])

    df_procesado = pd.merge(df_procesado, df_tasa[["Legajo", "Picks_por_Hora"]], on="Legajo", how="left")
    df_procesado["Picks_por_Hora"] = df_procesado["Picks_por_Hora"].fillna(125.0)

    df_procesado["Bultos_Perdidos_Estimados"] = df_procesado["Horas_Hombre_Totales"] * df_procesado["Picks_por_Hora"]

    # Separación final estricta en columnas AG y NP
    es_ag = df_procesado["Tipo_Tarea_Clean"].str.contains("AG", case=False, na=False)
    
    df_procesado["Horas_AG"] = np.where(es_ag, df_procesado["Horas_Hombre_Totales"], 0.0)
    df_procesado["Bultos_Perdidos_AG"] = np.where(es_ag, df_procesado["Bultos_Perdidos_Estimados"], 0.0)

    df_procesado["Horas_NP"] = np.where(~es_ag, df_procesado["Horas_Hombre_Totales"], 0.0)
    df_procesado["Bultos_Perdidos_NP"] = np.where(~es_ag, df_procesado["Bultos_Perdidos_Estimados"], 0.0)

    return df_procesado
# Alias de compatibilidad para que app.py pueda llamarla con cualquiera de los dos nombres
cargar_horas_ag = cargar_horas_no_productivas

def obtener_datos_hoja6(mes_seleccionado=10):
    """
    Procesa los datos de la Hoja 6 (Desempeño Día por Día).
    Obtiene la Pérdida de Tiempo sumando la columna SEGEMP (en segundos) 
    o HS CONEX cuando TPMOV == 5.
    """
    # -------------------------------------------------------------
    # 1. BÚSQUEDA Y LECTURA DEL ARCHIVO BDIDPR.CSV
    # -------------------------------------------------------------
    carpetas = [
        "Datos_mensuales", 
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "Datos_mensuales"), 
        os.path.dirname(os.path.abspath(__file__)), 
        os.getcwd()
    ]
    ruta_csv = None
    for c in carpetas:
        if os.path.exists(c) and os.path.isdir(c):
            for archivo in os.listdir(c):
                if "bdidpr" in archivo.lower() and archivo.lower().endswith(".csv"):
                    ruta_csv = os.path.join(c, archivo)
                    break
            if ruta_csv: 
                break

    if not ruta_csv or not os.path.exists(ruta_csv): 
        return None

    try:
        df_bd = pd.read_csv(ruta_csv, sep=';', encoding='utf-8-sig', low_memory=False)
        if len(df_bd.columns) == 1: 
            df_bd = pd.read_csv(ruta_csv, sep=',', encoding='utf-8-sig', low_memory=False)
    except Exception: 
        return None

    df_bd.columns = [str(col).strip() for col in df_bd.columns]
    
    # Identificación dinámica de la columna de movimiento (TPMOV o COD. MOV)
    col_mov = next((c for c in ["TPMOV", "COD. MOV", "TPMOV ", "COD. MOV "] if c in df_bd.columns), None)
    if not col_mov:
        col_mov = [col for col in df_bd.columns if "mov" in col.lower()][0]

    # Identificación de columna de fecha
    col_fecha_jornada = "FEIDPR" if "FEIDPR" in df_bd.columns else ("Jornada" if "Jornada" in df_bd.columns else "Fecha")
    
    # Corrección de fechas
    if 'corregir_domingos_bdidpr' in globals():
        df_bd = corregir_domingos_bdidpr(df_bd, col_fecha_jornada)
    else:
        # Si FEIDPR viene en formato numérico AAAAMMDD (ej: 20260601)
        df_bd["Fecha_dt"] = pd.to_datetime(df_bd[col_fecha_jornada].astype(str), format="%Y%m%d", errors='coerce')
        if df_bd["Fecha_dt"].isna().all():
            df_bd["Fecha_dt"] = pd.to_datetime(df_bd[col_fecha_jornada], errors='coerce')

    # Filtramos por el mes seleccionado
    df_bd = df_bd[df_bd["Fecha_dt"].dt.month == mes_seleccionado].copy()
    if len(df_bd) == 0: 
        return None

    # Normalización de legajo
    col_operario = "OPERARIO" if "OPERARIO" in df_bd.columns else "Legajo"
    df_bd["Legajo"] = df_bd[col_operario].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_bd["Fecha_Corta"] = df_bd["Fecha_dt"].dt.strftime("%d/%m")

    # -------------------------------------------------------------
    # 2. PROCESAMIENTO DEL MOVIMIENTO 4 (CONEXIÓN Y PICKS)
    # -------------------------------------------------------------
    df_m4 = df_bd[pd.to_numeric(df_bd[col_mov], errors='coerce') == 4].copy()
    
    if len(df_m4) > 0:
        df_m4["PICKS"] = pd.to_numeric(df_m4["PICKS"].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)
        
        # Columna de tiempo para Horas Conexión
        col_hs_prod = "HS CONEX" if "HS CONEX" in df_m4.columns else ("HS PRODUCTIVAS" if "HS PRODUCTIVAS" in df_m4.columns else None)
        if col_hs_prod:
            df_m4["HS_PRODUCTIVAS"] = pd.to_numeric(df_m4[col_hs_prod].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)
        elif "SEGEMP" in df_m4.columns:
            df_m4["HS_PRODUCTIVAS"] = pd.to_numeric(df_m4["SEGEMP"].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0) / 3600.0
        else:
            df_m4["HS_PRODUCTIVAS"] = 0.0

        col_area = 'ARSAL' if 'ARSAL' in df_m4.columns else ('COD. AREA SALIDA' if 'COD. AREA SALIDA' in df_m4.columns else 'COD. AREA')

        # Cargar maestro de operarios
        if 'obtener_maestro_operarios' in globals():
            maestro = obtener_maestro_operarios()
            df_m4 = pd.merge(df_m4, maestro, on="Legajo", how="left")
        
        if "Tipo_Personal" not in df_m4.columns:
            df_m4["Tipo_Personal"] = "Efectivo"
        else:
            df_m4["Tipo_Personal"] = df_m4["Tipo_Personal"].fillna("Efectivo")
            
        if "Nombre_Apellido" not in df_m4.columns:
            df_m4["Nombre_Apellido"] = "No Identificado"
        else:
            df_m4["Nombre_Apellido"] = df_m4["Nombre_Apellido"].fillna("No Identificado")

        # Asignación del Target
        def obtener_target_full_shift(row):
            area = str(row[col_area]).replace('.0', '').strip() if col_area in row else ""
            tipo = row["Tipo_Personal"]
            if tipo == "Eventual":
                return 1000.0
            else:
                targets_efectivos = {"11": 1200, "12": 1200, "21": 1275, "22": 660, "23": 1200, "95": 900}
                return targets_efectivos.get(area, 1200.0)

        df_m4["Target_Full_Area"] = df_m4.apply(obtener_target_full_shift, axis=1)

        # Ponderación del target
        df_areas = df_m4.groupby(["Legajo", "Fecha_dt", "Fecha_Corta", col_area, "Target_Full_Area"]).agg(
            Hs_Area=("HS_PRODUCTIVAS", "sum")
        ).reset_index()

        df_total_hs = df_areas.groupby(["Legajo", "Fecha_dt"])["Hs_Area"].sum().reset_index(name="Hs_Totales_Dia")
        df_areas = pd.merge(df_areas, df_total_hs, on=["Legajo", "Fecha_dt"])

        df_areas["Target_Ponderado"] = np.where(
            df_areas["Hs_Totales_Dia"] > 0,
            (df_areas["Hs_Area"] / df_areas["Hs_Totales_Dia"]) * df_areas["Target_Full_Area"],
            0.0
        )

        df_target_final = df_areas.groupby(["Legajo", "Fecha_dt"]).agg(
            Target_Area_Dia=("Target_Ponderado", "sum")
        ).reset_index()

        def area_concat(series):
            s = series.dropna().astype(str).str.replace(r'\.0$', '', regex=True).str.strip().unique()
            return " / ".join(sorted(s)) if len(s) > 0 else "Sin Especificar"

        df_diario = df_m4.groupby(["Legajo", "Fecha_dt", "Fecha_Corta"]).agg(
            Picks_Dia=("PICKS", "sum"),
            Hs_Productivas_Dia=("HS_PRODUCTIVAS", "sum"),
            Area_Salida=(col_area, area_concat),
            Nombre_Apellido=("Nombre_Apellido", "first"),
            Tipo_Personal=("Tipo_Personal", "first")
        ).reset_index()

        df_diario = pd.merge(df_diario, df_target_final, on=["Legajo", "Fecha_dt"], how="left")
    else:
        df_diario = pd.DataFrame(columns=["Legajo", "Fecha_dt", "Fecha_Corta", "Picks_Dia", "Hs_Productivas_Dia", "Area_Salida", "Nombre_Apellido", "Tipo_Personal", "Target_Area_Dia"])

    # -------------------------------------------------------------
    # 3. PROCESAMIENTO DEL MOVIMIENTO 5 (PÉRDIDA DE TIEMPO DESDE SEGEMP / HS CONEX)
    # -------------------------------------------------------------
    df_m5 = df_bd[pd.to_numeric(df_bd[col_mov], errors='coerce') == 5].copy()
    
    if len(df_m5) > 0:
        if "SEGEMP" in df_m5.columns:
            # SEGEMP está en segundos -> convertimos a horas dividiendo por 3600
            df_m5["Hs_Perdida_Calculada"] = pd.to_numeric(df_m5["SEGEMP"].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0) / 3600.0
        elif "HS CONEX" in df_m5.columns:
            # HS CONEX ya está en formato de horas decimales
            df_m5["Hs_Perdida_Calculada"] = pd.to_numeric(df_m5["HS CONEX"].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)
        else:
            df_m5["Hs_Perdida_Calculada"] = 0.0

        df_p5 = df_m5.groupby(["Legajo", "Fecha_dt"]).agg(Hs_Perdida_Dia=("Hs_Perdida_Calculada", "sum")).reset_index()
        df_diario = pd.merge(df_diario, df_p5, on=["Legajo", "Fecha_dt"], how="left")
    else:
        df_diario["Hs_Perdida_Dia"] = 0.0

    df_diario["Hs_Perdida_Dia"] = df_diario["Hs_Perdida_Dia"].fillna(0.0)

    # -------------------------------------------------------------------------
    # # 4. CRUCE CON HORAS AG / NO PRODUCTIVAS
    # -------------------------------------------------------------------------
    df_ag_base = cargar_horas_no_productivas(mes_seleccionado)

    if df_ag_base is not None and not df_ag_base.empty:
        df_ag_base = df_ag_base.copy()
        df_ag_base["Legajo"] = df_ag_base["Legajo"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)

        col_hs_cruce = "Horas_AG" if "Horas_AG" in df_ag_base.columns else "Tiempo_hs_num"
        if col_hs_cruce in df_ag_base.columns and "Fecha_dt" in df_ag_base.columns:
            df_ag_dia = df_ag_base.groupby(["Legajo", "Fecha_dt"]).agg(
                Hs_AG_Dia=(col_hs_cruce, "sum")
            ).reset_index()
            df_diario = pd.merge(df_diario, df_ag_dia, on=["Legajo", "Fecha_dt"], how="left")
        else:
            df_diario["Hs_AG_Dia"] = 0.0
    else:
        df_diario["Hs_AG_Dia"] = 0.0

    df_diario["Hs_AG_Dia"] = df_diario["Hs_AG_Dia"].fillna(0.0)

    # -------------------------------------------------------------
    # 5. FORMATEO VISUAL HH:MM
    # -------------------------------------------------------------
    def convertir_hhmm(val_hs):
        if pd.isna(val_hs) or val_hs <= 0:
            return "00:00"
        total_minutos = int(round(val_hs * 60))
        horas = total_minutos // 60
        minutos = total_minutos % 60
        return f"{horas:02d}:{minutos:02d}"

    df_diario["Horas Conexión"] = df_diario["Hs_Productivas_Dia"].apply(convertir_hhmm)
    df_diario["Pérdida de Tiempo"] = df_diario["Hs_Perdida_Dia"].apply(convertir_hhmm)
    df_diario["Horas AG"] = df_diario["Hs_AG_Dia"].apply(convertir_hhmm)

    df_diario["Fecha"] = df_diario["Fecha_Corta"]
    df_diario["Áreas (Separadas por /)"] = df_diario["Area_Salida"]
    df_diario["Objetivo Bultos"] = df_diario["Target_Area_Dia"].round(0).fillna(0).astype(int)
    df_diario["Bultos del día"] = df_diario["Picks_Dia"].round(0).fillna(0).astype(int)

    return df_diario


    # Paso C: Asignar el nombre recuperado
    def resolver_nombre_operario(fila):
        leg = fila["Legajo"]
        # Si es una nómina grupal, devolvemos la nómina
        if "NÓMINA" in leg.upper() or "NOMINA" in leg.upper():
            return leg
        # Si ya venía cargado en el registro actual y es válido, lo usamos
        nom_actual = str(fila.get(col_nom_csv, "")).strip()
        if nom_actual and nom_actual.lower() not in ["nan", "none", ""]:
            return nom_actual
        # Si no, lo buscamos en el diccionario maestro recuperado
        return mapa_nombres.get(leg, leg)

    df_ag_mes["Persona_O_Grupo"] = df_ag_mes.apply(resolver_nombre_operario, axis=1)

    # 6. Clasificación de Tareas AG vs NP y unificación de motivo
    col_tipo = next((c for c in df_ag_mes.columns if "tipo" in c.lower() and "tarea" in c.lower()), "Tipo de tarea")
    df_ag_mes["Tipo_Tarea_Clean"] = df_ag_mes[col_tipo].fillna("Tarea AG").astype(str).str.strip()

    def obtener_motivo(fila):
        tipo_str = str(fila.get("Tipo_Tarea_Clean", "")).upper()
        if "NP" in tipo_str:
            return str(fila.get("Motivo NP", "Sin Motivo NP")).strip()
        return str(fila.get("Motivo AG", "Sin Motivo AG")).strip()

    df_ag_mes["Motivo_Clean"] = df_ag_mes.apply(obtener_motivo, axis=1)

    # 7. Nóminas Globales y Multiplicador por Turno
    dotacion_turnos = {"TM": 20, "TT": 18, "TN": 13}
    def calcular_multiplicador(legajo_str):
        leg_up = str(legajo_str).upper()
        if "NÓMINA" in leg_up or "NOMINA" in leg_up:
            for turno, cantidad in dotacion_turnos.items():
                if turno in leg_up:
                    return cantidad
            return 15
        return 1

    df_ag_mes["Multiplicador"] = df_ag_mes["Legajo"].apply(calcular_multiplicador)
    df_ag_mes["Horas_Hombre_Totales"] = df_ag_mes["Tiempo_hs_num"] * df_ag_mes["Multiplicador"]

    # 8. Cálculo de Bultos Perdidos Estimados
    df_bdidpr = cargar_bdidpr_historico()
    if df_bdidpr is not None and not df_bdidpr.empty:
        df_tasa = df_bdidpr[["Legajo", "Picks_Promedio", "Hs_Productivas_Promedio"]].copy()
        df_tasa["Picks_por_Hora"] = np.where(
            df_tasa["Hs_Productivas_Promedio"] > 0, 
            df_tasa["Picks_Promedio"] / df_tasa["Hs_Productivas_Promedio"], 
            125.0
        )
    else:
        df_tasa = pd.DataFrame(columns=["Legajo", "Picks_por_Hora"])

    df_merged = pd.merge(df_ag_mes, df_tasa[["Legajo", "Picks_por_Hora"]], on="Legajo", how="left")
    df_merged["Picks_por_Hora"] = df_merged["Picks_por_Hora"].fillna(125.0)

    # Bultos perdidos totales
    df_merged["Bultos_Perdidos_Estimados"] = df_merged["Horas_Hombre_Totales"] * df_merged["Picks_por_Hora"]

    # Separación en columnas específicas para AG y NP
    es_ag = df_merged["Tipo_Tarea_Clean"].str.contains("AG", case=False, na=False)
    df_merged["Horas_AG"] = np.where(es_ag, df_merged["Horas_Hombre_Totales"], 0.0)
    df_merged["Bultos_Perdidos_AG"] = np.where(es_ag, df_merged["Bultos_Perdidos_Estimados"], 0.0)

    df_merged["Horas_NP"] = np.where(~es_ag, df_merged["Horas_Hombre_Totales"], 0.0)
    df_merged["Bultos_Perdidos_NP"] = np.where(~es_ag, df_merged["Bultos_Perdidos_Estimados"], 0.0)

    return df_merged

def calcular_bultos_perdidos_pasados(df_cerrado):
    if df_cerrado is None or len(df_cerrado) == 0: return 0, 0.0
    situacion_clean = df_cerrado["Situacion_Presentismo_Limpia"].astype(str).str.strip().str.lower()
    es_asistencia = (situacion_clean == "p") | (pd.to_numeric(df_cerrado["Situacion_Presentismo_Limpia"], errors="coerce").fillna(0) > 0)
    es_sin_registro_o_feriado = situacion_clean.isin(["sin registro", "nan", "", "none", "0", "0.0", "feriado", "com"])
    df_ausentes_pasados = df_cerrado[(~es_asistencia) & (~es_sin_registro_o_feriado)].copy()
    qty_ausentes_pasados = len(df_ausentes_pasados)
    if qty_ausentes_pasados == 0: return 0, 0.0
    
    df_ausentes_pasados["Legajo"] = df_ausentes_pasados["Legajo"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_bdidpr = cargar_bdidpr_historico()
    
    if df_bdidpr is not None and len(df_bdidpr) > 0:
        df_proms = df_bdidpr[["Legajo", "Picks_Promedio"]].copy()
        df_proms["Legajo"] = df_proms["Legajo"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    else:
        df_proms = pd.DataFrame(columns=["Legajo", "Picks_Promedio"])
        
    df_merged = pd.merge(df_ausentes_pasados, df_proms, on="Legajo", how="left")
    return qty_ausentes_pasados, df_merged["Picks_Promedio"].fillna(0.0).sum()

def calcular_estimacion_bultos_perdidos(df_futuro):
    if df_futuro is None or len(df_futuro) == 0: return 0.0, pd.DataFrame()
    situacion_clean = df_futuro["Situacion_Presentismo_Limpia"].astype(str).str.strip().str.lower()
    horas_num = pd.to_numeric(df_futuro["Situacion_Presentismo_Limpia"], errors="coerce").fillna(0)
    es_asistencia = (situacion_clean == "p") | (horas_num > 0)
    es_sin_registro_o_feriado = situacion_clean.isin(["sin registro", "nan", "", "none", "0", "0.0", "feriado", "com"])
    df_aus_futuras = df_futuro[(~es_asistencia) & (~es_sin_registro_o_feriado)].copy()
    
    if len(df_aus_futuras) == 0: return 0.0, pd.DataFrame()
    df_aus_futuras["Legajo"] = df_aus_futuras["Legajo"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_bdidpr = cargar_bdidpr_historico()
    
    if df_bdidpr is not None and len(df_bdidpr) > 0:
        df_proms = df_bdidpr[["Legajo", "Picks_Promedio"]].copy()
        df_proms["Legajo"] = df_proms["Legajo"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    else:
        df_proms = pd.DataFrame(columns=["Legajo", "Picks_Promedio"])
        
    df_detalle = pd.merge(df_aus_futuras, df_proms, on="Legajo", how="left")
    df_detalle["Picks_Promedio"] = df_detalle["Picks_Promedio"].fillna(0.0)
    total_bultos_perdidos = df_detalle["Picks_Promedio"].sum()
    cols_salida = ["Legajo", "Nombre_Apellido", "Fecha", "Dia_Semana", "Situacion_Presentismo", "Picks_Promedio"]
    df_detalle_salida = df_detalle[cols_salida].rename(columns={"Legajo": "Legajo Operario", "Nombre_Apellido": "Nombre y Apellido", "Fecha": "Fecha Ausencia", "Dia_Semana": "Día de la Semana", "Situacion_Presentismo": "Motivo de Ausencia", "Picks_Promedio": "Bultos Estimados Perdidos"}).sort_values("Fecha Ausencia")
    return total_bultos_perdidos, df_detalle_salida

def obtener_datos(anio, mes):
    df_pandas = cargar_base_presentismo(anio=anio, mes=mes)
    mes_anterior = mes - 1 if mes > 1 else 12
    anio_anterior = anio if mes > 1 else anio - 1
    df_pandas_ant = cargar_base_presentismo(anio=anio_anterior, mes=mes_anterior)
    
    dfs_combinados = [df for df in [df_pandas_ant, df_pandas] if df is not None and len(df) > 0]
    if not dfs_combinados: return None, None
    
    df_completo = pd.concat(dfs_combinados, ignore_index=True)
    df_completo["Situacion_Presentismo_Limpia"] = df_completo["Situacion_Presentismo"].astype(str).str.strip()
    df_completo["Fecha_dt"] = pd.to_datetime(df_completo["Fecha"])
    df_completo["Fecha_Corta"] = df_completo["Fecha_dt"].dt.strftime("%d/%m/%y")
    dias_espanol = {'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles', 'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'}
    
    def asignar_dia_o_feriado(fecha_obj):
        dt_val = fecha_obj.date() if isinstance(fecha_obj, pd.Timestamp) else fecha_obj
        if dt_val in FERIADOS_ARGENTINA_2026: return "Feriado"
        return dias_espanol.get(fecha_obj.day_name(), "Lunes")
        
    df_completo["Dia_Semana"] = df_completo["Fecha_dt"].apply(asignar_dia_o_feriado)
    
    def normalizar_situacion_feriado(row):
        dt_val = row["Fecha_dt"].date() if isinstance(row["Fecha_dt"], pd.Timestamp) else row["Fecha_dt"]
        sit = str(row["Situacion_Presentismo_Limpia"]).strip()
        if dt_val in FERIADOS_ARGENTINA_2026 and sit in ["0", "0.0", "", "nan", "None", "Sin Registro"]: return "Feriado"
        return sit
        
    df_completo["Situacion_Presentismo"] = df_completo.apply(normalizar_situacion_feriado, axis=1)
    df_completo["Situacion_Presentismo_Limpia"] = df_completo["Situacion_Presentismo"]
    df_completo = df_completo[df_completo["Dia_Semana"] != "Domingo"].copy()
    df_completo["Fecha_Solo_Fecha"] = df_completo["Fecha_dt"].dt.date
    
    codigos_no_planificados = ["aus c/a", "aus s/a", "aus del", "enf", "enf.fam", "susp", "art", "lic. maternidad", "lic. paternidad", "lic. casamiento", "lic. fallecimiento", "lic. examen", "lic. varias", "pg", "baja"]
    situacion_clean_lower = df_completo["Situacion_Presentismo_Limpia"].astype(str).str.strip().str.lower()
    df_completo["Jornada_Planificada (S/N)"] = np.where(situacion_clean_lower.isin(codigos_no_planificados), "S", "N")
    df_presupuesto = cargar_horas_presupuestadas()
    
    return df_completo, df_presupuesto
def cargar_budget_mensual(mes_seleccionado):
    """
    Lee el archivo budget.csv desde las carpetas del proyecto y devuelve 
    un DataFrame con las columnas 'Fecha_Corta' y 'Budget_VL' para el mes seleccionado.
    """
    carpetas = [
        "Datos_mensuales", 
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "Datos_mensuales"), 
        os.path.dirname(os.path.abspath(__file__)), 
        os.getcwd()
    ]
    ruta_csv = None
    for c in carpetas:
        if os.path.exists(c) and os.path.isdir(c):
            for archivo in os.listdir(c):
                if "budget" in archivo.lower() and archivo.lower().endswith(".csv"):
                    ruta_csv = os.path.join(c, archivo)
                    break
            if ruta_csv: 
                break

    if not ruta_csv or not os.path.exists(ruta_csv):
        return None

    try:
        # Leemos el CSV con separador ';'
        df_b = pd.read_csv(ruta_csv, sep=';', encoding='utf-8-sig')
        df_b.columns = [str(col).strip() for col in df_b.columns]
        
        # Convertimos la columna 'Jornada' a datetime
        df_b["Fecha_dt"] = pd.to_datetime(df_b["Jornada"], format="%d/%m/%Y", errors='coerce')
        
        # Filtramos por el mes seleccionado
        df_b = df_b[df_b["Fecha_dt"].dt.month == mes_seleccionado].copy()
        df_b["Fecha_Corta"] = df_b["Fecha_dt"].dt.strftime("%d/%m")
        df_b["Budget_VL"] = pd.to_numeric(df_b["VL"], errors='coerce').fillna(0)
        
        return df_b[["Fecha_Corta", "Budget_VL"]]
    except Exception as e:
        return None

def obtener_ftes_presupuestados(mes_seleccionado=10, anio_seleccionado=2026):
    """
    Carga el archivo FTEs_ausentes_presupuestados.csv y retorna el valor de 
    FTEs presupuestados para el mes y año seleccionados.
    Si no existe o no hay datos, retorna 0.0 de forma defensiva.
    """
    carpetas = [
        "Datos_mensuales",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "Datos_mensuales"),
        os.path.dirname(os.path.abspath(__file__)),
        os.getcwd()
    ]
    
    ruta_csv = None
    for c in carpetas:
        if os.path.exists(c) and os.path.isdir(c):
            for archivo in os.listdir(c):
                nombre_lower = archivo.lower()
                if "fte" in nombre_lower and "presupuest" in nombre_lower and nombre_lower.endswith(".csv"):
                    ruta_csv = os.path.join(c, archivo)
                    break
            if ruta_csv:
                break
                
    if not ruta_csv or not os.path.exists(ruta_csv):
        return 0.0

    try:
        # Intentamos leer con separador ';' (estándar de Excel en español)
        df_ppto = pd.read_csv(ruta_csv, sep=';', encoding='utf-8-sig', low_memory=False)
        if len(df_ppto.columns) == 1:
            df_ppto = pd.read_csv(ruta_csv, sep=',', encoding='utf-8-sig', low_memory=False)
    except Exception:
        return 0.0

    # Limpiamos nombres de columnas
    df_ppto.columns = [str(col).strip() for col in df_ppto.columns]
    
    # Identificación dinámica de columnas
    col_mes = next((c for c in df_ppto.columns if c.lower() in ["mes"]), None)
    col_anio = next((c for c in df_ppto.columns if c.lower() in ["año", "anio", "ano"]), None)
    col_fte = next((c for c in df_ppto.columns if "fte" in c.lower()), None)
    
    if not col_mes or not col_fte:
        return 0.0

    # Conversión a números
    df_ppto[col_mes] = pd.to_numeric(df_ppto[col_mes], errors='coerce')
    df_ppto[col_fte] = pd.to_numeric(df_ppto[col_fte].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)
    
    filtro = df_ppto[col_mes] == mes_seleccionado
    if col_anio and anio_seleccionado:
        df_ppto[col_anio] = pd.to_numeric(df_ppto[col_anio], errors='coerce')
        filtro = filtro & (df_ppto[col_anio] == anio_seleccionado)
        
    df_filtrado = df_ppto[filtro]
    
    if not df_filtrado.empty:
        return float(df_filtrado[col_fte].iloc[0])
    
    return 0.0    