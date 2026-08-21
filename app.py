import streamlit as st
import pandas as pd
import plotly.express as px
import io

# Configuración de la página de Streamlit
st.set_page_config(page_title="Calculadora Avanzada de Importación", layout="wide", page_icon="📈")

st.title("📈 Calculadora Avanzada de Costos de Importación, Reposición y Pricing")
st.markdown("Herramienta corporativa con **Prorrateo por Cantidad**, **Markup Inverso** e **IVA dinámico**.")

# --- PANEL LATERAL: Parámetros Globales ---
st.sidebar.header("💵 1. Variables Cambiarias y Multimoneda")
dolar_oficial = st.sidebar.number_input("Dólar Oficial (Aduana / AFIP)", min_value=1.0, value=980.0, step=5.0)
dolar_financiero = st.sidebar.number_input("Dólar Financiero / CCL (Reposición Real)", min_value=1.0, value=1280.0, step=5.0)

st.sidebar.subheader("💱 Cotizaciones vs Dólar (USD)")
eur_usd = st.sidebar.number_input("Euro (EUR/USD)", min_value=0.1, value=1.08, step=0.01)
cny_usd = st.sidebar.number_input("Yuan Chino (CNY/USD)", min_value=0.01, value=0.14, step=0.01)

st.sidebar.header("🚢 2. Modalidad de Pago de Logística Internacional")
pago_logistica_afuera = st.sidebar.checkbox(
    "¿Flete y Seguro se pagan afuera / con dólares financieros propios?", 
    value=True,
    help="ACTIVADO: Valúa el flete/seguro al Dólar Financiero (Escenario Real/Libre). DESACTIVADO: Valúa el flete/seguro al Dólar Oficial."
)

st.sidebar.header("📐 3. Alícuotas Fiscales Globales (%)")
impuesto_pais_pct = st.sidebar.number_input("Impuesto PAIS (%)", min_value=0.0, value=7.5, step=0.5)
tasa_estadistica_pct = st.sidebar.number_input("Tasa de Estadística (%)", min_value=0.0, value=3.0, step=0.5)
iva_pct = st.sidebar.number_input("IVA General (%)", min_value=0.0, value=21.0, step=0.5)
iva_adicional_pct = st.sidebar.number_input("IVA Adicional / Percepción (%)", min_value=0.0, value=20.0, step=0.5)
ganancias_pct = st.sidebar.number_input("Percepción de Ganancias (%)", min_value=0.0, value=6.0, step=0.5)
iibb_pct = st.sidebar.number_input("Percepción Ingresos Brutos (%)", min_value=0.0, value=2.5, step=0.5)

st.sidebar.header("🚚 4. Tasas y Gastos Locales")
tasa_rezago_pct = st.sidebar.number_input("Tasa de Rezago / Almacenaje (% del CIF)", min_value=0.0, value=1.0, step=0.1)
gastos_despacho_fijos_ars = st.sidebar.number_input("Gastos Fijos Despacho/Terminal (ARS Total)", min_value=0.0, value=450000.0, step=10000.0)
honorarios_despachante_pct = st.sidebar.number_input("Honorarios Despachante (% del CIF)", min_value=0.0, value=1.0, step=0.1)

