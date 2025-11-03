import streamlit as st
import bcrypt
import json
from typing import Optional, Dict
from pathlib import Path
import base64

# ===============================
# ---------  AUTH CORE  ---------
# ===============================

class AuthManager:
    """
    Gerenciador de autenticação com suporte a:
      - st.secrets (dois formatos)
      - fallback para credentials.json
      - senha em texto puro OU hash bcrypt
    """

    def __init__(self, credentials_file: str = "credentials.json"):
        self.credentials_file = Path(credentials_file)
        self.users: Dict[str, Dict] = self._load_credentials()

    # ---------- utils ----------

    @staticmethod
    def _is_bcrypt(value: str) -> bool:
        return isinstance(value, str) and value.startswith(("$2a$", "$2b$", "$2y$"))

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def _verify(password: str, stored: str) -> bool:
        """
        Se 'stored' for hash bcrypt → verifica com bcrypt.
        Caso contrário → comparação texto puro (útil p/ segredos simples).
        """
        try:
            if AuthManager._is_bcrypt(stored):
                return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
            return password == stored
        except Exception:
            return False

    # ---------- load/save ----------

    def _load_from_secrets(self) -> Dict[str, Dict]:
        """
        Suporta DOIS formatos:

        1) [credentials]
           usuario="sespe"
           senha="texto-ou-bcrypt"
           nome="Nome"
           role="admin"

        2) [credentials.sespe]
           password="texto-ou-bcrypt"
           name="Nome"
           role="admin"
        """
        creds: Dict[str, Dict] = {}
        if not hasattr(st, "secrets"):
            return creds

        if "credentials" not in st.secrets:
            return creds

        section = st.secrets["credentials"]

        # Caso 1: formato simples (usuario/senha direto dentro de [credentials])
        if (
            "usuario" in section
            and "senha" in section
            and isinstance(section.get("usuario"), str)
        ):
            username = str(section["usuario"]).strip()
            stored = str(section["senha"])
            name = str(section.get("nome") or section.get("name") or username)
            role = str(section.get("role") or "user")
            creds[username] = {"password": stored, "name": name, "role": role}
            return creds

        # Caso 2: formato por-usuário: [credentials.<username>]
        # section é um mapeamento de username -> dict
        try:
            for username, user_data in section.items():
                # Ignora chaves não-dict
                if not isinstance(user_data, (dict,)):
                    continue
                stored = str(user_data.get("password", ""))
                name = str(user_data.get("name") or user_data.get("nome") or username)
                role = str(user_data.get("role") or "user")
                if stored:
                    creds[str(username)] = {
                        "password": stored,
                        "name": name,
                        "role": role,
                    }
        except Exception:
            pass

        return creds

    def _load_from_json(self) -> Dict[str, Dict]:
        """
        Estrutura esperada em credentials.json:
        {
          "sespe": { "password": "$2b$12$...", "name": "Usuário", "role": "admin" }
        }
        """
        if not self.credentials_file.exists():
            return {}
        try:
            with open(self.credentials_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # garante strings
                for u, d in list(data.items()):
                    d["password"] = str(d.get("password", ""))
                    d["name"] = str(d.get("name", u))
                    d["role"] = str(d.get("role", "user"))
                return data
        except Exception:
            return {}

    def _load_credentials(self) -> Dict[str, Dict]:
        creds = self._load_from_secrets()
        if creds:
            return creds
        return self._load_from_json()

    def _save_credentials_json(self):
        """Salva no JSON (não salva em secrets)."""
        with open(self.credentials_file, "w", encoding="utf-8") as f:
            json.dump(self.users, f, indent=2, ensure_ascii=False)

    # ---------- API pública ----------

    def authenticate(self, username: str, password: str) -> bool:
        user = self.users.get(username)
        if not user:
            return False
        return self._verify(password, user.get("password", ""))

    def add_user(self, username: str, password: str, name: str, role: str = "user") -> bool:
        """
        Adiciona apenas no JSON (não tem como gravar nos secrets pelo app).
        """
        if username in self.users:
            return False
        self.users[username] = {
            "password": self._hash_password(password),
            "name": name,
            "role": role,
        }
        self._save_credentials_json()
        return True

    def get_user_info(self, username: str) -> Optional[Dict]:
        user = self.users.get(username)
        if not user:
            return None
        info = dict(user)
        info.pop("password", None)
        info["username"] = username
        return info


# ===============================
# ------  UI / SESSION  --------
# ===============================

def init_session_state():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "username" not in st.session_state:
        st.session_state.username = None
    if "user_info" not in st.session_state:
        st.session_state.user_info = None

def logout():
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.user_info = None
    st.rerun()

def _read_file_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None

def _img_to_base64(path: Path) -> str:
    try:
        return base64.b64encode(path.read_bytes()).decode()
    except Exception:
        return ""

DEFAULT_INLINE_CSS = """
/* Estilo mínimo para login */
.login-wrapper {max-width: 420px; margin: 2rem auto; padding: 1.25rem 1.25rem 0.75rem; border-radius: 1rem; border: 1px solid #e6e6e6;}
.logo-section {text-align:center; margin-bottom: 1rem;}
.logo-section img, .logo-section svg {max-width: 180px; height: auto;}
.login-footer {text-align:center; color:#6b7280; font-size:0.85rem; margin-top: 0.75rem;}
"""

def login_form(auth: AuthManager, logo_path: str = "logo.svg", css_path: str = "auth_style.css"):
    # CSS (externo se existir, senão um padrão leve)
    css = _read_file_text(Path(css_path)) or DEFAULT_INLINE_CSS
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    # Logo (svg ou png/jpg) — se não houver, usa texto
    logo_html = "<h2 style='text-align:center;'>Secretaria da Saúde - PE</h2>"
    lp = Path(logo_path)
    if lp.exists():
        if lp.suffix.lower() == ".svg":
            svg = _read_file_text(lp)
            if svg:
                logo_html = f'<div class="logo-section">{svg}</div>'
        else:
            b64 = _img_to_base64(lp)
            if b64:
                mime = "png" if lp.suffix.lower() == ".png" else "jpeg"
                logo_html = f'<div class="logo-section"><img src="data:image/{mime};base64,{b64}" alt="Logo"/></div>'

    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown('<div class="login-wrapper">', unsafe_allow_html=True)
        st.markdown(logo_html, unsafe_allow_html=True)

        with st.form("login_form"):
            username = st.text_input("Usuário", placeholder="Digite seu usuário")
            password = st.text_input("Senha", type="password", placeholder="Digite sua senha")
            submit = st.form_submit_button("Entrar", use_container_width=True)

        if submit:
            if not username or not password:
                st.error("❌ Por favor, preencha todos os campos.")
            elif auth.authenticate(username, password):
                st.session_state.authenticated = True
                st.session_state.username = username
                st.session_state.user_info = auth.get_user_info(username)
                st.success("✅ Login realizado com sucesso!")
                st.rerun()
            else:
                st.error("❌ Usuário ou senha incorretos.")

        with st.expander("Precisa de ajuda?"):
            st.markdown(
                """
                **Primeiro acesso**: contate o administrador do sistema.  
                **Esqueceu a senha**: suporte técnico da Secretaria.  
                **Suporte**: suporte@saude.pe.gov.br | (81) 3181-XXXX
                """
            )
        st.markdown('<div class="login-footer">🔒 Conexão segura • © 2025 Secretaria da Saúde - PE</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

def require_authentication(auth: AuthManager, logo_path: str = "logo.svg", css_path: str = "auth_style.css"):
    init_session_state()
    if not st.session_state.authenticated:
        login_form(auth, logo_path=logo_path, css_path=css_path)
        st.stop()
    return True


# ===============================
# ---------  APP MAIN  ---------
# ===============================

def main():
    st.set_page_config(page_title="BI Mobiliário", page_icon="🏢", layout="wide")

    # Instancia o AuthManager (lê primeiro de st.secrets; se não houver, tenta credentials.json)
    auth = AuthManager(credentials_file="credentials.json")

    # Protege a aplicação
    require_authentication(auth, logo_path="logo.svg", css_path="auth_style.css")

    # --- Conteúdo da aplicação autenticada ---
    user = st.session_state.get("user_info", {}) or {}
    col_left, col_right = st.columns([1, 5])
    with col_left:
        st.write(f"👤 **Usuário:** {user.get('username', 'desconhecido')}")
        st.write(f"🧭 **Perfil:** {user.get('role', 'user')}")
        if st.button("Sair", type="secondary"):
            logout()
    with col_right:
        st.title("Dashboard - BI Mobiliário")
        st.write("Seu conteúdo privado começa aqui.")

    # Exemplo de página…
    st.markdown("---")
    st.write("Coloque aqui suas páginas e componentes do Streamlit.")

if __name__ == "__main__":
    main()
