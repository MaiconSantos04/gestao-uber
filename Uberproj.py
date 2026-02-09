import streamlit as st
import pandas as pd
import requests
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
        sheet = client.open("GestaoUberDB").worksheet("Dados")
        return sheet
    except:
        st.error("⚠️ Planilha 'GestaoUberDB' não encontrada.")
        st.stop()

# --- LIMPEZA DE DADOS ---
def limpar_valor_brasileiro(valor):
    if isinstance(valor, (int, float)):
        return float(valor)
    valor_str = str(valor).strip().replace('R$', '').replace(' ', '')
    if ',' in valor_str:
        valor_str = valor_str.replace('.', '').replace(',', '.')
    try:
        return float(valor_str)
    except:
        return 0.0

# --- FUNÇÕES DE DADOS ---
def carregar_dados():
    try:
        sheet = conectar_gsheets()
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        
        if df.empty:
            return pd.DataFrame(columns=['Data', 'Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel', 'Obs'])
        
        if 'Bonus' not in df.columns: df['Bonus'] = 0.0

        # Cria ID visual (Linha do Excel)
        df['ID'] = df.index + 2 

        df['Data'] = pd.to_datetime(df['Data']).dt.date
        
        cols_num = ['Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel']
        for col in cols_num:
            if col in df.columns:
                df[col] = df[col].apply(limpar_valor_brasileiro)
            
        return df
    except:
        return pd.DataFrame(columns=['Data', 'Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel', 'Obs'])

def salvar_na_nuvem(nova_linha_df):
    try:
        sheet = conectar_gsheets()
        nova_linha_df['Data'] = nova_linha_df['Data'].astype(str)
        ordem_colunas = ['Data', 'Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel', 'Obs']
        nova_linha_df = nova_linha_df[ordem_colunas]
        lista_dados = nova_linha_df.values.tolist()
        sheet.append_row(lista_dados[0])
        return True
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")
        return False

def excluir_linha_pelo_id(id_linha):
    try:
        sheet = conectar_gsheets()
        sheet.delete_rows(id_linha)
        return True
    except Exception as e:
        st.error(f"Erro ao excluir: {e}")
        return False

def desfazer_ultimo_lancamento():
    try:
        sheet = conectar_gsheets()
        todas_linhas = sheet.get_all_values()
        if len(todas_linhas) > 1:
            sheet.delete_rows(len(todas_linhas))
            return True
        return False
    except Exception as e:
        st.error(f"Erro ao excluir: {e}")
        return False

# --- API FIPE ---
headers = {'User-Agent': 'Mozilla/5.0'}
def get_json(url):
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200: return response.json()
    except: pass
    return None

# --- CONFIGURAÇÃO ---
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
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', margin=dict(t=60, b=30, l=20, r=20), showlegend=False)
    return fig

MESES_PT = {'Jan': 'Jan', 'Feb': 'Fev', 'Mar': 'Mar', 'Apr': 'Abr', 'May': 'Mai', 'Jun': 'Jun', 'Jul': 'Jul', 'Aug': 'Ago', 'Sep': 'Set', 'Oct': 'Out', 'Nov': 'Nov', 'Dec': 'Dez'}

# --- INICIALIZAÇÃO ---
config = carregar_config()

# --- BARRA LATERAL ---
st.sidebar.title("Navegação")
menu_escolha = st.sidebar.radio("Ir para:", ["📝 Lançamento Diário", "📋 Extrato Completo", "📅 Relatório Semanal", "📅 Relatório Mensal", "📅 Relatório Anual"])

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Configurações")

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
                                st.session_state['config_user']['valor_carro'] = valor_limpo
                                st.success(f"Atualizado: {valor_str}")
                                st.rerun()

st.sidebar.markdown("---")
val_carro = st.sidebar.number_input("Valor Veículo (R$)", value=st.session_state['config_user']['valor_carro'], format="%.2f")
val_fixo = st.sidebar.number_input("Custo Fixo Anual", value=config['custo_fixo_anual'], format="%.2f")
val_manut = st.sidebar.number_input("Custo Manut/KM", value=config['custo_pneu_oleo'], format="%.2f")
val_deprec = st.sidebar.slider("Depreciação %", 0.0, 20.0, value=config['depreciacao_pct'])

