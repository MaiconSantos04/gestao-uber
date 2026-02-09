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
        # Tenta abrir a planilha principal
        spreadsheet = client.open("GestaoUberDB")
        
        # Tenta abrir a aba específica
        try:
            sheet = spreadsheet.worksheet(nome_aba)
            return sheet
        except:
            # Se a aba "Config" não existir, cria ela automaticamente
            if nome_aba == "Config":
                sheet = spreadsheet.add_worksheet(title="Config", rows=20, cols=2)
                # Define cabeçalho padrão
                sheet.append_row(["Parametro", "Valor"])
                # Define valores padrão
                padroes = [
                    ["valor_carro", "83000.0"],
                    ["custo_fixo_anual", "6300.0"],
                    ["dias_trabalho_semana", "5"],
                    ["custo_manut_km", "0.25"],
                    ["custo_deprec_km", "0.40"]
                ]
                for p in padroes: sheet.append_row(p)
                return sheet
            else:
                st.error(f"Aba '{nome_aba}' não encontrada.")
                st.stop()
    except:
        st.error("⚠️ Planilha 'GestaoUberDB' não encontrada.")
        st.stop()

# --- GERENCIAMENTO DE CONFIGURAÇÃO (NA NUVEM) ---
def carregar_config_nuvem():
    # Se já carregou na sessão, usa da memória (mais rápido)
    if 'config_user' in st.session_state and st.session_state.get('config_carregada', False):
        return st.session_state['config_user']

    try:
        sheet = conectar_gsheets("Config")
        dados = sheet.get_all_values()
        # Converte lista de listas em dicionário: {'valor_carro': 83000.0, ...}
        config_dict = {}
        # Pula o cabeçalho (linha 0) e lê o resto
        for linha in dados[1:]:
            if len(linha) >= 2:
                chave = linha[0]
                valor = linha[1]
                try:
                    config_dict[chave] = float(valor)
                except:
                    config_dict[chave] = valor
        
        # Garante valores padrão se faltar algo
        padrao = {
            "valor_carro": 83000.0,
            "custo_fixo_anual": 6300.0,
            "dias_trabalho_semana": 5.0,
            "custo_manut_km": 0.25,
            "custo_deprec_km": 0.40
        }
        
        # Mescla o que veio da nuvem com o padrão (prioridade para nuvem)
        config_final = {**padrao, **config_dict}
        
        st.session_state['config_user'] = config_final
        st.session_state['config_carregada'] = True
        return config_final
        
    except Exception as e:
        # Se der erro, usa padrão local
        return {
            "valor_carro": 83000.0, "custo_fixo_anual": 6300.0,
            "dias_trabalho_semana": 5.0, "custo_manut_km": 0.25, "custo_deprec_km": 0.40
        }

def salvar_config_nuvem(nova_config):
    try:
        sheet = conectar_gsheets("Config")
        sheet.clear() # Limpa tudo
        sheet.append_row(["Parametro", "Valor"]) # Cabeçalho
        
        # Prepara linhas
        linhas = []
        for chave, valor in nova_config.items():
            linhas.append([chave, str(valor)])
            
        # Salva em lote (mais rápido)
        for l in linhas:
            sheet.append_row(l)
            
        st.session_state['config_user'] = nova_config
        return True
    except Exception as e:
        st.error(f"Erro ao salvar config: {e}")
        return False

# --- LIMPEZA DE DADOS ---
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

# --- FUNÇÕES DE DADOS ---
def carregar_dados():
    try:
        sheet = conectar_gsheets("Dados")
        dados = sheet.get_all_values()
        if len(dados) < 2:
            return pd.DataFrame(columns=['Data', 'Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel', 'Obs'])
        cabecalho = dados[0]
        linhas = dados[1:]
        df = pd.DataFrame(linhas, columns=cabecalho)
        colunas_padrao = ['Data', 'Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel', 'Obs']
        for col in colunas_padrao:
            if col not in df.columns: df[col] = "0"
        df['ID'] = df.index + 2 
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce').dt.date
        cols_num = ['Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel']
        for col in cols_num: df[col] = df[col].apply(limpar_valor_hibrido)
        return df
    except:
        return pd.DataFrame(columns=['Data', 'Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel', 'Obs'])

def salvar_na_nuvem(nova_linha_df):
    try:
        sheet = conectar_gsheets("Dados")
        nova_linha_df['Data'] = nova_linha_df['Data'].astype(str)
        ordem_colunas = ['Data', 'Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel', 'Obs']
        for col in ordem_colunas:
            if col not in nova_linha_df.columns: nova_linha_df[col] = ""
        nova_linha_df = nova_linha_df[ordem_colunas]
        cols_valores = ['Ganhos', 'Bonus', 'Km_Rodado', 'Gastos_Combustivel']
        for col in cols_valores:
            val = nova_linha_df.iloc[0][col]
            if isinstance(val, (int, float)):
                nova_linha_df.at[0, col] = f"{val:.2f}".replace('.', ',')
        sheet.append_row(nova_linha_df.values.tolist()[0])
        return True
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")
        return False

