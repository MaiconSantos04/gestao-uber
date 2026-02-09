import streamlit as st
import pandas as pd
import requests
import json
import plotly.graph_objects as go
import plotly.express as px
from datetime import date
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gestão Uber Pro", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS (BANCO DE DADOS NA NUVEM) ---
def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    
    try:
        # Tenta pegar do Streamlit Cloud (Segredo)
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except:
        # Tenta pegar do PC (Arquivo Local)
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        except:
            st.error("⚠️ ERRO CRÍTICO: Não encontrei a chave 'credentials.json' no PC nem nos Segredos do site.")
            st.stop()

    client = gspread.authorize(creds)
    try:
        sheet = client.open("GestaoUberDB").worksheet("Dados")
        return sheet
    except:
        st.error("⚠️ ERRO: Não encontrei a planilha 'GestaoUberDB' ou a aba 'Dados'. Verifique no Google Sheets.")
        st.stop()

# --- FUNÇÕES DE ARQUIVO (MODO NUVEM) ---
def carregar_dados():
    try:
        sheet = conectar_gsheets()
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        
        if df.empty:
            return pd.DataFrame(columns=['Data', 'Ganhos', 'Km_Rodado', 'Gastos_Combustivel', 'Obs'])
            
        df['Data'] = pd.to_datetime(df['Data']).dt.date
        
        # Limpeza de números vindos do Google (troca vírgula por ponto)
        cols_num = ['Ganhos', 'Km_Rodado', 'Gastos_Combustivel']
        for col in cols_num:
            df[col] = df[col].astype(str).str.replace(',', '.').replace('', '0')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            
        return df
    except Exception as e:
        # Se der erro, retorna vazio para não travar, mas avisa
        return pd.DataFrame(columns=['Data', 'Ganhos', 'Km_Rodado', 'Gastos_Combustivel', 'Obs'])

def salvar_na_nuvem(nova_linha_df):
    try:
        sheet = conectar_gsheets()
        nova_linha_df['Data'] = nova_linha_df['Data'].astype(str)
        lista_dados = nova_linha_df.values.tolist()
        sheet.append_row(lista_dados[0])
        return True
    except Exception as e:
        st.error(f"Erro ao salvar no Google: {e}")
        return False

# --- CONFIGURAÇÃO DO CARRO (Memória da Sessão) ---
def carregar_config():
    padrao = {"valor_carro": 83000.0, "custo_fixo_anual": 6300.0, "custo_pneu_oleo": 0.20, "depreciacao_pct": 12.5}
    if 'config_user' not in st.session_state:
        st.session_state['config_user'] = padrao
    return st.session_state['config_user']

# --- TRADUÇÃO DE MESES ---
MESES_PT = {
    'Jan': 'Jan', 'Feb': 'Fev', 'Mar': 'Mar', 'Apr': 'Abr', 'May': 'Mai', 'Jun': 'Jun',
    'Jul': 'Jul', 'Aug': 'Ago', 'Sep': 'Set', 'Oct': 'Out', 'Nov': 'Nov', 'Dec': 'Dez'
}

# --- ESTILO GRÁFICO (PROFISSIONAL) ---
def estilo_grafico(fig, titulo_eixo_y):
    fig.update_traces(
        texttemplate='R$ %{y:,.2f}',
        textposition='outside',
        marker_cornerradius=10
    )
    fig.update_layout(
        title_x=0.5,
        title_font_size=18,
        yaxis_title=titulo_eixo_y,
        xaxis_title=None,
        xaxis=dict(type='category', showgrid=False, showline=False),
        yaxis=dict(showgrid=True, gridcolor='#444444', zerolinecolor='#444444', showline=False),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=60, b=30, l=60, r=20),
        showlegend=False
    )
    return fig

# --- API FIPE ---
headers = {'User-Agent': 'Mozilla/5.0'}
def get_json(url):
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200: return response.json()
    except: pass
    return None

# --- INICIALIZAÇÃO ---
config = carregar_config()

# --- BARRA LATERAL ---
st.sidebar.title("Navegação")
menu_escolha = st.sidebar.radio(
    "Ir para:", 
    ["📝 Lançamento Diário", "📅 Relatório Semanal", "📅 Relatório Mensal", "📅 Relatório Anual"]
)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Configurações do Carro")

# Inputs de Configuração
val_carro = st.sidebar.number_input("Valor Veículo (R$)", value=config['valor_carro'], format="%.2f")
val_fixo = st.sidebar.number_input("Custo Fixo Anual (IPVA/Seguro)", value=config['custo_fixo_anual'], format="%.2f")
val_manut = st.sidebar.number_input("Custo Manut/KM", value=config['custo_pneu_oleo'], format="%.2f")
val_deprec = st.sidebar.slider("Depreciação Anual (%)", 0.0, 20.0, value=config['depreciacao_pct'])

# Atualiza na sessão (Memória Volátil)
st.session_state['config_user'] = {
    "valor_carro": val_carro, "custo_fixo_anual": val_fixo, 
    "custo_pneu_oleo": val_manut, "depreciacao_pct": val_deprec
}

custo_fixo_dia = val_fixo / 365
depreciacao_dia = (val_carro * (val_deprec / 100)) / 365
st.sidebar.info(f"Meta Fixa Diária: R$ {custo_fixo_dia:.2f}\nPerda Diária (Deprec): R$ {depreciacao_dia:.2f}")

