import io
import unicodedata
import pandas as pd
import streamlit as st
import requests
from auth import require_authentication, AuthManager, init_session_state
from datetime import datetime
import plotly.graph_objects as go
from streamlit_plotly_events import plotly_events  # captura cliques no gráfico

st.set_page_config(page_title="BI - Entregas (GPCA)", page_icon="📦", layout="wide")

# Inicializa sessão e autenticação
init_session_state()
auth_manager = AuthManager(credentials_file="credentials.json")

if not require_authentication(auth_manager, logo_path="logo.svg"):
    st.stop()


# ---------------------------------------------------------------------
# FUNÇÃO: atualizar_cache_e_rerun
# ---------------------------------------------------------------------
def atualizar_cache_e_rerun():
    try:
        carregar_planilha_xlsx.clear()
    except Exception:
        st.cache_data.clear()

    st.session_state["reset_key"] = datetime.now().timestamp()
    st.rerun()


# ----------------- TOPO DA PÁGINA / BOTÕES -----------------
with st.container():
    col1, col2 = st.columns([4, 1.1])

    with col1:
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:10px;">
                <span style="font-size:25px;">👤</span>
                <h2 style="margin:0;color:#0C2856;">
                    SES-PE <span style="font-weight:300;">(sespe)</span>
                </h2>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:
        bcol1, bcol2 = st.columns([1, 1])
        with bcol1:
            if st.button("Atualizar", key="refresh_btn"):
                atualizar_cache_e_rerun()

        with bcol2:
            if st.button("Logout", key="logout_btn"):
                for key in list(st.session_state.keys()):
                    st.session_state.pop(key, None)
                st.session_state["authenticated"] = False
                st.rerun()

st.divider()

