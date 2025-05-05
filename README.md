**Dokumentation ScripNET**

**WebSocket:**

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
