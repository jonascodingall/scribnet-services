import psycopg2, hashlib
from fastapi import FastAPI


app = FastAPI()

@app.push("/api/create_user")
async def api_regist_user():
    pass
    # Data in der DB speichern --> kommt vom Frontend

@app.push("/api/gen_aut_cookie")
async def api_gen_aut_cookie():
    pass
    # Generat Autentivikation Cookie for User Session

@app.push("/api/check_aut_cookie")
async def api_check_aut_cookie():
    pass

@app.push("/")
async def api_profile_set():
    pass
# Profil einstellungen --> US015

@app.push("/")
async def api_send_message():
    pass

@app.push("/")
async def api_set_li_disl():
    pass
#Flags Like/Dislike/Neutral

@app.get("/")
async def api_get_li_disl():
    pass
#Flags anzeigen

@app.push("/")
async def api():
    pass
    # Alles rund um FastAPI

