# Relatório Técnico — Agente Inteligente de Agendamento para a Arena Marina

## 1. Definição do Problema

### 1.1 Contexto e problema identificado

A Arena Marina é um espaço esportivo com 4 quadras de vôlei que, como a
maioria dos pequenos negócios do setor, recebe pedidos de reserva
majoritariamente pelo WhatsApp. Esse atendimento é hoje feito manualmente
por um responsável, que precisa checar uma agenda (física ou em planilha),
responder a cada cliente individualmente e atualizar os horários ocupados
à mão. Esse modelo gera um conjunto recorrente de problemas:

- **Agendamento caótico e sujeito a erro humano**: é comum a mesma quadra
  ser oferecida a dois clientes diferentes por falta de atualização em
  tempo real da agenda (overbooking).
- **Dependência de disponibilidade humana**: pedidos fora do horário
  comercial ou em momentos de alta demanda (ex.: fim de tarde, quando
  vários clientes escrevem ao mesmo tempo) ficam sem resposta imediata,
  gerando perda de clientes para concorrentes.
- **Falta de padronização das informações**: preço, horários e regras
  variam na forma como são comunicados dependendo de quem responde.
- **Nenhum registro estruturado**: sem um banco de dados central, é
  difícil auditar quantos agendamentos foram feitos, cancelados ou quais
  horários têm maior demanda.

### 1.2 Público-alvo

- **Clientes finais**: jogadores avulsos ou grupos que buscam reservar uma
  quadra de vôlei por WhatsApp, canal que já usam no dia a dia e que não
  exige baixar um aplicativo novo ou aprender um sistema diferente.
- **Gestão da arena**: o responsável pela Arena Marina, que passa a ter um
  atendimento 24/7 automatizado e um banco de dados confiável para
  acompanhar a ocupação das quadras, sem precisar responder manualmente
  cada mensagem.

### 1.3 Justificativa técnica

A escolha por um **agente de IA com function calling**, em vez de um
chatbot de fluxo fixo (árvore de decisão) ou de uma chamada solta a um
modelo de linguagem, se justifica por três motivos técnicos centrais:

1. **Flexibilidade de linguagem natural com controle determinístico**: um
   chatbot de árvore de decisão (baseado em botões/menus numéricos) é
   rígido e frustra o usuário quando ele escreve de forma livre (ex.:
   "quero jogar depois de amanhã de tarde, umas 3 pessoas"). Um LLM puro,
   por outro lado, entende a linguagem natural mas pode **alucinar**
   informações — por exemplo, "confirmar" um horário que na verdade já
   está ocupado. A arquitetura de *function calling* combina os dois
   pontos fortes: o modelo interpreta a linguagem natural do cliente, mas
   toda decisão sobre disponibilidade e toda escrita no banco de dados
   passam obrigatoriamente por funções Python determinísticas
   (`consultar_disponibilidade`, `criar_agendamento`), que são a única
   fonte de verdade.
2. **Auditabilidade e integração real com dados**: como o edital exige que
   o sistema vá além de "apenas chamar uma API de IA generativa sem lógica
   própria", a lógica própria aqui está justamente na camada de acesso ao
   SQLite (`database.py`), que implementa regras de negócio (4 quadras,
   janela de 08h–22h, slots de 1h, preço fixo) e uma proteção estrutural
   contra overbooking via índice único parcial no banco — algo que nenhuma
   chamada solta a uma API de IA generativa oferece sozinha.
3. **Custo e complexidade de implementação compatíveis com o prazo do
   projeto**: o uso da API do Twilio Sandbox para WhatsApp elimina a
   necessidade de aprovação como provedor oficial de mensagens (processo
   que leva dias/semanas), permitindo entregar um protótipo **funcional
   com WhatsApp real** dentro do prazo da disciplina.

---

## 2. Planejamento e Arquitetura

### 2.1 Visão geral do fluxo

O sistema segue o fluxo:

```
Usuário (WhatsApp) → Twilio → Flask (webhook) → Agente de IA (LLM) → SQLite → resposta de volta ao usuário
```

Em detalhe, cada mensagem percorre as seguintes etapas:

1. **Usuário → Twilio**: o cliente envia uma mensagem de texto pelo
   WhatsApp para o número do Twilio Sandbox.
2. **Twilio → Flask**: o Twilio recebe a mensagem e faz uma requisição
   HTTP `POST` para o *webhook* configurado (rota `/webhook` da aplicação
   Flask), enviando o corpo da mensagem (`Body`) e o número do remetente
   (`From`).
