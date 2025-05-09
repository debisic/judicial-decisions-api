'''API for fetching decisions from the database.'''

import logging
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn

# Load environment variables from .env file
load_dotenv()

app = FastAPI()
security = HTTPBasic()

# In-memory user store for simplicity
users = {
    "admin": "password"
}

# Database configuration from environment variables
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_HOST = os.getenv("POSTGRES_HOST")
DB_PORT = os.getenv("POSTGRES_PORT")
DB_NAME = os.getenv("POSTGRES_DB")

# Create SQLAlchemy engine and session
engine = create_engine(f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    '''Provide a database session.'''
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    '''Authenticate the user using HTTP Basic Auth.'''
    logging.info("Authenticating user: %s", credentials.username)
    if credentials.username in users and users[credentials.username] == credentials.password:
        return credentials.username
    raise HTTPException(status_code=401, detail="Invalid credentials")

class Decision(BaseModel):
    '''Pydantic model for a decision.'''
    text_id: str
    titre: str
    chambre: str

@app.get("/")
def read_root():
    '''Root endpoint.'''
    return {"Instruction": "put <</decisions>> without the arrows."}

@app.get("/decisions", response_model=list[Decision])
def get_decisions(
    chambre: str = None,
    search: str = None,
    username: str = Depends(authenticate),
    db: SessionLocal = Depends(get_db)
):
    '''Get a list of decisions, optionally filtered by chambre or searched by text.'''
    logging.info("Authenticated user: %s", username)
    logging.info("Fetching decisions for chambre: %s, search: %s", chambre, search)

    if search:
        # Full-text search on titre and chambre OR substring search on contenu
        query = text("""
            SELECT text_id, titre, chambre, 
                   ts_rank(to_tsvector('english', titre || ' ' || chambre), plainto_tsquery(:search)) AS relevance
            FROM court_history
            WHERE (to_tsvector('english', titre || ' ' || chambre) @@ plainto_tsquery(:search))
               OR (contenu::text ILIKE :pattern)
            ORDER BY relevance DESC
        """)
        # Add wildcards around the search term for the ILIKE comparison.
        result = db.execute(query, {"search": search, "pattern": f"%{search}%"}).fetchall()
    # elif chambre:
    #     # Filter by chambre
    #     query = text(
    #         "SELECT text_id, titre, \
    #             chambre FROM court_history \
    #             WHERE TRIM(chambre) ILIKE:chambre")
    #     result = db.execute(query, {"chambre": chambre}).fetchall()
    elif chambre:
        if chambre.lower() == "empty" or chambre.lower() == "null":
        # Query for rows where chambre is NULL or an empty string
            query = text(
                "SELECT text_id, \
                    titre, \
                    chambre \
                    FROM court_history \
                    WHERE chambre IS NULL \
                    OR TRIM(chambre) = ''")
            result = db.execute(query).fetchall()
        else:
        # Filter by chambre (case-insensitive, trim whitespace)
            query = text(
                "SELECT text_id, \
                titre, \
                chambre \
                FROM court_history \
                WHERE TRIM(chambre) ILIKE :chambre")
            result = db.execute(query, {"chambre": chambre}).fetchall()
    else:
        # Fetch all decisions
        query = text("SELECT text_id, titre, chambre FROM court_history")
        result = db.execute(query).fetchall()

    return [Decision(text_id=row[0], titre=row[1], chambre=row[2] or "") for row in result]


@app.get("/decisions/{text_id}")
def get_decision_content(
    text_id: str,
    db: SessionLocal = Depends(get_db)
):
    '''Get the content of a decision by its text_id.'''
    query = text("SELECT contenu FROM court_history WHERE text_id = :text_id")
    result = db.execute(query, {"text_id": text_id}).fetchone()
    if result is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    # return {"text_id": text_id, "contenu": result['contenu']}
    return {"text_id": text_id, "contenu": result[0]}


if __name__ == '__main__':
    uvicorn.run(app, host=" 0.0.0.0 ", port=8000)
