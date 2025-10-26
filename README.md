# Automated PDF → CSV

## API
- `POST /bank/convert-pdf` (form field: `pdf`)
- `GET /bank/rules` / `POST /bank/rules` with:
```json
{ "Food": ["ROYAL CABRI","STARBUCKS"], "Transport": ["GRAB"] }
