import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib3

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="Gestão Uber Pro", layout="wide")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONEXÃO COM GOOGLE SHEETS ---
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
        try:
            sheet = spreadsheet.worksheet(nome_aba)
            return sheet
        except:
            if nome_aba == "Config":
                sheet = spreadsheet.add_worksheet(title="Config", rows=30, cols=2)
                sheet.append_row(["Parametro", "Valor"])
                return sheet
            else:
                st.error(f"Aba '{nome_aba}' não encontrada.")
                st.stop()
    except:
        st.error("⚠️ Planilha 'GestaoUberDB' não encontrada.")
        st.stop()

# --- CONFIGURAÇÃO (NUVEM) ---
def carregar_config_nuvem():
    if 'config_user' in st.session_state and st.session_state.get('config_carregada', False):
        return st.session_state['config_user']

    try:
        sheet = conectar_gsheets("Config")
        dados = sheet.get_all_values()
        config_dict = {}
        for linha in dados[1:]:
            if len(linha) >= 2:
                chave = linha[0]
                valor = linha[1]
                try: config_dict[chave] = float(valor)
                except: config_dict[chave] = valor
        
        padrao = {
            "valor_carro": 83000.0, "custo_fixo_anual": 6300.0, "dias_trabalho_mes": 4.0,
            "custo_manut_km": 0.25, "custo_deprec_km": 0.40, "media_km_dia": 150.0,
            "consumo_carro": 10.0, "preco_gasolina": 5.80,
            "fipe_nome_carro": "Carro Manual", "modo_fipe": "manual"
        }
        
        config_final = {**padrao, **config_dict}
        st.session_state['config_user'] = config_final
        st.session_state['config_carregada'] = True
        return config_final
    except:
        return {
            "valor_carro": 83000.0, "custo_fixo_anual": 6300.0, "dias_trabalho_mes": 4.0,
            "custo_manut_km": 0.25, "custo_deprec_km": 0.40, "media_km_dia": 150.0,
            "consumo_carro": 10.0, "preco_gasolina": 5.80,
            "fipe_nome_carro": "Carro Manual", "modo_fipe": "manual"
        }

def salvar_config_nuvem(nova_config):
    try:
        sheet = conectar_gsheets("Config")
        sheet.clear()
        sheet.append_row(["Parametro", "Valor"])
        linhas = []
        for chave, valor in nova_config.items():
            linhas.append([chave, str(valor)])
        for l in linhas: sheet.append_row(l)
        st.session_state['config_user'] = nova_config
        return True
    except Exception as e:
        st.error(f"Erro ao salvar config: {e}")
        return False

# --- FUNÇÕES DE DADOS ---
def limpar_valor_hibrido(valor):
    if isinstance(valor, (int, float)): return float(valor)
    val_str = str(valor).strip().replace('R$', '').replace(' ', '')
    if '.' in val_str and ',' not in val_str:
        try: return float(val_str)
        except: pass
    if ',' in val_str:
        val_str = val_str.replace('.', '').replace(',', '.')
    try: return float(val_str)
    except: return 0.0

def carregar_dados():
    try:
        sheet = conectar_gsheets("Dados")
        dados = sheet.get_all_values()
        if len(dados) < 2: return pd.DataFrame(columns=['Data', 'Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel', 'Obs'])
        cabecalho = dados[0]
        df = pd.DataFrame(dados[1:], columns=cabecalho)
        cols_nec = ['Data', 'Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel', 'Obs']
        for c in cols_nec: 
            if c not in df.columns: df[c] = "0"
        df['ID'] = df.index + 2 
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce').dt.date
        cols_num = ['Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel']
        for col in cols_num: df[col] = df[col].apply(limpar_valor_hibrido)
        return df
    except: return pd.DataFrame(columns=['Data', 'Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel', 'Obs'])

def salvar_na_nuvem(nova_linha_df):
    try:
        sheet = conectar_gsheets("Dados")
        nova_linha_df['Data'] = nova_linha_df['Data'].astype(str)
        ordem = ['Data', 'Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel', 'Obs']
        nova_linha_df = nova_linha_df[ordem]
        for col in ['Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel']:
            val = nova_linha_df.iloc[0][col]
            if isinstance(val, (int, float)):
                nova_linha_df.at[0, col] = f"{val:.2f}".replace('.', ',')
        sheet.append_row(nova_linha_df.values.tolist()[0])
        return True
    except Exception as e:
        st.error(f"Erro ao salvar: {e}"); return False

def excluir_linha_pelo_id(id_linha):
    try:
        sheet = conectar_gsheets("Dados"); sheet.delete_rows(id_linha); return True
    except: return False

