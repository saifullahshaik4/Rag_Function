python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp .env.example .env
# edit .env with your Google AI Studio key
python -m src.main \
  --docs data/docs \
  --out out \
  --max-stories 10

Run Backed: uvicorn backend.main:app --reload
Run Frontend: python3 -m http.server 5500 (Or run HTMl file while backend is running)

Create a .env file with own api key
