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

# --- CONEXÃO COM GOOGLE SHEETS ---
def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    
    try:
        # Tenta pegar do Streamlit Cloud
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except:
        # Tenta pegar do PC
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        except:
            st.error("⚠️ Erro de credenciais. Verifique os Secrets ou o arquivo JSON.")
            st.stop()

    client = gspread.authorize(creds)
    try:
        sheet = client.open("GestaoUberDB").worksheet("Dados")
        return sheet
    except:
        st.error("⚠️ Planilha 'GestaoUberDB' não encontrada.")
        st.stop()

# --- FUNÇÕES DE DADOS ---
def carregar_dados():
    try:
        sheet = conectar_gsheets()
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        
        if df.empty:
            return pd.DataFrame(columns=['Data', 'Ganhos', 'Km_Rodado', 'Gastos_Combustivel', 'Obs'])
            
        df['Data'] = pd.to_datetime(df['Data']).dt.date
        
        cols_num = ['Ganhos', 'Km_Rodado', 'Gastos_Combustivel']
        for col in cols_num:
            df[col] = df[col].astype(str).str.replace(',', '.').replace('', '0')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            
        return df
    except:
        return pd.DataFrame(columns=['Data', 'Ganhos', 'Km_Rodado', 'Gastos_Combustivel', 'Obs'])

def salvar_na_nuvem(nova_linha_df):
    try:
        sheet = conectar_gsheets()
        nova_linha_df['Data'] = nova_linha_df['Data'].astype(str)
        lista_dados = nova_linha_df.values.tolist()
        sheet.append_row(lista_dados[0])
        return True
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")
        return False

def desfazer_ultimo_lancamento():
    try:
        sheet = conectar_gsheets()
        # Pega todas as linhas
        todas_linhas = sheet.get_all_values()
        # Se tiver mais que 1 linha (ou seja, tem dados além do cabeçalho)
        if len(todas_linhas) > 1:
            sheet.delete_rows(len(todas_linhas))
            return True
        return False
    except Exception as e:
        st.error(f"Erro ao excluir: {e}")
        return False

# --- API FIPE (RESTAURADA) ---
headers = {'User-Agent': 'Mozilla/5.0'}
def get_json(url):
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200: return response.json()
    except: pass
    return None

# --- CONFIGURAÇÃO E MEMÓRIA ---
def carregar_config():
    padrao = {"valor_carro": 83000.0, "custo_fixo_anual": 6300.0, "custo_pneu_oleo": 0.20, "depreciacao_pct": 12.5}
    if 'config_user' not in st.session_state:
        st.session_state['config_user'] = padrao
    return st.session_state['config_user']

