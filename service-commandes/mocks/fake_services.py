"""Faux service Stocks (port 8003), temporaire.

Utilisé par le conteneur `stocks-notifications` tant que le vrai service Stocks n'est pas livré.
Le Catalogue, lui, est le vrai service-produits : il n'y a plus de faux Catalogue.
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

stocks = FastAPI(title="Faux Stocks")

STOCK = {1: 10, 2: 5, 3: 0, 4: 20}  # le produit 3 est en rupture


class StockOp(BaseModel):
    quantity: int
    order_id: int


@stocks.get("/health")
def stock_health():
    return {"status": "ok", "service": "faux-stocks"}


@stocks.get("/stocks")
def all_stocks():
    return STOCK


@stocks.post("/stocks/{product_id}/reserve")
def reserve(product_id: int, op: StockOp):
    if product_id not in STOCK:
        raise HTTPException(404, "Produit inconnu")
    if STOCK[product_id] < op.quantity:
        return JSONResponse(status_code=409, content={"detail": "Stock insuffisant"})
    STOCK[product_id] -= op.quantity
    print(f"[NOTIF simulée] commande {op.order_id}: produit {product_id} -{op.quantity}")
    return {"product_id": product_id, "remaining": STOCK[product_id]}


@stocks.post("/stocks/{product_id}/release")
def release(product_id: int, op: StockOp):
    if product_id not in STOCK:
        raise HTTPException(404, "Produit inconnu")
    STOCK[product_id] += op.quantity
    return {"product_id": product_id, "remaining": STOCK[product_id]}
