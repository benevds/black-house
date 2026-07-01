"""
Agente de IA da Arena Marina.

Implementa o loop de Function Calling: o LLM decide QUANDO consultar o
banco (disponibilidade) e QUANDO registrar/cancelar um agendamento, mas
todo acesso real ao banco é feito por código Python determinístico
(database.py) — o modelo nunca escreve diretamente no SQLite, apenas
solicita a execução de funções conhecidas e auditáveis.
"""
import json
import traceback
from datetime import datetime
from openai import OpenAI

import config
import database as db

client = OpenAI(
    api_key=config.OPENAI_API_KEY,
    base_url=config.OPENAI_BASE_URL,  # None = usa a API oficial da OpenAI
)

DIAS_SEMANA_PT = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]

# ---------------------------------------------------------------------------
# Definição das ferramentas (function calling) expostas ao modelo
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_disponibilidade",
            "description": (
                "Consulta no banco de dados quais quadras estão livres em uma data "
                "(e opcionalmente em um horário específico). DEVE ser chamada sempre "
                "antes de confirmar qualquer agendamento ou de informar ao cliente "
                "quais horários estão livres ou ocupados."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "string",
                        "description": "Data no formato AAAA-MM-DD",
                    },
                    "horario": {
                        "type": "string",
                        "description": (
                            "Horário específico no formato HH:MM (opcional). "
                            "Deixe vazio para ver todos os horários do dia."
                        ),
                    },
                },
                "required": ["data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "criar_agendamento",
            "description": (
                "Registra um novo agendamento no banco de dados. Só deve ser chamada "
                "depois que: (1) a disponibilidade foi checada com consultar_disponibilidade "
                "e (2) o cliente confirmou explicitamente quadra, data e horário."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "quadra": {"type": "integer", "description": "Número da quadra (1 a 4)"},
                    "data": {"type": "string", "description": "Data no formato AAAA-MM-DD"},
                    "horario": {"type": "string", "description": "Horário no formato HH:MM"},
                    "cliente_nome": {"type": "string", "description": "Nome do cliente"},
                },
                "required": ["quadra", "data", "horario", "cliente_nome"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_meus_agendamentos",
            "description": "Lista os agendamentos ativos do cliente que está enviando a mensagem.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancelar_agendamento",
            "description": "Cancela um agendamento existente do cliente, dado o ID do agendamento.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_agendamento": {"type": "integer", "description": "ID do agendamento a cancelar"},
                },
                "required": ["id_agendamento"],
            },
        },
    },
]


def _executar_ferramenta(nome_funcao: str, argumentos: dict, telefone_cliente: str) -> dict:
    """
    Executa a função solicitada pelo modelo.

    IMPORTANTE: o telefone do cliente vem sempre do campo 'From' real do
    Twilio (passado pelo backend), nunca de um argumento gerado pelo
    modelo. Isso evita que uma alucinação do LLM cancele ou consulte
    agendamentos de outra pessoa.
    """
    if nome_funcao == "consultar_disponibilidade":
        return db.consultar_disponibilidade(
            data=argumentos.get("data", ""),
            horario=argumentos.get("horario", ""),
        )

    if nome_funcao == "criar_agendamento":
        return db.criar_agendamento(
            quadra=int(argumentos.get("quadra", 0)),
            data=argumentos.get("data", ""),
            horario=argumentos.get("horario", ""),
            cliente_nome=argumentos.get("cliente_nome", ""),
            cliente_telefone=telefone_cliente,
        )

    if nome_funcao == "listar_meus_agendamentos":
        return {"agendamentos": db.listar_agendamentos_cliente(telefone_cliente)}

    if nome_funcao == "cancelar_agendamento":
        return db.cancelar_agendamento(
            id_agendamento=int(argumentos.get("id_agendamento", 0)),
            cliente_telefone=telefone_cliente,
        )

    return {"erro": f"Ferramenta desconhecida: {nome_funcao}"}