# --- ESTILO GRÁFICO ---
def estilo_grafico(fig, titulo_eixo_y):
    fig.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside', marker_cornerradius=10)
    fig.update_layout(title_x=0.5, title_font_size=18, yaxis_title=titulo_eixo_y, xaxis_title=None,
        xaxis=dict(type='category', showgrid=False, showline=False),
        yaxis=dict(showgrid=True, gridcolor='#444444', zerolinecolor='#444444', showline=False),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', margin=dict(t=60, b=30, l=60, r=20), showlegend=False)
    return fig

MESES_PT = {'Jan': 'Jan', 'Feb': 'Fev', 'Mar': 'Mar', 'Apr': 'Abr', 'May': 'Mai', 'Jun': 'Jun', 'Jul': 'Jul', 'Aug': 'Ago', 'Sep': 'Set', 'Oct': 'Out', 'Nov': 'Nov', 'Dec': 'Dez'}

# --- INICIALIZAÇÃO ---
config = carregar_config()

# --- BARRA LATERAL ---
st.sidebar.title("Navegação")
menu_escolha = st.sidebar.radio("Ir para:", ["📝 Lançamento Diário", "📅 Relatório Semanal", "📅 Relatório Mensal", "📅 Relatório Anual"])

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Configurações do Carro")

# --- BLOCO FIPE (RESTAURADO) ---
with st.sidebar.expander("🔍 Atualizar Valor FIPE"):
    marcas_data = get_json("https://parallelum.com.br/fipe/api/v1/carros/marcas")
    if marcas_data:
        marcas_dict = {m['nome']: m['codigo'] for m in marcas_data}
        idx_marca = list(marcas_dict.keys()).index("Chevrolet") if "Chevrolet" in marcas_dict else 0
        marca_nome = st.selectbox("Marca", list(marcas_dict.keys()), index=idx_marca)
        
        if marca_nome:
            cod_marca = marcas_dict[marca_nome]
            modelos_data = get_json(f"https://parallelum.com.br/fipe/api/v1/carros/marcas/{cod_marca}/modelos")
            
            if modelos_data:
                modelos_dict = {m['nome']: m['codigo'] for m in modelos_data['modelos']}
                modelo_nome = st.selectbox("Modelo", list(modelos_dict.keys()))
                
                if modelo_nome:
                    cod_modelo = modelos_dict[modelo_nome]
                    anos_data = get_json(f"https://parallelum.com.br/fipe/api/v1/carros/marcas/{cod_marca}/modelos/{cod_modelo}/anos")
                    
                    if anos_data:
                        anos_dict = {a['nome']: a['codigo'] for a in anos_data}
                        ano_nome = st.selectbox("Ano", list(anos_dict.keys()))
                        
                        if st.button("Aplicar Valor FIPE"):
                            cod_ano = anos_dict[ano_nome]
                            valor_final = get_json(f"https://parallelum.com.br/fipe/api/v1/carros/marcas/{cod_marca}/modelos/{cod_modelo}/anos/{cod_ano}")
                            if valor_final:
                                valor_str = valor_final['Valor']
                                valor_limpo = float(valor_str.replace("R$ ", "").replace(".", "").replace(",", "."))
                                # Atualiza o valor na memória
                                st.session_state['config_user']['valor_carro'] = valor_limpo
                                st.success(f"Atualizado: {valor_str}")
                                st.rerun()

st.sidebar.markdown("---")
# Inputs com a FIPE integrada
val_carro = st.sidebar.number_input("Valor Veículo (R$)", value=st.session_state['config_user']['valor_carro'], format="%.2f")
val_fixo = st.sidebar.number_input("Custo Fixo Anual", value=config['custo_fixo_anual'], format="%.2f")
val_manut = st.sidebar.number_input("Custo Manut/KM", value=config['custo_pneu_oleo'], format="%.2f")
val_deprec = st.sidebar.slider("Depreciação %", 0.0, 20.0, value=config['depreciacao_pct'])

# Atualiza Sessão
st.session_state['config_user'] = {"valor_carro": val_carro, "custo_fixo_anual": val_fixo, "custo_pneu_oleo": val_manut, "depreciacao_pct": val_deprec}

custo_fixo_dia = val_fixo / 365
depreciacao_dia = (val_carro * (val_deprec / 100)) / 365
st.sidebar.info(f"Meta Fixa Diária: R$ {custo_fixo_dia:.2f}\nPerda Diária (Deprec): R$ {depreciacao_dia:.2f}")

# --- TELA 1: LANÇAMENTO ---
if menu_escolha == "📝 Lançamento Diário":
    st.title("🚗 Controle Diário (Google Sheets)")
    
    c1, c2, c3 = st.columns(3)
    hoje_ganho = c1.number_input("Ganho (R$)", value=0.0, step=10.0, format="%.2f")
    hoje_km = c2.number_input("KM Rodado", value=0.0, step=5.0, format="%.1f")
    hoje_comb = c3.number_input("Combustível (R$)", value=0.0, step=5.0, format="%.2f")
    obs = st.text_input("Observação")

    hoje_manutencao = hoje_km * val_manut
    hoje_total_guardar = hoje_manutencao + custo_fixo_dia + depreciacao_dia
    hoje_lucro = hoje_ganho - hoje_total_guardar - hoje_comb

    st.markdown("---")
    col1, col2 = st.columns(2)
    col1.error(f"🚨 GUARDAR: R$ {hoje_total_guardar:.2f}")
    if hoje_lucro > 0: col2.success(f"💵 LUCRO: R$ {hoje_lucro:.2f}")
    else: col2.error(f"💸 PREJUÍZO: R$ {hoje_lucro:.2f}")

    labels = ['Lucro', 'Guardar', 'Combustível']
    values = [max(0, hoje_lucro), hoje_total_guardar, hoje_comb]
    fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.4, marker=dict(colors=['#28a745', '#dc3545', '#ffc107']))])
    fig.update_layout(height=300, margin=dict(t=10, b=0, l=0, r=0))
    st.plotly_chart(fig, width="stretch")

    st.markdown("---")
    col_save, col_undo = st.columns([3, 1])
    
    if col_save.button("💾 Salvar no Google Sheets", type="primary", use_container_width=True):
        if hoje_ganho > 0:
            with st.spinner("Salvando..."):
                novo = pd.DataFrame([{'Data': date.today(), 'Ganhos': hoje_ganho, 'Km_Rodado': hoje_km, 'Gastos_Combustivel': hoje_comb, 'Obs': obs}])
                if salvar_na_nuvem(novo):
                    st.success("Salvo com sucesso!")
                    st.cache_data.clear()
        else:
            st.warning("Preencha os valores.")
            
    if col_undo.button("↩️ Desfazer Último", help="Apaga a última linha da planilha", use_container_width=True):
        with st.spinner("Apagando..."):
            if desfazer_ultimo_lancamento():
                st.toast("Último lançamento apagado!", icon="🗑️")
                st.cache_data.clear()
            else:
                st.error("Não há nada para apagar.")

