import bcrypt
import streamlit as st
from typing import Optional, Dict
import json
from pathlib import Path
import base64

class AuthManager:
    """Gerenciador de autenticação com bcrypt"""

    def __init__(self, credentials_file: str = "credentials.json"):
        self.credentials_file = Path(credentials_file)
        self.users = self._load_credentials()

    def _load_credentials(self) -> Dict:
        """Carrega credenciais do arquivo JSON ou Streamlit Secrets"""
        try:
            if hasattr(st, "secrets") and "credentials" in st.secrets:
                credentials_section = st.secrets["credentials"]

                creds = {}
                for username in credentials_section:
                    user_data = credentials_section[username]
                    creds[username] = {
                        "password": str(user_data["password"]),
                        "name": str(user_data["name"]),
                        "role": str(user_data["role"]),
                    }

                if creds:
                    return creds
        except Exception:
            pass

        if self.credentials_file.exists():
            try:
                with open(self.credentials_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        return {}

    def _save_credentials(self):
        """Salva credenciais no arquivo JSON"""
        with open(self.credentials_file, "w", encoding="utf-8") as f:
            json.dump(self.users, f, indent=4, ensure_ascii=False)

    def hash_password(self, password: str) -> str:
        """Gera hash bcrypt da senha"""
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def verify_password(self, password: str, hashed: str) -> bool:
        """Verifica se a senha corresponde ao hash"""
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False

    def authenticate(self, username: str, password: str) -> bool:
        """Autentica usuário"""
        if username not in self.users:
            return False

        stored_hash = self.users[username]["password"]
        return self.verify_password(password, stored_hash)

    def add_user(self, username: str, password: str, name: str, role: str = "user"):
        """Adiciona novo usuário ao sistema"""
        if username in self.users:
            return False

        self.users[username] = {
            "password": self.hash_password(password),
            "name": name,
            "role": role,
        }
        self._save_credentials()
        return True

    def get_user_info(self, username: str) -> Optional[Dict]:
        """Retorna informações do usuário (sem a senha)"""
        if username not in self.users:
            return None

        user_info = self.users[username].copy()
        user_info.pop("password", None)
        return user_info

def init_session_state():
    """Inicializa variáveis de sessão"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "username" not in st.session_state:
        st.session_state.username = None
    if "user_info" not in st.session_state:
        st.session_state.user_info = None

def logout():
    """Realiza logout do usuário"""
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.user_info = None
    st.rerun()

def get_image_base64(image_path: Path) -> str:
    """Converte imagem para base64 para embedding no HTML"""
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except Exception:
        return ""

def login_form(
    auth_manager: AuthManager,
    logo_path: str = "logo.svg",
    css_path: str = "auth_style.css"
):
    """Renderiza formulário de login minimalista com suporte a logo SVG e CSS externo"""

    # === Carrega CSS externo ===
    try:
        with open(css_path, "r", encoding="utf-8") as f:
            css_content = f.read()
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning("⚠️ Arquivo CSS não encontrado. O layout pode ficar diferente do esperado.")

    # --- Carrega logo ---
    logo_html = ""
    logo_file = Path(logo_path)

    if logo_file.exists():
        if logo_file.suffix.lower() == ".svg":
            with open(logo_file, "r", encoding="utf-8") as f:
                svg_content = f.read()
                logo_html = f'<div class="logo-section">{svg_content}</div>'
        else:
            logo_b64 = get_image_base64(logo_file)
            logo_html = f"""
            <div class="logo-section">
                <img src="data:image/png;base64,{logo_b64}" alt="Logo" />
            </div>
            """
    else:
        logo_html = "<h2 style='text-align:center;'>Secretaria da Saúde - PE</h2>"

    # Layout centralizado
    col1, col2, col3 = st.columns([1, 3, 1])

    with col2:
        st.markdown('<div class="login-wrapper">', unsafe_allow_html=True)

        # Logo centralizada
        st.markdown(logo_html, unsafe_allow_html=True)

        # Formulário de login
        with st.form("login_form"):
            username = st.text_input(
                "Usuário", placeholder="Digite seu usuário", key="login_username"
            )
            password = st.text_input(
                "Senha", type="password", placeholder="Digite sua senha", key="login_password"
            )
            submit = st.form_submit_button("Entrar", use_container_width=True)

            if submit:
                if not username or not password:
                    st.error("❌ Por favor, preencha todos os campos")
                    return False

                if auth_manager.authenticate(username, password):
                    st.session_state.authenticated = True
                    st.session_state.username = username
                    st.session_state.user_info = auth_manager.get_user_info(username)
                    st.success("✅ Login realizado com sucesso!")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("❌ Usuário ou senha incorretos")
                    return False

        # Expander de ajuda
        with st.expander("Precisa de ajuda?"):
            st.markdown(
                """
                *Primeiro acesso:*  
                Entre em contato com o administrador do sistema.
                
                *Esqueceu a senha:*  
                Contate o suporte técnico da Secretaria.
                
                *Suporte:*  
                📧 suporte@saude.pe.gov.br  
                📞 (81) 3181-XXXX
                """
            )

        # Rodapé
        st.markdown(
            """
            <div class="login-footer">
                <p>🔒 Conexão segura • © 2025 Secretaria da Saúde - Governo de Pernambuco</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("</div>", unsafe_allow_html=True)

    return False

def require_authentication(auth_manager: AuthManager, logo_path: str = "logo.svg"):
    """Decorator/wrapper para proteger páginas"""
    init_session_state()

    if not st.session_state.authenticated:
        login_form(auth_manager, logo_path)
        st.stop()

    return True