def _montar_prompt_sistema() -> str:
    agora = datetime.now()
    dia_semana = DIAS_SEMANA_PT[agora.weekday()]
    data_formatada = agora.strftime("%d/%m/%Y %H:%M")

    return f"""Você é o assistente virtual da {config.NOME_ARENA}, uma arena de vôlei com {len(config.QUADRAS)} quadras.

DATA E HORA ATUAL: {dia_semana}, {data_formatada}
(use isso para resolver termos relativos como "hoje", "amanhã", "sexta que vem" e sempre converta para o formato AAAA-MM-DD ao chamar as ferramentas).

REGRAS DE NEGÓCIO (fixas — nunca invente valores diferentes destes):
- Quadras disponíveis: {config.QUADRAS} (total de {len(config.QUADRAS)} quadras).
- Horário de funcionamento: {config.HORA_ABERTURA:02d}:00 às {config.HORA_FECHAMENTO:02d}:00.
- Agendamentos duram sempre 1 hora, começando em: {', '.join(config.HORARIOS)}.
- Preço fixo: R$ {config.PRECO_HORA:.2f} por hora, por quadra.

REGRAS DE COMPORTAMENTO (muito importantes):
1. NUNCA informe um horário como livre ou ocupado sem antes chamar a ferramenta
   consultar_disponibilidade. Você não possui essa informação de memória — só o
   banco de dados sabe a disponibilidade real.
2. NUNCA invente números de quadra, preços ou horários fora dos definidos acima.
3. Antes de chamar criar_agendamento, confirme com o cliente: nome, data, horário
   e quadra. Só chame a ferramenta depois que o cliente confirmar explicitamente
   (ex: "sim", "pode confirmar", "fechado").
4. Se o cliente ainda não informou o nome, pergunte antes de confirmar o agendamento.
5. Se o horário pedido estiver ocupado, ofereça alternativas próximas usando os
   dados reais retornados pela ferramenta de consulta — nunca invente alternativas.
6. Seja breve, cordial e objetivo: as mensagens são trocadas via WhatsApp.
7. Sempre responda em português do Brasil.
8. Se perguntarem algo sem relação com agendamento de quadras de vôlei, redirecione
   educadamente o assunto de volta para os serviços da arena.
"""


def processar_mensagem(telefone: str, mensagem_usuario: str) -> str:
    """
    Ponto de entrada do agente: recebe a mensagem recebida no WhatsApp e
    devolve o texto de resposta, persistindo o histórico da conversa.
    """
    if not mensagem_usuario:
        return "Oi! Não recebi nenhuma mensagem de texto. Pode repetir? 🏐"

    db.salvar_mensagem(telefone, "user", mensagem_usuario)
    historico = db.get_historico(telefone)

    mensagens = [{"role": "system", "content": _montar_prompt_sistema()}] + historico

    for _ in range(config.MAX_ITERACOES_AGENTE):
        try:
            resposta = client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=mensagens,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
            )
        except Exception as e:
            print(f"[ERRO AGENTE] Falha na chamada ao serviço de IA: {e}")
            print(traceback.format_exc())
            # Retorna uma mensagem amigável no canal de usuário em vez de propagar erro
            fallback_erro = (
                "Desculpe, não consegui contactar o serviço de IA no momento. "
                "Tente novamente em alguns instantes."
            )
            db.salvar_mensagem(telefone, "assistant", fallback_erro)
            return fallback_erro
        msg = resposta.choices[0].message

        if msg.tool_calls:
            mensagens.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tool_call in msg.tool_calls:
                nome_funcao = tool_call.function.name
                try:
                    argumentos = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    argumentos = {}

                resultado = _executar_ferramenta(nome_funcao, argumentos, telefone)

                mensagens.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(resultado, ensure_ascii=False, default=str),
                })
            continue  # devolve os resultados das ferramentas ao modelo

        texto_final = msg.content or "Desculpe, não consegui gerar uma resposta agora."
        db.salvar_mensagem(telefone, "assistant", texto_final)
        return texto_final

    fallback = ("Desculpe, tive dificuldade para concluir sua solicitação agora. "
                "Pode tentar reformular, por favor? 🙏")
    db.salvar_mensagem(telefone, "assistant", fallback)
    return fallback
