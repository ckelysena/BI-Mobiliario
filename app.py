# -*- coding: utf-8 -*-
"""
BI - Entregas por Unidade (multi-abas Google Sheets)
- Lê TODAS as abas via export XLSX (planilha pública ou com acesso aberto)
- Usa CABEÇALHO NA LINHA 3 (índice 2) em TODAS as abas
- Une tudo e adiciona coluna ABA (nome da guia)
- Filtros encadeados: Unidade de destino → Quantidade entregue na unidade → DESCRIÇÃO DO ITEM RESUMIDA → n° da OF
- Filtro por ABA(s)
- Mostra "Dados filtrados" no topo (com TODAS as colunas úteis já com o cabeçalho)
"""

import io
import unicodedata
import pandas as pd
import streamlit as st
import requests
import streamlit as st
from auth import require_authentication, AuthManager, init_session_state
from datetime import datetime
import plotly.express as px  # opcional para o resumo por ABA

# =========================
# CONFIGURAÇÃO
# =========================
st.set_page_config(page_title="BI - Entregas (GPCA)", page_icon="📦", layout="wide")

init_session_state()
auth_manager = AuthManager(credentials_file="credentials.json")

if not require_authentication(auth_manager, logo_path="logo.svg"):
    st.stop()

# ===============================
# 🔹 CABEÇALHO DO SISTEMA
# ===============================
with st.container():
    st.markdown(
        """
        <div style="
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 10px 10px 10px;
        ">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 26px;">👤</span>
                <h2 style="margin: 0; color: #0C2856;">SES-PE <span style="font-weight:400;">(sespe)</span></h2>
            </div>
            <form action="#" method="post">
                <button type="submit" style="
                    background-color: #004080;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 6px 16px;
                    font-size: 15px;
                    font-weight: 600;
                    cursor: pointer;
                ">Logout</button>
            </form>
        </div>
        """,
        unsafe_allow_html=True
    )

st.divider()

