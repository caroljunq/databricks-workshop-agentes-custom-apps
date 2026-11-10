"""Teste ponta a ponta do agente (sem UI), usando o app/ deste repositório.

Verifica:
  1. Criação das tabelas do app no Lakebase (sessoes, memorias_usuario) e do checkpoint.
  2. Conversa multi-turno em uma sessão (memória de curto prazo via checkpoint).
  3. Consulta ao Genie (tool consultar_dados).
  4. Busca de trechos do relatório no Lakebase (tool buscar_documentos).
  5. Memória de longo prazo entre sessões (salvar_memoria / buscar_memorias).
  6. Recuperação do histórico de uma sessão anterior.

Pré-requisitos de ambiente (exemplo para teste local — NÃO use em produção):
    export DATABRICKS_CONFIG_PROFILE=<seu-profile>
    export DATABRICKS_HOST=https://<seu-workspace>.cloud.databricks.com
    export DEV_USER_EMAIL=<seu-email>
    export DEV_USER_TOKEN=$(databricks auth token -p <seu-profile> -o json | jq -r .access_token)
    export LAKEBASE_ENDPOINT=projects/workshop-agentes-<prefixo>/branches/production/endpoints/primary
    export PGHOST=<host do endpoint do Lakebase (Seção 4 do notebook)>
    export PGUSER=<seu-email>
    export MODEL_ENDPOINT=system.ai.claude-sonnet-5-5
    export EMBEDDING_ENDPOINT=system.ai.qwen3-embedding-0-6b
    export GENIE_SPACE_ID=<ID do Genie Space>
    export DOCUMENTOS_TABELA=documentos_chunks

Uso:
    python scripts/testar_agente_local.py
"""

import os
import sys
import time
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

import agente  # noqa: E402
import lakebase  # noqa: E402

EMAIL = os.environ["DEV_USER_EMAIL"]
TOKEN = os.environ.get("DEV_USER_TOKEN", "")


def secao(titulo):
    print("\n" + "=" * 90 + f"\n{titulo}\n" + "=" * 90)


def mostrar(pergunta, resposta, inicio):
    print(f"\n👤 {pergunta}\n🤖 ({time.time() - inicio:.1f}s)\n{resposta}")


secao("1) Tabelas do app no Lakebase")
with lakebase.conectar() as conn:
    lakebase.criar_tabelas_do_app(conn)
    n_chunks = conn.execute("SELECT count(*) FROM public.documentos_chunks").fetchone()[0]
print(f"documentos_chunks: {n_chunks} linhas  |  tabelas sessoes/memorias_usuario: OK")
assert n_chunks > 0, "Carregue os chunks do relatório antes (Seção 3 do notebook)."

with lakebase.conectar() as conn:
    sessao_1 = lakebase.nova_sessao(conn, EMAIL, "Teste sessao 1")
print(f"sessão 1: {sessao_1}")

secao("2) Conversa multi-turno (sessão 1)")
turnos = [
    "Qual foi a média de perdas de gás em 2025 e qual era a meta regulatória? Responda com os números.",
    "E qual região teve o maior tempo médio de emergência em 2025?",
]
for pergunta in turnos:
    inicio = time.time()
    resposta = agente.turno(EMAIL, TOKEN, sessao_1, pergunta)["texto"]
    mostrar(pergunta, resposta, inicio)
    assert resposta and "Erro" not in resposta[:20], "Resposta com erro"

secao("3) Tool de documentos (Lakebase / pgvector)")
inicio = time.time()
pergunta = "O que o relatório diz sobre o evento climático no Litoral em julho de 2024? Cite a página."
resposta = agente.turno(EMAIL, TOKEN, sessao_1, pergunta)["texto"]
mostrar(pergunta, resposta, inicio)

secao("4) Memória de longo prazo entre sessões")
inicio = time.time()
pergunta = "Lembre que eu prefiro respostas com tabelas sempre que houver números."
resposta = agente.turno(EMAIL, TOKEN, sessao_1, pergunta)["texto"]
mostrar(pergunta, resposta, inicio)

with lakebase.conectar() as conn:
    sessao_2 = lakebase.nova_sessao(conn, EMAIL, "Teste sessao 2")
print(f"\nsessão 2 (nova, sem histórico da sessão 1): {sessao_2}")
inicio = time.time()
pergunta = "Quais são as minhas preferências de formato de resposta?"
resposta = agente.turno(EMAIL, TOKEN, sessao_2, pergunta)["texto"]
mostrar(pergunta, resposta, inicio)

secao("5) Recuperação do histórico da sessão 1")
historico = agente.carregar_historico(EMAIL, TOKEN, sessao_1)
print(f"mensagens recuperadas da sessão 1: {len(historico)}")
for m in historico[:4]:
    print(f"- [{m['papel']}] {m['texto'][:110].replace(chr(10), ' ')}... ({len(m['artefatos'])} resultado(s) do Genie)")
assert len(historico) >= 4, "Histórico da sessão 1 não foi recuperado do Lakebase"

secao("Resultado")
print("Todos os passos executaram. Revise as respostas acima antes de usar no workshop.")
