# 🏐 Arena Marina — Agente de IA para Agendamento via WhatsApp

Protótipo funcional de um agente inteligente que atende clientes da Arena
Marina pelo WhatsApp, consulta a disponibilidade real das 4 quadras em um
banco SQLite e registra agendamentos automaticamente, usando **function
calling** (chamada de ferramentas) para nunca inventar horários.

## Arquitetura

```
Cliente (WhatsApp)
      │
      ▼
  Twilio Sandbox  ──(POST /webhook)──▶  Flask (app.py)
                                            │
                                            ▼
                                     Agente de IA (agent.py)
                                     - monta prompt de sistema
                                     - decide chamar ferramentas
                                            │
                                            ▼
                                     database.py ──▶ SQLite (arena_marina.db)
                                     - consultar_disponibilidade
                                     - criar_agendamento
                                     - listar_meus_agendamentos
                                     - cancelar_agendamento
```

O modelo de IA **nunca** escreve diretamente no banco. Ele apenas solicita
a execução de uma das 4 funções acima; quem executa é código Python
determinístico, que é a única fonte de verdade sobre disponibilidade.

## Estrutura de arquivos

```
arena-marina-bot/
├── app.py              # Servidor Flask + rota de webhook do Twilio
├── agent.py            # Lógica do agente de IA (function calling)
├── database.py          # Schema SQLite + regras de acesso ao banco
├── config.py            # Configurações e regras de negócio centrais
├── requirements.txt      # Dependências Python
├── .env.example          # Modelo de variáveis de ambiente
└── README.md
```

---

## Passo 1 — Pré-requisitos

- Python 3.10 ou superior instalado
- Uma conta gratuita no [Twilio](https://www.twilio.com/try-twilio)
- Uma chave de API da [OpenAI](https://platform.openai.com/api-keys) **ou**
  da [Groq](https://console.groq.com/keys) (gratuita, compatível com a API
  da OpenAI — veja a Parte 4)
- O [ngrok](https://ngrok.com/download) instalado (para expor seu
  `localhost` publicamente)

## Passo 2 — Instalação do projeto

```bash
# Entre na pasta do projeto
cd arena-marina-bot

# Crie e ative um ambiente virtual (recomendado)
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Instale as dependências
pip install -r requirements.txt
```

## Passo 3 — Configurar as variáveis de ambiente

```bash
cp .env.example .env
```

Abra o arquivo `.env` e preencha:

```env
OPENAI_API_KEY=sua_chave_aqui
OPENAI_MODEL=gpt-4o-mini
```

> 💡 **Não tem uma chave da OpenAI?** Você pode usar a **Groq** (gratuita).
> No `.env`, descomente e ajuste:
> ```env
> OPENAI_BASE_URL=https://api.groq.com/openai/v1
> OPENAI_MODEL=llama-3.3-70b-versatile
> OPENAI_API_KEY=sua_chave_da_groq
> ```

## Passo 4 — Rodar o servidor localmente

```bash
python app.py
```

Se tudo estiver certo, você verá o Flask rodando em
`http://127.0.0.1:5000`. Acesse essa URL no navegador — deve aparecer a
mensagem "Servidor da Arena Marina rodando! 🏐".

O arquivo `arena_marina.db` (SQLite) é criado automaticamente na primeira
execução, com as tabelas `agendamentos` e `historico_conversas`.

## Passo 5 — Expor o servidor com ngrok

Em **outro terminal** (deixe o `python app.py` rodando):

```bash
ngrok http 5000
```

O ngrok vai gerar uma URL pública parecida com:

```
https://a1b2c3d4e5.ngrok-free.app
```

Guarde essa URL — você vai usá-la no próximo passo. **Atenção:** no plano
gratuito do ngrok, essa URL muda toda vez que você reinicia o `ngrok`, e
será preciso atualizar o webhook no Twilio novamente.

## Passo 6 — Configurar o Twilio WhatsApp Sandbox

1. Acesse o [Console do Twilio](https://console.twilio.com/).
2. No menu lateral, vá em **Messaging → Try it out → Send a WhatsApp message**
   (o caminho exato pode variar um pouco conforme atualizações da interface;
   procure por "WhatsApp Sandbox").
3. O Twilio vai te mostrar um número de WhatsApp deles (americano) e um
   código de ativação, por exemplo `join zebra-purple`.
4. No **seu celular**, abra o WhatsApp e envie essa frase (`join
   zebra-purple`, com o código que aparecer para você) para o número
   informado. Isso conecta seu número real ao ambiente de testes (sandbox)
   por 72 horas.
5. Ainda na página do Sandbox, procure o campo **"WHEN A MESSAGE COMES
   IN"** (Sandbox Settings) e cole a URL do ngrok seguida de `/webhook`:
   ```
   https://a1b2c3d4e5.ngrok-free.app/webhook
   ```
6. Confirme que o método está como **HTTP POST** e clique em **Save**.

## Passo 7 — Testar

No WhatsApp do seu celular, envie mensagens para o número do Sandbox do
Twilio, por exemplo:

```
Oi, quero agendar uma quadra para amanhã às 19h
```

O agente deve:
1. Consultar a disponibilidade real no banco (`consultar_disponibilidade`)
2. Informar quais quadras estão livres nesse horário e o preço (R$ 40,00)
3. Perguntar seu nome, se ainda não souber
4. Pedir confirmação antes de registrar
5. Registrar o agendamento no SQLite (`criar_agendamento`) só depois da
   sua confirmação

Você também pode testar:
- `"Quais os meus agendamentos?"` → lista os agendamentos ativos
- `"Quero cancelar o agendamento 1"` → cancela pelo ID

## Passo 8 — Inspecionar o banco de dados (opcional)

```bash
sqlite3 arena_marina.db "SELECT * FROM agendamentos;"
sqlite3 arena_marina.db "SELECT * FROM historico_conversas ORDER BY id;"
```

---

## Solução de problemas comuns

| Problema | Causa provável | Solução |
|---|---|---|
| Twilio não recebe resposta | ngrok/Flask não estão rodando, ou a URL do webhook está desatualizada | Confirme que os dois terminais (Flask e ngrok) estão ativos e que a URL no Twilio bate com a atual do ngrok |
| Erro `401 Unauthorized` da OpenAI | Chave de API inválida ou não configurada | Confira o `.env` e se a variável foi carregada (`OPENAI_API_KEY`) |
| Agendamento "some" ao reiniciar | Você apagou o arquivo `arena_marina.db` | O SQLite é um arquivo local; não o exclua entre os testes |
| Erro `sqlite3.IntegrityError` | **Esperado** — é a proteção contra overbooking funcionando (dois agendamentos no mesmo horário/quadra) | Nenhuma ação necessária, é o comportamento correto |
| Sandbox "expirou" | Sessões do WhatsApp Sandbox duram 72h | Reenvie a mensagem `join <código>` para reconectar |

---

## Regras de negócio implementadas

- 4 quadras (numeradas 1 a 4)
- Funcionamento das 08:00 às 22:00
- Slots fixos de 1 hora (08:00, 09:00, ..., 21:00 — 14 horários/dia)
- Preço fixo de R$ 40,00 por hora, por quadra
- Proteção a nível de banco de dados contra overbooking (índice único
  parcial em `quadra + data + horario` para agendamentos confirmados)
