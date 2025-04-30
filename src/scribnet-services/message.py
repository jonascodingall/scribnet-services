#!/bin/env python3
import bcrypt, psycopg2
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class Message(BaseModel):
    """
    Modell für Chatnachrichten zwischen Benutzern.
    Attributes:
        sender_id (int): ID des Absenders.
        receiver_id (int): ID des Empfängers.
        content (str): Textinhalt der Nachricht.
        timestamp (int): Unix-Zeitstempel der Nachricht.
    """
    sender_id: int = Field(..., alias="senderId")
    receiver_id: int = Field(..., alias="receiverId")
    content: str
    timestamp: int


class User(BaseModel):
    """
    internes Benutzer-Modell (enthält sensible Daten).
    Attributes:
        id (int): Einzigartige Nutzer-ID.
        username (str): Benutzername.
        email (str): E-Mail-Adresse.
        password (str): Gehashtes Passwort.
        avatar (str): Pfad oder URL zum Avatarbild.
        status (str): Aktueller Status (z.B. "online", "offline").
    """
    id: int
    username: str
    email: str
    password: str
    avatar: str
    status: str


class UserPublic(BaseModel):
    """
    öffentliches Benutzer-Modell (ohne Passwort).
    Attributes:
        id (int): Einzigartige Nutzer-ID.
        username (str): Benutzername.
        email (str): E-Mail-Adresse.
        avatar (str): Pfad oder URL zum Avatarbild.
        status (str): Aktueller Status.
    """
    id: int
    username: str
    email: str
    avatar: str
    status: str


class RegisterRequest(BaseModel):
    """
    Anfrage-Daten für die Benutzerregistrierung.
    Attributes:
        username (str): Gewünschter Benutzername.
        email (str): E-Mail-Adresse für die Registrierung.
        password (str): Klartextpasswort.
    """
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    """
    Anfrage-Daten für das Benutzer-Login.
    Attributes:
        email (str): E-Mail-Adresse.
        password (str): Klartextpasswort.
    """
    email: str
    password: str

# Verbinde mit dem Datenbank Managment System
dbcon = psycopg2.connect(dbname='ScribNET_template', user='oliver', host='localhost')

# Instanziierung der FastAPI-Anwendung
app = FastAPI()

# In-Memory-Datenstrukturen (nur zu Demonstrationszwecken)
connected_users: Dict[int, WebSocket] = {}
message_store: List[Message] = []
user_store: List[User] = [
    User(id=1, username="alice", email="alice@example.com", password=bcrypt.hashpw("1234".encode("utf-8"), bcrypt.gensalt()).decode("utf-8"), avatar="avatar1.png", status="online"),
    User(id=2, username="bob", email="bob@example.com", password=bcrypt.hashpw("1234".encode("utf-8"), bcrypt.gensalt()).decode("utf-8"), avatar="avatar2.png", status="offline"),
    User(id=3, username="carol", email="carol@example.com", password=bcrypt.hashpw("1234".encode("utf-8"), bcrypt.gensalt()).decode("utf-8"), avatar="avatar3.png", status="online"),
    User(id=4, username="dave", email="dave@example.com", password=bcrypt.hashpw("1234".encode("utf-8"), bcrypt.gensalt()).decode("utf-8"), avatar="avatar4.png", status="online"),
    User(id=5, username="eve", email="eve@example.com", password=bcrypt.hashpw("1234".encode("utf-8"), bcrypt.gensalt()).decode("utf-8"), avatar="avatar5.png", status="offline"),
]


@app.websocket("/messages/{user_id}")
async def messages(user_id: int, websocket: WebSocket):
    """
    WebSocket-Endpunkt für bidirektionale Chatkommunikation.
    - Speichert eingehende Nachrichten im `message_store`.
    - Leitet Nachrichten in Echtzeit an verbundene Benutzer weiter.
    """
    await websocket.accept()
    connected_users[user_id] = websocket

    try:
        while True:
            data = await websocket.receive_text()
            msg = Message.model_validate_json(data)
            message_store.append(msg)

            # Nachricht an Empfänger senden, falls online
            receiver_ws: Optional[WebSocket] = connected_users.get(msg.receiver_id)
            if receiver_ws:
                await receiver_ws.send_text(data)

    except WebSocketDisconnect:
        # Entferne Nutzer bei Trennung
        connected_users.pop(user_id, None)
    except Exception as e:
        # Log und Aufräumen bei Fehler
        print(f"WebSocket-Fehler für User {user_id}: {e}")
        connected_users.pop(user_id, None)