3. **Flask → Agente de IA**: o servidor Flask repassa o texto e o telefone
   do cliente para a camada do agente (`agent.py`), que:
   a. Recupera o histórico recente da conversa daquele número no SQLite
      (memória de curto prazo).
   b. Monta um *prompt* de sistema dinâmico, contendo a data/hora atual e
      as regras de negócio fixas (quadras, horários, preço).
   c. Envia esse contexto ao modelo de linguagem junto com a definição
      das 4 ferramentas disponíveis (function calling): consultar
      disponibilidade, criar agendamento, listar agendamentos do cliente
      e cancelar agendamento.
4. **Agente ⇄ SQLite (function calling)**: quando o modelo decide que
   precisa de um dado real (ex.: "quais quadras estão livres às 19h?"),
   ele não responde de memória — ele solicita a execução da função
   `consultar_disponibilidade`. O backend Python executa essa função
   contra o banco SQLite, retorna o resultado ao modelo, e só então o
   modelo formula a resposta final em linguagem natural. O mesmo vale
   para a escrita: o agendamento só é gravado no banco após a função
   `criar_agendamento` ser explicitamente chamada, o que só deve
   acontecer depois de o cliente confirmar os dados.
5. **Flask → Usuário**: a resposta final em texto é embrulhada em um
   documento TwiML (`<Response><Message>...</Message></Response>`) e
   devolvida na resposta HTTP ao Twilio, que entrega a mensagem ao
   WhatsApp do cliente.

### 2.2 Componentes da arquitetura

| Componente | Papel | Tecnologia |
|---|---|---|
| Canal de mensagens | Recebe/envia mensagens de WhatsApp | Twilio WhatsApp Sandbox |
| Servidor web | Expõe o endpoint de webhook, roteia requisições | Flask (Python) |
| Agente de IA | Interpreta linguagem natural, decide quando usar ferramentas | LLM com function calling (API compatível com OpenAI) |
| Camada de dados | Fonte única de verdade sobre disponibilidade e agendamentos | SQLite |
| Túnel de exposição | Expõe o `localhost` publicamente durante o desenvolvimento | ngrok |

### 2.3 Modelagem dos dados

O banco SQLite possui duas tabelas principais:

- **`agendamentos`**: armazena `quadra`, `data`, `horario`, `cliente_nome`,
  `cliente_telefone`, `valor`, `status` (`confirmado`/`cancelado`) e
  `criado_em`. Um índice único parcial garante, a nível de banco, que não
  existam dois registros `confirmado` para a mesma combinação de
  `quadra + data + horario` — essa é a principal barreira estrutural
  contra *overbooking*, funcionando mesmo em cenários de concorrência
  (duas requisições quase simultâneas).
- **`historico_conversas`**: armazena cada mensagem trocada (papel
  `user`/`assistant` e conteúdo), indexada por telefone, permitindo que o
  agente mantenha contexto entre mensagens (ex.: lembrar o nome do
  cliente informado dois turnos atrás) sem depender de estado em memória
  do processo, que se perderia a cada reinício do servidor.

### 2.4 Decisões de design relevantes

- **O modelo nunca recebe nem grava o telefone do cliente como argumento
  de função**: o número de telefone usado para `criar_agendamento`,
  `listar_meus_agendamentos` e `cancelar_agendamento` é sempre obtido do
  campo `From` real da requisição do Twilio, no código Python — nunca de
  um valor gerado pelo LLM. Isso evita que uma eventual alucinação do
  modelo altere ou cancele o agendamento de outra pessoa.
- **Separação entre "conversar" e "decidir"**: o histórico salvo no banco
  contém apenas o texto final trocado com o cliente, não as chamadas de
  ferramenta intermediárias. Isso mantém o contexto conversacional limpo,
  enquanto fatos objetivos (disponibilidade) são sempre reconsultados em
  tempo real a cada novo turno, em vez de "lembrados" pelo modelo.

---

## 3. Testes e Validação

### 3.1 Estratégia de avaliação qualitativa

Como o comportamento do agente depende de linguagem natural, a validação
não pode se basear apenas em testes unitários tradicionais. Foram usadas
duas frentes complementares:

1. **Testes automatizados determinísticos** (camada de dados e de
   integração HTTP): cobrem a lógica que não depende do LLM — criação de
   agendamento, bloqueio de horário duplicado (overbooking), validação de
   horário/quadra inválidos, cancelamento, listagem por cliente e
   persistência do histórico de conversa. Essa camada garante que, mesmo
   que o modelo de linguagem "erre" alguma coisa, o banco de dados nunca
   entra em um estado inconsistente (ex.: dois clientes com a mesma
   quadra no mesmo horário).
