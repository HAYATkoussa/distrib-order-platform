from fastapi import FastAPI

app = FastAPI(title="Service Produits")

@app.get("/")
def read_root():
    return {"message": "Bienvenue sur le Service Produits de notre architecture distribuée !"}

@app.get("/produits")
def get_produits():
    # Exemple de données simulées pour l'instant
    return [
        {"id": 1, "nom": "Graines bio", "stock": 50},
        {"id": 2, "nom": "Engrais naturel", "stock": 30}
    ]