# Carrega CSS externo (se existir)
try:
    with open("style.css", "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    pass

# 🔵 CSS para botões
st.markdown(
    """
    <style>
    /* BOTÕES PRINCIPAIS */
    [data-testid="stAppViewContainer"] div.stButton > button {
        background-color: #0C2856 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-size: 15px !important;
        font-weight: 600;
        padding: 0 20px !important;
        height: 40px !important;
        white-space: nowrap !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
    }

    [data-testid="stAppViewContainer"] div.stButton > button:hover {
        background-color: #0F3A82 !important;
        color: white !important;
    }

    /* BOTÕES SIDEBAR */
    [data-testid="stSidebar"] div.stButton > button {
        background-color: #004080 !important;
        color: white !important;
        border-radius: 8px !important;
        border: none !important;
        font-weight: 600;
        padding: 0.5em 1em !important;
        width: 100% !important;
        transition: background-color 0.2s ease-in-out;
    }

    [data-testid="stSidebar"] div.stButton > button:hover {
        background-color: #0059b3 !important;
        color: white !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# ----------------- CONFIG DA PLANILHA -----------------
SHEET_ID = "1asY-XmwXtHa7Nb-hYpxSpjz1PeSU96I5"
XLSX_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"
HEADER_ROW_INDEX = 2  # linha do cabeçalho no Excel (0 = primeira linha)


def norm(s: str) -> str:
    s = str(s or "").lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("utf-8")
    s = s.replace("\n", " ").replace("\r", " ")
    s = " ".join(s.split())
    return s.strip()


# ---------------------------------------------------------------------
# FUNÇÃO: carregar_planilha_xlsx (TODAS AS ABAS, JUNTA EM UM DF)
# ---------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=True)
def carregar_planilha_xlsx(url: str, header_row_index: int) -> pd.DataFrame:
    resp = requests.get(url)
    resp.raise_for_status()
    with io.BytesIO(resp.content) as f:
        all_sheets = pd.read_excel(
            f,
            sheet_name=None,
            dtype=str,
            header=header_row_index
        )

    frames = []
    for nome_aba, df in all_sheets.items():
        if df is None or df.empty:
            continue

        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(how="all")
        if df.empty:
            continue

        df["ABA_ORIGEM"] = nome_aba
        frames.append(df.reset_index(drop=True))

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


# ----------------- CARREGAMENTO DA PLANILHA -----------------
try:
    df_full = carregar_planilha_xlsx(XLSX_URL, HEADER_ROW_INDEX)
except Exception as e:
    st.error(
        "❌ Não consegui ler a planilha. Abra o acesso "
        "(Qualquer pessoa com o link - Leitor).\n\n"
        f"Detalhes: {e}"
    )
    st.stop()

if df_full.empty:
    st.warning("Planilha sem conteúdo legível.")
    st.stop()

df_work = df_full.copy()


# ----------------- CABEÇALHO PRINCIPAL -----------------
col1, col2 = st.columns([4, 1])

with col1:
    st.title("📊 Acompanhamento das Aquisições de Mobiliário")
    data_atual = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
    st.markdown(
        f"""
        <div style="color:#666; font-size:0.95em; line-height:1.15;">
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


st.sidebar.header("Filtros")


def limpar_filtros():
    for key in list(st.session_state.keys()):
        if any(x in key.lower() for x in ["filtro", "valor", "selectbox"]):
            st.session_state.pop(key, None)

    # zera estados de drill dos dois gráficos
    st.session_state["nivel_pizza"] = "descricao"
    st.session_state["filtros_pizza"] = {}

    st.session_state["quad_nivel_idx"] = -1
    st.session_state["quad_rota_label"] = None
    st.session_state["quad_selecoes"] = []
    st.session_state["quad_msg_ultimo"] = False

    st.session_state["reset_key"] = datetime.now().timestamp()
    st.rerun()


if st.sidebar.button("🧹 Limpar filtros"):
    limpar_filtros()


def select_valor_com_todos(rotulo: str, serie: pd.Series, key: str):
    valores_unicos = sorted(serie.dropna().astype(str).unique().tolist())
    opcoes = ["(Todos)"] + valores_unicos
    escolha = st.sidebar.selectbox(rotulo, opcoes, key=key)
    return None if escolha == "(Todos)" else escolha


# ----------------- CONFIG DOS CAMPOS DOS FILTROS -----------------
CAMPOS = [
    "DESCRIÇÃO DO ITEM RESUMIDA",
    "QUANTIDADE NA ATA E CONSUMO",
    "QUANT. ENTREGUE NA UNIDADE",
    "UNIDADES DE DESTINO RESUMIDA",
    "PROJETO",
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


# =====================================================
#           CONSTANTES DE COLUNAS / NOMES
# =====================================================
NOME_ALVO_DESCRICAO = "DESCRIÇÃO DO ITEM RESUMIDA"
NOME_ALVO_QTD_ATA = "QUANTIDADE NA ATA E CONSUMO"
NOME_ALVO_QTD_ENT = "QUANT. ENTREGUE NA UNIDADE"
NOME_ALVO_UNIDADE = "UNIDADES DE DESTINO RESUMIDA"
NOME_ALVO_PROJETO = "PROJETO"
NOME_ALVO_DESCRICAO_DETALHADO = "DESCRIÇÃO DO ITEM DETALHADO"
NOME_ALVO_UNIDADE_DETALHADA = "UNIDADES DE DESTINO"
NOME_ALVO_RESPONSAVEL = "RESPONSÁVEL"

NOME_ALVO_VALOR_TOTAL = "VALOR TOTAL"
NOME_ALVO_STATUS = "STATUS DA ENTREGA"


def encontrar_coluna_real(df: pd.DataFrame, nome_alvo: str) -> str | None:
    alvo_norm = norm(nome_alvo)
    for c in df.columns:
        if norm(c) == alvo_norm:
            return c
    return None


COL_DESCRICAO_DETALHADO = encontrar_coluna_real(df_filtrado, NOME_ALVO_DESCRICAO_DETALHADO)
COL_QTD_ATA = encontrar_coluna_real(df_filtrado, NOME_ALVO_QTD_ATA)
COL_QTD_ENT = encontrar_coluna_real(df_filtrado, NOME_ALVO_QTD_ENT)
COL_UNIDADE = encontrar_coluna_real(df_filtrado, NOME_ALVO_UNIDADE)
COL_PROJETO = encontrar_coluna_real(df_filtrado, NOME_ALVO_PROJETO)
COL_DESCRICAO = encontrar_coluna_real(df_filtrado, NOME_ALVO_DESCRICAO)
COL_UNIDADE_DETALHADA = encontrar_coluna_real(df_filtrado, NOME_ALVO_UNIDADE_DETALHADA)
COL_RESPONSAVEL = encontrar_coluna_real(df_filtrado, NOME_ALVO_RESPONSAVEL)

COL_VALOR_TOTAL = encontrar_coluna_real(df_filtrado, NOME_ALVO_VALOR_TOTAL)
COL_STATUS = encontrar_coluna_real(df_filtrado, NOME_ALVO_STATUS)


# ---------------- HELPERS NUMÉRICOS / TEXTO ----------------
def _coerce_numeric_serie(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    s = s.replace(["-", "–", "", "nan", "None"], "0")
    s = s.str.replace(r"[^\d,.\-]", "", regex=True)
    s = s.str.replace(".", "", regex=False)
    s = s.str.replace(",", ".", regex=False)
    num = pd.to_numeric(s, errors="coerce").fillna(0)
    return num


def fmt_moeda(x):
    if pd.isna(x):
        return "-"
    return f"{float(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_inteiro(x):
    if pd.isna(x):
        return "-"
    try:
        return f"{int(float(x)):,}".replace(",", ".")
    except Exception:
        return str(x)


def wrap_text_html(text: str, width: int = 45) -> str:
    """
    Quebra o texto em linhas de no máximo `width` caracteres,
    usando <br> para o hover do Plotly.
    """
    text = str(text or "").strip()
    if not text:
        return ""

    words = text.split()
    lines = []
    current = []
    current_len = 0

    for w in words:
        wlen = len(w)
        # se passar do limite, quebra linha
        if current and current_len + wlen + 1 > width:
            lines.append(" ".join(current))
            current = [w]
            current_len = wlen
        else:
            current.append(w)
            current_len += wlen + 1

    if current:
        lines.append(" ".join(current))

    return "<br>".join(lines)


def preparar_dados_pizza(df: pd.DataFrame, coluna_chave: str) -> pd.DataFrame:
    base = df.copy()

    for col in [COL_QTD_ENT, COL_QTD_ATA, COL_VALOR_TOTAL]:
        if col and col in base.columns:
            base[col] = _coerce_numeric_serie(base[col])

    agg_dict = {}
    if COL_QTD_ENT and COL_QTD_ENT in base.columns:
        agg_dict[COL_QTD_ENT] = "sum"
    if COL_QTD_ATA and COL_QTD_ATA in base.columns:
        agg_dict[COL_QTD_ATA] = "sum"
    if COL_VALOR_TOTAL and COL_VALOR_TOTAL in base.columns:
        agg_dict[COL_VALOR_TOTAL] = "sum"
    if COL_STATUS and COL_STATUS in base.columns:
        agg_dict[COL_STATUS] = lambda x: ", ".join(
            sorted({str(v) for v in x if pd.notna(v)})
        )[:200]

    if agg_dict:
        grouped = (
            base.groupby(coluna_chave, dropna=True, as_index=False)
            .agg(agg_dict)
        )
    else:
        grouped = (
            base.groupby(coluna_chave, dropna=True, as_index=False)
            .size()
            .rename(columns={"size": "contagem"})
        )

    grouped = grouped.rename(columns={coluna_chave: "label"})

    if COL_QTD_ENT and COL_QTD_ENT in grouped.columns:
        grouped["qtd_entregue"] = grouped[COL_QTD_ENT]
    else:
        grouped["qtd_entregue"] = pd.NA

    if COL_QTD_ATA and COL_QTD_ATA in grouped.columns:
        grouped["qtd_ata"] = grouped[COL_QTD_ATA]
    else:
        grouped["qtd_ata"] = pd.NA

    if COL_VALOR_TOTAL and COL_VALOR_TOTAL in grouped.columns:
        grouped["valor_total"] = grouped[COL_VALOR_TOTAL]
    else:
        grouped["valor_total"] = pd.NA

    if COL_STATUS and COL_STATUS in grouped.columns:
        grouped["status"] = grouped[COL_STATUS]
    else:
        grouped["status"] = ""

    return grouped[["label", "qtd_entregue", "qtd_ata", "valor_total", "status"]]


def contar_unicos_col(df: pd.DataFrame, col: str | None) -> int:
    if not col or col not in df.columns:
        return 0
    serie = df[col].astype(str).str.strip().replace("", pd.NA).dropna()
    return serie.nunique()


# =====================================================
#   GRÁFICO 1 – DRILL-DOWN PRINCIPAL (DESATIVADO)
# =====================================================
if False:  # 🔴 gráfico antigo desativado
    st.subheader("📊 Descrição Itens")

    if "nivel_pizza" not in st.session_state:
        st.session_state["nivel_pizza"] = "descricao"
    if "filtros_pizza" not in st.session_state:
        st.session_state["filtros_pizza"] = {}

    nivel = st.session_state["nivel_pizza"]
    filtros_pizza = st.session_state["filtros_pizza"]

    if COL_DESCRICAO is None:
        st.info(
            "Para o gráfico em pizza, é necessário que exista uma coluna equivalente a "
            f"**{NOME_ALVO_DESCRICAO}** na planilha filtrada.\n\n"
            f"Colunas encontradas: {', '.join(map(str, df_filtrado.columns))}"
        )
    else:
        df_nivel = df_filtrado.copy()

        if "descricao" in filtros_pizza and COL_DESCRICAO in df_nivel.columns:
            df_nivel = df_nivel[df_nivel[COL_DESCRICAO] == filtros_pizza["descricao"]]

        if "quantidadeAta" in filtros_pizza and COL_QTD_ATA in df_nivel.columns:
            df_nivel = df_nivel[df_nivel[COL_QTD_ATA] == filtros_pizza["quantidadeAta"]]

        if "quantidadeEntregue" in filtros_pizza and COL_QTD_ENT in df_nivel.columns:
            df_nivel = df_nivel[df_nivel[COL_QTD_ENT] == filtros_pizza["quantidadeEntregue"]]

        if "unidade" in filtros_pizza and COL_UNIDADE in df_nivel.columns:
            df_nivel = df_nivel[df_nivel[COL_UNIDADE] == filtros_pizza["unidade"]]

        if "projeto" in filtros_pizza and COL_PROJETO in df_nivel.columns:
            df_nivel = df_nivel[df_nivel[COL_PROJETO] == filtros_pizza["projeto"]]

        if df_nivel.empty:
            st.info("Nenhum registro disponível para o nível atual do gráfico.")
        else:
            # ----- define coluna-chave e rótulo -----
            if nivel == "descricao":
                coluna_chave = COL_DESCRICAO
                titulo_nivel = "DESCRIÇÃO DO ITEM RESUMIDA"
            elif nivel == "unidade":
                coluna_chave = COL_UNIDADE
                titulo_nivel = "UNIDADES DE DESTINO RESUMIDA"
            elif nivel == "quantidadeAta":
                coluna_chave = COL_QTD_ATA
                titulo_nivel = "QUANTIDADE NA ATA E CONSUMO"
            elif nivel == "quantidadeEntregue":
                coluna_chave = COL_QTD_ENT
                titulo_nivel = "QUANTIDADE ENTREGUE NA UNIDADE"
            else:
                coluna_chave = COL_PROJETO
                titulo_nivel = "PROJETO"

            if coluna_chave not in df_nivel.columns:
                st.info(f"Não encontrei a coluna **{coluna_chave}** para este nível.")
            else:
                df_nivel = df_nivel[
                    df_nivel[coluna_chave].notna()
                    & (df_nivel[coluna_chave].astype(str).str.strip() != "")
                ]
                if df_nivel.empty:
                    st.info("Nenhum dado válido para o nível atual do gráfico.")
                else:
                    dados_pizza = preparar_dados_pizza(df_nivel, coluna_chave)

                    if dados_pizza.empty:
                        st.info("Nenhum dado disponível para o nível atual.")
                    else:
                        # mapa de detalhes para DESCRIÇÃO / UNIDADE
                        map_detalhe = {}
                        if (
                            nivel == "descricao"
                            and COL_DESCRICAO
                            and COL_DESCRICAO_DETALHADO
                            and COL_DESCRICAO in df_nivel.columns
                            and COL_DESCRICAO_DETALHADO in df_nivel.columns
                        ):
                            tmp = (
                                df_nivel[[COL_DESCRICAO, COL_DESCRICAO_DETALHADO]]
                                .dropna()
                                .astype(str)
                            )
                            map_detalhe = (
                                tmp.groupby(COL_DESCRICAO)[COL_DESCRICAO_DETALHADO]
                                .apply(lambda s: "; ".join(sorted(set(s)))[:500])
                                .to_dict()
                            )
                        elif (
                            nivel == "unidade"
                            and COL_UNIDADE
                            and COL_UNIDADE_DETALHADA
                            and COL_UNIDADE in df_nivel.columns
                            and COL_UNIDADE_DETALHADA in df_nivel.columns
                        ):
                            tmp = (
                                df_nivel[[COL_UNIDADE, COL_UNIDADE_DETALHADA]]
                                .dropna()
                                .astype(str)
                            )
                            map_detalhe = (
                                tmp.groupby(COL_UNIDADE)[COL_UNIDADE_DETALHADA]
                                .apply(lambda s: "; ".join(sorted(set(s)))[:500])
                                .to_dict()
                            )

                        # escolhe valores
                        if nivel == "quantidadeAta" and "qtd_ata" in dados_pizza.columns:
                            valores = dados_pizza["qtd_ata"]
                            legenda_valor = "Quantidade na ata e consumo"
                        elif nivel == "quantidadeEntregue" and "qtd_entregue" in dados_pizza.columns:
                            valores = dados_pizza["qtd_entregue"]
                            legenda_valor = "Quantidade entregue na unidade"
                        else:
                            if "valor_total" in dados_pizza.columns and dados_pizza["valor_total"].notna().any():
                                valores = dados_pizza["valor_total"]
                                legenda_valor = "Valor total"
                            elif "qtd_entregue" in dados_pizza.columns and dados_pizza["qtd_entregue"].notna().any():
                                valores = dados_pizza["qtd_entregue"]
                                legenda_valor = "Quantidade entregue"
                            elif "qtd_ata" in dados_pizza.columns and dados_pizza["qtd_ata"].notna().any():
                                valores = dados_pizza["qtd_ata"]
                                legenda_valor = "Quantidade na ata e consumo"
                            else:
                                valores = pd.Series([1] * len(dados_pizza))
                                legenda_valor = "Contagem"

                        valores = pd.to_numeric(valores, errors="coerce").fillna(0)

                        if len(valores) == 0 or valores.sum() <= 0:
                            st.info("A soma dos valores para este nível é zero. Verifique os dados da planilha.")
                        else:
                            # ---------- HOVER GRÁFICO 1 ----------
                            hovertext = []
                            for _, row in dados_pizza.iterrows():
                                label = row["label"]
                                detalhe = ""
                                if map_detalhe:
                                    detalhe = map_detalhe.get(label, "")

                                linha = f"<b>{label}</b><br>"
                                # comentário de nível
                                linha += f"<span style='font-size:0.75em;'>Nível: {titulo_nivel}</span><br>"

                                if detalhe and isinstance(detalhe, str):
                                    detalhe_wrapped = wrap_text_html(detalhe, width=70)
                                    linha += f"<span style='font-size:0.75em;'>{detalhe_wrapped}</span><br>"

                                linha += (
                                    f"Qtd Entregue: {fmt_inteiro(row['qtd_entregue'])}<br>"
                                    f"Qtd Ata/Consumo: {fmt_inteiro(row['qtd_ata'])}<br>"
                                    f"Valor Total: R$ {fmt_moeda(row['valor_total'])}<br>"
                                    f"Status: {row['status'] or ''}"
                                )

                                hovertext.append(linha)

                            fig = go.Figure(
                                data=[
                                    go.Pie(
                                        labels=dados_pizza["label"],
                                        values=valores,
                                        hovertext=hovertext,
                                        hoverinfo="text",
                                        textposition="inside",
                                        texttemplate="%{label}",
                                    )
                                ]
                            )

                            fig.update_layout(
                                title=f"Nível atual: {titulo_nivel} ({legenda_valor})",
                                margin=dict(t=50, b=10, l=10, r=10),
                                legend_title_text=titulo_nivel,
                            )

                            col_btn_voltar, _ = st.columns([1, 3])
                            with col_btn_voltar:
                                # só mostra botão se NÃO estiver no topo (descricao)
                                if nivel != "descricao":
                                    if st.button("⬅️ Voltar nível"):
                                        if nivel == "unidade":
                                            st.session_state["nivel_pizza"] = "descricao"
                                            st.session_state["filtros_pizza"].pop("unidade", None)

                                        elif nivel == "quantidadeAta":
                                            st.session_state["nivel_pizza"] = "unidade"
                                            st.session_state["filtros_pizza"].pop("quantidadeAta", None)

                                        elif nivel == "quantidadeEntregue":
                                            st.session_state["nivel_pizza"] = "quantidadeAta"
                                            st.session_state["filtros_pizza"].pop("quantidadeEntregue", None)

                                        elif nivel == "projeto":
                                            st.session_state["nivel_pizza"] = "quantidadeEntregue"
                                            st.session_state["filtros_pizza"].pop("projeto", None)

                                        st.rerun()

                            selected_points = plotly_events(
                                fig,
                                click_event=True,
                                hover_event=False,
                                key=f"pie_{nivel}_{st.session_state.get('reset_key', 0)}",
                                override_height=500,
                                override_width="100%",
                            )

                            if selected_points:
                                idx = selected_points[0].get("pointNumber", selected_points[0].get("pointIndex"))
                                if isinstance(idx, int) and 0 <= idx < len(dados_pizza):
                                    label_clicked = dados_pizza.iloc[idx]["label"]

                                    # ordem: descricao -> unidade -> quantidadeAta -> quantidadeEntregue -> projeto
                                    if nivel == "descricao":
                                        st.session_state["nivel_pizza"] = "unidade"
                                        st.session_state["filtros_pizza"]["descricao"] = label_clicked

                                    elif nivel == "unidade":
                                        st.session_state["nivel_pizza"] = "quantidadeAta"
                                        st.session_state["filtros_pizza"]["unidade"] = label_clicked

                                    elif nivel == "quantidadeAta":
                                        st.session_state["nivel_pizza"] = "quantidadeEntregue"
                                        st.session_state["filtros_pizza"]["quantidadeAta"] = label_clicked

                                    elif nivel == "quantidadeEntregue":
                                        st.session_state["nivel_pizza"] = "projeto"
                                        st.session_state["filtros_pizza"]["quantidadeEntregue"] = label_clicked

                                    elif nivel == "projeto":
                                        st.info("Você já está no último nível deste caminho.")
                                        st.session_state["filtros_pizza"]["projeto"] = label_clicked

                                    st.rerun()


# =====================================================
#   GRÁFICO 2 – QUADRANTES / ROTAS DIFERENTES
# =====================================================

st.markdown("---")
st.subheader("📊 Visões por eixo (quadrantes)")

# estado do gráfico 2
if "quad_nivel_idx" not in st.session_state:
    st.session_state["quad_nivel_idx"] = -1   # -1 = menu
if "quad_rota_label" not in st.session_state:
    st.session_state["quad_rota_label"] = None
if "quad_selecoes" not in st.session_state:
    st.session_state["quad_selecoes"] = []    # lista de {dim, label}
if "quad_msg_ultimo" not in st.session_state:
    st.session_state["quad_msg_ultimo"] = False

quad_nivel_idx = st.session_state["quad_nivel_idx"]
quad_rota_label = st.session_state["quad_rota_label"]
quad_selecoes = st.session_state["quad_selecoes"]
quad_msg_ultimo = st.session_state["quad_msg_ultimo"]

QUADRANTE_LABELS = [
    "Status da entrega",
    "Quantidade de itens",
    "Unidade de destino",
    "Responsável",
]

ROTA_CONFIG = {
    "Status da entrega":   ["status", "descricao", "unidade"],
    "Quantidade de itens": ["descricao", "unidade"],
    "Unidade de destino":  ["unidade", "descricao", "status"],
    "Responsável":         ["responsavel", "descricao", "unidade", "status"],
}


def coluna_para_dim(dim: str) -> str | None:
    if dim == "descricao":
        return COL_DESCRICAO
    if dim == "unidade":
        return COL_UNIDADE
    if dim == "status":
        return COL_STATUS
    if dim == "responsavel":
        return COL_RESPONSAVEL
    return None


def titulo_para_dim(dim: str) -> str:
    if dim == "descricao":
        return "DESCRIÇÃO DO ITEM RESUMIDA"
    if dim == "unidade":
        return "UNIDADES DE DESTINO RESUMIDA"
    if dim == "status":
        return "STATUS DA ENTREGA"
    if dim == "responsavel":
        return "RESPONSÁVEL"
    return dim


# --------- Menu dos quadrantes ----------
if quad_nivel_idx == -1 or quad_rota_label not in ROTA_CONFIG:
    st.session_state["quad_selecoes"] = []
    st.session_state["quad_msg_ultimo"] = False

    qtd_status = contar_unicos_col(df_filtrado, COL_STATUS)
    qtd_desc = contar_unicos_col(df_filtrado, COL_DESCRICAO)
    qtd_unidade = contar_unicos_col(df_filtrado, COL_UNIDADE)
    qtd_resp = contar_unicos_col(df_filtrado, COL_RESPONSAVEL)

    df_menu = pd.DataFrame({
        "label": QUADRANTE_LABELS,
        "valor": [1, 1, 1, 1],
        "qtd_unicos": [qtd_status, qtd_desc, qtd_unidade, qtd_resp],
    })

    # ---------- HOVER G2 – MENU (eixo + nível) ----------
    hover_menu = []
    for _, row in df_menu.iterrows():
        lbl = row["label"]
        qtd = row["qtd_unicos"]
        hover_menu.append(
            f"<b>{lbl}</b><br>"
            f"Eixo: {lbl} | Nível: seleção do eixo<br>"
            f"Itens únicos: {qtd}"
        )

    fig_q = go.Figure(
        data=[
            go.Pie(
                labels=df_menu["label"],
                values=df_menu["valor"],
                hovertext=hover_menu,
                hoverinfo="text",
                textposition="inside",
                texttemplate="%{label}",
                marker=dict(colors=["#004c6d", "#006d8f", "#008fa3", "#00b3a4"]),
            )
        ]
    )
    fig_q.update_layout(
        title="Escolha um eixo para detalhar",
        margin=dict(t=50, b=10, l=10, r=10),
    )

    selected_quad = plotly_events(
        fig_q,
        click_event=True,
        hover_event=False,
        key=f"pie_quadrantes_{st.session_state.get('reset_key', 0)}",
        override_height=450,
        override_width="100%",
    )

    if selected_quad:
        idx = selected_quad[0].get("pointNumber", selected_quad[0].get("pointIndex"))
        if isinstance(idx, int) and 0 <= idx < len(df_menu):
            label_clicked = df_menu.iloc[idx]["label"]
            st.session_state["quad_rota_label"] = label_clicked
            st.session_state["quad_nivel_idx"] = 0
            st.session_state["quad_selecoes"] = []
            st.session_state["quad_msg_ultimo"] = False
            st.rerun()

else:
    rota = ROTA_CONFIG[quad_rota_label]
    dim_atual = rota[quad_nivel_idx]
    col_atual = coluna_para_dim(dim_atual)
    titulo_dim = titulo_para_dim(dim_atual)

    # 🔹 Botão de voltar SEMPRE visível quando estamos dentro de um eixo
    col_btn_voltar2, _ = st.columns([1, 3])
    with col_btn_voltar2:
        if st.button("⬅️ Voltar nível (quadrantes)"):
            if quad_nivel_idx == 0:
                # volta para o menu dos quadrantes
                st.session_state["quad_nivel_idx"] = -1
                st.session_state["quad_rota_label"] = None
                st.session_state["quad_selecoes"] = []
                st.session_state["quad_msg_ultimo"] = False
            else:
                # sobe um nível na rota e remove última seleção
                if st.session_state["quad_selecoes"]:
                    st.session_state["quad_selecoes"].pop()
                st.session_state["quad_nivel_idx"] = quad_nivel_idx - 1
                st.session_state["quad_msg_ultimo"] = False
            st.rerun()

    df_quad = df_filtrado.copy()

    # aplica seleções anteriores (até nível atual - 1)
    if quad_selecoes:
        for sel in quad_selecoes:
            col_sel = coluna_para_dim(sel["dim"])
            if col_sel and col_sel in df_quad.columns:
                df_quad = df_quad[df_quad[col_sel] == sel["label"]]

    if not col_atual or col_atual not in df_quad.columns:
        st.info(f"Não encontrei coluna para a dimensão **{titulo_dim}**.")
    elif df_quad.empty:
        st.info("Nenhum dado disponível para os filtros atuais.")
    else:
        df_quad = df_quad[
            df_quad[col_atual].notna()
            & (df_quad[col_atual].astype(str).str.strip() != "")
        ]
        if df_quad.empty:
            st.info("Nenhum dado válido para este nível.")
        else:
            dados_pizza2 = preparar_dados_pizza(df_quad, col_atual)
            if dados_pizza2.empty:
                st.info("Nenhum dado disponível para este nível.")
            else:
                map_detalhe2 = {}
                if (
                    dim_atual == "descricao"
                    and COL_DESCRICAO
                    and COL_DESCRICAO_DETALHADO
                    and COL_DESCRICAO in df_quad.columns
                    and COL_DESCRICAO_DETALHADO in df_quad.columns
                ):
                    tmp = (
                        df_quad[[COL_DESCRICAO, COL_DESCRICAO_DETALHADO]]
                        .dropna()
                        .astype(str)
                    )
                    map_detalhe2 = (
                        tmp.groupby(COL_DESCRICAO)[COL_DESCRICAO_DETALHADO]
                        .apply(lambda s: "; ".join(sorted(set(s)))[:500])
                        .to_dict()
                    )
                elif (
                    dim_atual == "unidade"
                    and COL_UNIDADE
                    and COL_UNIDADE_DETALHADA
                    and COL_UNIDADE in df_quad.columns
                    and COL_UNIDADE_DETALHADA in df_quad.columns
                ):
                    tmp = (
                        df_quad[[COL_UNIDADE, COL_UNIDADE_DETALHADA]]
                        .dropna()
                        .astype(str)
                    )
                    map_detalhe2 = (
                        tmp.groupby(COL_UNIDADE)[COL_UNIDADE_DETALHADA]
                        .apply(lambda s: "; ".join(sorted(set(s)))[:500])
                        .to_dict()
                    )

                if "valor_total" in dados_pizza2.columns and dados_pizza2["valor_total"].notna().any():
                    valores2 = dados_pizza2["valor_total"]
                    legenda_valor2 = "Valor total"
                elif "qtd_entregue" in dados_pizza2.columns and dados_pizza2["qtd_entregue"].notna().any():
                    valores2 = dados_pizza2["qtd_entregue"]
                    legenda_valor2 = "Quantidade entregue"
                elif "qtd_ata" in dados_pizza2.columns and dados_pizza2["qtd_ata"].notna().any():
                    valores2 = dados_pizza2["qtd_ata"]
                    legenda_valor2 = "Quantidade na ata e consumo"
                else:
                    valores2 = pd.Series([1] * len(dados_pizza2))
                    legenda_valor2 = "Contagem"

                valores2 = pd.to_numeric(valores2, errors="coerce").fillna(0)
                if len(valores2) == 0 or valores2.sum() <= 0:
                    st.info("A soma dos valores para este nível é zero.")
                else:
                    # ---------- HOVER G2 – NÍVEIS INTERNOS (quadrante + nível) ----------
                    hovertext2 = []
                    for _, row in dados_pizza2.iterrows():
                        label = row["label"]
                        detalhe = ""
                        if map_detalhe2:
                            detalhe = map_detalhe2.get(label, "")

                        linha = f"<b>{label}</b><br>"
                        linha += (
                            f"<span style='font-size:0.75em;'>"
                            f"Eixo: {quad_rota_label} | Nível: {titulo_dim}"
                            f"</span><br>"
                        )

                        # exemplo extra: eixo STATUS no 1º nível → qtd de itens únicos
                        if quad_rota_label == "Status da entrega" and dim_atual == "status":
                            subset = df_quad[df_quad[col_atual] == label]
                            qtd_itens_unicos = contar_unicos_col(subset, COL_DESCRICAO)
                            linha += f"Itens únicos (descrição): {qtd_itens_unicos}<br>"

                        if detalhe and isinstance(detalhe, str):
                            detalhe_wrapped = wrap_text_html(detalhe, width=70)
                            linha += f"<span style='font-size:0.75em;'>{detalhe_wrapped}</span><br>"

                        linha += (
                            f"Qtd Entregue: {fmt_inteiro(row['qtd_entregue'])}<br>"
                            f"Qtd Ata/Consumo: {fmt_inteiro(row['qtd_ata'])}<br>"
                            f"Valor Total: R$ {fmt_moeda(row['valor_total'])}<br>"
                            f"Status: {row['status'] or ''}"
                        )
                        hovertext2.append(linha)

                    fig2 = go.Figure(
                        data=[
                            go.Pie(
                                labels=dados_pizza2["label"],
                                values=valores2,
                                hovertext=hovertext2,
                                hoverinfo="text",
                                textposition="inside",
                                texttemplate="%{label}",
                            )
                        ]
                    )

                    caminho2 = [f"Eixo: {quad_rota_label}"]
                    for sel in quad_selecoes:
                        caminho2.append(f"{titulo_para_dim(sel['dim'])}: {sel['label']}")
                    if caminho2:
                        st.caption(" ➜ ".join(caminho2))

                    fig2.update_layout(
                        title=f"Nível atual ({quad_rota_label}): {titulo_dim} ({legenda_valor2})",
                        margin=dict(t=50, b=10, l=10, r=10),
                    )

                    # mensagem fixa se estiver no último nível
                    if quad_nivel_idx == len(rota) - 1 and quad_msg_ultimo:
                        st.info("Você já está no último nível deste eixo.")

                    selected_points2 = plotly_events(
                        fig2,
                        click_event=True,
                        hover_event=False,
                        key=f"pie_quad_{quad_rota_label}_{quad_nivel_idx}_{st.session_state.get('reset_key', 0)}",
                        override_height=500,
                        override_width="100%",
                    )

                    if selected_points2:
                        idx2 = selected_points2[0].get("pointNumber", selected_points2[0].get("pointIndex"))
                        if isinstance(idx2, int) and 0 <= idx2 < len(dados_pizza2):
                            label_clicked2 = dados_pizza2.iloc[idx2]["label"]

                            if quad_nivel_idx < len(rota) - 1:
                                # adiciona seleção e desce 1 nível
                                st.session_state["quad_selecoes"].append(
                                    {"dim": dim_atual, "label": label_clicked2}
                                )
                                st.session_state["quad_nivel_idx"] = quad_nivel_idx + 1
                                st.session_state["quad_msg_ultimo"] = False
                            else:
                                # último nível: só marca flag para mostrar mensagem
                                st.session_state["quad_msg_ultimo"] = True

                            st.rerun()


# ----------------- TABELA FILTRADA -----------------
st.subheader("Dados Filtrados")
st.caption(f"{len(df_filtrado)} registros exibidos após os filtros aplicados.")

st.download_button(
    "⬇️ Exportar Dados",
    data=df_filtrado.to_csv(index=False).encode("utf-8"),
    file_name="emendas_filtrado.csv",
    mime="text/csv",
)

st.dataframe(df_filtrado, use_container_width=True)