# --- TELA 1: LANÇAMENTO DIÁRIO ---
if menu_escolha == "📝 Lançamento Diário":
    st.title("🚗 Controle Diário (Salva no Google)")
    st.markdown("### 📅 Resultados de Hoje")

    c1, c2, c3 = st.columns(3)
    hoje_ganho = c1.number_input("Ganho do Dia (R$)", value=0.0, step=10.0, format="%.2f")
    hoje_km = c2.number_input("KM Rodado Hoje", value=0.0, step=5.0, format="%.1f")
    hoje_comb = c3.number_input("Gasto Combustível (R$)", value=0.0, step=5.0, format="%.2f")
    obs = st.text_input("Observação")

    # Cálculos
    hoje_manutencao = hoje_km * val_manut
    hoje_total_guardar = hoje_manutencao + custo_fixo_dia + depreciacao_dia
    hoje_lucro_liquido = hoje_ganho - hoje_total_guardar - hoje_comb

    # Exibição
    st.markdown("---")
    col1, col2 = st.columns(2)
    col1.error(f"🚨 GUARDAR HOJE: R$ {hoje_total_guardar:.2f}")
    if hoje_lucro_liquido > 0:
        col2.success(f"💵 LUCRO REAL: R$ {hoje_lucro_liquido:.2f}")
    else:
        col2.error(f"💸 PREJUÍZO REAL: R$ {hoje_lucro_liquido:.2f}")

    # Gráfico Donut (COM CORREÇÃO DE WIDTH)
    labels = ['Lucro (Bolso)', 'Guardar (Carro)', 'Combustível']
    values = [max(0, hoje_lucro_liquido), hoje_total_guardar, hoje_comb]
    colors = ['#28a745', '#dc3545', '#ffc107']
    fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.4, marker=dict(colors=colors))])
    fig.update_layout(height=300, margin=dict(t=30, b=0, l=0, r=0), title_text="Distribuição do Dinheiro")
    st.plotly_chart(fig, width="stretch") # Corrigido para não dar aviso

    # Botão Salvar
    st.markdown("---")
    if st.button("💾 Salvar no Google Sheets"):
        if hoje_ganho > 0:
            with st.spinner("Enviando para a nuvem..."):
                novo = pd.DataFrame([{
                    'Data': date.today(), 'Ganhos': hoje_ganho, 'Km_Rodado': hoje_km,
                    'Gastos_Combustivel': hoje_comb, 'Obs': obs
                }])
                if salvar_na_nuvem(novo):
                    st.success("Salvo com sucesso no Google Sheets! ☁️")
                    st.cache_data.clear() # Limpa o cache para recarregar dados novos
        else:
            st.warning("Preencha os ganhos antes de salvar.")

# --- TELAS DE RELATÓRIO ---
else:
    df = carregar_dados()
    if not df.empty:
        # Prepara chaves de agrupamento
        if menu_escolha == "📅 Relatório Semanal":
            df['Chave'] = df['Data'].astype(str).apply(lambda x: f"Semana {pd.to_datetime(x).strftime('%U/%Y')}")
            titulo = "Semanal"
        elif menu_escolha == "📅 Relatório Mensal":
            df['Mes_PT'] = pd.to_datetime(df['Data']).dt.strftime('%b').map(MESES_PT)
            df['Chave'] = df['Mes_PT'] + '/' + pd.to_datetime(df['Data']).dt.strftime('%Y')
            titulo = "Mensal"
        else:
            df['Chave'] = pd.to_datetime(df['Data']).dt.strftime('%Y')
            titulo = "Anual"

        # Agrupa
        resumo = df.groupby('Chave').agg({
            'Ganhos': 'sum', 'Gastos_Combustivel': 'sum', 'Km_Rodado': 'sum', 'Data': 'nunique'
        }).rename(columns={'Data': 'Dias_Trabalhados'}).reset_index()

        # Ordenação básica (para Mensal tentar ficar cronológico precisa de lógica extra, aqui fica alfabético/numérico)
        resumo = resumo.sort_values('Chave', ascending=False)

        # Cálculos Financeiros
        resumo['IPVA_Seguro_Guardado'] = resumo['Dias_Trabalhados'] * custo_fixo_dia
        resumo['Manutencao_Guardada'] = resumo['Km_Rodado'] * val_manut
        resumo['Depreciacao_Guardada'] = resumo['Dias_Trabalhados'] * depreciacao_dia
        resumo['Lucro_Liquido'] = resumo['Ganhos'] - resumo['Gastos_Combustivel'] - resumo['IPVA_Seguro_Guardado'] - resumo['Manutencao_Guardada'] - resumo['Depreciacao_Guardada']

        st.title(f"📅 Relatório {titulo}")

        # Tabela (COM CORREÇÃO DE WIDTH)
        st.dataframe(
            resumo,
            column_config={
                "Chave": "Período",
                "Ganhos": st.column_config.NumberColumn("💰 Faturamento", format="R$ %.2f"),
                "Lucro_Liquido": st.column_config.NumberColumn("💵 Lucro", format="R$ %.2f"),
                "Dias_Trabalhados": "Dias"
            },
            hide_index=True,
            width="stretch" # Corrigido
        )

        # Gráficos
        tab_fat, tab_lucro, tab_custos = st.tabs(["💰 Faturamento", "💵 Lucro Real", "📉 Custos Guardados"])
        
        with tab_fat:
            st.plotly_chart(estilo_grafico(px.bar(resumo, x='Chave', y='Ganhos', color_discrete_sequence=['#00CC96']), "R$"), width="stretch")
        with tab_lucro:
            st.plotly_chart(estilo_grafico(px.bar(resumo, x='Chave', y='Lucro_Liquido', color_discrete_sequence=['#28a745']), "R$"), width="stretch")
        with tab_custos:
            st.plotly_chart(estilo_grafico(px.bar(resumo, x='Chave', y=['IPVA_Seguro_Guardado', 'Manutencao_Guardada'], barmode='group'), "R$"), width="stretch")

    else:
        st.warning("Nenhum dado encontrado no Google Sheets ou erro na conexão.")