"""Acesso ao Lakebase (Postgres) usado pelo app.

O Lakebase guarda três coisas no workshop:
  1. documentos_chunks  -> dados NÃO estruturados (trechos do PDF + embedding pgvector)
  2. sessoes / checkpoints -> sessões de conversa (histórico recuperável)
  3. memorias_usuario   -> memória de longo prazo por usuário (embedding pgvector)

Autenticação: token OAuth do próprio service principal do app (não do usuário).
O isolamento por usuário é feito pela coluna user_email em todas as consultas.
"""

import os
import uuid

import psycopg
from databricks.sdk import WorkspaceClient

DIM_EMBEDDING = 1024


def _cliente_sp() -> WorkspaceClient:
    # Dentro do Databricks Apps usa as credenciais do service principal do app.
    return WorkspaceClient()


def conectar(row_factory=None) -> psycopg.Connection:
    """Abre uma conexão nova com token OAuth (o token expira em ~60 min, então não guardamos conexões)."""
    endpoint = os.environ["LAKEBASE_ENDPOINT"]  # valueFrom: postgres (app.yaml)
    host = os.environ["PGHOST"]  # injetado pelo recurso postgres do app
    user = os.environ.get("PGUSER") or os.environ["DATABRICKS_CLIENT_ID"]
    token = _cliente_sp().postgres.generate_database_credential(endpoint=endpoint).token
    kwargs = {"row_factory": row_factory} if row_factory else {}
    return psycopg.connect(
        host=host,
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ.get("PGDATABASE", "databricks_postgres"),
        user=user,
        password=token,
        sslmode=os.environ.get("PGSSLMODE", "require"),
        autocommit=True,
        **kwargs,
    )


def _tabela_existe(conn: psycopg.Connection, nome: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{nome}",)).fetchone()[0]


def criar_tabelas_do_app(conn: psycopg.Connection) -> None:
    """Cria as tabelas próprias do app se ainda não existirem.

    As tabelas são criadas pelo notebook guia (com o usuário do workshop); aqui só há criação
    de fallback, então a role do app não precisa de CREATE no schema public para rodar normalmente.
    """
    if not _tabela_existe(conn, "sessoes"):
        conn.execute(
            """
            CREATE TABLE public.sessoes (
                session_id   UUID PRIMARY KEY,
                user_email   TEXT NOT NULL,
                titulo       TEXT NOT NULL,
                criado_em    TIMESTAMPTZ NOT NULL DEFAULT now(),
                atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
            )"""
        )
    if not _tabela_existe(conn, "memorias_usuario"):
        conn.execute(
            f"""
            CREATE TABLE public.memorias_usuario (
                id          SERIAL PRIMARY KEY,
                user_email  TEXT NOT NULL,
                memoria     TEXT NOT NULL,
                embedding   vector({DIM_EMBEDDING}) NOT NULL,
                criado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
            )"""
        )


# ------------------------------------------------------------------ sessões
def nova_sessao(conn, user_email: str, titulo: str = "Nova conversa") -> str:
    sid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO public.sessoes (session_id, user_email, titulo) VALUES (%s, %s, %s)",
        (sid, user_email, titulo[:80]),
    )
    return sid


def listar_sessoes(conn, user_email: str) -> list[dict]:
    rows = conn.execute(
        """SELECT session_id::text, titulo, atualizado_em
           FROM public.sessoes WHERE user_email = %s
           ORDER BY atualizado_em DESC LIMIT 30""",
        (user_email,),
    ).fetchall()
    return [{"session_id": r[0], "titulo": r[1], "atualizado_em": r[2]} for r in rows]


def sessao_pertence_ao_usuario(conn, user_email: str, session_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM public.sessoes WHERE session_id = %s AND user_email = %s",
        (session_id, user_email),
    ).fetchone()
    return row is not None


def atualizar_sessao(conn, session_id: str, titulo: str | None = None) -> None:
    if titulo:
        conn.execute(
            "UPDATE public.sessoes SET atualizado_em = now(), titulo = CASE WHEN titulo = 'Nova conversa' THEN %s ELSE titulo END WHERE session_id = %s",
            (titulo[:80], session_id),
        )
    else:
        conn.execute("UPDATE public.sessoes SET atualizado_em = now() WHERE session_id = %s", (session_id,))


# ------------------------------------------------------------------ memória de longo prazo
def salvar_memoria(conn, user_email: str, texto: str, embedding: list[float]) -> bool:
    """Grava a memória do usuário. Retorna False se o mesmo texto já estiver salvo (evita duplicatas)."""
    ja_existe = conn.execute(
        "SELECT 1 FROM public.memorias_usuario WHERE user_email = %s AND memoria = %s LIMIT 1",
        (user_email, texto),
    ).fetchone()
    if ja_existe:
        return False
    conn.execute(
        "INSERT INTO public.memorias_usuario (user_email, memoria, embedding) VALUES (%s, %s, %s::vector)",
        (user_email, texto, _vetor(embedding)),
    )
    return True


def buscar_memorias(conn, user_email: str, embedding: list[float], k: int = 3) -> list[str]:
    rows = conn.execute(
        """SELECT memoria FROM public.memorias_usuario
           WHERE user_email = %s
           ORDER BY embedding <=> %s::vector LIMIT %s""",
        (user_email, _vetor(embedding), k),
    ).fetchall()
    return [r[0] for r in rows]


# ------------------------------------------------------------------ documentos (não estruturados)
def buscar_documentos(conn, embedding: list[float], k: int = 3) -> list[dict]:
    tabela = os.environ.get("DOCUMENTOS_TABELA", "documentos_chunks")
    rows = conn.execute(
        f"""SELECT documento, pagina, conteudo, 1 - (embedding <=> %s::vector) AS score
            FROM public.{tabela}
            ORDER BY embedding <=> %s::vector LIMIT %s""",
        (_vetor(embedding), _vetor(embedding), k),
    ).fetchall()
    return [{"documento": r[0], "pagina": r[1], "conteudo": r[2], "score": float(r[3])} for r in rows]


def _vetor(valores: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in valores) + "]"