def excluir_linha_pelo_id(id_linha):
    try:
        sheet = conectar_gsheets("Dados")
        sheet.delete_rows(id_linha)
        return True
    except Exception as e:
        st.error(f"Erro ao excluir: {e}")
        return False

def desfazer_ultimo_lancamento():
    try:
        sheet = conectar_gsheets("Dados")
        todas_linhas = sheet.get_all_values()
        if len(todas_linhas) > 1:
            sheet.delete_rows(len(todas_linhas))
            return True
        return False
    except: return False

# --- API FIPE ---
headers = {'User-Agent': 'Mozilla/5.0'}
def get_json(url):
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200: return response.json()
    except: pass
    return None

# --- ESTILO GRÁFICO ---
def estilo_grafico(fig, titulo_eixo_y):
    fig.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside', marker_cornerradius=10)
    fig.update_layout(title_x=0.5, title_font_size=18, yaxis_title=titulo_eixo_y, xaxis_title=None,
        xaxis=dict(type='category', showgrid=False, showline=False),
        yaxis=dict(showgrid=True, gridcolor='#444444', zerolinecolor='#444444', showline=False),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', margin=dict(t=60, b=30, l=20, r=20), showlegend=False)
    return fig

MESES_PT = {'Jan': 'Jan', 'Feb': 'Fev', 'Mar': 'Mar', 'Apr': 'Abr', 'May': 'Mai', 'Jun': 'Jun', 'Jul': 'Jul', 'Aug': 'Ago', 'Sep': 'Set', 'Oct': 'Out', 'Nov': 'Nov', 'Dec': 'Dez'}

# --- INICIALIZAÇÃO DE CONFIGURAÇÃO ---
config = carregar_config_nuvem()

# --- BARRA LATERAL ---
st.sidebar.title("Navegação")
menu_escolha = st.sidebar.radio("Ir para:", ["📝 Lançamento Diário", "📋 Extrato Completo", "📅 Relatório Semanal", "📅 Relatório Mensal", "📅 Relatório Anual"])

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Configurações (Nuvem)")

# Botão FIPE
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
                                # Atualiza no estado local, usuário deve salvar depois
                                st.session_state['config_user']['valor_carro'] = valor_limpo
                                st.success(f"FIPE Atualizada: {valor_str}. Clique em 'Salvar Configurações' abaixo!")
                                st.rerun()

# Inputs de Configuração
val_carro = st.sidebar.number_input("Valor Veículo (R$)", value=float(config.get('valor_carro', 83000)), format="%.2f")
val_fixo = st.sidebar.number_input("Custo Fixo Anual (IPVA/Seguro)", value=float(config.get('custo_fixo_anual', 6300)), format="%.2f")
dias_semana = st.sidebar.slider("Dias trabalho/semana", 1, 7, value=int(config.get('dias_trabalho_semana', 5)))
val_manut = st.sidebar.number_input("Manutenção/KM (R$)", value=float(config.get('custo_manut_km', 0.25)), format="%.2f", step=0.05)
val_deprec = st.sidebar.number_input("Depreciação/KM (R$)", value=float(config.get('custo_deprec_km', 0.40)), format="%.2f", step=0.05)

# Cálculo de exibição
dias_trabalhados_ano = dias_semana * 52
custo_fixo_dia = val_fixo / dias_trabalhados_ano
st.sidebar.info(f"Meta Fixa: R$ {custo_fixo_dia:.2f}/dia trabalhado")

# --- BOTÃO DE SALVAR CONFIGURAÇÃO ---
if st.sidebar.button("💾 Salvar Configurações"):
    nova_config = {
        "valor_carro": val_carro,
        "custo_fixo_anual": val_fixo,
        "dias_trabalho_semana": dias_semana,
        "custo_manut_km": val_manut,
        "custo_deprec_km": val_deprec
    }
    with st.spinner("Salvando configurações na nuvem..."):
        if salvar_config_nuvem(nova_config):
            st.sidebar.success("Configurações salvas!")
            st.rerun()

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
    hoje_depreciacao = hoje_km * val_deprec
    hoje_ipva = custo_fixo_dia # Fixo por dia trabalhado
    
    hoje_total_guardar = hoje_manutencao + hoje_depreciacao + hoje_ipva
    hoje_lucro = (hoje_ganho + hoje_bonus) - hoje_total_guardar - hoje_comb

    st.markdown("---")
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.error(f"🚨 GUARDAR: R$ {hoje_total_guardar:.2f}")
    if hoje_lucro > 0: kpi2.success(f"💵 LUCRO LÍQUIDO: R$ {hoje_lucro:.2f}")
    else: kpi2.error(f"💸 PREJUÍZO: R$ {hoje_lucro:.2f}")
    kpi3.metric("Custo por KM", f"R$ {(val_manut + val_deprec):.2f}")

    labels = ['Lucro (Inclui Bônus)', 'Guardar', 'Combustível']
    values = [max(0, hoje_lucro), hoje_total_guardar, hoje_comb]
    fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.5, textinfo='percent', textposition='inside', marker=dict(colors=['#28a745', '#dc3545', '#ffc107'], line=dict(color='#000000', width=1)))])
    fig.update_layout(height=350, margin=dict(t=30, b=10, l=10, r=10), legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    st.plotly_chart(fig, width="stretch")

    st.markdown("---")
    col_save, col_undo = st.columns([3, 1])
    
    if col_save.button("💾 Salvar no Google Sheets", type="primary", use_container_width=True):
        if (hoje_ganho > 0 or hoje_bonus > 0):
            if hoje_comb > 800 or hoje_km > 2000:
                st.error(f"⚠️ Valor suspeito (R$ {hoje_comb} ou {hoje_km} km). Verifique vírgulas.")
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

# --- TELA 2: EXTRATO COMPLETO ---
elif menu_escolha == "📋 Extrato Completo":
    st.title("📋 Extrato de Lançamentos")
    df = carregar_dados()
    if not df.empty:
        st.dataframe(df.sort_values('Data', ascending=False), width="stretch", column_config={
            "ID": st.column_config.NumberColumn("🆔 ID", format="%d"),
            "Ganhos": st.column_config.NumberColumn(format="R$ %.2f"),
            "Bonus": st.column_config.NumberColumn(format="R$ %.2f"),
            "Gastos_Combustivel": st.column_config.NumberColumn(format="R$ %.2f"),
            "Km_Rodado": st.column_config.NumberColumn(format="%.1f km")
        })
        col_del1, col_del2 = st.columns([1, 2])
        id_para_excluir = col_del1.number_input("Digite o ID para apagar:", min_value=0, step=1)
        if col_del2.button("❌ Apagar Linha"):
            if id_para_excluir > 1:
                with st.spinner("Apagando..."):
                    if excluir_linha_pelo_id(id_para_excluir):
                        st.success(f"Linha {id_para_excluir} apagada!")
                        st.cache_data.clear()
                        st.rerun()
            else: st.warning("ID inválido.")
    else: st.info("Nenhum dado encontrado.")

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
        
        # CÁLCULOS FINAIS COM CONFIGURAÇÃO DA NUVEM
        resumo['Receita_Total'] = resumo['Ganhos'] + resumo['Bonus']
        
        # IPVA proporcional aos dias trabalhados
        resumo['IPVA_Seguro_Guardado'] = resumo['Dias'] * custo_fixo_dia
        
        # Manut e Deprec puramente por KM
        resumo['Manutencao_Guardada'] = resumo['Km_Rodado'] * val_manut
        resumo['Depreciacao_Guardada'] = resumo['Km_Rodado'] * val_deprec
        
        resumo['Lucro_Liquido'] = resumo['Receita_Total'] - resumo['Gastos_Combustivel'] - resumo['IPVA_Seguro_Guardado'] - resumo['Manutencao_Guardada'] - resumo['Depreciacao_Guardada']

        st.title(f"Relatório {titulo}")
        st.dataframe(resumo, hide_index=True, width="stretch", column_config={
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

        t1, t2, t3 = st.tabs(["Faturamento vs Bônus", "Lucro", "Custos"])
        with t1: 
            fig_fat = px.bar(resumo, x='Chave', y=['Ganhos', 'Bonus'], title="Composição da Receita", barmode='stack', color_discrete_map={'Ganhos': '#00CC96', 'Bonus': '#636EFA'})
            st.plotly_chart(estilo_grafico(fig_fat, "R$"), width="stretch")
        with t2: st.plotly_chart(estilo_grafico(px.bar(resumo, x='Chave', y='Lucro_Liquido', color_discrete_sequence=['#28a745']), "R$"), width="stretch")
        with t3: st.plotly_chart(estilo_grafico(px.bar(resumo, x='Chave', y=['IPVA_Seguro_Guardado', 'Manutencao_Guardada', 'Depreciacao_Guardada'], barmode='group'), "R$"), width="stretch")
    else:
        st.info("Nenhum dado na planilha.")
