import os
from collections.abc import Generator
from typing import Optional

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Response, status
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

app = FastAPI(
    title="Service Catalogue / Produits",
    description="Microservice de gestion des produits et articles",
    version="1.0.0",
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/catalogue_db",
)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS articles (
    id SERIAL PRIMARY KEY,
    nom VARCHAR(120) NOT NULL,
    prix NUMERIC(10, 2) NOT NULL,
    description TEXT
);
"""


class ArticleCreate(BaseModel):
    nom: str = Field(..., min_length=1, max_length=120)
    prix: float = Field(..., gt=0)
    description: Optional[str] = Field(default=None, max_length=500)


class ArticleUpdate(BaseModel):
    nom: Optional[str] = Field(default=None, min_length=1, max_length=120)
    prix: Optional[float] = Field(default=None, gt=0)
    description: Optional[str] = Field(default=None, max_length=500)


class ArticleResponse(BaseModel):
    id: int
    nom: str
    prix: float
    description: Optional[str] = None


def open_connection(connect_timeout: int = 2) -> psycopg.Connection:
    try:
        return psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
            connect_timeout=connect_timeout,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Base de données indisponible : {exc}",
        )


def get_db() -> Generator[psycopg.Connection, None, None]:
    conn = open_connection()
    try:
        yield conn
    finally:
        if not conn.closed:
            conn.close()


def ensure_schema(conn: psycopg.Connection) -> None:
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)


def serialize_article(row: dict) -> dict:
    return {
        "id": row["id"],
        "nom": row["nom"],
        "prix": float(row["prix"]),
        "description": row["description"],
    }


@app.on_event("startup")
def on_startup() -> None:
    try:
        with psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
            connect_timeout=2,
        ) as conn:
            ensure_schema(conn)
    except Exception:
        pass


@app.get("/health")
def health_check(db: psycopg.Connection = Depends(get_db)):
    with db.cursor() as cur:
        cur.execute("SELECT 1;")
        cur.fetchone()
    return {"status": "ok", "service": "catalogue", "database": "up"}


@app.get("/articles", response_model=list[ArticleResponse])
def list_articles(db: psycopg.Connection = Depends(get_db)):
    ensure_schema(db)
    with db.cursor() as cur:
        cur.execute("SELECT id, nom, prix, description FROM articles ORDER BY id ASC;")
        rows = cur.fetchall()
        return [serialize_article(row) for row in rows]


@app.get("/articles/{article_id}", response_model=ArticleResponse)
def get_article(article_id: int, db: psycopg.Connection = Depends(get_db)):
    ensure_schema(db)
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, nom, prix, description FROM articles WHERE id = %s;",
            (article_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Article introuvable",
            )
        return serialize_article(row)


@app.post(
    "/articles",
    response_model=ArticleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_article(article: ArticleCreate, db: psycopg.Connection = Depends(get_db)):
    ensure_schema(db)
    with db.transaction():
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO articles (nom, prix, description)
                VALUES (%s, %s, %s)
                RETURNING id, nom, prix, description;
                """,
                (article.nom, article.prix, article.description),
            )
            row = cur.fetchone()
            return serialize_article(row)


@app.put("/articles/{article_id}", response_model=ArticleResponse)
def update_article(
    article_id: int,
    article: ArticleUpdate,
    db: psycopg.Connection = Depends(get_db),
):
    updates = article.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aucun champ à mettre à jour",
        )

    ensure_schema(db)
    with db.transaction():
        with db.cursor() as cur:
            cur.execute(
                "SELECT id, nom, prix, description FROM articles WHERE id = %s;",
                (article_id,),
            )
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Article introuvable",
                )

            new_nom = updates.get("nom", existing["nom"])
            new_prix = updates.get("prix", existing["prix"])
            new_description = updates.get("description", existing["description"])

            cur.execute(
                """
                UPDATE articles
                SET nom = %s, prix = %s, description = %s
                WHERE id = %s
                RETURNING id, nom, prix, description;
                """,
                (new_nom, new_prix, new_description, article_id),
            )
            row = cur.fetchone()
            return serialize_article(row)


@app.delete("/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_article(article_id: int, db: psycopg.Connection = Depends(get_db)):
    ensure_schema(db)
    with db.transaction():
        with db.cursor() as cur:
            cur.execute(
                "DELETE FROM articles WHERE id = %s RETURNING id;",
                (article_id,),
            )
            deleted = cur.fetchone()
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Article introuvable",
                )
    return Response(status_code=status.HTTP_204_NO_CONTENT)