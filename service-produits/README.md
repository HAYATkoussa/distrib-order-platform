# Service Produits / Catalogue

Microservice **FastAPI** (port `8001`) responsable de la gestion des articles du catalogue, connecté à une base **PostgreSQL** dédiée (*Database-per-service*).

## Endpoints disponibles

- `GET /health` : vérifie que le service et la base PostgreSQL répondent (`200 OK` ou `503 Service Unavailable`).
- `GET /articles` : liste tous les articles (`200 OK`).
- `GET /articles/{article_id}` : récupère un article par ID (`200 OK` ou `404 Not Found`).
- `POST /articles` : crée un article (`201 Created`).
- `PUT /articles/{article_id}` : met à jour un article (`200 OK`, `400 Bad Request` ou `404 Not Found`).
- `DELETE /articles/{article_id}` : supprime un article (`204 No Content` ou `404 Not Found`).

## Lancement en local (PowerShell)

Depuis la racine du dépôt (`distrib-order-platform`) avec l'environnement virtuel activé :

```powershell
uvicorn service-produits.main:app --reload --port 8001