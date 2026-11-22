# Service Commandes

Microservice **FastAPI** (port `8002`) qui gère les commandes, connecté à une base **PostgreSQL**
dédiée (*Database-per-service*). Il appelle le Catalogue (prix, existence du produit) et
Stocks (réservation). Tout le code est dans `main.py`.

## Endpoints disponibles

- `GET /health` : vérifie que le service et sa base répondent (`200 OK` ou `503`).
- `POST /orders` : crée une commande (`201`, ou `404` produit inconnu, `409` stock insuffisant, `503` service indisponible).
- `GET /orders` : liste les commandes, filtres `customer_id` et `status` (`200 OK`).
- `GET /orders/{order_id}` : consulte une commande (`200 OK` ou `404`).
- `POST /orders/{order_id}/cancel` : annule une commande validée et rend le stock (`200`, `404`, `409` ou `503`).

Exemple : `POST /orders` avec `{"customer_id": "c1", "items": [{"product_id": 1, "quantity": 2}]}`

Statuts : `EN_ATTENTE` → `VALIDEE` ou `REFUSEE`, puis `VALIDEE` → `ANNULEE`.

## Tables (créées automatiquement)

- `orders` : id, customer_id, status, total, reject_reason, created_at
- `order_items` : id, order_id, product_id, quantity, unit_price (prix figé à la commande)

## Services appelés

- Catalogue : `GET /articles/{id}` → `{"id", "nom", "prix", "description"}`
- Stocks : `POST /stocks/{product_id}/reserve` et `/release`, corps `{"quantity": 2, "order_id": 7}`
  (`reserve` répond 409 si le stock est insuffisant)

## Lancement en local (PowerShell)

Avec la base lancée par Docker Compose (port 5435) :

```powershell
pip install -r requirements.txt
uvicorn main:app --reload --port 8002
```

Variables d'environnement : `DATABASE_URL`, `CATALOGUE_URL`, `STOCKS_URL`.

## Dossier `mocks`

`mocks/fake_services.py` contient un faux Stocks temporaire (produits 1 à 4), utilisé par le
conteneur `stocks-notifications` tant que le vrai service n'est pas livré.
