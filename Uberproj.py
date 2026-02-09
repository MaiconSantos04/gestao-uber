import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
import plotly.express as px
from datetime import date
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib3
import time
import random

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="Gestão Uber Pro", layout="wide")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- SISTEMA FIPE BLINDADO (MANTIDO O QUE FUNCIONOU) ---
HEADERS_ROTATIVOS = [
    {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'},
    {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15'}
]

@st.cache_data(ttl=3600, show_spinner=False)
def buscar_marcas_blindado():
    try:
        resp = requests.get("https://parallelum.com.br/fipe/api/v1/carros/marcas", headers=random.choice(HEADERS_ROTATIVOS), timeout=3, verify=False)
        if resp.status_code == 200: return {m['nome']: m['codigo'] for m in resp.json()}
    except: pass
    try:
        resp = requests.get("https://brasilapi.com.br/api/fipe/marcas/v1/carros", headers=random.choice(HEADERS_ROTATIVOS), timeout=3)
        if resp.status_code == 200: return {m['nome']: m['valor'] for m in resp.json()}
    except: pass
    return {"Chevrolet": "23", "Fiat": "21", "Volkswagen": "59", "Ford": "22", "Hyundai": "25", "Toyota": "56", "Honda": "20", "Renault": "44", "Nissan": "43", "Jeep": "29"}

@st.cache_data(ttl=3600, show_spinner=False)
def buscar_modelos(cod_marca):
    try:
        url = f"https://parallelum.com.br/fipe/api/v1/carros/marcas/{cod_marca}/modelos"
        resp = requests.get(url, headers=random.choice(HEADERS_ROTATIVOS), timeout=5, verify=False)
        if resp.status_code == 200: return {m['nome']: m['codigo'] for m in resp.json()['modelos']}
    except: return {}

@st.cache_data(ttl=3600, show_spinner=False)
def buscar_anos(cod_marca, cod_modelo):
    try:
        url = f"https://parallelum.com.br/fipe/api/v1/carros/marcas/{cod_marca}/modelos/{cod_modelo}/anos"
        resp = requests.get(url, headers=random.choice(HEADERS_ROTATIVOS), timeout=5, verify=False)
        if resp.status_code == 200: return {a['nome']: a['codigo'] for a in resp.json()}
    except: return {}

def buscar_valor_final(cod_marca, cod_modelo, cod_ano):
    try:
        url = f"https://parallelum.com.br/fipe/api/v1/carros/marcas/{cod_marca}/modelos/{cod_modelo}/anos/{cod_ano}"
        resp = requests.get(url, headers=random.choice(HEADERS_ROTATIVOS), timeout=5, verify=False)
        if resp.status_code == 200: return resp.json()
    except: return None

# --- GOOGLE SHEETS ---
def conectar_gsheets(nome_aba="Dados"):
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except:
        try: creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        except: st.error("Erro credenciais"); st.stop()
    client = gspread.authorize(creds)
    try:
        sh = client.open("GestaoUberDB")
        try: return sh.worksheet(nome_aba)
        except: 
            if nome_aba=="Config": 
                ws = sh.add_worksheet("Config", 30, 2); ws.append_row(["Parametro","Valor"]); return ws
            st.error(f"Aba {nome_aba} não existe"); st.stop()
    except: st.error("Planilha não encontrada"); st.stop()

# --- CONFIGURAÇÃO ---
def carregar_config():
    if 'config_user' in st.session_state: return st.session_state['config_user']
    try:
        ws = conectar_gsheets("Config"); data = ws.get_all_values()
        cfg = {r[0]: r[1] for r in data[1:] if len(r)>1}
        padrao = {"valor_carro": 83000.0, "custo_fixo_anual": 6300.0, "dias_trabalho_mes": 4.0, "media_km_dia": 150.0, "consumo_carro": 10.0, "preco_gasolina": 5.80, "custo_manut_km": 0.25, "custo_deprec_km": 0.40, "fipe_nome_carro": "Não Definido"}
        final = {k: float(v) if k not in ['fipe_nome_carro','fipe_marca_id','fipe_modelo_id','fipe_ano_id'] else v for k,v in cfg.items()}
        st.session_state['config_user'] = {**padrao, **final}
        return st.session_state['config_user']
    except: return {}

def salvar_config(cfg):
    try:
        ws = conectar_gsheets("Config"); ws.clear(); ws.append_row(["Parametro","Valor"])
        ws.append_rows([[k,str(v)] for k,v in cfg.items()])
        st.session_state['config_user'] = cfg
        return True
    except: return False

# --- DADOS ---
def limpar_valor(v):
    if isinstance(v, (float,int)): return float(v)
    try: return float(str(v).replace('R$','').replace('.','').replace(',','.').strip())
    except: return 0.0

def carregar_dados():
    try:
        ws = conectar_gsheets("Dados"); rows = ws.get_all_values()
        if len(rows)<2: return pd.DataFrame(columns=['Data','Ganhos','Bonus','Km_Rodado','Gastos_Combustivel','Obs'])
        df = pd.DataFrame(rows[1:], columns=rows[0])
        for c in ['Ganhos','Bonus','Km_Rodado','Gastos_Combustivel']: 
            if c in df.columns: df[c] = df[c].apply(limpar_valor)
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce').dt.date
        df['ID'] = df.index + 2
        return df
    except: return pd.DataFrame()

def salvar_dados(df_novo):
    try:
        ws = conectar_gsheets("Dados")
        row = df_novo.iloc[0]
        lista = [str(row['Data']), f"{row['Ganhos']:.2f}".replace('.',','), f"{row['Bonus']:.2f}".replace('.',','), 
                 f"{row['Km_Rodado']:.1f}".replace('.',','), f"{row['Gastos_Combustivel']:.2f}".replace('.',','), row['Obs']]
        ws.append_row(lista); return True
    except: return False

def excluir_linha(id_linha):
    try: ws = conectar_gsheets("Dados"); ws.delete_rows(id_linha); return True
    except: return False

def desfazer():
    try: ws = conectar_gsheets("Dados"); ws.delete_rows(len(ws.get_all_values())); return True
    except: return False

# --- GRÁFICOS (RESTAURADOS) ---
def estilo_grafico(fig, titulo_y):
    fig.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside', marker_cornerradius=5, hovertemplate='<b>%{data.name}</b>: R$ %{y:,.2f}<extra></extra>')
    fig.update_layout(title_x=0.5, yaxis_title=titulo_y, xaxis_title=None, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', showlegend=False, margin=dict(t=60, b=30, l=20, r=20))
    return fig

MESES = {'Jan':'Jan', 'Feb':'Fev', 'Mar':'Mar', 'Apr':'Abr', 'May':'Mai', 'Jun':'Jun', 'Jul':'Jul', 'Aug':'Ago', 'Sep':'Set', 'Oct':'Out', 'Nov':'Nov', 'Dec':'Dez'}

# --- APP ---
config = carregar_config()

st.sidebar.title("Navegação")
menu = st.sidebar.radio("Ir para:", ["📝 Lançamento Diário", "📋 Extrato Completo", "📅 Relatório Semanal", "📅 Relatório Mensal", "📅 Relatório Anual"])

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Custos & Calculadora")

# --- SEÇÃO 1: FIPE (COM ABAS - CORREÇÃO QUE FUNCIONOU) ---
with st.sidebar.expander("🚘 Meu Carro (FIPE)", expanded=True):
    st.info(f"Carro Atual: **{config.get('fipe_nome_carro', '---')}**\n\nValor Base: **R$ {config.get('valor_carro', 0):,.2f}**")
    
    t_auto, t_man = st.tabs(["🔍 Auto", "✍️ Manual"])
    
    with t_auto:
        marcas = buscar_marcas_blindado()
        nm_marca = st.selectbox("Marca", sorted(marcas.keys()), key="sb_m")
        if nm_marca:
            id_marca = marcas[nm_marca]
            modelos = buscar_modelos(id_marca)
            if modelos:
                nm_modelo = st.selectbox("Modelo", sorted(modelos.keys()), key="sb_mod")
                if nm_modelo:
                    id_modelo = modelos[nm_modelo]
                    anos = buscar_anos(id_marca, id_modelo)
                    if anos:
                        nm_ano = st.selectbox("Ano", sorted(anos.keys()), key="sb_ano")
                        if st.button("💾 Salvar FIPE"):
                            res = buscar_valor_final(id_marca, id_modelo, anos[nm_ano])
                            if res:
                                v = limpar_valor(res['Valor'])
                                config.update({'valor_carro': v, 'fipe_nome_carro': f"{nm_marca} {nm_modelo}", 'fipe_marca_id': id_marca, 'fipe_modelo_id': id_modelo, 'fipe_ano_id': anos[nm_ano]})
                                salvar_config(config); st.success(f"Atualizado: {v}"); st.rerun()
                            else: st.error("Erro busca.")
                    else: st.info("Carregando anos...")
            else: st.warning("Use aba Manual.")

    with t_man:
        n_man = st.text_input("Nome", config.get('fipe_nome_carro',''), key="nm_man")
        v_man = st.number_input("Valor (R$)", value=float(config.get('valor_carro',0)), format="%.2f", key="vl_man")
        if st.button("💾 Salvar Manual"):
            config.update({'valor_carro': v_man, 'fipe_nome_carro': n_man, 'fipe_marca_id':'', 'fipe_modelo_id':''})
            salvar_config(config); st.success("Salvo!"); st.rerun()

# --- SEÇÃO 2: INPUTS RESTAURADOS (ORGANIZADOS COMO ANTES) ---
with st.sidebar.expander("📝 Parâmetros Gerais", expanded=False):
    # O valor do carro vem da FIPE acima, aqui só mostra
    st.write(f"Valor Veículo: R$ {config.get('valor_carro', 0):,.2f}")
    v_fixo = st.number_input("IPVA+Seguro Anual (R$)", value=float(config.get('custo_fixo_anual', 6000)), format="%.2f")
    dias_mes = st.number_input("Dias Trab/Mês", value=int(config.get('dias_trabalho_mes', 4)))

with st.sidebar.expander("⛽ Combustível e Rodagem", expanded=True):
    km_med = st.number_input("Média KM/Dia", value=float(config.get('media_km_dia', 150)))
    pr_gas = st.number_input("Preço Gasolina (R$)", value=float(config.get('preco_gasolina', 5.80)), format="%.2f")
    cons = st.number_input("Consumo (km/l)", value=float(config.get('consumo_carro', 10)), format="%.1f")

with st.sidebar.expander("🛠️ Manutenção/Depreciação", expanded=False):
    c_manut = st.number_input("Manut/km (R$)", value=float(config.get('custo_manut_km', 0.25)), format="%.2f", step=0.05)
    c_deprec = st.number_input("Deprec/km (R$)", value=float(config.get('custo_deprec_km', 0.40)), format="%.2f", step=0.05)

# CÁLCULOS STOP LOSS
custo_dia_fixo = (v_fixo/12) / dias_mes if dias_mes else 0
custo_km_fixo = custo_dia_fixo / km_med if km_med else 0
custo_km_gas = pr_gas / cons if cons else 0
stop_loss = custo_km_fixo + custo_km_gas + c_manut + c_deprec

st.sidebar.markdown("---")
st.sidebar.markdown("### ⛔ STOP LOSS (Mínimo)")
st.sidebar.metric("Aceitar acima de:", f"R$ {stop_loss:.2f} / km")
st.sidebar.caption(f"Meta Diária IPVA: **R$ {custo_dia_fixo:.2f}**")

if st.sidebar.button("💾 Salvar Parâmetros"):
    config.update({"custo_fixo_anual":v_fixo, "dias_trabalho_mes":dias_mes, "media_km_dia":km_med, "preco_gasolina":pr_gas, "consumo_carro":cons, "custo_manut_km":c_manut, "custo_deprec_km":c_deprec})
    salvar_config(config); st.sidebar.success("Salvo!"); st.rerun()

# --- PÁGINAS RESTAURADAS ---
if menu == "📝 Lançamento Diário":
    st.title("🚗 Controle Diário")
    c1, c2, c3, c4 = st.columns(4)
    ganhos = c1.number_input("Ganhos Corridas (R$)", 0.0, step=10.0, format="%.2f")
    bonus = c2.number_input("Bônus/Promo (R$)", 0.0, step=10.0, format="%.2f")
    km = c3.number_input("KM Rodado", 0.0, step=5.0, format="%.1f")
    gas = c4.number_input("Combustível (R$)", 0.0, step=5.0, format="%.2f")
    obs = st.text_input("Observação")

    # Cálculos Diários
    dia_ipva = custo_dia_fixo
    dia_manut = km * c_manut
    dia_deprec = km * c_deprec
    dia_guardar = dia_ipva + dia_manut + dia_deprec
    dia_lucro = (ganhos + bonus) - dia_guardar - gas

    st.markdown("---")
    k1, k2, k3 = st.columns(3)
    k1.error(f"🚨 GUARDAR HOJE: R$ {dia_guardar:.2f}")
    if dia_lucro > 0: k2.success(f"💵 LUCRO LÍQUIDO: R$ {dia_lucro:.2f}")
    else: k2.error(f"💸 PREJUÍZO: R$ {dia_lucro:.2f}")
    
    media_hj = (ganhos+bonus)/km if km>0 else 0
    k3.metric("Sua Média Hoje", f"R$ {media_hj:.2f} / km", delta=f"{media_hj - stop_loss:.2f} sobre o mínimo")

    # GRÁFICO PIZZA (RESTAURADO)
    fig = go.Figure(data=[go.Pie(labels=['Lucro','Guardar (IPVA+Manut+Deprec)','Combustível'], 
                                 values=[max(0, dia_lucro), dia_guardar, gas], 
                                 hole=.5, textinfo='percent', textposition='inside', 
                                 marker=dict(colors=['#28a745','#dc3545','#ffc107'], line=dict(color='#000000', width=1)))])
    fig.update_layout(height=350, margin=dict(t=30, b=10, l=10, r=10), showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    c_save, c_undo = st.columns([3,1])
    if c_save.button("💾 Salvar no Google Sheets", type="primary", use_container_width=True):
        if ganhos or bonus:
            df_new = pd.DataFrame([{'Data': date.today(), 'Ganhos': ganhos, 'Bonus': bonus, 'Km_Rodado': km, 'Gastos_Combustivel': gas, 'Obs': obs}])
            salvar_dados(df_new); st.success("Salvo com sucesso!"); st.cache_data.clear()
        else: st.warning("Preencha algum valor.")
    if c_undo.button("↩️ Desfazer Último", use_container_width=True):
        if desfazer(): st.toast("Apagado!", icon="🗑️"); st.cache_data.clear()

elif menu == "📋 Extrato Completo":
    st.title("📋 Extrato de Lançamentos")
    df = carregar_dados()
    if not df.empty:
        st.dataframe(df.sort_values('Data', ascending=False), use_container_width=True, column_config={
            "ID": st.column_config.NumberColumn("🆔 ID", format="%d"),
            "Ganhos": st.column_config.NumberColumn(format="R$ %.2f"),
            "Bonus": st.column_config.NumberColumn(format="R$ %.2f"),
            "Gastos_Combustivel": st.column_config.NumberColumn(format="R$ %.2f"),
            "Km_Rodado": st.column_config.NumberColumn(format="%.1f km")
        })
        c_del1, c_del2 = st.columns([1,2])
        del_id = c_del1.number_input("Digite o ID para apagar:", 0, step=1)
        if c_del2.button("❌ Apagar Linha"):
            if excluir_linha(del_id): st.success("Linha apagada!"); st.cache_data.clear(); st.rerun()
    else: st.info("Nenhum dado encontrado.")

else:
    # --- RELATÓRIOS COMPLETOS (RESTAURADOS) ---
    df = carregar_dados()
    if not df.empty:
        if menu == "📅 Relatório Semanal":
            df['Chave'] = df['Data'].apply(lambda x: f"Semana {x.strftime('%U/%Y')}")
            tit = "Semanal"
        elif menu == "📅 Relatório Mensal":
            df['Chave'] = df['Data'].apply(lambda x: f"{MESES.get(x.strftime('%b'), x.strftime('%b'))}/{x.year}")
            tit = "Mensal"
        else:
            df['Chave'] = df['Data'].apply(lambda x: str(x.year))
            tit = "Anual"

        # AGREGAMENTO
        res = df.groupby('Chave').agg({'Ganhos':'sum', 'Bonus':'sum', 'Gastos_Combustivel':'sum', 'Km_Rodado':'sum', 'Data':'nunique'}).rename(columns={'Data':'Dias'}).reset_index().sort_values('Chave', ascending=False)
        
        # CÁLCULOS FINAIS
        res['Receita_Total'] = res['Ganhos'] + res['Bonus']
        res['IPVA_Seguro_Guardado'] = res['Dias'] * custo_dia_fixo
        res['Manutencao_Guardada'] = res['Km_Rodado'] * c_manut
        res['Depreciacao_Guardada'] = res['Km_Rodado'] * c_deprec
        res['Lucro_Liquido'] = res['Receita_Total'] - res['Gastos_Combustivel'] - res['IPVA_Seguro_Guardado'] - res['Manutencao_Guardada'] - res['Depreciacao_Guardada']

        st.title(f"Relatório {tit}")
        st.dataframe(res, hide_index=True, use_container_width=True, column_config={
            "Receita_Total": st.column_config.NumberColumn("💰 Total", format="R$ %.2f"),
            "Ganhos": st.column_config.NumberColumn("🚗 Corridas", format="R$ %.2f"),
            "Bonus": st.column_config.NumberColumn("🎁 Bônus", format="R$ %.2f"),
            "Gastos_Combustivel": st.column_config.NumberColumn("⛽ Gasolina", format="R$ %.2f"),
            "Km_Rodado": st.column_config.NumberColumn("🛣️ KM", format="%.1f km"),
            "IPVA_Seguro_Guardado": st.column_config.NumberColumn("🏦 IPVA", format="R$ %.2f"),
            "Manutencao_Guardada": st.column_config.NumberColumn("🛠️ Manut", format="R$ %.2f"),
            "Depreciacao_Guardada": st.column_config.NumberColumn("📉 Deprec", format="R$ %.2f"),
            "Lucro_Liquido": st.column_config.NumberColumn("💵 Lucro", format="R$ %.2f")
        })

        # RENOMEIA PARA GRÁFICOS
        gdf = res.rename(columns={'Ganhos':'Corridas', 'Bonus':'Bônus', 'Lucro_Liquido':'Lucro Real', 'IPVA_Seguro_Guardado':'IPVA/Seguro', 'Manutencao_Guardada':'Manutenção', 'Depreciacao_Guardada':'Depreciação'})
        
        # ABAS DOS GRÁFICOS (RESTAURADAS)
        t1, t2, t3 = st.tabs(["Faturamento vs Bônus", "Lucro", "Custos"])
        
        with t1:
            fig_fat = px.bar(gdf, x='Chave', y=['Corridas', 'Bônus'], title="Composição da Receita", barmode='stack', color_discrete_map={'Corridas':'#00CC96', 'Bônus':'#636EFA'})
            st.plotly_chart(estilo_grafico(fig_fat, "R$"), use_container_width=True)
        
        with t2:
            fig_luc = px.bar(gdf, x='Chave', y='Lucro Real', title="Evolução do Lucro Real", color_discrete_sequence=['#28a745'])
            st.plotly_chart(estilo_grafico(fig_luc, "R$"), use_container_width=True)
            
        with t3:
            # O GRÁFICO DE COMPOSIÇÃO DE CUSTO QUE FALTAVA
            fig_cus = px.bar(gdf, x='Chave', y=['IPVA/Seguro', 'Manutenção', 'Depreciação'], title="Detalhamento dos Custos", barmode='group')
            st.plotly_chart(estilo_grafico(fig_cus, "R$"), use_container_width=True)
    else:
        st.info("Nenhum dado na planilha.")