# --- LÓGICA CORE DE CÁLCULO ---
def calcular_simulacion_completa(df_input):
    df = df_input.copy()
    
    # Asegurar mínimos en cantidad
    df['cantidad'] = df['cantidad'].apply(lambda x: max(1, int(x)))
    
    # 1. Normalización Multimoneda a USD (FOB Total)
    def obtener_fob_total_usd(row):
        moneda = str(row['moneda_origen']).upper().strip()
        val_unitario = row['precio_origen']
        cant = row['cantidad']
        fob_u_usd = val_unitario
        if moneda == 'EUR': fob_u_usd = val_unitario * eur_usd
        elif moneda == 'CNY': fob_u_usd = val_unitario * cny_usd
        return fob_u_usd * cant
        
    df['fob_total_usd'] = df.apply(obtener_fob_total_usd, axis=1)
    
    # 2. Base CIF General (Total del Embarque)
    df['cif_total_usd'] = df['fob_total_usd'] + df['flete_usd'] + df['seguro_usd']
    df['cif_total_ars_oficial'] = df['cif_total_usd'] * dolar_oficial
    
    # 3. Derechos e Impuestos Aduaneros Totales
    df['derechos_importacion_ars'] = df['cif_total_ars_oficial'] * (df['arancel_pct'] / 100)
    df['tasa_estadistica_ars'] = df['cif_total_ars_oficial'] * (tasa_estadistica_pct / 100)
    df['impuesto_pais_ars'] = df['cif_total_ars_oficial'] * (impuesto_pais_pct / 100)
    df['tasa_rezago_ars'] = df['cif_total_ars_oficial'] * (tasa_rezago_pct / 100)
    
    base_iva = df['cif_total_ars_oficial'] + df['derechos_importacion_ars'] + df['tasa_estadistica_ars'] + df['tasa_rezago_ars']
    
    df['iva_ars'] = base_iva * (iva_pct / 100)
    df['iva_adicional_ars'] = base_iva * (iva_adicional_pct / 100)
    df['anticipo_ganancias_ars'] = base_iva * (ganancias_pct / 100)
    df['ingresos_brutos_ars'] = base_iva * (iibb_pct / 100)
    
    df['total_impuestos_y_tasas_ars'] = (
        df['derechos_importacion_ars'] + df['tasa_estadistica_ars'] + df['impuesto_pais_ars'] + 
        df['tasa_rezago_ars'] + df['iva_ars'] + df['iva_adicional_ars'] + 
        df['anticipo_ganancias_ars'] + df['ingresos_brutos_ars']
    )
    
    # 4. Gastos Locales de Despacho (Prorrateo entre ítems)
    total_cif_global = df['cif_total_ars_oficial'].sum()
    if total_cif_global > 0:
        df['gastos_fijos_proporcional_ars'] = (df['cif_total_ars_oficial'] / total_cif_global) * gastos_despacho_fijos_ars
    else:
        df['gastos_fijos_proporcional_ars'] = 0.0
        
    df['honorarios_despachante_ars'] = df['cif_total_ars_oficial'] * (honorarios_despachante_pct / 100)
    df['total_gastos_locales_ars'] = df['gastos_fijos_proporcional_ars'] + df['honorarios_despachante_ars']
    
    # 5. Brecha y Costos de Reposición Totales
    df['fob_reposicion_real_ars'] = df['fob_total_usd'] * dolar_financiero
    tc_logistica = dolar_financiero if pago_logistica_afuera else dolar_oficial
    df['flete_seguro_real_ars'] = (df['flete_usd'] + df['seguro_usd']) * tc_logistica
    
    df['costo_total_reposicion_batch_ars'] = (
        df['fob_reposicion_real_ars'] + df['flete_seguro_real_ars'] + 
        df['total_impuestos_y_tasas_ars'] + df['total_gastos_locales_ars']
    )
    
    # 6. MÉTRICAS UNITARIAS CRÍTICAS (La división por piezas)
    df['costo_reposicion_unitario_ars'] = df['costo_total_reposicion_batch_ars'] / df['cantidad']
    df['fob_unitario_usd'] = df['fob_total_usd'] / df['cantidad']
    
    # Factor de nacionalización (Costo Unitario Real ARS pasado a USD Financiero / FOB Unitario USD)
    df['factor_nacionalizacion'] = (df['costo_reposicion_unitario_ars'] / dolar_financiero) / df['fob_unitario_usd']
    
    # 7. Pricing Unitario Local (Markup Inverso)
    def calcular_precio_neto_u(row):
        margen = row['margen_pretendido_pct']
        if margen >= 100: return row['costo_reposicion_unitario_ars'] * 2
        return row['costo_reposicion_unitario_ars'] / (1 - (margen / 100))
        
    df['precio_venta_neto_unitario_ars'] = df.apply(calcular_precio_neto_u, axis=1)
    df['utilidad_neta_unitaria_ars'] = df['precio_venta_neto_unitario_ars'] - df['costo_reposicion_unitario_ars']
    
    df['iva_ventas_unitario_ars'] = df['precio_venta_neto_unitario_ars'] * (df['iva_ventas_pct'] / 100)
    df['precio_venta_final_unitario_con_iva_ars'] = df['precio_venta_neto_unitario_ars'] + df['iva_ventas_unitario_ars']
    
    # Proyección de facturación total del lote
    df['facturacion_total_lote_con_iva_ars'] = df['precio_venta_final_unitario_con_iva_ars'] * df['cantidad']
    
    return df