2. **Roteiro de conversas simuladas (avaliação qualitativa manual)**: um
   conjunto de diálogos de ponta a ponta é conduzido manualmente via
   WhatsApp real (Twilio Sandbox), cobrindo cenários como:
   - Pedido direto com todos os dados ("quero a quadra 2 amanhã às 18h,
     meu nome é João") → o agente deve consultar disponibilidade, pedir
     confirmação e só então registrar.
   - Pedido vago ("quero jogar sexta à noite") → o agente deve perguntar
     o horário exato antes de consultar o banco.
   - Horário já ocupado → o agente deve informar isso com base no
     resultado real da consulta e oferecer alternativas verdadeiras.
   - Cliente que muda de ideia no meio da conversa → o agente deve manter
     o contexto (nome já informado) sem repetir perguntas desnecessárias.
   - Pergunta fora do escopo ("vocês vendem uniforme?") → o agente deve
     redirecionar educadamente, sem inventar uma resposta sobre um
     serviço que não existe no sistema.

Cada diálogo é avaliado nos seguintes critérios: (a) o agente consultou o
banco antes de afirmar disponibilidade; (b) o agente pediu confirmação
antes de gravar o agendamento; (c) a informação de preço/horário
corresponde exatamente às regras de negócio fixas; (d) a resposta é
coerente com o histórico da conversa.

### 3.2 Limites do sistema

- **Sandbox do Twilio**: por ser um ambiente gratuito de testes, exige que
  cada usuário "ative" o número enviando uma palavra-código, e a conexão
  expira em 72 horas — em produção seria necessário um número de WhatsApp
  Business aprovado.
- **Concorrência**: o Flask, no modo de desenvolvimento padrão usado neste
  protótipo, atende as requisições de forma essencialmente sequencial;
  para uso em produção real com muitos clientes simultâneos seria
  necessário um servidor WSGI de produção (ex.: Gunicorn) com múltiplos
  workers.
- **Sem autenticação/pagamento real**: o sistema registra o agendamento
  como "confirmado" a partir da confirmação verbal do cliente pelo
  WhatsApp; não há integração com um gateway de pagamento, o que em um
  cenário real poderia gerar não comparecimento (*no-show*).
- **Janela de contexto limitada**: apenas as últimas mensagens de cada
  conversa (parametrizável) são enviadas ao modelo a cada novo turno, por
  custo e limite de tokens; conversas muito longas ou que ficaram
  "paradas" por dias podem perder parte do contexto mais antigo.

### 3.3 Estratégias contra alucinação

A alucinação — o modelo "inventar" um horário livre, um preço diferente
ou confirmar algo que não foi de fato salvo — é o principal risco em um
sistema de agendamento real. Foram adotadas as seguintes estratégias,
combinadas:

1. **Fonte única de verdade fora do modelo**: o LLM nunca é a fonte da
   informação de disponibilidade; ele é instruído (no prompt de sistema)
   a **sempre** chamar `consultar_disponibilidade` antes de responder
   sobre horários livres/ocupados, e o resultado dessa função — vindo
   diretamente do SQLite — é o único dado usado na resposta.
2. **Regras de negócio fixas injetadas no prompt, não "lembradas" pelo
   modelo**: quadras, janela de horário e preço são escritos
   explicitamente no prompt de sistema a cada requisição (a partir de
   `config.py`), reduzindo a chance de o modelo usar um valor genérico
   aprendido em treinamento em vez do valor real da Arena Marina.
3. **Confirmação explícita antes da escrita**: o prompt exige que o
   modelo obtenha confirmação verbal do cliente antes de chamar
   `criar_agendamento`, criando um "ponto de checagem" humano no fluxo.
4. **Validação e proteção no backend, não apenas no prompt**: mesmo que o
   modelo, por falha, tente registrar um horário ou quadra inválidos, a
   função `criar_agendamento` valida os valores contra as regras de
   negócio e o índice único do banco impede fisicamente um agendamento
   duplicado — ou seja, a defesa contra alucinação não depende
   exclusivamente do bom comportamento do modelo, existe uma segunda
   camada de garantia no código determinístico.
5. **Temperatura reduzida**: a chamada ao modelo usa uma temperatura
   baixa (0,3), o que reduz a variabilidade criativa da resposta em favor
   de respostas mais consistentes e ancoradas nos dados retornados pelas
   ferramentas.
