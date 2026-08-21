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
pago_logistica_afuera = st.sidebar.checkbox("¿Flete y Seguro se pagan afuera?", value=True)

st.sidebar.header("📐 3. Alícuotas Fiscales Globales (%)")
impuesto_pais_pct = st.sidebar.number_input("Impuesto PAIS (%)", min_value=0.0, value=7.5, step=0.5)
tasa_estadistica_pct = st.sidebar.number_input("Tasa de Estadística (%)", min_value=0.0, value=3.0, step=0.5)
iva_pct = st.sidebar.number_input("IVA General (%)", min_value=0.0, value=21.0, step=0.5)
iva_adicional_pct = st.sidebar.number_input("IVA Adicional / Percepción (%)", min_value=0.0, value=20.0, step=0.5)
ganancias_pct = st.sidebar.number_input("Percepción de Ganancias (%)", min_value=0.0, value=6.0, step=0.5)
iibb_pct = st.sidebar.number_input("Percepción Ingresos Brutos (%)", min_value=0.0, value=2.5, step=0.5)

st.sidebar.header("🚚 4. Tasas y Gastos Locales")
tasa_rezago_pct = st.sidebar.number_input("Tasa de Rezago (%)", min_value=0.0, value=1.0, step=0.1)
gastos_despacho_fijos_ars = st.sidebar.number_input("Gastos Fijos Despacho (ARS Total)", min_value=0.0, value=450000.0, step=10000.0)
honorarios_despachante_pct = st.sidebar.number_input("Honorarios Despachante (%)", min_value=0.0, value=1.0, step=0.1)

# --- LÓGICA CORE DE CÁLCULO ---
def calcular_simulacion_completa(df_input):
    df = df_input.copy()
    df['cantidad'] = df['cantidad'].apply(lambda x: max(1, int(x)))
    
    def obtener_fob_total_usd(row):
        moneda = str(row['moneda_origen']).upper().strip()
        val_unitario = row['precio_origen']
        cant = row['cantidad']
        fob_u_usd = val_unitario
        if moneda == 'EUR': fob_u_usd = val_unitario * eur_usd
        elif moneda == 'CNY': fob_u_usd = val_unitario * cny_usd
        return fob_u_usd * cant
        
    df['fob_total_usd'] = df.apply(obtener_fob_total_usd, axis=1)
    df['cif_total_usd'] = df['fob_total_usd'] + df['flete_usd'] + df['seguro_usd']
    df['cif_total_ars_oficial'] = df['cif_total_usd'] * dolar_oficial
    
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
    
    total_cif_global = df['cif_total_ars_oficial'].sum()
    if total_cif_global > 0:
        df['gastos_fijos_proporcional_ars'] = (df['cif_total_ars_oficial'] / total_cif_global) * gastos_despacho_fijos_ars
    else:
        df['gastos_fijos_proporcional_ars'] = 0.0
        
    df['honorarios_despachante_ars'] = df['cif_total_ars_oficial'] * (honorarios_despachante_pct / 100)
    df['total_gastos_locales_ars'] = df['gastos_fijos_proporcional_ars'] + df['honorarios_despachante_ars']
    
    df['fob_reposicion_real_ars'] = df['fob_total_usd'] * dolar_financiero
    tc_logistica = dolar_financiero if pago_logistica_afuera else dolar_oficial
    df['flete_seguro_real_ars'] = (df['flete_usd'] + df['seguro_usd']) * tc_logistica
    
    df['costo_total_reposicion_batch_ars'] = (
        df['fob_reposicion_real_ars'] + df['flete_seguro_real_ars'] + 
        df['total_impuestos_y_tasas_ars'] + df['total_gastos_locales_ars']
    )
    
    df['costo_reposicion_unitario_ars'] = df['costo_total_reposicion_batch_ars'] / df['cantidad']
    df['fob_unitario_usd'] = df['fob_total_usd'] / df['cantidad']
    df['factor_nacionalizacion'] = (df['costo_reposicion_unitario_ars'] / dolar_financiero) / df['fob_unitario_usd']
    
    def calcular_precio_neto_u(row):
        margen = row['margen_pretendido_pct']
        if margen >= 100: return row['costo_reposicion_unitario_ars'] * 2
        return row['costo_reposicion_unitario_ars'] / (1 - (margen / 100))
        
    df['precio_venta_neto_unitario_ars'] = df.apply(calcular_precio_neto_u, axis=1)
    df['utilidad_neta_unitaria_ars'] = df['precio_venta_neto_unitario_ars'] - df['costo_reposicion_unitario_ars']
    df['iva_ventas_unitario_ars'] = df['precio_venta_neto_unitario_ars'] * (df['iva_ventas_pct'] / 100)
    df['precio_venta_final_unitario_con_iva_ars'] = df['precio_venta_neto_unitario_ars'] + df['iva_ventas_unitario_ars']
    df['facturacion_total_lote_con_iva_ars'] = df['precio_venta_final_unitario_con_iva_ars'] * df['cantidad']
    
    return df

# --- INTERFAZ CENTRAL ---
uploaded_file = st.file_uploader("📂 Cargá tu archivo de productos (CSV)", type=["csv"])

if uploaded_file is not None:
    df_origen = pd.read_csv(uploaded_file)
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
        "Tasa de Rezago / Almacenaje": float(df_resultado['tasa_rezago_ars'].sum()),
        "IVA (Aduana)": float(df_resultado['iva_ars'].sum()),
        "IVA Adicional": float(df_resultado['iva_adicional_ars'].sum()),
        "Anticipo de Ganancias": float(df_resultado['anticipo_ganancias_ars'].sum()),
        "Percepción Ingresos Brutos": float(df_resultado['ingresos_brutos_ars'].sum()),
        "Gastos de Despacho y Logística Local": float(df_resultado['total_gastos_locales_ars'].sum())
    }
    
    df_pie = pd.DataFrame(list(componentes_costo.items()), columns=['Concepto', 'Monto_ARS'])
    df_pie = df_pie[df_pie['Monto_ARS'] > 0]
    
    fig = px.pie(df_pie, values='Monto_ARS', names='Concepto', title='Distribución de la Inversión Total', hole=0.4)
    st.plotly_chart(fig, use_container_width=True)
    
    with st.expander("🔍 Ver Sábana de Datos Técnica Completa"):
        st.dataframe(df_resultado.style.format(lambda x: f"{x:,.2f}" if isinstance(x, (int, float)) else x), use_container_width=True)
        
    st.subheader("💾 Exportar Resultados Comerciales")
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_resultado.to_excel(writer, index=False, sheet_name='Pricing Unitario')
    processed_data = output.getvalue()
    
    st.download_button(
        label="📥 Descargar Master Excel De Costos y Precios (.xlsx)",
        data=processed_data,
        file_name='master_importacion_unitario.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
else:st.info("💡 Subí un archivo CSV estructurado para arrancar.")
