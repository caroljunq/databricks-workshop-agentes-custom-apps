"""Agente customizado em LangGraph.

Componentes:
  - Modelo: Claude Sonnet do catálogo system.ai via AI Gateway (MODEL_ENDPOINT), autenticado com o service principal do app.
  - Tool buscar_documentos: busca vetorial (pgvector) nos chunks do relatório guardados no Lakebase.
  - Tool consultar_dados: chama o Genie Space (GENIE_SPACE_ID) COM A IDENTIDADE DO USUÁRIO (OBO),
    então o Genie respeita as permissões de Unity Catalog de quem está logado. O resultado tabular
    (e o gráfico, quando o Genie gera um) volta como artefato da tool: fica no checkpoint para a UI,
    mas não é enviado ao modelo.
  - Tools salvar_memoria / buscar_memorias: memória de longo prazo por usuário no Lakebase.
  - Sessão: LangGraph PostgresSaver gravando o checkpoint do grafo no Lakebase (thread_id = usuário:sessão).
"""

import base64
import json
import os
from functools import lru_cache

import httpx
from databricks.sdk import WorkspaceClient
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.prebuilt import create_react_agent

import graficos
import lakebase

MAX_LINHAS_RESULTADO = 500
MAX_LINHAS_PARA_O_MODELO = 60

PROMPT_SISTEMA = """Você é o Assistente Regulatório da Exemplo Gás (dados fictícios para workshop).
Responda sempre em português, de forma objetiva.
Quando o usuário pedir para lembrar algo, apenas salve a informação com salvar_memoria e confirme em uma frase.
Não repita respostas de perguntas anteriores nesse caso.

Ferramentas disponíveis:
- buscar_documentos: trechos do relatório regulatório anual (texto, tabelas e legendas). Use para normas, metas,
  contexto e explicações do relatório. Cite a página.
- consultar_dados: consulta o Genie sobre as tabelas de indicadores operacionais e tarifas. Use para números,
  rankings, comparações e tendências. Informe o resultado e o critério usado.
- salvar_memoria: guarde preferências ou fatos duráveis que o usuário pedir para lembrar.
- buscar_memorias: consulte memórias anteriores do usuário quando ele se referir a algo combinado antes.

Quando consultar_dados retornar um gráfico ou tabela, eles já aparecem para o usuário na interface:
não desenhe gráficos nem monte tabelas em Markdown com esses dados. Responda com um resumo curto
(2 a 4 frases ou tópicos) destacando os principais números, variações e conclusões, sem comentar
que o gráfico ou a tabela aparecem na interface.

Se a informação não existir nas fontes, diga isso claramente em vez de inventar."""


def _host() -> str:
    return os.environ["DATABRICKS_HOST"]


@lru_cache(maxsize=1)
def _ws_app() -> WorkspaceClient:
    """Cliente com a identidade do app (service principal). O SDK renova o token OAuth sozinho."""
    return WorkspaceClient()


def _gateway_url() -> str:
    """Endpoint OpenAI-compatível do AI Gateway (aceita os modelos do catálogo system.ai)."""
    return f"{_ws_app().config.host.rstrip('/')}/ai-gateway/mlflow/v1"


class _AuthApp(httpx.Auth):
    """Injeta o token atual do service principal em cada requisição ao AI Gateway."""

    def auth_flow(self, request):
        request.headers.update(_ws_app().config.authenticate())
        yield request


