"""
Camada de acesso ao banco de dados SQLite da Arena Marina.

Responsabilidades:
- Criar o schema (agendamentos + histórico de conversas)
- Consultar disponibilidade real de quadras (fonte única de verdade)
- Criar e cancelar agendamentos, com proteção contra overbooking
- Persistir o histórico de conversa por telefone (memória do agente)
"""
import sqlite3
from contextlib import contextmanager

from config import DB_PATH, QUADRAS, HORARIOS, PRECO_HORA, MAX_HISTORICO_MENSAGENS


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Cria as tabelas do banco caso ainda não existam. Idempotente."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agendamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quadra INTEGER NOT NULL,
                data TEXT NOT NULL,
                horario TEXT NOT NULL,
                cliente_nome TEXT NOT NULL,
                cliente_telefone TEXT NOT NULL,
                valor REAL NOT NULL DEFAULT 40.00,
                status TEXT NOT NULL DEFAULT 'confirmado',
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Índice único PARCIAL: impede dois agendamentos 'confirmado' na
        # mesma quadra/data/horario. É a garantia, a nível de banco, de que
        # nunca existirá overbooking mesmo se o LLM "errar" ou duas
        # requisições chegarem ao mesmo tempo.
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_slot_unico
            ON agendamentos (quadra, data, horario)
            WHERE status = 'confirmado'
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS historico_conversas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telefone TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_historico_telefone
            ON historico_conversas (telefone, id)
        """)


# ---------------------------------------------------------------------------
# Histórico de conversa (memória do agente por número de telefone)
# ---------------------------------------------------------------------------

def salvar_mensagem(telefone: str, role: str, content: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO historico_conversas (telefone, role, content) VALUES (?, ?, ?)",
            (telefone, role, content)
        )


def get_historico(telefone: str, limite: int = MAX_HISTORICO_MENSAGENS):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT role, content FROM historico_conversas
               WHERE telefone = ?
               ORDER BY id DESC
               LIMIT ?""",
            (telefone, limite)
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# ---------------------------------------------------------------------------
# Disponibilidade e agendamentos
# ---------------------------------------------------------------------------

def _validar_horario(horario: str) -> bool:
    return horario in HORARIOS


def consultar_disponibilidade(data: str, horario: str = ""):
    """
    Retorna a disponibilidade real de quadras para uma data (e,
    opcionalmente, um horário específico). Esta função é a ÚNICA fonte de
    verdade sobre horários livres/ocupados: o agente de IA é instruído a
    NUNCA responder sobre disponibilidade sem antes chamar esta função.
    """
    with get_conn() as conn:
        ocupados = conn.execute(
            """SELECT quadra, horario FROM agendamentos
               WHERE data = ? AND status = 'confirmado'""",
            (data,)
        ).fetchall()

    ocupados_set = {(row["quadra"], row["horario"]) for row in ocupados}

    horarios_para_checar = [horario] if horario and _validar_horario(horario) else HORARIOS

    disponibilidade = {}
    for h in horarios_para_checar:
        livres = [q for q in QUADRAS if (q, h) not in ocupados_set]
        disponibilidade[h] = livres

    return {
        "data": data,
        "preco_por_hora": PRECO_HORA,
        "disponibilidade": disponibilidade,
    }


def criar_agendamento(quadra: int, data: str, horario: str, cliente_nome: str, cliente_telefone: str):
    if quadra not in QUADRAS:
        return {"sucesso": False, "erro": f"Quadra inválida. Quadras disponíveis: {QUADRAS}"}
    if not _validar_horario(horario):
        return {"sucesso": False, "erro": f"Horário inválido. Horários válidos: {HORARIOS}"}
    if not cliente_nome or not cliente_nome.strip():
        return {"sucesso": False, "erro": "Nome do cliente é obrigatório para confirmar o agendamento."}

    try:
        with get_conn() as conn:
            cursor = conn.execute(
                """INSERT INTO agendamentos
                   (quadra, data, horario, cliente_nome, cliente_telefone, valor, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'confirmado')""",
                (quadra, data, horario, cliente_nome.strip(), cliente_telefone, PRECO_HORA)
            )
            novo_id = cursor.lastrowid
        return {
            "sucesso": True,
            "id_agendamento": novo_id,
            "quadra": quadra,
            "data": data,
            "horario": horario,
            "valor": PRECO_HORA,
        }
    except sqlite3.IntegrityError:
        # O índice único parcial barrou uma tentativa de overbooking
        # (ex: dois clientes confirmando o mesmo horário quase ao mesmo tempo).
        return {
            "sucesso": False,
            "erro": "Esse horário acabou de ser reservado por outra pessoa. "
                    "Por favor, consulte a disponibilidade novamente e escolha outro horário."
        }


def listar_agendamentos_cliente(cliente_telefone: str):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, quadra, data, horario, valor, status
               FROM agendamentos
               WHERE cliente_telefone = ? AND status = 'confirmado'
               ORDER BY data, horario""",
            (cliente_telefone,)
        ).fetchall()
    return [dict(r) for r in rows]


def cancelar_agendamento(id_agendamento: int, cliente_telefone: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM agendamentos WHERE id = ? AND cliente_telefone = ?",
            (id_agendamento, cliente_telefone)
        ).fetchone()

        if not row:
            return {"sucesso": False, "erro": "Agendamento não encontrado para este número de telefone."}
        if row["status"] != "confirmado":
            return {"sucesso": False, "erro": "Este agendamento já está cancelado."}

        conn.execute(
            "UPDATE agendamentos SET status = 'cancelado' WHERE id = ?",
            (id_agendamento,)
        )
    return {"sucesso": True, "id_agendamento": id_agendamento}


# ---------------------------------------------------------------------------
# Painel administrativo (Dashboard Arena Black House)
#
# As funções abaixo servem exclusivamente a interface web da recepção.
# Diferente do fluxo do WhatsApp, aqui não existe um "cliente_telefone"
# autenticado por sessão — quem opera é a própria recepção, então as
# funções trabalham por data (visão geral) e por id (ações pontuais),
# em vez de filtrar por telefone de quem está pedindo.
# ---------------------------------------------------------------------------

def listar_agendamentos_por_data(data: str):
    """
    Lista todos os agendamentos confirmados de uma data específica,
    para alimentar a grade de ocupação e a tabela do painel administrativo.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, quadra, data, horario, cliente_nome, cliente_telefone,
                      valor, status, criado_em
               FROM agendamentos
               WHERE data = ? AND status = 'confirmado'
               ORDER BY horario, quadra""",
            (data,)
        ).fetchall()
    return [dict(r) for r in rows]


def cancelar_agendamento_admin(id_agendamento: int):
    """
    Cancela um agendamento pelo ID, sem exigir correspondência de telefone.
    Uso restrito ao painel administrativo (recepção), nunca ao agente de IA
    do WhatsApp — lá, cancelar_agendamento() continua exigindo o telefone
    real de quem está conversando, para que um cliente não cancele o
    agendamento de outra pessoa.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM agendamentos WHERE id = ?",
            (id_agendamento,)
        ).fetchone()

        if not row:
            return {"sucesso": False, "erro": "Agendamento não encontrado."}
        if row["status"] != "confirmado":
            return {"sucesso": False, "erro": "Este agendamento já está cancelado."}

        conn.execute(
            "UPDATE agendamentos SET status = 'cancelado' WHERE id = ?",
            (id_agendamento,)
        )
    return {"sucesso": True, "id_agendamento": id_agendamento}
