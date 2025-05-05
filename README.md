**Dokumentation ScripNET**

Hier kommt  unsere Dokumentation von dem Programm ScripNET


    @app.websocket("/messages/{user_id}")
    async def messages(user_id: int, websocket: WebSocket):
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

In diesem Abschnitt wird der WebSocket vorbereitet. Damit die Nachrichten im Backend verarbeitet werden kann.
Danach wird der eine Schleife für die Verarbeitung einer Nachricht eröffnet. Der Erste Block empfängt die Nachricht. Der zweite hingegen sendet diese an das Ziel falls dieser auch online ist.     
Der nächste Block enfernt den User bei der Trennung und führt den Log bei Fehlern.  



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

Hier wird der Chat aus der DB mithilfe von 
PostgreSQL and den User gegeben.

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

Hier sieht man die Benutzerverwaltung. Man kann mit dieser sich die Öffentlich verfügbaren Informationen anzeigen lassen.

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
Zu letzt wird in diesem Block die Registierung und der Login möglich gemacht. Bei der Registierung werden die Information in der DB eingeflegt. Nach dem Login wird auch der Status eines User auf "Online" gestellt.