import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
from oauth2client.service_account import ServiceAccountCredentials
import gspread
import urllib3
import time
import random

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="Gestão Uber Pro", layout="wide")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- SISTEMA DE CACHE E RETRY (O SEGREDO PARA NÃO TRAVAR) ---
# Simula um navegador real para enganar bloqueios simples
HEADERS_ROTATIVOS = [
    {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'},
    {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15'},
    {'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G960U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.181 Mobile Safari/537.36'}
]

@st.cache_data(ttl=3600, show_spinner=False) # Cache de 1 hora
def buscar_marcas_blindado():
    """Busca marcas com redundância: Tenta Parallelum -> BrasilAPI -> Lista Fixa"""
    # 1. Tentativa: Parallelum
    try:
        url = "https://parallelum.com.br/fipe/api/v1/carros/marcas"
        resp = requests.get(url, headers=random.choice(HEADERS_ROTATIVOS), timeout=5, verify=False)
        if resp.status_code == 200:
            return {m['nome']: m['codigo'] for m in resp.json()}
    except: pass
    
    # 2. Tentativa: Brasil API
    try:
        url = "https://brasilapi.com.br/api/fipe/marcas/v1/carros"
        resp = requests.get(url, headers=random.choice(HEADERS_ROTATIVOS), timeout=5)
        if resp.status_code == 200:
            # BrasilAPI retorna 'nome' e 'valor' (que é o código)
            return {m['nome']: m['valor'] for m in resp.json()}
    except: pass

    # 3. Fallback: Lista Fixa (Segurança)
    return {
        "Chevrolet": "23", "Fiat": "21", "Volkswagen": "59", "Ford": "22", 
        "Hyundai": "25", "Toyota": "56", "Honda": "20", "Renault": "44", 
        "Nissan": "43", "Jeep": "29", "Caoa Chery": "136", "Citroën": "11",
        "Peugeot": "41", "Mitsubishi": "40", "BMW": "7", "Mercedes-Benz": "39", 
        "Audi": "6", "Kia": "31", "BYD": "176"
    }

@st.cache_data(ttl=3600, show_spinner=False)
def buscar_modelos(cod_marca):
    """Busca modelos na API"""
    try:
        url = f"https://parallelum.com.br/fipe/api/v1/carros/marcas/{cod_marca}/modelos"
        resp = requests.get(url, headers=random.choice(HEADERS_ROTATIVOS), timeout=6, verify=False)
        if resp.status_code == 200:
            return {m['nome']: m['codigo'] for m in resp.json()['modelos']}
    except: return {}

@st.cache_data(ttl=3600, show_spinner=False)
def buscar_anos(cod_marca, cod_modelo):
    """Busca anos na API"""
    try:
        url = f"https://parallelum.com.br/fipe/api/v1/carros/marcas/{cod_marca}/modelos/{cod_modelo}/anos"
        resp = requests.get(url, headers=random.choice(HEADERS_ROTATIVOS), timeout=6, verify=False)
        if resp.status_code == 200:
            return {a['nome']: a['codigo'] for a in resp.json()}
    except: return {}

def buscar_valor_final(cod_marca, cod_modelo, cod_ano):
    """Busca valor final (SEM CACHE para garantir preço atual)"""
    try:
        url = f"https://parallelum.com.br/fipe/api/v1/carros/marcas/{cod_marca}/modelos/{cod_modelo}/anos/{cod_ano}"
        resp = requests.get(url, headers=random.choice(HEADERS_ROTATIVOS), timeout=8, verify=False)
        if resp.status_code == 200:
            return resp.json()
    except: return None

# --- CONEXÃO GOOGLE SHEETS ---
def conectar_gsheets(nome_aba="Dados"):
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except:
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        except:
            st.error("⚠️ Erro de credenciais.")
            st.stop()

    client = gspread.authorize(creds)
    try:
        spreadsheet = client.open("GestaoUberDB")
        try: return spreadsheet.worksheet(nome_aba)
        except:
            if nome_aba == "Config":
                s = spreadsheet.add_worksheet("Config", 30, 2)
                s.append_row(["Parametro", "Valor"]); return s
            st.error(f"Aba {nome_aba} sumiu."); st.stop()
    except: st.error("Planilha não encontrada."); st.stop()

# --- CONFIGURAÇÃO ---
def carregar_config():
    if 'config_user' in st.session_state and st.session_state.get('loaded', False):
        return st.session_state['config_user']
    try:
        ws = conectar_gsheets("Config")
        d = dict(ws.get_all_values()[1:])
        cfg = {
            "valor_carro": float(d.get("valor_carro", 83000)),
            "custo_fixo_anual": float(d.get("custo_fixo_anual", 6300)),
            "dias_trabalho_mes": int(float(d.get("dias_trabalho_mes", 4))),
            "media_km_dia": float(d.get("media_km_dia", 150)),
            "consumo_carro": float(d.get("consumo_carro", 10)),
            "preco_gasolina": float(d.get("preco_gasolina", 5.80)),
            "custo_manut_km": float(d.get("custo_manut_km", 0.25)),
            "custo_deprec_km": float(d.get("custo_deprec_km", 0.40)),
            "fipe_nome_carro": d.get("fipe_nome_carro", "Não Definido"),
            "fipe_marca_id": d.get("fipe_marca_id", ""),
            "fipe_modelo_id": d.get("fipe_modelo_id", ""),
            "fipe_ano_id": d.get("fipe_ano_id", "")
        }
        st.session_state['config_user'] = cfg
        st.session_state['loaded'] = True
        return cfg
    except: return {}

def salvar_config(cfg):
    try:
        ws = conectar_gsheets("Config"); ws.clear(); ws.append_row(["Parametro", "Valor"])
        ws.append_rows([[k, str(v)] for k, v in cfg.items()])
        st.session_state['config_user'] = cfg
        return True
    except: return False

# --- UTILS ---
def clean_float(v):
    if isinstance(v, (float, int)): return float(v)
    try: return float(str(v).replace('R$', '').replace('.', '').replace(',', '.').strip())
    except: return 0.0

def load_data():
    try:
        ws = conectar_gsheets("Dados"); rows = ws.get_all_values()
        if len(rows) < 2: return pd.DataFrame(columns=['Data', 'Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel', 'Obs'])
        df = pd.DataFrame(rows[1:], columns=rows[0])
        cols = ['Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel']
        for c in cols: df[c] = df[c].apply(clean_float)
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce').dt.date
        return df
    except: return pd.DataFrame()

def save_entry(entry):
    try:
        ws = conectar_gsheets("Dados")
        row = [str(entry['Data']), f"{entry['Ganhos']:.2f}".replace('.',','), f"{entry['Bonus']:.2f}".replace('.',','), 
               f"{entry['Km_Rodado']:.1f}".replace('.',','), f"{entry['Gastos_Combustivel']:.2f}".replace('.',','), entry['Obs']]
        ws.append_row(row); return True
    except: return False

# --- APP ---
config = carregar_config()

st.sidebar.title("Navegação")
page = st.sidebar.radio("Ir para", ["📝 Lançamento", "📋 Extrato", "📊 Relatórios"])

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Configuração do Carro")

# --- LÓGICA HÍBRIDA FIPE (CORRIGIDA) ---
# Mostra o carro atual salvo
st.sidebar.info(f"🚗 **{config.get('fipe_nome_carro', '---')}**\n💰 Valor Base: **R$ {config.get('valor_carro', 0):,.2f}**")

# Tenta atualização rápida se tiver IDs salvos
if config.get('fipe_marca_id') and config.get('fipe_modelo_id'):
    if st.sidebar.button("🔄 Atualizar Valor (Automático)"):
        with st.sidebar.status("Conectando FIPE..."):
            dados = buscar_valor_final(config['fipe_marca_id'], config['fipe_modelo_id'], config['fipe_ano_id'])
            if dados:
                v = clean_float(dados['Valor'])
                config['valor_carro'] = v
                salvar_config(config)
                st.sidebar.success(f"Atualizado: R$ {v:,.2f}")
                time.sleep(1); st.rerun()
            else:
                st.sidebar.error("Erro de conexão. Tente mais tarde.")

# Abas para edição
tab_auto, tab_man = st.sidebar.tabs(["🔍 Automático", "✍️ Manual"])

with tab_auto:
    st.caption("Use esta aba para buscar na tabela FIPE.")
    
    # 1. Marca (Com Cache - Instantâneo)
    marcas = buscar_marcas_blindado()
    nome_marca = st.selectbox("Marca", sorted(marcas.keys()), key="s_marca")
    
    if nome_marca:
        id_marca = marcas[nome_marca]
        # 2. Modelo (Com Cache)
        modelos = buscar_modelos(id_marca)
        if modelos:
            nome_modelo = st.selectbox("Modelo", sorted(modelos.keys()), key="s_modelo")
            if nome_modelo:
                id_modelo = modelos[nome_modelo]
                # 3. Ano (Com Cache)
                anos = buscar_anos(id_marca, id_modelo)
                if anos:
                    nome_ano = st.selectbox("Ano", sorted(anos.keys()), key="s_ano")
                    if st.button("💾 Salvar Este Carro"):
                        id_ano = anos[nome_ano]
                        # Busca valor final
                        dados_finais = buscar_valor_final(id_marca, id_modelo, id_ano)
                        if dados_finais:
                            val_final = clean_float(dados_finais['Valor'])
                            config.update({
                                'valor_carro': val_final,
                                'fipe_nome_carro': f"{nome_marca} {nome_modelo} {nome_ano}",
                                'fipe_marca_id': id_marca, 'fipe_modelo_id': id_modelo, 'fipe_ano_id': id_ano
                            })
                            salvar_config(config)
                            st.success("Salvo com sucesso!"); st.rerun()
                        else: st.error("Erro ao buscar preço final.")
                else: st.warning("Carregando anos...")
        else: st.warning("Erro ao carregar modelos. Tente a aba Manual.")

with tab_man:
    st.caption("Edite se a busca automática falhar.")
    n_man = st.text_input("Nome", config.get('fipe_nome_carro', ''), key="m_nome")
    v_man = st.number_input("Valor (R$)", value=float(config.get('valor_carro', 0)), format="%.2f", key="m_valor")
    if st.button("💾 Salvar Manual"):
        config.update({'valor_carro': v_man, 'fipe_nome_carro': n_man, 'fipe_marca_id': '', 'fipe_modelo_id': ''})
        salvar_config(config); st.success("Salvo!"); st.rerun()

st.sidebar.markdown("---")
# Inputs Financeiros
val_fixo = st.sidebar.number_input("IPVA+Seguro (Anual)", value=float(config.get('custo_fixo_anual', 6000)))
dias_mes = st.sidebar.number_input("Dias trab/mês", value=int(config.get('dias_trabalho_mes', 4)))
km_dia = st.sidebar.number_input("Média KM/dia", value=float(config.get('media_km_dia', 150)))
gas_pr = st.sidebar.number_input("Preço Gasolina", value=float(config.get('preco_gasolina', 5.89)))
consu = st.sidebar.number_input("Consumo (km/l)", value=float(config.get('consumo_carro', 10)))
c_man = st.sidebar.number_input("Manut/km", value=float(config.get('custo_manut_km', 0.25)))
c_dep = st.sidebar.number_input("Deprec/km", value=float(config.get('custo_deprec_km', 0.40)))

# Cálculos
c_fixo_dia = (val_fixo / 12) / dias_mes if dias_mes else 0
c_km_fixo = c_fixo_dia / km_dia if km_dia else 0
c_km_gas = gas_pr / consu if consu else 0
stop_loss = c_km_fixo + c_km_gas + c_man + c_dep

st.sidebar.metric("⛔ Stop Loss", f"R$ {stop_loss:.2f}/km")
if st.sidebar.button("Salvar Parâmetros"):
    config.update({
        "custo_fixo_anual": val_fixo, "dias_trabalho_mes": dias_mes, "media_km_dia": km_dia,
        "preco_gasolina": gas_pr, "consumo_carro": consu, "custo_manut_km": c_man, "custo_deprec_km": c_dep
    })
    salvar_config(config); st.success("Salvo!"); st.rerun()

# --- PAGINAS ---
if page == "📝 Lançamento":
    st.title("Lançamento Diário")
    c1, c2, c3, c4 = st.columns(4)
    v_gan = c1.number_input("Ganhos", 0.0)
    v_bon = c2.number_input("Bônus", 0.0)
    v_km = c3.number_input("KM", 0.0)
    v_gas = c4.number_input("Gasolina (R$)", 0.0)
    obs = st.text_input("Obs")
    
    # KPIs do dia
    k_ipva = c_fixo_dia # Valor cheio do dia
    k_man = v_km * c_man
    k_dep = v_km * c_dep
    k_guardar = k_ipva + k_man + k_dep
    k_lucro = (v_gan + v_bon) - k_guardar - v_gas
    
    k1, k2 = st.columns(2)
    k1.error(f"GUARDAR HOJE: R$ {k_guardar:.2f}")
    if k_lucro > 0: k2.success(f"LUCRO: R$ {k_lucro:.2f}")
    else: k2.error(f"PREJUÍZO: R$ {k_lucro:.2f}")
    
    if st.button("Salvar Diária", type="primary"):
        if v_gan or v_bon:
            save_entry({'Data': date.today(), 'Ganhos': v_gan, 'Bonus': v_bon, 'Km_Rodado': v_km, 'Gastos_Combustivel': v_gas, 'Obs': obs})
            st.success("Salvo!"); st.cache_data.clear()

elif page == "📋 Extrato":
    st.title("Extrato"); df = load_data()
    if not df.empty:
        st.dataframe(df.sort_values('Data', ascending=False), use_container_width=True)
        # Delete logic here (simplificada)
        id_del = st.number_input("ID Deletar", 0)
        if st.button("Apagar Linha"):
            if excluir_linha_pelo_id(id_del): st.success("Feito!"); st.cache_data.clear(); st.rerun()

elif page == "📊 Relatórios":
    df = load_data()
    if not df.empty:
        # Lógica resumida de relatório
        df['Mes'] = pd.to_datetime(df['Data']).dt.strftime('%Y-%m')
        res = df.groupby('Mes').sum(numeric_only=True).reset_index()
        st.bar_chart(res, x='Mes', y='Ganhos')
