@echo off
cd /d %~dp0
if not exist venv ( python -m venv venv )
call venv\Scripts\activate
pip install -r requirements.txt
start "" http://127.0.0.1:8000
uvicorn app.main:app --reload