def desfazer_ultimo_lancamento():
    try:
        sheet = conectar_gsheets("Dados"); sheet.delete_rows(len(sheet.get_all_values())); return True
    except: return False

def estilo_grafico(fig, titulo_eixo_y):
    fig.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside', marker_cornerradius=10, hovertemplate='<b>%{data.name}</b>: R$ %{y:,.2f}<extra></extra>')
    fig.update_layout(title_x=0.5, title_font_size=18, yaxis_title=titulo_eixo_y, xaxis_title=None,
        xaxis=dict(type='category', showgrid=False, showline=False),
        yaxis=dict(showgrid=True, gridcolor='#444444', zerolinecolor='#444444', showline=False),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', margin=dict(t=60, b=30, l=20, r=20), showlegend=False)
    return fig

MESES_PT = {'Jan': 'Jan', 'Feb': 'Fev', 'Mar': 'Mar', 'Apr': 'Abr', 'May': 'Mai', 'Jun': 'Jun', 'Jul': 'Jul', 'Aug': 'Ago', 'Sep': 'Set', 'Oct': 'Out', 'Nov': 'Nov', 'Dec': 'Dez'}

# --- INICIALIZAÇÃO ---
config = carregar_config_nuvem()

# --- BARRA LATERAL ---
st.sidebar.title("Navegação")
menu_escolha = st.sidebar.radio("Ir para:", ["📝 Lançamento Diário", "📋 Extrato Completo", "📅 Relatório Semanal", "📅 Relatório Mensal", "📅 Relatório Anual"])

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Configurações do Carro")

# --- SELETOR DE MODO ---
st.sidebar.info("Como a conexão com a FIPE está instável, use o modo Manual para digitar o valor do carro diretamente.")
modo_carro = st.sidebar.radio("Modo de Cadastro:", ["✍️ Manual (Recomendado)", "🔍 Automático (FIPE)"])

if modo_carro == "✍️ Manual (Recomendado)":
    # MODO MANUAL: O usuário é o chefe
    nome_manual = st.sidebar.text_input("Nome do Carro", value=config.get('fipe_nome_carro', 'Meu Carro'))
    valor_manual = st.sidebar.number_input("Valor de Mercado (R$)", value=float(config.get('valor_carro', 83000)), format="%.2f", help="Digite aqui quanto vale seu carro hoje.")
    
    if st.sidebar.button("💾 Salvar Valor Manual"):
        st.session_state['config_user'].update({
            'valor_carro': valor_manual,
            'fipe_nome_carro': nome_manual,
            'modo_fipe': 'manual'
        })
        salvar_config_nuvem(st.session_state['config_user'])
        st.sidebar.success(f"Salvo! Valor: R$ {valor_manual:,.2f}")
        st.rerun()

else:
    # MODO AUTOMÁTICO (Tenta API, mas avisa se falhar)
    try:
        url_marcas = "https://parallelum.com.br/fipe/api/v1/carros/marcas"
        resp = requests.get(url_marcas, timeout=3, verify=False)
        if resp.status_code == 200:
            marcas = {m['nome']: m['codigo'] for m in resp.json()}
            marca_sel = st.sidebar.selectbox("Marca", sorted(marcas.keys()))
            if marca_sel:
                cod_marca = marcas[marca_sel]
                modelos = requests.get(f"{url_marcas}/{cod_marca}/modelos", timeout=3, verify=False).json()['modelos']
                mod_dict = {m['nome']: m['codigo'] for m in modelos}
                mod_sel = st.sidebar.selectbox("Modelo", list(mod_dict.keys()))
                if mod_sel:
                    cod_mod = mod_dict[mod_sel]
                    anos = requests.get(f"{url_marcas}/{cod_marca}/modelos/{cod_mod}/anos", timeout=3, verify=False).json()
                    ano_dict = {a['nome']: a['codigo'] for a in anos}
                    ano_sel = st.sidebar.selectbox("Ano", list(ano_dict.keys()))
                    if st.sidebar.button("Buscar FIPE"):
                        final = requests.get(f"{url_marcas}/{cod_marca}/modelos/{cod_mod}/anos/{ano_dict[ano_sel]}", timeout=3, verify=False).json()
                        val = float(final['Valor'].replace("R$ ", "").replace(".", "").replace(",", "."))
                        st.session_state['config_user'].update({'valor_carro': val, 'fipe_nome_carro': f"{marca_sel} {mod_sel}"})
                        salvar_config_nuvem(st.session_state['config_user'])
                        st.sidebar.success(f"Atualizado: {val}")
                        st.rerun()
        else:
            st.sidebar.error("API Bloqueada. Use o modo Manual acima.")
    except:
        st.sidebar.error("Erro de conexão. Use o modo Manual acima.")

st.sidebar.markdown("---")

# --- INPUTS ---
st.sidebar.header("⚙️ Custos Operacionais")
# O valor do carro aqui é apenas visualização, a edição é feita no bloco acima
st.sidebar.metric("Valor do Carro Considerado", f"R$ {float(config.get('valor_carro', 0)):,.2f}")

val_fixo = st.sidebar.number_input("IPVA+Seguro Anual (R$)", value=float(config.get('custo_fixo_anual', 6300)), format="%.2f")
dias_mes = st.sidebar.number_input("Dias trab/mês", min_value=1, max_value=31, value=int(float(config.get('dias_trabalho_mes', 4))))

with st.sidebar.expander("⛽ Combustível e Rodagem", expanded=True):
    media_km_dia = st.number_input("Média KM/dia", value=float(config.get('media_km_dia', 150)))
    consumo_carro = st.number_input("Consumo (Km/L)", value=float(config.get('consumo_carro', 10)), format="%.1f")
    preco_gasolina = st.number_input("Preço Gasolina (R$)", value=float(config.get('preco_gasolina', 5.89)), format="%.2f")

with st.sidebar.expander("🛠️ Manut/Deprec", expanded=False):
    val_manut = st.number_input("Manut/KM (R$)", value=float(config.get('custo_manut_km', 0.25)), format="%.2f", step=0.05)
    val_deprec = st.number_input("Deprec/KM (R$)", value=float(config.get('custo_deprec_km', 0.40)), format="%.2f", step=0.05)

# CÁLCULOS
custo_fixo_mensal = val_fixo / 12
custo_fixo_dia = custo_fixo_mensal / dias_mes if dias_mes > 0 else 0
custo_fixo_km = custo_fixo_dia / media_km_dia if media_km_dia > 0 else 0
custo_gas_km = preco_gasolina / consumo_carro if consumo_carro > 0 else 0
custo_km_total = custo_fixo_km + custo_gas_km + val_manut + val_deprec

st.sidebar.markdown("---")
st.sidebar.metric("⛔ Stop Loss (Min/KM)", f"R$ {custo_km_total:.2f}")
st.sidebar.caption(f"Meta Diária IPVA: **R$ {custo_fixo_dia:.2f}**")

if st.sidebar.button("💾 Salvar Parâmetros"):
    st.session_state['config_user'].update({
        "custo_fixo_anual": val_fixo, "dias_trabalho_mes": dias_mes,
        "custo_manut_km": val_manut, "custo_deprec_km": val_deprec,
        "media_km_dia": media_km_dia, "consumo_carro": consumo_carro, "preco_gasolina": preco_gasolina
    })
    with st.spinner("Salvando..."):
        salvar_config_nuvem(st.session_state['config_user']); st.sidebar.success("Salvo!"); st.rerun()

# --- TELA PRINCIPAL ---
if menu_escolha == "📝 Lançamento Diário":
    st.title("🚗 Controle Diário")
    c1, c2, c3, c4 = st.columns(4)
    hg = c1.number_input("Ganhos (R$)", 0.0, step=10.0, format="%.2f")
    hb = c2.number_input("Bônus (R$)", 0.0, step=10.0, format="%.2f")
    hk = c3.number_input("KM Rodado", 0.0, step=5.0, format="%.1f")
    hc = c4.number_input("Combustível (R$)", 0.0, step=5.0, format="%.2f")
    obs = st.text_input("Obs")

    h_manut = hk * val_manut
    h_deprec = hk * val_deprec
    h_ipva = custo_fixo_dia 
    h_guardar = h_manut + h_deprec + h_ipva
    h_lucro = (hg + hb) - h_guardar - hc

    st.markdown("---")
    k1, k2, k3 = st.columns(3)
    k1.error(f"🚨 GUARDAR: R$ {h_guardar:.2f}")
    if h_lucro > 0: k2.success(f"💵 LUCRO: R$ {h_lucro:.2f}")
    else: k2.error(f"💸 PREJUÍZO: R$ {h_lucro:.2f}")
    
    val_km_hj = (hg + hb) / hk if hk > 0 else 0
    k3.metric("Média Hoje", f"R$ {val_km_hj:.2f}/km", delta=f"{val_km_hj - custo_km_total:.2f} vs Min")

    fig = go.Figure(data=[go.Pie(labels=['Lucro', 'Guardar', 'Combustível'], values=[max(0, h_lucro), h_guardar, hc], hole=.5, textinfo='percent', textposition='inside', marker=dict(colors=['#28a745', '#dc3545', '#ffc107'], line=dict(color='#000000', width=1)))])
    fig.update_layout(height=350, margin=dict(t=30, b=10, l=10, r=10), showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    cs, cu = st.columns([3, 1])
    if cs.button("💾 Salvar", type="primary", use_container_width=True):
        if hg > 0 or hb > 0:
            if hc > 800 or hk > 2000: st.error("⚠️ Valores altos demais.")
            else:
                salvar_na_nuvem(pd.DataFrame([{'Data': date.today(), 'Ganhos': hg, 'Bonus': hb, 'Km_Rodado': hk, 'Gastos_Combustivel': hc, 'Obs': obs}]))
                st.success("Salvo!"); st.cache_data.clear()
        else: st.warning("Preencha valores.")
    if cu.button("↩️ Desfazer", use_container_width=True):
        if desfazer_ultimo_lancamento(): st.toast("Desfeito!"); st.cache_data.clear()

elif menu_escolha == "📋 Extrato Completo":
    st.title("📋 Extrato"); df = carregar_dados()
    if not df.empty:
        st.dataframe(df.sort_values('Data', ascending=False), use_container_width=True)
        id_del = st.number_input("ID para apagar", 0, step=1)
        if st.button("❌ Apagar Linha"): 
            if excluir_linha_pelo_id(id_del): st.success("Apagado!"); st.cache_data.clear(); st.rerun()
    else: st.info("Vazio.")

else:
    df = carregar_dados()
    if not df.empty:
        if menu_escolha == "📅 Relatório Semanal":
            df['Chave'] = df['Data'].astype(str).apply(lambda x: f"Semana {pd.to_datetime(x).strftime('%U/%Y')}")
            titulo = "Semanal"
        elif menu_escolha == "📅 Relatório Mensal":
            df['Chave'] = pd.to_datetime(df['Data']).dt.strftime('%b').map(MESES_PT) + '/' + pd.to_datetime(df['Data']).dt.strftime('%Y')
            titulo = "Mensal"
        else:
            df['Chave'] = pd.to_datetime(df['Data']).dt.strftime('%Y')
            titulo = "Anual"

        resumo = df.groupby('Chave').agg({'Ganhos':'sum', 'Bonus':'sum', 'Gastos_Combustivel':'sum', 'Km_Rodado':'sum', 'Data':'nunique'}).rename(columns={'Data':'Dias'}).reset_index().sort_values('Chave', ascending=False)
        resumo['Receita_Total'] = resumo['Ganhos'] + resumo['Bonus']
        resumo['IPVA_Seguro_Guardado'] = resumo['Dias'] * custo_fixo_dia
        resumo['Manutencao_Guardada'] = resumo['Km_Rodado'] * val_manut
        resumo['Depreciacao_Guardada'] = resumo['Km_Rodado'] * val_deprec
        resumo['Lucro_Liquido'] = resumo['Receita_Total'] - resumo['Gastos_Combustivel'] - resumo['IPVA_Seguro_Guardado'] - resumo['Manutencao_Guardada'] - resumo['Depreciacao_Guardada']

        st.title(f"Relatório {menu_escolha.split()[-1]}")
        st.dataframe(resumo, use_container_width=True)
        
        gdf = resumo.rename(columns={'Ganhos':'Corridas', 'Bonus':'Bônus', 'Lucro_Liquido':'Lucro Real', 'IPVA_Seguro_Guardado':'IPVA', 'Manutencao_Guardada':'Manut', 'Depreciacao_Guardada':'Deprec'})
        t1, t2, t3 = st.tabs(["Faturamento", "Lucro", "Custos"])
        with t1: st.plotly_chart(estilo_grafico(px.bar(gdf, x='Chave', y=['Corridas', 'Bônus'], barmode='stack', title='Receita'), "R$"), use_container_width=True)
        with t2: st.plotly_chart(estilo_grafico(px.bar(gdf, x='Chave', y='Lucro Real', title='Lucro Real', color_discrete_sequence=['#28a745']), "R$"), use_container_width=True)
        with t3: st.plotly_chart(estilo_grafico(px.bar(gdf, x='Chave', y=['IPVA', 'Manut', 'Deprec'], barmode='group', title='Custos'), "R$"), use_container_width=True)
    else: st.info("Sem dados.")