# --- INTERFAZ CENTRAL ---
uploaded_file = st.file_uploader("📂 Cargá tu archivo de productos (CSV)", type=["csv"])

if uploaded_file is not None:
    try:
        df_origen = pd.read_csv(uploaded_file)
        columnas_requeridas = ['item', 'cantidad', 'moneda_origen', 'precio_origen', 'flete_usd', 'seguro_usd', 'arancel_pct', 'margen_pretendido_pct', 'iva_ventas_pct']
        
        if not all(col in df_origen.columns for col in columnas_requeridas):
            st.error(f"El archivo debe contener exactamente estas columnas: {', '.join(columnas_requeridas)}")
        else:
            df_resultado = calcular_simulacion_completa(df_origen)
            
            tot_fob_usd = df_resultado['fob_total_usd'].sum()
            tot_imp_ars = df_resultado['total_impuestos_y_tasas_ars'].sum()
            tot_costo_ars = df_resultado['costo_total_reposicion_batch_ars'].sum()
            tot_venta_publico = df_resultado['facturacion_total_lote_con_iva_ars'].sum()
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("FOB Total Operación", f"USD {tot_fob_usd:,.2f}")
            c2.metric("Impuestos + Tasas Totales", f"ARS {tot_imp_ars:,.2f}")
            c3.metric("Inversión de Reposición Total", f"ARS {tot_costo_ars:,.2f}")
            c4.metric("Facturación Proyectada Lote", f"ARS {tot_venta_publico:,.2f}")
            
            st.write("---")
            
            # VISTA COMERCIAL UNITARIA
            st.subheader("📋 Matriz de Costos y Precios de Venta UNITARIOS Sugeridos")
            vista_comercial = df_resultado[[
                'item', 'cantidad', 'precio_origen', 'costo_reposicion_unitario_ars', 
                'margen_pretendido_pct', 'utilidad_neta_unitaria_ars', 'precio_venta_neto_unitario_ars', 'iva_ventas_pct', 'precio_venta_final_unitario_con_iva_ars', 'factor_nacionalizacion'
            ]].copy()
            
            st.dataframe(vista_comercial.style.format({
                'precio_origen': '{:,.2f}', 'costo_reposicion_unitario_ars': 'ARS {:,.2f}',
                'margen_pretendido_pct': '{:.1f}%', 'utilidad_neta_unitaria_ars': 'ARS {:,.2f}',
                'precio_venta_neto_unitario_ars': 'ARS {:,.2f}', 'iva_ventas_pct': '{:.1f}%', 'precio_venta_final_unitario_con_iva_ars': 'ARS {:,.2f}',
                'factor_nacionalizacion': '{:.4f}'
            }), use_container_width=True)
            
            st.write("---")
            st.subheader("📊 Análisis de Composición del Costo Real de la Operación")
            
            componentes_costo = {
                "FOB Reposición Real (Divisas)": float(df_resultado['fob_reposicion_real_ars'].sum()),
                "Flete y Seguro Internacional": float(df_resultado['flete_seguro_real_ars'].sum()),
                "Derechos de Importación": float(df_resultado['derechos_importacion_ars'].sum()),
                "Tasa Estadística": float(df_resultado['tasa_estadistica_ars'].sum()),
                "Impuesto PAIS": float(df_resultado['impuesto_pais_ars'].sum()),
