import os
from collections.abc import Generator
from datetime import datetime
from typing import Optional

import httpx
import psycopg
from fastapi import Depends, FastAPI, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

app = FastAPI(
    title="Service Commandes",
    description="Microservice de gestion des commandes",
    version="1.0.0",
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://orders:orders@localhost:5435/orders",
).replace("postgresql+psycopg2://", "postgresql://")
CATALOGUE_URL = os.getenv("CATALOGUE_URL", "http://service-produits:8001")
STOCKS_URL = os.getenv("STOCKS_URL", "http://stocks-notifications:8003")
TIMEOUT = 3  # secondes, par appel vers un autre service

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'EN_ATTENTE',
    total NUMERIC(12, 2) NOT NULL DEFAULT 0,
    reject_reason VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
);
"""


class OrderItemIn(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0, le=1000)


class OrderCreate(BaseModel):
    customer_id: str = Field(..., min_length=1, max_length=64)
    items: list[OrderItemIn] = Field(..., min_length=1, max_length=50)


class OrderItemResponse(BaseModel):
    product_id: int
    quantity: int
    unit_price: float


class OrderResponse(BaseModel):
    id: int
    customer_id: str
    status: str
    total: float
    reject_reason: Optional[str] = None
    created_at: datetime
    items: list[OrderItemResponse]


def get_db() -> Generator[psycopg.Connection, None, None]:
    try:
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=2)
    except Exception as exc:
        raise HTTPException(503, f"Base de données indisponible : {exc}")
    try:
        conn.execute(CREATE_TABLES_SQL)  # crée les tables si elles n'existent pas
        conn.commit()
        yield conn
    finally:
        conn.close()


def call_service(service: str, method: str, url: str, **kwargs) -> httpx.Response:
    """Appelle un autre service : 503 s'il ne répond pas ou s'il est en erreur."""
    try:
        resp = httpx.request(method, url, timeout=TIMEOUT, **kwargs)
    except httpx.HTTPError:
        raise HTTPException(503, f"Service {service} indisponible")
    if resp.status_code >= 500:
        raise HTTPException(503, f"Service {service} indisponible")
    return resp


def get_price(product_id: int) -> float:
    """Demande le prix d'un article au Catalogue."""
    resp = call_service("catalogue", "GET", f"{CATALOGUE_URL}/articles/{product_id}")
    if resp.status_code == 404:
        raise HTTPException(404, f"Produit {product_id} introuvable")
    if resp.status_code != 200:
        raise HTTPException(502, f"Réponse inattendue du catalogue ({resp.status_code})")
    return resp.json()["prix"]


def stock_call(product_id: int, action: str, quantity: int, order_id: int) -> None:
    """Demande à Stocks de réserver ('reserve') ou de rendre ('release') une quantité."""
    resp = call_service(
        "stocks", "POST", f"{STOCKS_URL}/stocks/{product_id}/{action}",
        json={"quantity": quantity, "order_id": order_id},
    )
    if resp.status_code == 409:
        raise HTTPException(409, f"Stock insuffisant pour le produit {product_id}")
    if resp.status_code == 404:
        raise HTTPException(404, f"Produit {product_id} inconnu du service Stocks")
    if resp.status_code >= 400:
        raise HTTPException(502, f"Réponse inattendue de Stocks ({resp.status_code})")


def load_order(db: psycopg.Connection, order_id: int) -> dict:
    order = db.execute(
        "SELECT id, customer_id, status, total, reject_reason, created_at "
        "FROM orders WHERE id = %s;",
        (order_id,),
    ).fetchone()
    if not order:
        raise HTTPException(404, f"Commande {order_id} introuvable")
    order["items"] = db.execute(
        "SELECT product_id, quantity, unit_price FROM order_items "
        "WHERE order_id = %s ORDER BY id;",
        (order_id,),
    ).fetchall()
    return order


@app.get("/health")
def health_check(db: psycopg.Connection = Depends(get_db)):
    db.execute("SELECT 1;")
    return {"status": "ok", "service": "commandes", "database": "up"}


@app.post("/orders", response_model=OrderResponse, status_code=201)
def create_order(payload: OrderCreate, db: psycopg.Connection = Depends(get_db)):
    # 1. On enregistre la commande EN_ATTENTE (trace conservée même en cas de panne)
    order_id = db.execute(
        "INSERT INTO orders (customer_id) VALUES (%s) RETURNING id;",
        (payload.customer_id,),
    ).fetchone()["id"]
    db.commit()

    items, reserved, total = [], [], 0.0
    try:
        # 2. Catalogue : le produit existe-t-il ? quel prix ?
        for line in payload.items:
            price = get_price(line.product_id)
            items.append((line.product_id, line.quantity, price))
            total += price * line.quantity
        # 3. Stocks : on réserve chaque ligne
        for product_id, quantity, _ in items:
            stock_call(product_id, "reserve", quantity, order_id)
            reserved.append((product_id, quantity))
    except HTTPException as exc:
        # Échec : on rend le stock déjà réservé (compensation) et on refuse la commande
        for product_id, quantity in reserved:
            try:
                stock_call(product_id, "release", quantity, order_id)
            except HTTPException:
                pass
        db.execute(
            "UPDATE orders SET status = 'REFUSEE', reject_reason = %s WHERE id = %s;",
            (str(exc.detail)[:255], order_id),
        )
        db.commit()
        raise HTTPException(exc.status_code, f"{exc.detail} (commande {order_id} refusée)")

    # 4. Tout est bon : on enregistre les lignes et on valide la commande
    for product_id, quantity, price in items:
        db.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
            "VALUES (%s, %s, %s, %s);",
            (order_id, product_id, quantity, price),
        )
    db.execute(
        "UPDATE orders SET status = 'VALIDEE', total = %s WHERE id = %s;",
        (round(total, 2), order_id),
    )
    db.commit()
    return load_order(db, order_id)


@app.get("/orders", response_model=list[OrderResponse])
def list_orders(
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    db: psycopg.Connection = Depends(get_db),
):
    rows = db.execute(
        "SELECT id FROM orders "
        "WHERE (%s::text IS NULL OR customer_id = %s) "
        "AND (%s::text IS NULL OR status = %s) ORDER BY id DESC;",
        (customer_id, customer_id, status, status),
    ).fetchall()
    return [load_order(db, row["id"]) for row in rows]


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, db: psycopg.Connection = Depends(get_db)):
    return load_order(db, order_id)


@app.post("/orders/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(order_id: int, db: psycopg.Connection = Depends(get_db)):
    order = load_order(db, order_id)
    if order["status"] != "VALIDEE":
        raise HTTPException(409, f"Une commande {order['status']} ne peut pas être annulée")
    # On rend le stock ; si Stocks est en panne : 503 et le statut ne change pas
    for item in order["items"]:
        stock_call(item["product_id"], "release", item["quantity"], order_id)
    db.execute("UPDATE orders SET status = 'ANNULEE' WHERE id = %s;", (order_id,))
    db.commit()
    return load_order(db, order_id)
