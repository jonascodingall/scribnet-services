#!/bin/env python3
import bcrypt, psycopg2, psycopg2.extras, datetime, random
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Response, Cookie
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

def random_id(length):
    number = '0123456789'
    alpha = 'abcdefghijklmnopqrstuvwxyz'
    id = str()
    for i in range(0,length,2):
        id += random.choice(number)
        id += random.choice(alpha)
    return id


# Verbinde mit dem Datenbank Managment System
dbcon = psycopg2.connect(dbname='ScribNET_template', user='oliver', host='192.168.0.46')

# Instanziierung der FastAPI-Anwendung
app = FastAPI()

# In-Memory-Datenstrukturen (nur zu Demonstrationszwecken)
connected_users: Dict[int, WebSocket] = {}

@app.websocket("/messages/{user_id}")
async def messages(user_id: int, websocket: WebSocket, token: str = Cookie(None)):
    """
    WebSocket-Endpunkt für bidirektionale Chatkommunikation.
    - Speichert eingehende Nachrichten im der datenbank.
    - Leitet Nachrichten in Echtzeit an verbundene Benutzer weiter.
    """
    with dbcon.cursor() as dbcur:
        if not my_cookie:
            raise HTTPException(status_code=401, detail="No token")
        dbcur.execute('''SELECT user_id FROM sessions WHERE ttl > CURRENT_TIMESTAMP AND session = %s;''', (token,))
        if dbcur.fetchone()[0] != user_id:
            raise HTTPException(status_code=401, detail="Wronge token")

        await websocket.accept()
        connected_users[user_id] = websocket

        try:
            while True:
                data = await websocket.receive_text()
                msg = Message.model_validate_json(data)

                with dbcon:
                        dbcur.execute('''INSERT INTO messages (sender_id, receiver_id, message, creation_timestamp) VALUES (%(sender_id)s, %(receiver_id)s, %(content)s, %(timestamp)s)''', dict(msg))

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

    return UserPublic(id = user_id, username = userinfo[0], email = userinfo[1], avatar = userinfo[2], status = 'online' if connected_users[user_id] else 'offline')


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
        return UserPublic(id = user_id, username = reg["username"], email = reg["email"], avatar = avatar, status = 'offline')


@app.post(
    "/users/login",
    response_model=UserPublic,
    summary="Benutzeranmeldung",
    tags=["Benutzerverwaltung"]
)
def login_user(login: LoginRequest, response: Response) -> UserPublic:
    """
    Authentifiziert einen Benutzer anhand von E-Mail und Passwort.

    Raises:
        HTTPException 401: Bei ungültigen Anmeldedaten.
    """
    with dbcon.cursor(cursor_factory=psycopg2.extras.DictCursor) as dbcur:
        dbcur.execute('''SELECT user_id as id, username, email, avatar, password FROM users WHERE email = %s''', (login.email,))
        userdict = dbcur.fetchone()
        if not userdict:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        elif not bcrypt.checkpw(login.password.encode(), bytes(userdict["password"])):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        userdict = dict(userdict)

        with dbcon:
            dbcur.execute('''INSERT INTO sessions (user_id, session, ttl) VALUES (%s, %s, %s::timestamp) RETURNING session''', (1, random_id(32), (datetime.datetime.now()+datetime.timedelta(days=1)).utcnow()))
            token, = dbcur.fetchone()
            response.set_cookie(key="token", value=token, max_age=86400, httponly=True)
        userdict['status'] = 'offline'
        user = UserPublic(**userdict)

    return UserPublic(**user.model_dump())


if __name__ == "__main__":
    import uvicorn

    # Starte Entwicklungsserver
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