def _embedding(texto: str) -> list[float]:
    """Gera o embedding via AI Gateway (mesmo modelo system.ai usado na preparação dos dados)."""
    resp = httpx.post(
        f"{_gateway_url()}/embeddings",
        headers=_ws_app().config.authenticate(),
        json={"model": os.environ["EMBEDDING_ENDPOINT"], "input": [texto]},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


def _consultar_genie(pergunta: str, user_token: str) -> tuple[str, dict]:
    """Pergunta ao Genie como o usuário (OBO).

    Retorna (texto para o modelo, artefato para a UI). O artefato traz, para cada consulta do Genie,
    título, SQL, colunas, linhas e se o Genie gerou gráfico.
    """
    artefato = {"tabelas": [], "sugestoes": []}
    if not user_token:
        return "Erro: token do usuário ausente. Ative a autorização de usuário (OBO) no app.", artefato
    ws_usuario = WorkspaceClient(host=_host(), token=user_token, auth_type="pat")
    space_id = os.environ["GENIE_SPACE_ID"]
    try:
        msg = ws_usuario.genie.start_conversation_and_wait(space_id=space_id, content=pergunta)
    except Exception as e:
        texto = str(e)
        if "required scopes: genie" in texto.lower() or ("invalid scope" in texto.lower() and "genie" in texto.lower()):
            return (
                "O token do usuário não tem o escopo `genie`. Em Settings → User authorization, "
                "confirme os escopos `sql`, `genie` e `ai-gateway`. Depois pare e inicie o app "
                "(ou faça Deploy) e abra a URL em uma janela anônima para autorizar de novo."
            ), artefato
        return f"Erro ao consultar o Genie: {e}", artefato

    partes = []
    consultas = {}  # attachment_id da consulta -> tabela do artefato
    visualizacoes = []  # (attachment_id da viz, attachment_id da consulta, título)
    for anexo in msg.attachments or []:
        if anexo.text and anexo.text.content:
            partes.append(anexo.text.content)
        if anexo.suggested_questions and anexo.suggested_questions.questions:
            artefato["sugestoes"].extend(anexo.suggested_questions.questions)
        if anexo.viz and anexo.viz.query_attachment_id:
            visualizacoes.append((anexo.attachment_id, anexo.viz.query_attachment_id, anexo.viz.title))
        if anexo.query and anexo.query.query:
            partes.append(f"SQL usado pelo Genie:\n{anexo.query.query}")
            tabela = {
                "titulo": anexo.query.title or "",
                "sql": anexo.query.query,
                "colunas": [],
                "linhas": [],
                "grafico": False,
            }
            try:
                res = ws_usuario.genie.get_message_attachment_query_result(
                    space_id=space_id,
                    conversation_id=msg.conversation_id,
                    message_id=msg.message_id,
                    attachment_id=anexo.attachment_id,
                )
                resp = res.statement_response
                if resp and resp.manifest and resp.manifest.schema:
                    tabela["colunas"] = [
                        {"nome": c.name, "tipo": c.type_name.value if c.type_name else ""}
                        for c in resp.manifest.schema.columns or []
                    ]
                if resp and resp.result:
                    tabela["linhas"] = (resp.result.data_array or [])[:MAX_LINHAS_RESULTADO]
                nomes = [c["nome"] for c in tabela["colunas"]]
                previa = tabela["linhas"][:MAX_LINHAS_PARA_O_MODELO]
                if previa:
                    total = len(tabela["linhas"])
                    cabecalho = "Resultado" if total <= len(previa) else f"Primeiras {len(previa)} de {total} linhas do resultado"
                    partes.append(
                        f"{cabecalho}:\n" + " | ".join(nomes) + "\n"
                        + "\n".join(" | ".join(map(str, l)) for l in previa)
                    )
            except Exception as e:  # o resultado tabular é opcional para a resposta
                partes.append(f"(não foi possível carregar o resultado tabular: {e})")
            consultas[anexo.attachment_id] = tabela

    for viz_id, consulta_id, titulo in visualizacoes:
        tabela = consultas.get(consulta_id)
        if not tabela:
            continue
        tabela["grafico"] = True
        if titulo:
            tabela["titulo"] = titulo
        if graficos.grafico(graficos.dataframe(tabela)) is None:
            # Formato não reconhecido para redesenhar: guarda a imagem renderizada pelo próprio Genie.
            try:
                nome = f"spaces/{space_id}/conversations/{msg.conversation_id}/messages/{msg.message_id}/attachments/{viz_id}"
                conteudo = ws_usuario.genie.download_message_attachment_visualization(name=nome).contents
                dados = conteudo.read() if hasattr(conteudo, "read") else conteudo
                if dados:
                    tabela["png_b64"] = base64.b64encode(dados).decode()
            except Exception:
                pass
        partes.append("(O gráfico deste resultado já foi exibido ao usuário na interface.)")

    artefato["tabelas"] = list(consultas.values())
    artefato["sugestoes"] = artefato["sugestoes"][:3]
    return "\n\n".join(partes) or "O Genie não retornou resposta para esta pergunta.", artefato


def construir_ferramentas(user_email: str, user_token: str, conn_factory) -> list:
    """Cria as tools ligadas ao usuário atual (email e token ficam no closure, nunca são escolhidos pelo modelo)."""

    @tool
    def buscar_documentos(pergunta: str) -> str:
        """Busca trechos do relatório regulatório (texto, tabelas e legendas) no Lakebase. Retorna página e conteúdo."""
        emb = _embedding(pergunta)
        with conn_factory() as conn:
            resultados = lakebase.buscar_documentos(conn, emb, k=3)
        if not resultados:
            return "Nenhum trecho encontrado."
        return "\n\n".join(
            f"[{r['documento']} · página {r['pagina']} · relevância {r['score']:.2f}]\n{r['conteudo']}" for r in resultados
        )

    @tool(response_format="content_and_artifact")
    def consultar_dados(pergunta: str):
        """Consulta o Genie sobre as tabelas de indicadores operacionais e tarifas (Unity Catalog), com as permissões do usuário."""
        return _consultar_genie(pergunta, user_token)

    @tool
    def salvar_memoria(texto: str) -> str:
        """Salva uma preferência ou fato durável do usuário para lembrar em conversas futuras."""
        emb = _embedding(texto)
        with conn_factory() as conn:
            salva = lakebase.salvar_memoria(conn, user_email, texto, emb)
        return "Memória salva." if salva else "Essa memória já estava salva."

    @tool
    def buscar_memorias(consulta: str) -> str:
        """Busca memórias anteriores do usuário relacionadas à consulta."""
        emb = _embedding(consulta)
        with conn_factory() as conn:
            memorias = lakebase.buscar_memorias(conn, user_email, emb, k=3)
        return "\n".join(f"- {m}" for m in memorias) or "Nenhuma memória encontrada."

    return [buscar_documentos, consultar_dados, salvar_memoria, buscar_memorias]


def construir_agente(user_email: str, user_token: str, conn_factory, saver: PostgresSaver):
    """Monta o grafo LangGraph com o checkpointer do Lakebase (sessão recuperável)."""
    # Sem temperature: o Claude Sonnet 5.5 não aceita esse parâmetro.
    llm = ChatOpenAI(
        model=os.environ["MODEL_ENDPOINT"],
        base_url=_gateway_url(),
        api_key="gerenciado-pelo-sdk",  # valor ignorado: o token real é injetado por _AuthApp
        http_client=httpx.Client(auth=_AuthApp(), timeout=120),
    )
    ferramentas = construir_ferramentas(user_email, user_token, conn_factory)
    return create_react_agent(llm, ferramentas, prompt=PROMPT_SISTEMA, checkpointer=saver)


def thread_id(user_email: str, session_id: str) -> str:
    return f"{user_email}:{session_id}"


def _texto(conteudo) -> str:
    """Extrai só o texto da resposta. Modelos Claude podem devolver lista de blocos
    (reasoning, text, tool_use); aqui ficam apenas os blocos de texto."""
    if isinstance(conteudo, str):
        s = conteudo.strip()
        if not (s.startswith("[") and '"type"' in s):
            return conteudo
        try:  # às vezes a lista de blocos chega serializada como JSON dentro de uma string
            conteudo = json.loads(s)
        except json.JSONDecodeError:
            return conteudo
    partes = []
    for bloco in conteudo or []:
        if isinstance(bloco, str):
            partes.append(bloco)
        elif isinstance(bloco, dict) and bloco.get("type") == "text":
            partes.append(bloco.get("text", ""))
    return "".join(partes).strip()


def _artefatos(mensagem) -> tuple[list, list]:
    artefato = getattr(mensagem, "artifact", None) or {}
    if not isinstance(artefato, dict):
        return [], []
    return artefato.get("tabelas") or [], artefato.get("sugestoes") or []


def turno(user_email: str, user_token: str, session_id: str, pergunta: str, ao_progresso=None) -> dict:
    """Executa um turno da conversa. O estado do grafo é salvo no Lakebase ao final de cada passo.

    Retorna {"texto", "artefatos", "sugestoes"}. ao_progresso(nomes_das_tools) é chamado a cada
    chamada de ferramenta, para a UI mostrar o que o agente está fazendo.
    """
    from psycopg.rows import dict_row

    texto, artefatos, sugestoes = "", [], []
    with lakebase.conectar(row_factory=dict_row) as conn_saver:
        saver = PostgresSaver(conn_saver)
        if not conn_saver.execute("SELECT to_regclass('public.checkpoints') IS NOT NULL AS ok").fetchone()["ok"]:
            saver.setup()  # cria as tabelas de checkpoint na primeira execução
        agente = construir_agente(user_email, user_token, lakebase.conectar, saver)
        config = {"configurable": {"thread_id": thread_id(user_email, session_id)}}
        for atualizacao in agente.stream({"messages": [("user", pergunta)]}, config=config, stream_mode="updates"):
            for dados in atualizacao.values():
                for m in (dados or {}).get("messages", []) if isinstance(dados, dict) else []:
                    if m.type == "ai" and getattr(m, "tool_calls", None):
                        if ao_progresso:
                            ao_progresso([c["name"] for c in m.tool_calls])
                    elif m.type == "ai":
                        texto = _texto(m.content)
                    elif m.type == "tool":
                        tabelas, sugs = _artefatos(m)
                        artefatos.extend(tabelas)
                        sugestoes.extend(sugs)
    return {"texto": texto, "artefatos": artefatos, "sugestoes": sugestoes[:3]}


def carregar_historico(user_email: str, user_token: str, session_id: str) -> list[dict]:
    """Recupera as mensagens de uma sessão anterior a partir do checkpoint no Lakebase,
    incluindo os resultados do Genie (artefatos das tools) ligados a cada resposta."""
    from psycopg.rows import dict_row

    with lakebase.conectar(row_factory=dict_row) as conn_saver:
        saver = PostgresSaver(conn_saver)
        agente = construir_agente(user_email, user_token, lakebase.conectar, saver)
        config = {"configurable": {"thread_id": thread_id(user_email, session_id)}}
        estado = agente.get_state(config)
    msgs = estado.values.get("messages", []) if estado and estado.values else []
    saida, pendentes, sugestoes = [], [], []
    for m in msgs:
        papel = getattr(m, "type", "")
        if papel == "tool":
            tabelas, sugs = _artefatos(m)
            pendentes.extend(tabelas)
            sugestoes.extend(sugs)
            continue
        if papel not in ("human", "ai"):
            continue
        texto = _texto(m.content)  # ignora mensagens só com chamadas de tool (sem texto)
        if not texto:
            continue
        if papel == "human":
            pendentes, sugestoes = [], []
            saida.append({"papel": "user", "texto": texto, "artefatos": [], "sugestoes": []})
        else:
            saida.append({"papel": "assistant", "texto": texto, "artefatos": pendentes, "sugestoes": sugestoes[:3]})
            pendentes, sugestoes = [], []
    return saida