@app.get(
    "/messages/{sender_id}/{receiver_id}",
    response_model=List[Message],
    summary="Chatverlauf abrufen",
    tags=["Nachrichten"]
)
def get_messages(sender_id: int, receiver_id: int) -> List[Message]:
    """
    Liefert den gesamten Chatverlauf zwischen zwei Benutzer-IDs.
    """
    with dbcon.cursor() as dbcur:
        dbcur.execute('''SELECT message, creation_timestamp FROM messages WHERE sender_id = %s AND receiver_id = %s''', (sender_id, receiver_id))
        msg = list()
        for message, timestamp in dbcur:
            msg.append(Message(senderId=sender_id, receiverId=receiver_id, content=message, timestamp=int(timestamp.timestamp())))
    return msg


@app.get(
    "/users/{user_id}",
    response_model=UserPublic,
    summary="Benutzerdetails abrufen",
    tags=["Benutzerverwaltung"]
)
def get_user(user_id: int) -> UserPublic:
    """
    Gibt öffentliche Informationen eines Benutzers zurück.
    Raises:
        HTTPException 404: Falls der Benutzer nicht existiert.
    """

    with dbcon.cursor() as dbcur:
        dbcur.execute('''SELECT username, email, avatar FROM users WHERE user_id = %s AND NOT deactivated;''', (user_id,))
        userinfo = dbcur.fetchall()
        if not userinfo:
            raise HTTPException(status_code=404, detail="User not found")
        userinfo, = userinfo
    return UserPublic(id = user_id, username = userinfo[0], email = userinfo[1], avatar = userinfo[2], status = 'NULL')


@app.post(
    "/users/register",
    response_model=UserPublic,
    summary="Neuen Benutzer registrieren",
    tags=["Benutzerverwaltung"]
)
def register_user(reg: RegisterRequest) -> UserPublic:
    """
    Registriert einen neuen Benutzer.
    - Verhindert doppelte E-Mail-Adressen.
    - Hash des Passworts wird gespeichert.

    Raises:
        HTTPException 400: Wenn E-Mail bereits registriert.
    """
    with dbcon:
        with dbcon.cursor() as dbcur:
            reg = dict(reg)
            reg.update({'password': bcrypt.hashpw(reg["password"].encode(), bcrypt.gensalt()).decode()})
            try:
                dbcur.execute('''INSERT INTO users (username, email, password) VALUES (%(username)s, %(email)s, %(password)s) RETURNING user_id, avatar''', reg)
            except psycopg2.errors.UniqueViolation as unique:
                match unique:
                    case 'duplicate key value violates unique constraint "users_username_user_id_key"':
                        raise HTTPException(status_code=400, detail="Email already registered")
                    case 'duplicate key value violates unique constraint "users_email_key"':
                        raise HTTPException(status_code=400, detail="Username already registered")
                    case _:
                        raise psycopg2.errors.UniqueViolation(unique)
            user_id, avatar = dbcur.fetchone()
        return UserPublic(id = user_id, username = reg["username"], email = reg["email"], avatar = avatar, status = 'null')


@app.post(
    "/users/login",
    response_model=UserPublic,
    summary="Benutzeranmeldung",
    tags=["Benutzerverwaltung"]
)
def login_user(login: LoginRequest) -> UserPublic:
    """
    Authentifiziert einen Benutzer anhand von E-Mail und Passwort.

    Raises:
        HTTPException 401: Bei ungültigen Anmeldedaten.
    """
    user = next((u for u in user_store if u.email == login.email), None)
    if not user or not bcrypt.checkpw(login.password.encode(), user.password.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Setze Status auf 'online' beim Login
    user.status = "online"
    return UserPublic(**user.model_dump())


if __name__ == "__main__":
    import uvicorn

    # Starte Entwicklungsserver
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