# --- RELATÓRIOS ---
else:
    df = carregar_dados()
    if not df.empty:
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

        resumo = df.groupby('Chave').agg({'Ganhos': 'sum', 'Gastos_Combustivel': 'sum', 'Km_Rodado': 'sum', 'Data': 'nunique'}).rename(columns={'Data': 'Dias'}).reset_index().sort_values('Chave', ascending=False)
        
        resumo['IPVA_Seguro_Guardado'] = resumo['Dias'] * custo_fixo_dia
        resumo['Manutencao_Guardada'] = resumo['Km_Rodado'] * val_manut
        resumo['Depreciacao_Guardada'] = resumo['Dias'] * depreciacao_dia
        resumo['Lucro_Liquido'] = resumo['Ganhos'] - resumo['Gastos_Combustivel'] - resumo['IPVA_Seguro_Guardado'] - resumo['Manutencao_Guardada'] - resumo['Depreciacao_Guardada']

        st.title(f"Relatório {titulo}")
        st.dataframe(resumo, hide_index=True, width="stretch", column_config={"Ganhos": st.column_config.NumberColumn(format="R$ %.2f"), "Lucro_Liquido": st.column_config.NumberColumn(format="R$ %.2f")})

        t1, t2, t3 = st.tabs(["Faturamento", "Lucro", "Custos"])
        with t1: st.plotly_chart(estilo_grafico(px.bar(resumo, x='Chave', y='Ganhos', color_discrete_sequence=['#00CC96']), "R$"), width="stretch")
        with t2: st.plotly_chart(estilo_grafico(px.bar(resumo, x='Chave', y='Lucro_Liquido', color_discrete_sequence=['#28a745']), "R$"), width="stretch")
        with t3: st.plotly_chart(estilo_grafico(px.bar(resumo, x='Chave', y=['IPVA_Seguro_Guardado', 'Manutencao_Guardada'], barmode='group'), "R$"), width="stretch")
    else:
        st.info("Nenhum dado na planilha.")