try:
    with open("style.css", "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    pass

# ID da planilha informada pelo usuário
SHEET_ID = "1asY-XmwXtHa7Nb-hYpxSpjz1PeSU96I5"
# Baixa TODAS as abas como XLSX
XLSX_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"

# Linha do cabeçalho (3ª linha visível na planilha → índice 2)
HEADER_ROW_INDEX = 2

CONFIG_MODEBAR = {
    "displaylogo": False,
    "modeBarButtonsToRemove": [
        "pan2d", "select2d", "lasso2d",
        "zoomIn2d", "zoomOut2d", "autoScale2d",
        "hoverClosestCartesian", "hoverCompareCartesian",
        "toggleSpikelines", "zoom2d", "resetScale2d"
    ],
    "modeBarButtonsToAdd": ["toImage"]
}

# Campos que viram filtros (com variações de nomes vistas nas abas)
ALVO_NOMES = {
    "DESCRIÇÃO DO ITEM RESUMIDA": [
        "descrição do item resumida", "descricao do item resumida", "descricao", "resumida", "item"
    ],
    "UNIDADE DE DESTINO": [
        "unidade de destino", "unidades de destino", "unidade destino", "unidade", "destino",
        "projeto das equipagem das unidades"
    ],
    "N° DA OF": [
        "n° da of", "nº da of", "no da of", "n da of",
        "n° of", "nº of", "no of", "n of", "of"
    ],
    # ⇩⇩ apenas adição de aliases "quant." e "quant"
    "QUANTIDADE ENTREGUE NA UNIDADE": [
        "quantidade entregue na unidade", "QUANT. ENTREGUE NA UNIDADE",
        "quantidade entregue", "quantidade", "qtd", "quant.", "quant"
    ],
    "QUANTIDADE NA ATA E CONSUMO": [
        "quantidade na ata e consumo", "qtd na ata e consumo", "quantidade na ata",
        "quantidade", "qtd", "quant.", "quant"
    ],
}

# Colunas “de capa” que, quando existirem, devem aparecer primeiro no grid
CAPA_PRIORIDADE = [
    "ABA",
    "Nº ATA", "N° ATA", "NO ATA", "N ATA",
    "GESTOR DA ATA",
    "SEI DE CONSUMO",
    "E-FISCO", "E FISCO", "EFISCO",
    "GRUPO DE DESPESA",
    "DESCRIÇÃO DO ITEM RESUMIDA",
    "UNIDADES DE DESTINO", "UNIDADE DE DESTINO",
    "FORNECEDOR",
    "N° OF", "Nº OF", "N° DA OF", "Nº DA OF", "n° da OF", "n° da of",
    "PREVISÃO DO FORN", "PREVISAO DO FORN", "PREVISÃO DO FORNECIMENTO"
]

# =========================
# HELPERS
# =========================
def norm(s: str) -> str:
    """Normaliza texto: minúsculo e sem acentos (para match robusto)."""
    s = str(s or "").strip().lower()
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("utf-8")


def mapear_colunas(df: pd.DataFrame) -> dict:
    """
    Encontra, no df, qual coluna corresponde a cada campo-alvo.
    Retorna dict: { "Unidade de destino": "nome_real_no_df", ... }
    """
    cols_norm = {c: norm(c) for c in df.columns}
    mapeamento = {}
    for alvo, aliases in ALVO_NOMES.items():
        achou = None
        # match exato
        for c, cn in cols_norm.items():
            if any(cn == norm(a) for a in aliases):
                achou = c
                break
        # fallback: contém parte do alias
        if not achou:
            for c, cn in cols_norm.items():
                if any(norm(a) in cn for a in aliases):
                    achou = c
                    break
        if achou:
            mapeamento[alvo] = achou
    return mapeamento


@st.cache_data(ttl=600, show_spinner=True)
def carregar_planilha_xlsx(url: str, header_row_index: int) -> dict:
    """
    Baixa XLSX e lê TODAS as abas com a linha 'header_row_index' como cabeçalho.
    Retorna: {nome_aba: DataFrame}
    """
    resp = requests.get(url)
    resp.raise_for_status()
    with io.BytesIO(resp.content) as f:
        sheets = pd.read_excel(
            f,
            sheet_name=None,
            dtype=str,              # tudo como texto para evitar conversões indesejadas
            header=header_row_index # 3ª linha como header
        )

    limpos = {}
    for aba, df in sheets.items():
        if df is None or df.empty:
            continue
        # tira espaços e colunas totalmente vazias
        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(how="all").dropna(axis=1, how="all")
        if not df.empty:
            limpos[aba] = df.reset_index(drop=True)
    return limpos


def selectbox_com_todos(label, serie: pd.Series):
    """Select com opção '(Todos)'; retorna None quando '(Todos)' for escolhido."""
    vals = sorted(pd.Series(serie, dtype="object").dropna().astype(str).unique().tolist())
    opcoes = ["(Todos)"] + vals
    esco = st.selectbox(label, opcoes)
    return None if esco == "(Todos)" else esco


# =========================
# CARGA
# =========================
try:
    todas_abas = carregar_planilha_xlsx(XLSX_URL, HEADER_ROW_INDEX)
except Exception as e:
    st.error("❌ Não consegui ler a planilha. Abra o acesso (Qualquer pessoa com o link - Leitor)."
             f"\n\nDetalhes: {e}")
    st.stop()

if not todas_abas:
    st.warning("Planilha sem conteúdo legível.")
    st.stop()

# Une tudo e marca origem (ABA)
dfs = []
aba_col_mapeios = {}
for aba, df in todas_abas.items():
    aba_col_mapeios[aba] = mapear_colunas(df)  # guarda mapeamento desta aba
    d2 = df.copy()
    d2["ABA"] = aba
    dfs.append(d2)

df_full = pd.concat(dfs, ignore_index=True)

# =========================
# UI / FILTROS
# =========================
col1, col2 = st.columns([4, 1])

with col1:
    st.title("📊 BI - Emendas Mobiliárias")

    data_atual = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
    st.markdown(
        f"""
        <div style="color:#666; font-size:0.95em; line-height:1.3;">
            <strong>Secretaria da Saúde - Governo de Pernambuco</strong><br>
            Última atualização: {data_atual}
        </div>
        """,
        unsafe_allow_html=True
    )

with col2:
    st.markdown("<div style='margin-top: 35px;'></div>", unsafe_allow_html=True)
    try:
        st.image("logo.svg", width=200)
    except:
        pass

# ===== Sidebar: seleção de abas =====
with st.sidebar:
    st.header("Abas")

    opcoes_abas = ["(Todas)"] + list(todas_abas.keys())

    # Callbacks SEGUROS para alterar o estado (executam fora do bloco do widget)
    def _selecionar_todas():
        st.session_state["abas_sel"] = ["(Todas)"]

    def _limpar_selecao():
        st.session_state["abas_sel"] = []



    # Seleção inicial: começa com "(Todas)" se ainda não houver estado
    selecao_inicial = st.session_state.get("abas_sel", ["(Todas)"])

    abas_sel = st.multiselect(
        "Quais abas considerar?",
        options=opcoes_abas,
        default=selecao_inicial,
        key="abas_sel",
        help="Escolha uma ou várias abas específicas, ou selecione (Todas)."
    )

# ===== Regra: todas, específicas, ou mistura =====
abas_especificas = [a for a in st.session_state.get("abas_sel", []) if a != "(Todas)"]

# Se "(Todas)" estiver marcada OU se não houver específicas -> usar TODAS
if "(Todas)" in st.session_state.get("abas_sel", []) or len(abas_especificas) == 0:
    abas_escolhidas = list(todas_abas.keys())
else:
    abas_escolhidas = abas_especificas

# recorte por aba
df_work = df_full[df_full["ABA"].isin(abas_escolhidas)].copy()

# === FIX: não sobrescrever colunas existentes e evitar copia de/para a mesma coluna ===
# Cria a coluna padronizada só se ela ainda NÃO existir
for alvo in ALVO_NOMES.keys():
    if alvo not in df_work.columns:
        df_work[alvo] = None

for aba in df_work["ABA"].unique():
    mask = df_work["ABA"] == aba
    m = aba_col_mapeios.get(aba, {})
    for alvo in ALVO_NOMES.keys():
        col_real = m.get(alvo)
        if not col_real:
            continue
        # Se a coluna real já tem o MESMO nome do alvo, não faça nada (já está correta)
        if col_real == alvo:
            continue
        # Senão, copia da coluna real para a padronizada (somente nas linhas da aba)
        if col_real in df_work.columns and alvo in df_work.columns:
            df_work.loc[mask, alvo] = df_work.loc[mask, col_real]

# =========================================================
# 🔄 Função para limpar filtros e resetar selects
# =========================================================
st.sidebar.header("Filtros")

def limpar_filtros():
    """Apaga todas as variáveis relacionadas a filtros"""
    for key in list(st.session_state.keys()):
        if any(x in key.lower() for x in ["filtro", "valor", "selectbox"]):
            st.session_state.pop(key, None)
    # Gera uma chave única para forçar reset
    st.session_state["reset_key"] = datetime.now().timestamp()
    st.rerun()

if st.sidebar.button("🧹 Limpar filtros"):
    limpar_filtros()

def select_valor_com_todos(rotulo: str, serie: pd.Series, key: str):
    """Selectbox com opção (Todos), retorna None se selecionado."""
    valores_unicos = sorted(serie.dropna().astype(str).unique().tolist())
    opcoes = ["(Todos)"] + valores_unicos
    escolha = st.sidebar.selectbox(rotulo, opcoes, key=key)
    return None if escolha == "(Todos)" else escolha

CAMPOS = [
    "DESCRIÇÃO DO ITEM RESUMIDA",
    "UNIDADES DE DESTINO",
    "N° OF",
    "QUANTIDADE ENTREGUE NA UNIDADE",
    "QUANTIDADE NA ATA E CONSUMO",
]

# Garante que só campos existentes apareçam
opcoes_presentes = [c for c in CAMPOS if c in df_work.columns]

if not opcoes_presentes:
    st.sidebar.warning("⚠️ Nenhuma das colunas de filtro iniciais existe na planilha.")
    df_filtrado = df_work.copy()
else:
    reset_key = st.session_state.get("reset_key", 0)

    # 1º filtro (obrigatório)
    filtro1 = st.sidebar.selectbox(
        "1º filtro:",
        opcoes_presentes,
        key=f"filtro1_{reset_key}"
    )
    valor1 = select_valor_com_todos(
        f"Escolha {filtro1}:",
        df_work[filtro1],
        key=f"valor1_{reset_key}"
    )
    df_filtrado = df_work[df_work[filtro1] == valor1] if valor1 is not None else df_work.copy()

    # 2º filtro (opcional)
    restantes2 = [c for c in opcoes_presentes if c != filtro1]
    filtro2 = st.sidebar.selectbox(
        "2º filtro (opcional):",
        ["(Nenhum)"] + restantes2,
        key=f"filtro2_{reset_key}"
    )
    if filtro2 != "(Nenhum)" and filtro2 in df_filtrado.columns:
        valor2 = select_valor_com_todos(
            f"Escolha {filtro2}:",
            df_filtrado[filtro2],
            key=f"valor2_{reset_key}"
        )
        if valor2 is not None:
            df_filtrado = df_filtrado[df_filtrado[filtro2] == valor2]

    # 3º filtro (opcional)
    restantes3 = [c for c in opcoes_presentes if c not in [filtro1, filtro2] and c != "(Nenhum)"]
    filtro3 = st.sidebar.selectbox(
        "3º filtro (opcional):",
        ["(Nenhum)"] + restantes3,
        key=f"filtro3_{reset_key}"
    )
    if filtro3 != "(Nenhum)" and filtro3 in df_filtrado.columns:
        valor3 = select_valor_com_todos(
            f"Escolha {filtro3}:",
            df_filtrado[filtro3],
            key=f"valor3_{reset_key}"
        )
        if valor3 is not None:
            df_filtrado = df_filtrado[df_filtrado[filtro3] == valor3]

    # 4º filtro (opcional)
    restantes4 = [c for c in opcoes_presentes if c not in [filtro1, filtro2, filtro3] and c != "(Nenhum)"]
    filtro4 = st.sidebar.selectbox(
        "4º filtro (opcional):",
        ["(Nenhum)"] + restantes4,
        key=f"filtro4_{reset_key}"
    )
    if filtro4 != "(Nenhum)" and filtro4 in df_filtrado.columns:
        valor4 = select_valor_com_todos(
            f"Escolha {filtro4}:",
            df_filtrado[filtro4],
            key=f"valor4_{reset_key}"
        )
        if valor4 is not None:
            df_filtrado = df_filtrado[df_filtrado[filtro4] == valor4]

    # 5º filtro (opcional)
    restantes5 = [c for c in opcoes_presentes if c not in [filtro1, filtro2, filtro3, filtro4] and c != "(Nenhum)"]
    filtro5 = st.sidebar.selectbox(
        "5º filtro (opcional):",
        ["(Nenhum)"] + restantes5,
        key=f"filtro5_{reset_key}"
    )
    if filtro5 != "(Nenhum)" and filtro5 in df_filtrado.columns:
        valor5 = select_valor_com_todos(
            f"Escolha {filtro5}:",
            df_filtrado[filtro5],
            key=f"valor4_{reset_key}"
        )
        if valor5 is not None:
            df_filtrado = df_filtrado[df_filtrado[filtro5] == valor5]


# ——— GRID com o CABEÇALHO certo já embutido ———
abas_texto = ", ".join(abas_escolhidas)
st.subheader("Dados Filtrados")
if abas_texto:
    st.caption(f"Filtros aplicados: {abas_texto}")

st.caption(f"{len(df_filtrado)} registros exibidos após os filtros aplicados.")

st.download_button(
    "⬇️ Exportar Dados",
    data=df_filtrado.to_csv(index=False).encode("utf-8"),
    file_name="emendas_filtrado.csv",
    mime="text/csv",
)

prior = []
for c in CAPA_PRIORIDADE:
    if c in df_filtrado.columns and c not in prior:
        prior.append(c)

filtros_padrao = [c for c in ALVO_NOMES.keys() if c in df_filtrado.columns and c not in prior]
resto = [c for c in df_filtrado.columns if c not in prior + filtros_padrao]
ordem_cols = prior + filtros_padrao + resto

cols_exibir = [c for c in ordem_cols if c != "ABA"]
st.dataframe(df_filtrado[cols_exibir], use_container_width=True)

# =========================================================
# 📊 Barras agrupadas por UNIDADE(S) DE DESTINO (3 métricas)
# =========================================================
import plotly.graph_objects as go

def norm(s: str) -> str:
    s = str(s or "").strip().lower()
    import unicodedata
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("utf-8")

def find_col(df, targets):
    cols_norm = {c: norm(c) for c in df.columns}
    for t in targets:
        tnorm = norm(t)
        for c, cn in cols_norm.items():
            if cn == tnorm or tnorm in cn:
                return c
    return None

dest = find_col(df_filtrado, ["UNIDADE DE DESTINO", "UNIDADES DE DESTINO"])
if not dest:
    st.info("Não encontrei a coluna 'UNIDADE(S) DE DESTINO)' para montar o gráfico.")
else:
    col_valor = find_col(df_filtrado, [
        "VALOR TOTAL", "VALOR", "VALOR TOTAL (R$)", "TOTAL (R$)", "VALOR PREVISTO",
        "VALOR DA OF", "VALOR GLOBAL"
    ])
    col_unid = find_col(df_filtrado, [
        "QUANTIDADE ENTREGUE NA UNIDADE", "QTD ENTREGUE NA UNIDADE", "QUANT. ENTREGUE NA UNIDADE",
        "QUANT ENTREGUE NA UNIDADE", "QUANT", "QTD"
    ])

    faltantes = [n for n, c in {
        "VALOR TOTAL": col_valor,
        "QUANTIDADE ENTREGUE NA UNIDADE": col_unid
    }.items() if c is None]

    if faltantes:
        st.warning("Não encontrei as colunas: " + ", ".join(faltantes))
    else:
        def to_number(v):
            if pd.isna(v):
                return 0.0
            x = str(v).strip().replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
            try:
                return float(x)
            except Exception:
                return 0.0

        work = df_filtrado[[dest, col_valor, col_unid]].copy()
        for c in [col_valor, col_unid]:
            work[c] = work[c].map(to_number)

        agg = work.groupby(dest, dropna=False)[[col_valor, col_unid]].sum().reset_index()
        agg = agg.sort_values(col_valor, ascending=False)

        fig = go.Figure()

        # adiciona labels nas barras
        fig.add_trace(go.Bar(
            x=agg[dest], y=agg[col_valor],
            name="VALOR TOTAL",
            text=[f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") for v in agg[col_valor]],
            textposition="outside",
            marker_color="#2E86DE"
        ))


        fig.add_trace(go.Bar(
            x=agg[dest], y=agg[col_unid],
            name="QUANTIDADE ENTREGUE NA UNIDADE", text=agg[col_unid],
            textposition="outside", marker_color="#E74C3C"
        ))

        fig.update_layout(
            title=f"Entregas por {dest} — VALOR e QUANTIDADES",
            barmode="group",
            xaxis_title=dest,
            yaxis_title="Valores / Quantidades",
            legend_title="Métricas",
            margin=dict(l=10, r=10, t=60, b=10),
            height=560,
            uniformtext_minsize=8,
            uniformtext_mode='hide'
        )


        st.plotly_chart(fig, use_container_width=True, config=CONFIG_MODEBAR)