import io
import unicodedata
import pandas as pd
import streamlit as st
import requests
from auth import require_authentication, AuthManager, init_session_state
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go


st.set_page_config(page_title="BI - Entregas (GPCA)", page_icon="📦", layout="wide")

init_session_state()
auth_manager = AuthManager(credentials_file="credentials.json")

if not require_authentication(auth_manager, logo_path="logo.svg"):
    st.stop()


def atualizar_cache_e_rerun():
    try:
        carregar_planilha_xlsx.clear()
    except Exception:
        st.cache_data.clear()

    st.session_state["reset_key"] = datetime.now().timestamp()
    st.rerun()


with st.container():
    col1, col2 = st.columns([4, 1.1])

    with col1:
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:10px;">
                <span style="font-size:26px;">👤</span>
                <h2 style="margin:0;color:#0C2856;">
                    SES-PE <span style="font-weight:400;">(sespe)</span>
                </h2>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:
        st.markdown(
            """
            <style>
            .top-actions button {
                width: 120px !important;
                height: 36px !important;
                background-color:#0C2856 !important;
                color:white !important;
                border:none !important;
                border-radius:8px !important;
                font-size:15px !important;
                margin-left:8px !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        bcol1, bcol2 = st.columns([1, 1])
        with bcol1:
            st.markdown('<div class="top-actions">', unsafe_allow_html=True)
            if st.button("Atualizar", key="refresh_btn"):
                atualizar_cache_e_rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        with bcol2:
            st.markdown('<div class="top-actions">', unsafe_allow_html=True)
            if st.button("Logout", key="logout_btn"):
                for key in list(st.session_state.keys()):
                    st.session_state.pop(key, None)
                st.session_state["authenticated"] = False
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

st.divider()

try:
    with open("style.css", "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    pass


SHEET_ID = "1asY-XmwXtHa7Nb-hYpxSpjz1PeSU96I5"
XLSX_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"
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

def norm(s: str) -> str:
    s = str(s or "").strip().lower()
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("utf-8")


@st.cache_data(ttl=600, show_spinner=True)
def carregar_planilha_xlsx(url: str, header_row_index: int) -> dict:
    resp = requests.get(url)
    resp.raise_for_status()
    with io.BytesIO(resp.content) as f:
        sheets = pd.read_excel(
            f,
            sheet_name=None,
            dtype=str,
            header=header_row_index
        )

    limpos = {}
    for aba, df in sheets.items():
        if df is None or df.empty:
            continue

        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(how="all").dropna(axis=1, how="all")
        if not df.empty:
            limpos[aba] = df.reset_index(drop=True)
    return limpos


def selectbox_com_todos(label, serie: pd.Series):
    vals = sorted(pd.Series(serie, dtype="object").dropna().astype(str).unique().tolist())
    opcoes = ["(Todos)"] + vals
    esco = st.selectbox(label, opcoes)
    return None if esco == "(Todos)" else esco


try:
    todas_abas = carregar_planilha_xlsx(XLSX_URL, HEADER_ROW_INDEX)
except Exception as e:
    st.error("❌ Não consegui ler a planilha. Abra o acesso (Qualquer pessoa com o link - Leitor)."
             f"\n\nDetalhes: {e}")
    st.stop()

if not todas_abas:
    st.warning("Planilha sem conteúdo legível.")
    st.stop()

# Concatena todas as abas mantendo as colunas como vieram;
# o pandas preserva a ordem da primeira aba e adiciona novas ao final.
dfs = []
for aba, df in todas_abas.items():
    d2 = df.copy()
    d2["ABA"] = aba
    dfs.append(d2)

df_full = pd.concat(dfs, ignore_index=True, sort=False)

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
    except Exception:
        pass

with st.sidebar:
    st.header("Abas")

    opcoes_abas = ["(Todas)"] + list(todas_abas.keys())

    def _selecionar_todas():
        st.session_state["abas_sel"] = ["(Todas)"]

    def _limpar_selecao():
        st.session_state["abas_sel"] = []

    selecao_inicial = st.session_state.get("abas_sel", ["(Todas)"])

    abas_sel = st.multiselect(
        "Quais abas considerar?",
        options=opcoes_abas,
        default=selecao_inicial,
        key="abas_sel",
        help="Escolha uma ou várias abas específicas, ou selecione (Todas)."
    )

abas_especificas = [a for a in st.session_state.get("abas_sel", []) if a != "(Todas)"]

if "(Todas)" in st.session_state.get("abas_sel", []) or len(abas_especificas) == 0:
    abas_escolhidas = list(todas_abas.keys())
else:
    abas_escolhidas = abas_especificas

df_work = df_full[df_full["ABA"].isin(abas_escolhidas)].copy()

st.sidebar.header("Filtros")

def limpar_filtros():
    for key in list(st.session_state.keys()):
        if any(x in key.lower() for x in ["filtro", "valor", "selectbox"]):
            st.session_state.pop(key, None)
    st.session_state["reset_key"] = datetime.now().timestamp()
    st.rerun()

if st.sidebar.button("🧹 Limpar filtros"):
    limpar_filtros()

def select_valor_com_todos(rotulo: str, serie: pd.Series, key: str):
    valores_unicos = sorted(serie.dropna().astype(str).unique().tolist())
    opcoes = ["(Todos)"] + valores_unicos
    escolha = st.sidebar.selectbox(rotulo, opcoes, key=key)
    return None if escolha == "(Todos)" else escolha

# <<< NÃO alterei os filtros >>>
CAMPOS = [
    "DESCRIÇÃO DO ITEM RESUMIDA",
    "UNIDADES DE DESTINO",
    "N° OF",
    "QUANTIDADE ENTREGUE NA UNIDADE",
    "QUANTIDADE NA ATA E CONSUMO",
]

opcoes_presentes = [c for c in CAMPOS if c in df_work.columns]

if not opcoes_presentes:
    st.sidebar.warning("⚠️ Nenhuma das colunas de filtro iniciais existe na planilha.")
    df_filtrado = df_work.copy()
else:
    reset_key = st.session_state.get("reset_key", 0)

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
            key=f"valor5_{reset_key}"
        )
        if valor5 is not None:
            df_filtrado = df_filtrado[df_filtrado[filtro5] == valor5]

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

# >>> Exibe exatamente na ordem das colunas do DataFrame (como vieram da planilha)
st.dataframe(df_filtrado, use_container_width=True)

# --- Gráfico (inalterado) ---
def find_col(df, targets):
    cols_norm = {c: norm(c) for c in df.columns}
    for t in targets:
        tnorm = norm(t)
        for c, cn in cols_norm.items():
            if cn == tnorm or tnorm in cn:
                return c
    return None

dest = find_col(df_filtrado, ["UNIDADES DE DESTINO"])
if not dest:
    st.info("Não encontrei a coluna 'UNIDADE(S) DE DESTINO' para montar o gráfico.")
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

        fig.add_trace(go.Bar(
            x=agg[dest], y=agg[col_valor],
            name="VALOR TOTAL",
            text=[f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") for v in agg[col_valor]],
            textposition="outside",
            marker_color="#2E86DE"
        ))

        fig.add_trace(go.Bar(
            x=agg[dest], y=agg[col_unid],
            name="QUANTIDADE ENTREGUE NA UNIDADE",
            text=agg[col_unid],
            textposition="outside",
            marker_color="#E74C3C"
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
