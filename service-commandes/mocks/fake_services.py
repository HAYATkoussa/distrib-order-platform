"""Faux services Catalogue et Stocks pour tester le service Commandes seul.

Lancement (depuis le dossier service-commandes) :
    uvicorn mocks.fake_services:catalogue --port 8001
    uvicorn mocks.fake_services:stocks --port 8003
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ---------------- Faux Catalogue (8001) ----------------
catalogue = FastAPI(title="Faux Catalogue")

# Même format que le vrai service-produits : /articles/{id} avec nom et prix
PRODUCTS = {
    1: {"id": 1, "nom": "Clavier", "prix": 25.0, "description": None},
    2: {"id": 2, "nom": "Souris", "prix": 10.5, "description": None},
    3: {"id": 3, "nom": "Écran", "prix": 149.9, "description": None},
}


@catalogue.get("/health")
def cat_health():
    return {"status": "ok", "service": "faux-catalogue"}


@catalogue.get("/articles/{product_id}")
def get_product(product_id: int):
    if product_id not in PRODUCTS:
        raise HTTPException(404, "Article introuvable")
    return PRODUCTS[product_id]


# ---------------- Faux Stocks (8003) ----------------
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
