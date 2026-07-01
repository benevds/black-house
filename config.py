"""
Configurações centrais do sistema Arena Marina.
Carrega variáveis de ambiente (.env) e define as regras de negócio fixas
usadas tanto pelo banco de dados quanto pelo agente de IA.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Credenciais e configuração da IA ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
_base_url = os.getenv("OPENAI_BASE_URL", "").strip()
OPENAI_BASE_URL = _base_url or None
# Dica: para usar a Groq (gratuita e rápida), no .env defina:
# OPENAI_BASE_URL=https://api.groq.com/openai/v1
# OPENAI_MODEL=llama-3.3-70b-versatile
# OPENAI_API_KEY=<sua_chave_groq>

# --- Banco de dados ---
DB_PATH = os.getenv("DB_PATH", "arena_marina.db")

# --- Regras de negócio da Arena Marina (fixas pelo edital do projeto) ---
NOME_ARENA = "Arena Marina"
QUADRAS = [1, 2, 3, 4]
HORA_ABERTURA = 8   # 08:00
HORA_FECHAMENTO = 22  # 22:00
HORARIOS = [f"{h:02d}:00" for h in range(HORA_ABERTURA, HORA_FECHAMENTO)]  # 08:00 ... 21:00
PRECO_HORA = 40.00

# --- Parâmetros do agente ---
MAX_ITERACOES_AGENTE = 6          # trava de segurança contra loop infinito de tool calls
MAX_HISTORICO_MENSAGENS = 16      # quantas mensagens passadas entram no contexto do LLM
