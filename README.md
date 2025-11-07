python -m venv .venv && source .venv/bin/activate  # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your Google AI Studio key
python -m src.main \
  --docs data/docs \
  --out out \
  --max-stories 10
