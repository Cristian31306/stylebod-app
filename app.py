import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA (MOBILE-FRIENDLY) ---
st.set_page_config(
    page_title="Gestión StyleBod",
    page_icon="https://img.icons8.com/material-rounded/96/hanger.png",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .block-container { padding: 1.5rem 1rem 1rem 1rem; }
    .stButton>button { width: 100%; height: 3em; font-weight: bold; border-radius: 8px; }
    h1 { font-size: 2.2rem !important; line-height: 1.2 !important; }
    .stTabs [data-baseweb="tab-list"] { overflow-x: auto; }
</style>
""", unsafe_allow_html=True)

# --- INICIALIZAR CLIENTE DE SUPABASE ---
@st.cache_resource
def init_connection() -> Client:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except KeyError:
        st.error("Faltan credenciales de Supabase en secrets.toml")
        st.stop()

supabase = init_connection()

# --- AUTENTICACIÓN (LOGIN) ---
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    st.title(":material/lock: Acceso Restringido")
    st.write("Por favor, ingresa tu PIN para acceder al sistema.")
    with st.form("login_form"):
        pwd = st.text_input("PIN de seguridad", type="password")
        if st.form_submit_button("Ingresar", type="primary"):
            if pwd == st.secrets.get("APP_PASSWORD", "1234"):
                st.session_state["autenticado"] = True
                st.rerun()
            else:
                st.error("PIN Incorrecto.")
    st.stop() 

# --- FUNCIONES DE CONSULTA ---
@st.cache_data(ttl=60)
def fetch_inventario():
    resp = supabase.table("tabla_inventario").select("*").execute()
    return pd.DataFrame(resp.data)

@st.cache_data(ttl=60)
def fetch_ventas():
    resp = supabase.table("tabla_ventas").select("*, tabla_inventario(modelo, color)").order('creado_en', desc=True).execute()
    return pd.DataFrame(resp.data)

@st.cache_data(ttl=60)
def fetch_gastos():
    resp = supabase.table("tabla_gastos").select("*").execute()
    return pd.DataFrame(resp.data)

def limpiar_cache():
    fetch_inventario.clear()
    fetch_ventas.clear()
    fetch_gastos.clear()

def formato_moneda(valor):
    # Esto asegura que no haya decimales y use punto de separador de miles
    return f"${int(valor):,.0f}".replace(",", ".")

# --- INTERFAZ PRINCIPAL ---
st.title("Panel StyleBod")

tab_venta, tab_gastos, tab_historial, tab_metricas, tab_inventario = st.tabs([
    ":material/shopping_cart: Venta", 
    ":material/payments: Gastos", 
    ":material/history: Historial", 
    ":material/monitoring: Métricas", 
    ":material/inventory: Inventario"
])

# ==========================================
# PESTAÑA 1: VENTA
# ==========================================
with tab_venta:
    st.subheader("Registrar Nueva Venta")
    df_inv = fetch_inventario()
    if df_inv.empty:
        st.warning("No hay productos en el inventario.")
    else:
        if 'activo' not in df_inv.columns:
            df_inv['activo'] = True
            
        df_disponible = df_inv[(df_inv['stock_actual'] > 0) & (df_inv['activo'] == True)].copy()
        
        if df_disponible.empty:
            st.error("Todos los productos están agotados o desactivados.")
        else:
            df_disponible['label'] = df_disponible['modelo'] + " - " + df_disponible['color'] + " (Disponibles: " + df_disponible['stock_actual'].astype(str) + ")"
            with st.form("form_venta", clear_on_submit=True):
                producto_sel = st.selectbox("Selecciona el producto a vender", df_disponible['label'].tolist())
                prod_idx = df_disponible[df_disponible['label'] == producto_sel].index[0]
                prod_id = df_disponible.loc[prod_idx, 'id']
                precio_sug = int(df_disponible.loc[prod_idx, 'precio_venta_sugerido'])
                costo_compra = int(df_disponible.loc[prod_idx, 'costo_compra'])
                stock_max = int(df_disponible.loc[prod_idx, 'stock_actual'])
                
                c1, c2 = st.columns(2)
                cantidad = c1.number_input("Cantidad", min_value=1, max_value=stock_max, value=1, step=1)
                precio_cobrado = c2.number_input("Precio unitario cobrado", min_value=0, value=precio_sug, step=1000)
                
                metodo_pago = st.selectbox("Método de Pago", ["Nequi", "Efectivo", "Daviplata"])
                tipo_domicilio = st.selectbox("Modalidad de Entrega", ["Pagado por cliente", "Asumido por negocio", "Retiro en persona"])
                
                costo_dom = st.number_input("Costo del Domicilio", min_value=0, value=0, step=1000, help="Déjalo en cero si no hubo. Si elegiste 'Asumido por negocio', se restará de tu ganancia.")
                
                if st.form_submit_button("Confirmar Venta", type="primary"):
                    costo_real_asumido = int(costo_dom) if tipo_domicilio == "Asumido por negocio" else 0
                    ganancia_neta = (int(precio_cobrado) * cantidad) - (costo_compra * cantidad) - costo_real_asumido
                    
                    data_venta = {
                        "producto_id": prod_id, "cantidad": int(cantidad), "precio_cobrado": int(precio_cobrado),
                        "metodo_pago": metodo_pago, "tipo_domicilio": tipo_domicilio,
                        "costo_domicilio_asumido": int(costo_real_asumido), "ganancia_neta": int(ganancia_neta)
                    }
                    try:
                        supabase.table("tabla_ventas").insert(data_venta).execute()
                        nuevo_stock = stock_max - cantidad
                        supabase.table("tabla_inventario").update({"stock_actual": int(nuevo_stock)}).eq("id", prod_id).execute()
                        st.success(f"¡Venta registrada con éxito! Ganancia Neta: {formato_moneda(ganancia_neta)}")
                        limpiar_cache()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

# ==========================================
# PESTAÑA 2: GASTOS
# ==========================================
with tab_gastos:
    st.subheader("Registrar Gasto Operativo")
    st.markdown("Añade pagos de publicidad, empaques, transporte extra, etc. para calcular tu flujo de caja real.")
    with st.form("form_gastos", clear_on_submit=True):
        concepto = st.text_input("Concepto o Motivo del Gasto (Ej: Bolsas Kraft)")
        monto = st.number_input("Monto ($)", min_value=0, step=1000)
        if st.form_submit_button("Registrar Gasto"):
            if concepto.strip() and monto > 0:
                try:
                    supabase.table("tabla_gastos").insert({"concepto": concepto.strip(), "monto": int(monto)}).execute()
                    st.success("Gasto registrado correctamente.")
                    limpiar_cache()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.error("El concepto y el monto son obligatorios.")

    st.markdown("---")
    st.write("**Últimos Gastos Registrados**")
    try:
        df_g = fetch_gastos()
        if not df_g.empty:
            df_g['creado_en'] = pd.to_datetime(df_g['creado_en'])
            df_g = df_g.sort_values(by='creado_en', ascending=False)
            
            for idx, row in df_g.head(10).iterrows():
                with st.container(border=True):
                    fecha_gasto = row['creado_en'].strftime('%d/%m/%Y %I:%M %p')
                    c1, c2, c3 = st.columns([3, 2, 1])
                    c1.markdown(f"**{row['concepto']}**")
                    c1.caption(f"{fecha_gasto}")
                    c2.markdown(f"**Valor:** {formato_moneda(row['monto'])}")
                    
                    if c3.button("Anular", key=f"del_gasto_{row['id']}", help="Eliminar este gasto"):
                        try:
                            supabase.table("tabla_gastos").delete().eq("id", row['id']).execute()
                            st.success("Gasto anulado exitosamente.")
                            limpiar_cache()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al anular gasto: {e}")
        else:
            st.info("No hay gastos registrados recientes.")
    except Exception:
        pass

# ==========================================
# PESTAÑA 3: HISTORIAL (Y ANULACIONES)
# ==========================================
with tab_historial:
    st.subheader("Últimas Ventas")
    df_v = fetch_ventas()
    if df_v.empty:
        st.info("No hay ventas registradas.")
    else:
        st.markdown("Revisa o anula ventas recientes. Al anular, el stock volverá automáticamente al inventario.")
        for idx, row in df_v.head(20).iterrows():
            with st.container(border=True):
                nombre_prod = row['tabla_inventario']['modelo'] + " - " + row['tabla_inventario']['color'] if isinstance(row['tabla_inventario'], dict) else "Prod. Eliminado"
                fecha_formateada = pd.to_datetime(row['creado_en']).strftime('%d/%m/%Y %I:%M %p')
                
                c1, c2, c3 = st.columns([3, 2, 1])
                c1.markdown(f"**{nombre_prod}** (x{row['cantidad']})")
                c1.caption(f"{fecha_formateada} | {row['metodo_pago']}")
                c2.markdown(f"**Ganancia:** {formato_moneda(row['ganancia_neta'])}")
                
                if c3.button("Anular", key=f"del_{row['id']}", help="Eliminar venta y devolver stock"):
                    try:
                        supabase.table("tabla_ventas").delete().eq("id", row['id']).execute()
                        if row['producto_id']:
                            inv_actual = supabase.table("tabla_inventario").select("stock_actual").eq("id", row['producto_id']).execute()
                            if inv_actual.data:
                                stock_viejo = inv_actual.data[0]['stock_actual']
                                supabase.table("tabla_inventario").update({"stock_actual": stock_viejo + int(row['cantidad'])}).eq("id", row['producto_id']).execute()
                        st.success("Venta anulada con éxito.")
                        limpiar_cache()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al anular: {e}")

# ==========================================
# PESTAÑA 4: MÉTRICAS AVANZADAS
# ==========================================
with tab_metricas:
    st.subheader("Resumen Financiero")
    df_v = fetch_ventas()
    try:
        df_g = fetch_gastos()
    except Exception:
        df_g = pd.DataFrame()
    
    if df_v.empty:
        st.info("No hay datos suficientes para mostrar métricas.")
    else:
        filtro = st.selectbox("Rango de Fechas", ["Últimos 7 Días", "Este Mes", "Mes Pasado", "Histórico Total"])
        df_v['creado_en'] = pd.to_datetime(df_v['creado_en'])
        if not df_g.empty:
            df_g['creado_en'] = pd.to_datetime(df_g['creado_en'])
        
        ahora = datetime.now(df_v['creado_en'].dt.tz)
        if filtro == "Últimos 7 Días":
            inicio = ahora - timedelta(days=7)
            df_v_filtrado = df_v[df_v['creado_en'] >= inicio]
            df_g_filtrado = df_g[df_g['creado_en'] >= inicio] if not df_g.empty else pd.DataFrame()
        elif filtro == "Este Mes":
            inicio = ahora.replace(day=1, hour=0, minute=0, second=0)
            df_v_filtrado = df_v[df_v['creado_en'] >= inicio]
            df_g_filtrado = df_g[df_g['creado_en'] >= inicio] if not df_g.empty else pd.DataFrame()
        elif filtro == "Mes Pasado":
            fin = ahora.replace(day=1, hour=0, minute=0, second=0) - timedelta(seconds=1)
            inicio = fin.replace(day=1)
            df_v_filtrado = df_v[(df_v['creado_en'] >= inicio) & (df_v['creado_en'] <= fin)]
            df_g_filtrado = df_g[(df_g['creado_en'] >= inicio) & (df_g['creado_en'] <= fin)] if not df_g.empty else pd.DataFrame()
        else:
            df_v_filtrado = df_v.copy()
            df_g_filtrado = df_g.copy()
            
        ingresos_totales = int(df_v_filtrado['precio_cobrado'].multiply(df_v_filtrado['cantidad']).sum()) if not df_v_filtrado.empty else 0
        ganancia_bruta = int(df_v_filtrado['ganancia_neta'].sum()) if not df_v_filtrado.empty else 0
        gastos_totales = int(df_g_filtrado['monto'].sum()) if not df_g_filtrado.empty else 0
        utilidad_neta = ganancia_bruta - gastos_totales
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ingresos Brutos", formato_moneda(ingresos_totales))
        c2.metric("Gastos (Egresos)", formato_moneda(gastos_totales), delta_color="inverse")
        c3.metric("Utilidad Real", formato_moneda(utilidad_neta))
        
        st.divider()
        st.write(":material/workspace_premium: **Top Modelos Más Vendidos**")
        if not df_v_filtrado.empty:
            df_v_filtrado['modelo'] = df_v_filtrado['tabla_inventario'].apply(lambda x: x['modelo'] if isinstance(x, dict) else "Desconocido")
            top_modelos = df_v_filtrado.groupby('modelo')['cantidad'].sum().nlargest(5).reset_index()
            if not top_modelos.empty and top_modelos['cantidad'].sum() > 0:
                st.bar_chart(data=top_modelos, x='modelo', y='cantidad', color="#ff4b4b")
            else:
                st.info("No hay ventas en este periodo para graficar.")
            csv = df_v_filtrado.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=":material/download: Descargar Reporte de Ventas (CSV)",
                data=csv,
                file_name=f"ventas_{filtro.replace(' ', '_')}.csv",
                mime="text/csv",
            )
        else:
            st.info("No hay ventas en este periodo para graficar.")

# ==========================================
# PESTAÑA 5: INVENTARIO
# ==========================================
with tab_inventario:
    st.subheader("Gestión de Inventario")
    df_inv_full = fetch_inventario()
    
    if not df_inv_full.empty and 'activo' not in df_inv_full.columns:
        df_inv_full['activo'] = True
    
    with st.expander(":material/input: Registrar Entrada de Mercancía (Reabastecer)"):
        st.markdown("Suma automáticamente nuevas unidades a un modelo que ya existe.")
        if df_inv_full.empty:
            st.info("No hay productos disponibles para reabastecer.")
        else:
            df_existentes = df_inv_full[df_inv_full['activo'] == True].copy()
            if df_existentes.empty:
                st.error("Todos los productos están inactivos.")
            else:
                with st.form("form_entrada", clear_on_submit=True):
                    df_existentes['label'] = df_existentes['modelo'] + " - " + df_existentes['color'] + " (Actual: " + df_existentes['stock_actual'].astype(str) + ")"
                    prod_sel = st.selectbox("Selecciona el producto que llegó", df_existentes['label'].tolist())
                    cant_ingresa = st.number_input("Cantidad que ingresa", min_value=1, step=1)
                    if st.form_submit_button("Sumar al Inventario"):
                        p_idx = df_existentes[df_existentes['label'] == prod_sel].index[0]
                        p_id = df_existentes.loc[p_idx, 'id']
                        s_actual = int(df_existentes.loc[p_idx, 'stock_actual'])
                        n_stock = s_actual + cant_ingresa
                        try:
                            supabase.table("tabla_inventario").update({"stock_actual": n_stock}).eq("id", p_id).execute()
                            st.success(f"¡Se sumaron {cant_ingresa} unidades! Nuevo total en sistema: {n_stock}")
                            limpiar_cache()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

    with st.expander(":material/add_circle: Añadir Nueva Referencia al Sistema"):
        with st.form("form_nuevo_inv", clear_on_submit=True):
            n_modelo = st.text_input("Nombre del Modelo (Ej. Body Cruzado)")
            n_color = st.text_input("Color (Ej. Negro)")
            c1, c2 = st.columns(2)
            n_costo = c1.number_input("Costo de Compra", min_value=0, step=1000)
            n_precio = c2.number_input("Precio de Venta Sug.", min_value=0, step=1000)
            n_stock = st.number_input("Cantidad Inicial", min_value=0, step=1)
                
            if st.form_submit_button("Crear Nuevo Producto"):
                if n_modelo.strip() and n_color.strip():
                    nuevo_data = {
                        "modelo": n_modelo.strip(), "color": n_color.strip(),
                        "costo_compra": int(n_costo), "precio_venta_sugerido": int(n_precio), "stock_actual": n_stock
                    }
                    if 'activo' in df_inv_full.columns:
                        nuevo_data["activo"] = True
                        
                    try:
                        supabase.table("tabla_inventario").insert(nuevo_data).execute()
                        st.success("Referencia creada correctamente.")
                        limpiar_cache()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")
                else:
                    st.error("El modelo y el color son obligatorios.")

    st.markdown("---")
    if not df_inv_full.empty:
        st.write("**Edita directamente la cantidad, los precios, o apaga/prende productos:**")
        df_editable = df_inv_full[['id', 'activo', 'modelo', 'color', 'costo_compra', 'precio_venta_sugerido', 'stock_actual']].copy()
        
        # Forzar visualización limpia sin decimales en la tabla
        df_editable['costo_compra'] = df_editable['costo_compra'].astype(int)
        df_editable['precio_venta_sugerido'] = df_editable['precio_venta_sugerido'].astype(int)

        editado = st.data_editor(
            df_editable,
            column_config={
                "id": None,
                "activo": st.column_config.CheckboxColumn("Activo", help="Desmárcalo para ocultarlo de las ventas"),
                "modelo": st.column_config.TextColumn("Modelo", disabled=True),
                "color": st.column_config.TextColumn("Color", disabled=True),
                "costo_compra": st.column_config.NumberColumn("Costo $", format="%d", min_value=0, step=1000),
                "precio_venta_sugerido": st.column_config.NumberColumn("Precio Sug. $", format="%d", min_value=0, step=1000),
                "stock_actual": st.column_config.NumberColumn("Disponibles", min_value=0, step=1)
            },
            hide_index=True,
            use_container_width=True
        )
        
        if st.button("Guardar Cambios de la Tabla", type="secondary"):
            cambios_aplicados = 0
            for index, row in editado.iterrows():
                original = df_inv_full.loc[df_inv_full['id'] == row['id']].iloc[0]
                if (row['costo_compra'] != int(original['costo_compra']) or 
                    row['precio_venta_sugerido'] != int(original['precio_venta_sugerido']) or 
                    row['stock_actual'] != int(original['stock_actual']) or
                    row['activo'] != original['activo']):
                    try:
                        supabase.table("tabla_inventario").update({
                            "costo_compra": int(row['costo_compra']),
                            "precio_venta_sugerido": int(row['precio_venta_sugerido']),
                            "stock_actual": int(row['stock_actual']),
                            "activo": bool(row['activo'])
                        }).eq("id", row['id']).execute()
                        cambios_aplicados += 1
                    except Exception as e:
                        st.error(f"Error actualizando ID {row['id']}: {e}")
                        
            if cambios_aplicados > 0:
                st.success(f"Se actualizaron {cambios_aplicados} registros exitosamente.")
                limpiar_cache()
                st.rerun()