st.session_state['config_user'] = {"valor_carro": val_carro, "custo_fixo_anual": val_fixo, "custo_pneu_oleo": val_manut, "depreciacao_pct": val_deprec}
custo_fixo_dia = val_fixo / 365
depreciacao_dia = (val_carro * (val_deprec / 100)) / 365
st.sidebar.info(f"Meta Fixa Diária: R$ {custo_fixo_dia:.2f}\nPerda Diária (Deprec): R$ {depreciacao_dia:.2f}")

# --- TELA 1: LANÇAMENTO ---
if menu_escolha == "📝 Lançamento Diário":
    st.title("🚗 Controle Diário (Google Sheets)")
    
    c1, c2, c3, c4 = st.columns(4)
    hoje_ganho = c1.number_input("Ganhos Corridas (R$)", value=0.0, step=10.0, format="%.2f")
    hoje_bonus = c2.number_input("Bônus/Promo (R$)", value=0.0, step=10.0, format="%.2f")
    hoje_km = c3.number_input("KM Rodado", value=0.0, step=5.0, format="%.1f")
    hoje_comb = c4.number_input("Combustível (R$)", value=0.0, step=5.0, format="%.2f")
    obs = st.text_input("Observação")

    hoje_manutencao = hoje_km * val_manut
    hoje_total_guardar = hoje_manutencao + custo_fixo_dia + depreciacao_dia
    hoje_lucro = (hoje_ganho + hoje_bonus) - hoje_total_guardar - hoje_comb

    st.markdown("---")
    col1, col2 = st.columns(2)
    col1.error(f"🚨 GUARDAR: R$ {hoje_total_guardar:.2f}")
    if hoje_lucro > 0: col2.success(f"💵 LUCRO LÍQUIDO: R$ {hoje_lucro:.2f}")
    else: col2.error(f"💸 PREJUÍZO: R$ {hoje_lucro:.2f}")

    # Gráfico Donut
    labels = ['Lucro (Inclui Bônus)', 'Guardar', 'Combustível']
    values = [max(0, hoje_lucro), hoje_total_guardar, hoje_comb]
    fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.5, textinfo='percent', textposition='inside', marker=dict(colors=['#28a745', '#dc3545', '#ffc107'], line=dict(color='#000000', width=1)))])
    fig.update_layout(height=350, margin=dict(t=30, b=10, l=10, r=10), legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    st.plotly_chart(fig, width="stretch")

    st.markdown("---")
    col_save, col_undo = st.columns([3, 1])
    
    # BOTÃO SALVAR COM TRAVA DE SEGURANÇA
    if col_save.button("💾 Salvar no Google Sheets", type="primary", use_container_width=True):
        if (hoje_ganho > 0 or hoje_bonus > 0):
            # TRAVA DE SEGURANÇA: Se valores forem absurdos, avisa antes
            if hoje_comb > 500 or hoje_km > 1500:
                st.error(f"⚠️ VALOR SUSPEITO! Você digitou R$ {hoje_comb} de combustível ou {hoje_km} KM. Verifique se não esqueceu a vírgula.")
            else:
                with st.spinner("Salvando..."):
                    novo = pd.DataFrame([{'Data': date.today(), 'Ganhos': hoje_ganho, 'Bonus': hoje_bonus, 'Km_Rodado': hoje_km, 'Gastos_Combustivel': hoje_comb, 'Obs': obs}])
                    if salvar_na_nuvem(novo):
                        st.success("Salvo com sucesso!")
                        st.cache_data.clear()
        else: st.warning("Preencha algum valor.")
            
    if col_undo.button("↩️ Desfazer Último", use_container_width=True):
        with st.spinner("Apagando..."):
            if desfazer_ultimo_lancamento():
                st.toast("Apagado!", icon="🗑️")
                st.cache_data.clear()
            else: st.error("Erro ao apagar.")

# --- TELA 2: EXTRATO COMPLETO (CORREÇÃO DE DADOS) ---
elif menu_escolha == "📋 Extrato Completo":
    st.title("📋 Extrato de Lançamentos")
    st.warning("🔎 Use esta tela para encontrar e APAGAR lançamentos errados (ex: Combustível 6914).")
    
    df = carregar_dados()
    if not df.empty:
        # Mostra primeiro os lançamentos mais recentes
        st.dataframe(df.sort_values('Data', ascending=False), width="stretch", column_config={
            "ID": st.column_config.NumberColumn("🆔 ID (Para Apagar)", format="%d"),
            "Ganhos": st.column_config.NumberColumn(format="R$ %.2f"),
            "Bonus": st.column_config.NumberColumn(format="R$ %.2f"),
            "Gastos_Combustivel": st.column_config.NumberColumn(format="R$ %.2f"),
            "Km_Rodado": st.column_config.NumberColumn(format="%.1f km")
        })
        
        st.markdown("### 🗑️ Apagar Lançamento Errado")
        col_del1, col_del2 = st.columns([1, 2])
        id_para_excluir = col_del1.number_input("Digite o ID da linha errada:", min_value=0, step=1)
        if col_del2.button("❌ Apagar Linha Definitivamente"):
            if id_para_excluir > 1:
                with st.spinner("Conectando ao Google e apagando..."):
                    if excluir_linha_pelo_id(id_para_excluir):
                        st.success(f"Linha {id_para_excluir} apagada com sucesso!")
                        st.cache_data.clear()
                        st.rerun()
            else:
                st.warning("ID inválido.")
    else:
        st.info("Nenhum dado encontrado.")

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

        resumo = df.groupby('Chave').agg({'Ganhos': 'sum', 'Bonus': 'sum', 'Gastos_Combustivel': 'sum', 'Km_Rodado': 'sum', 'Data': 'nunique'}).rename(columns={'Data': 'Dias'}).reset_index().sort_values('Chave', ascending=False)
        
        resumo['Receita_Total'] = resumo['Ganhos'] + resumo['Bonus']
        resumo['IPVA_Seguro_Guardado'] = resumo['Dias'] * custo_fixo_dia
        resumo['Manutencao_Guardada'] = resumo['Km_Rodado'] * val_manut
        resumo['Depreciacao_Guardada'] = resumo['Dias'] * depreciacao_dia
        resumo['Lucro_Liquido'] = resumo['Receita_Total'] - resumo['Gastos_Combustivel'] - resumo['IPVA_Seguro_Guardado'] - resumo['Manutencao_Guardada'] - resumo['Depreciacao_Guardada']

        st.title(f"Relatório {titulo}")
        st.dataframe(resumo, hide_index=True, width="stretch", column_config={
            "Receita_Total": st.column_config.NumberColumn("💰 Total", format="R$ %.2f"),
            "Ganhos": st.column_config.NumberColumn("🚗 Corridas", format="R$ %.2f"),
            "Bonus": st.column_config.NumberColumn("🎁 Bônus", format="R$ %.2f"),
            "Gastos_Combustivel": st.column_config.NumberColumn("⛽ Combustível", format="R$ %.2f"),
            "Km_Rodado": st.column_config.NumberColumn("🛣️ KM", format="%.1f km"),
            "IPVA_Seguro_Guardado": st.column_config.NumberColumn("🏦 IPVA", format="R$ %.2f"),
            "Manutencao_Guardada": st.column_config.NumberColumn("🛠️ Manut", format="R$ %.2f"),
            "Depreciacao_Guardada": st.column_config.NumberColumn("📉 Deprec", format="R$ %.2f"),
            "Lucro_Liquido": st.column_config.NumberColumn("💵 Lucro", format="R$ %.2f")
        })

        t1, t2, t3 = st.tabs(["Faturamento vs Bônus", "Lucro", "Custos"])
        with t1: 
            fig_fat = px.bar(resumo, x='Chave', y=['Ganhos', 'Bonus'], title="Composição da Receita", barmode='stack', color_discrete_map={'Ganhos': '#00CC96', 'Bonus': '#636EFA'})
            st.plotly_chart(estilo_grafico(fig_fat, "R$"), width="stretch")
        with t2: st.plotly_chart(estilo_grafico(px.bar(resumo, x='Chave', y='Lucro_Liquido', color_discrete_sequence=['#28a745']), "R$"), width="stretch")
        with t3: st.plotly_chart(estilo_grafico(px.bar(resumo, x='Chave', y=['IPVA_Seguro_Guardado', 'Manutencao_Guardada'], barmode='group'), "R$"), width="stretch")
    else:
        st.info("Nenhum dado na planilha.")
