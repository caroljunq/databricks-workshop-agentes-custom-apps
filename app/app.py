"""Assistente Regulatório — Databricks App (Streamlit + LangGraph).

Recursos:
  - Interface de chat no estilo ChatGPT: barra lateral com "Nova conversa" e conversas recentes,
    tela inicial com sugestões e respostas em coluna central.
  - Ao selecionar uma conversa, o histórico (incluindo os gráficos do Genie) é recuperado do Lakebase.
  - Gráficos: quando o Genie gera uma visualização, o app redesenha o gráfico com os dados da consulta.
  - Autorização de usuário (OBO): o token do usuário chega no header x-forwarded-access-token
    e é usado apenas para consultar o Genie como o próprio usuário.

Execução local (somente para desenvolvimento): veja README, seção "Testar localmente".
"""

import base64
import html
import os
from datetime import datetime, timedelta, timezone

import streamlit as st

import agente
import graficos
import lakebase

st.set_page_config(
    page_title="Assistente Regulatório",
    page_icon=":material/insights:",
    layout="centered",
    initial_sidebar_state="expanded",
)

AVATAR_ASSISTENTE = ":material/insights:"
TITULO_PADRAO = "Nova conversa"
SUGESTOES_INICIAIS = [
    (":material/trending_down:", "Qual foi a média de perdas de gás em 2025 e qual era a meta regulatória?"),
    (":material/bar_chart:", "Mostre em um gráfico o volume distribuído total por região em 2025."),
    (":material/show_chart:", "Como evoluiu a tarifa final residencial por trimestre desde 2022?"),
    (":material/description:", "O que o relatório diz sobre o evento climático no Litoral em 2024?"),
]
ROTULOS_FERRAMENTAS = {
    "consultar_dados": "Consultando os dados no Genie",
    "buscar_documentos": "Buscando no relatório regulatório",
    "salvar_memoria": "Salvando sua preferência",
    "buscar_memorias": "Consultando suas memórias",
}

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, button, textarea, input { font-family: 'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif; }

/* Cabeçalho e menus padrão do Streamlit */
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbarActions"], [data-testid="stAppDeployButton"], [data-testid="stMainMenu"], footer { display: none !important; }

/* Coluna central */
[data-testid="stMainBlockContainer"] { max-width: 820px; padding-top: 2.5rem; padding-bottom: 8rem; }

/* Barra lateral */
[data-testid="stSidebar"] { background: #F7F7F8; border-right: 1px solid #ECECF1; }
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding-top: 0.5rem; }
.marca { display: flex; align-items: center; gap: .65rem; margin: .25rem 0 1rem 0; }
.marca .logo { width: 36px; height: 36px; border-radius: 10px; background: linear-gradient(135deg, #1F4E79, #2E86AB);
  color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 15px; }
.marca .nome { font-weight: 700; font-size: 15px; color: #101828; line-height: 1.15; }
.marca .sub { font-size: 12px; color: #667085; }
.grupo { font-size: 12px; font-weight: 600; color: #667085; margin: 1rem 0 .25rem .35rem; text-transform: uppercase; letter-spacing: .02em; }

[data-testid="stSidebar"] .stButton button { width: 100%; justify-content: flex-start; border: none; background: transparent;
  color: #344054; border-radius: 8px; padding: .4rem .6rem; min-height: 0; font-size: 14px; box-shadow: none; }
[data-testid="stSidebar"] .stButton button > div, [data-testid="stSidebar"] .stButton button > div > span { justify-content: flex-start; width: 100%; }
[data-testid="stSidebar"] .stButton button p { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left; }
.st-key-nova_conversa button > div, .st-key-nova_conversa button > div > span { justify-content: center !important; }
[data-testid="stSidebar"] .stButton button:hover { background: #ECECF1; color: #101828; }
[data-testid="stSidebar"] .stButton button[kind="primary"] { background: #E4E7EC; color: #101828; font-weight: 600; }
.st-key-nova_conversa button { border: 1px solid #D0D5DD !important; background: #FFFFFF !important; font-weight: 600 !important; }
.st-key-nova_conversa button:hover { background: #F2F4F7 !important; }

.usuario { display: flex; align-items: center; gap: .6rem; padding: .6rem .35rem; border-top: 1px solid #ECECF1; margin-top: 1.25rem; }
.usuario .avatar { width: 30px; height: 30px; border-radius: 50%; background: #1F4E79; color: #fff; font-size: 12px; font-weight: 600;
  display: flex; align-items: center; justify-content: center; }
.usuario .email { font-size: 13px; color: #344054; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Tela inicial */
.saudacao { text-align: center; margin: 9vh 0 2rem 0; }
.saudacao h1 { font-size: 2rem; font-weight: 600; color: #101828; margin-bottom: .35rem; }
.saudacao p { color: #667085; font-size: 1rem; }
[class*="st-key-sugestao_"] button { width: 100%; min-height: 76px; height: 100%; justify-content: flex-start; align-items: flex-start;
  text-align: left; border: 1px solid #E4E7EC; border-radius: 14px; background: #FFFFFF; padding: .8rem 1rem; color: #344054; }
[class*="st-key-sugestao_"] button > div, [class*="st-key-sugestao_"] button > div > span { justify-content: flex-start; align-items: flex-start; }
[class*="st-key-sugestao_"] button p { text-align: left; font-size: 14px; line-height: 1.45; }
[class*="st-key-seguir_"] { gap: .15rem; margin-top: .25rem; }
[class*="st-key-seguir_"] button p { color: #475467; font-size: 14px; text-align: left; }
[class*="st-key-seguir_"] button:hover p { color: #1F4E79; }
[class*="st-key-sugestao_"] button:hover { background: #F9FAFB; border-color: #D0D5DD; color: #101828; }

/* Mensagens */
[data-testid="stChatMessage"] { background: transparent; padding: .35rem 0; gap: .75rem; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { flex-direction: row-reverse; }
[data-testid="stChatMessageAvatarUser"] { display: none; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
  background: #F2F4F7; border-radius: 18px; padding: .6rem 1rem; max-width: 78%; flex: 0 1 auto; margin-left: auto; }
[data-testid="stChatMessageAvatarCustom"] { background: #1F4E79; color: #fff; border-radius: 50%; }
[data-testid="stChatMessageContent"] p, [data-testid="stChatMessageContent"] li { font-size: 15px; line-height: 1.65; color: #1F2328; }

/* Cartões de resultado do Genie */
[class*="st-key-resultado_"] { border-radius: 14px !important; border-color: #E4E7EC !important; }
.resultado-titulo { font-size: 13px; font-weight: 600; color: #344054; display: flex; align-items: center; gap: .4rem; }
.resultado-titulo .selo { font-size: 11px; font-weight: 600; color: #1F4E79; background: #E8F1FA; border-radius: 999px; padding: .1rem .5rem; }

/* Caixa de mensagem */
[data-testid="stBottom"] > div { background: transparent; }
[data-testid="stBottomBlockContainer"] { max-width: 820px; padding-bottom: .75rem; }
[data-testid="stChatInput"] { border-radius: 26px !important; border: 1px solid #D0D5DD !important; background: #FFFFFF !important;
  box-shadow: 0 6px 24px rgba(16, 24, 40, .08); }
[data-testid="stChatInput"] textarea { font-size: 15px; }
[data-testid="stBottomBlockContainer"]::after { content: "O assistente pode cometer erros. Confira os números e as páginas citadas.";
  display: block; text-align: center; font-size: 12px; color: #98A2B3; padding-top: .45rem; }
</style>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------ identidade do usuário
cabecalhos = st.context.headers
EMAIL = cabecalhos.get("x-forwarded-email") or os.environ.get("DEV_USER_EMAIL", "")
TOKEN_USUARIO = cabecalhos.get("x-forwarded-access-token") or os.environ.get("DEV_USER_TOKEN", "")

if not EMAIL:
    st.error("Não foi possível identificar o usuário. Verifique a configuração do app.")
    st.stop()


def _primeiro_nome(email: str) -> str:
    parte = email.split("@")[0].replace("_", ".").split(".")[0]
    return parte.capitalize() if parte else ""


def _iniciais(email: str) -> str:
    partes = [p for p in email.split("@")[0].replace("_", ".").split(".") if p]
    return "".join(p[0] for p in partes[:2]).upper() or "U"


# ------------------------------------------------------------------ estado e conexão
ss = st.session_state
ss.setdefault("sessao_atual", None)  # None = conversa nova, ainda não gravada no Lakebase
ss.setdefault("mensagens", {})  # session_id -> lista de mensagens (dicts) para a UI
ss.setdefault("pendente", None)  # pergunta vinda de um botão de sugestão


@st.cache_resource(show_spinner=False)
def _preparar_lakebase() -> None:
    with lakebase.conectar() as conn:
        lakebase.criar_tabelas_do_app(conn)


try:
    _preparar_lakebase()
except Exception as e:  # mostra o erro para o workshop, sem derrubar a página
    st.error(
        "Não foi possível conectar ao Lakebase. Confira o recurso `postgres` do app, a variável "
        f"LAKEBASE_ENDPOINT e as permissões da role do app.\n\nDetalhe: {e}"
    )
    st.stop()


def _abrir_conversa(session_id):
    ss.sessao_atual = session_id


def _enviar(pergunta: str):
    ss.pendente = pergunta


# ------------------------------------------------------------------ barra lateral
def _grupo(data) -> str:
    if data is None:
        return "Mais antigas"
    agora = datetime.now(timezone.utc)
    if data.tzinfo is None:
        data = data.replace(tzinfo=timezone.utc)
    if data.date() == agora.date():
        return "Hoje"
    if agora - data <= timedelta(days=7):
        return "Últimos 7 dias"
    return "Mais antigas"


with st.sidebar:
    st.markdown(
        """<div class="marca"><div class="logo">AR</div>
        <div><div class="nome">Assistente Regulatório</div><div class="sub">Indicadores · Tarifas · Relatório</div></div></div>""",
        unsafe_allow_html=True,
    )
    st.button(
        "Nova conversa", key="nova_conversa", icon=":material/edit_square:",
        on_click=_abrir_conversa, args=(None,), width="stretch",
    )

    with lakebase.conectar() as conn:
        sessoes = [s for s in lakebase.listar_sessoes(conn, EMAIL) if s["titulo"] != TITULO_PADRAO]
    if not sessoes:
        st.caption("Suas conversas aparecem aqui.")
    grupo_atual = None
    for s in sessoes:
        grupo = _grupo(s["atualizado_em"])
        if grupo != grupo_atual:
            st.markdown(f'<div class="grupo">{grupo}</div>', unsafe_allow_html=True)
            grupo_atual = grupo
        st.button(
            s["titulo"], key=f"sessao_{s['session_id']}", help=s["titulo"],
            type="primary" if s["session_id"] == ss.sessao_atual else "secondary",
            on_click=_abrir_conversa, args=(s["session_id"],), width="stretch",
        )

    st.markdown(
        f"""<div class="usuario"><div class="avatar">{html.escape(_iniciais(EMAIL))}</div>
        <div class="email">{html.escape(EMAIL)}</div></div>""",
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------------ entrada do usuário
pergunta = st.chat_input("Pergunte sobre indicadores, tarifas ou o relatório regulatório")
if not pergunta and ss.pendente:
    pergunta, ss.pendente = ss.pendente, None

sid = ss.sessao_atual
if pergunta:
    if sid is None:
        with lakebase.conectar() as conn:
            sid = lakebase.nova_sessao(conn, EMAIL, titulo=pergunta[:60])
        ss.sessao_atual = sid
        ss.mensagens[sid] = []
    ss.mensagens.setdefault(sid, [])
    ss.mensagens[sid].append({"papel": "user", "texto": pergunta, "artefatos": [], "sugestoes": []})

if sid is not None and sid not in ss.mensagens:
    with st.spinner("Recuperando conversa..."):
        ss.mensagens[sid] = agente.carregar_historico(EMAIL, TOKEN_USUARIO, sid)

mensagens = ss.mensagens.get(sid, []) if sid else []


# ------------------------------------------------------------------ renderização
def _mostrar_resultado(tabela: dict, chave: str):
    df = graficos.dataframe(tabela)
    with st.container(border=True, key=f"resultado_{chave}"):
        titulo = html.escape(tabela.get("titulo") or "Resultado da consulta")
        st.markdown(
            f'<div class="resultado-titulo"><span class="selo">Genie</span>{titulo}</div>',
            unsafe_allow_html=True,
        )
        desenhado = False
        if tabela.get("grafico"):
            grafico = graficos.grafico(df)
            if grafico is not None:
                st.altair_chart(grafico, width="stretch", theme=None, key=f"grafico_{chave}")
                desenhado = True
            elif tabela.get("png_b64"):
                st.image(base64.b64decode(tabela["png_b64"]), width="stretch")
                desenhado = True
        tabela_df = df.rename(columns=graficos.rotulo)
        if not desenhado and len(df):
            st.dataframe(tabela_df, hide_index=True, width="stretch", height=min(36 * (len(df) + 1) + 4, 320))
        with st.expander("Ver dados e SQL" if desenhado else "Ver SQL"):
            if desenhado:
                st.dataframe(tabela_df, hide_index=True, width="stretch", height=min(36 * (len(df) + 1) + 4, 320))
            if tabela.get("sql"):
                st.code(tabela["sql"], language="sql")


def _markdown(texto: str):
    # "R$ 6,03 ... R$ 6,42" seria interpretado como fórmula LaTeX pelo Streamlit.
    st.markdown((texto or "").replace("$", "\\$"))


def _mostrar_mensagem(m: dict, indice: int, ultima: bool):
    if m["papel"] == "user":
        with st.chat_message("user"):
            _markdown(m["texto"])
        return
    with st.chat_message("assistant", avatar=AVATAR_ASSISTENTE):
        _markdown(m["texto"])
        for j, tabela in enumerate(m.get("artefatos") or []):
            _mostrar_resultado(tabela, f"{indice}_{j}")
        if ultima and m.get("sugestoes"):
            with st.container(key=f"seguir_{indice}"):
                for k, sugestao in enumerate(m["sugestoes"]):
                    st.button(
                        sugestao, key=f"proxima_{indice}_{k}", type="tertiary", wrap=True,
                        icon=":material/subdirectory_arrow_right:", on_click=_enviar, args=(sugestao,),
                    )


if not mensagens:
    nome = html.escape(_primeiro_nome(EMAIL))
    st.markdown(
        f"""<div class="saudacao"><h1>Olá{', ' + nome if nome else ''}. Como posso ajudar?</h1>
        <p>Pergunte sobre indicadores operacionais, tarifas ou o relatório regulatório anual.</p></div>""",
        unsafe_allow_html=True,
    )
    colunas = st.columns(2)
    for i, (icone, texto) in enumerate(SUGESTOES_INICIAIS):
        with colunas[i % 2]:
            st.button(
                texto, key=f"sugestao_{i}", icon=icone, wrap=True,
                on_click=_enviar, args=(texto,), width="stretch",
            )
    if not TOKEN_USUARIO:
        st.info(
            "Token de usuário (OBO) não encontrado. A consulta ao Genie precisa da autorização de usuário "
            "habilitada no app (escopos sql, genie e ai-gateway).",
            icon=":material/info:",
        )

aguardando_resposta = bool(mensagens) and mensagens[-1]["papel"] == "user"
for i, m in enumerate(mensagens):
    _mostrar_mensagem(m, i, ultima=(i == len(mensagens) - 1))

# ------------------------------------------------------------------ resposta do agente
if pergunta and aguardando_resposta:
    with st.chat_message("assistant", avatar=AVATAR_ASSISTENTE):
        status = st.status("Analisando a pergunta...", expanded=False)

        def _progresso(nomes):
            status.update(label=" · ".join(ROTULOS_FERRAMENTAS.get(n, n) for n in nomes) + "...")

        try:
            r = agente.turno(EMAIL, TOKEN_USUARIO, sid, pergunta, ao_progresso=_progresso)
            status.update(label="Resposta pronta", state="complete")
        except Exception as e:
            r = {"texto": f"Não foi possível processar a pergunta: {e}", "artefatos": [], "sugestoes": []}
            status.update(label="Erro ao processar a pergunta", state="error")
    ss.mensagens[sid].append({"papel": "assistant", **r})
    with lakebase.conectar() as conn:
        lakebase.atualizar_sessao(conn, sid)
    st.rerun()
