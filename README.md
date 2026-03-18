# Portfolio Modèle — investir.blog
## Backend FastAPI — Phase 1

---

## Stack
- **Backend** : FastAPI + SQLAlchemy
- **Base de données** : PostgreSQL (Railway)
- **Prix** : yfinance (refresh toutes les heures)
- **Déploiement** : Railway

---

## Structure des fichiers

```
portfolio-model/
├── app/
│   ├── __init__.py
│   ├── main.py          # Endpoints FastAPI
│   ├── models.py        # Modèles SQLAlchemy
│   ├── schemas.py       # Schémas Pydantic
│   ├── services.py      # Logique prix & performance
│   ├── auth.py          # JWT admin
│   ├── config.py        # Paramètres centraux
│   └── database.py      # Connexion PostgreSQL
├── migrations/
│   └── schema.sql       # Schéma SQL de référence
├── .env.example
├── Procfile
├── requirements.txt
└── README.md
```

---

## Déploiement Railway (étape par étape)

### 1. Préparer le repo GitHub
```bash
git init
git add .
git commit -m "Portfolio modèle — Phase 1"
git remote add origin https://github.com/TON_USER/portfolio-model.git
git push -u origin main
```

### 2. Créer le projet sur Railway
1. Aller sur [railway.app](https://railway.app)
2. **New Project → Deploy from GitHub repo**
3. Sélectionner ton repo

### 3. Ajouter PostgreSQL
1. Dans le projet Railway : **New → Database → PostgreSQL**
2. Railway génère automatiquement `DATABASE_URL`

### 4. Variables d'environnement
Dans Railway → Settings → Variables, ajouter :
```
DATABASE_URL=         ← copier depuis l'onglet PostgreSQL
SECRET_KEY=           ← openssl rand -hex 32
BREVO_API_KEY=        ← depuis app.brevo.com
ENVIRONMENT=production
ALLOWED_ORIGINS=https://investir.blog
```

### 5. Vérifier le déploiement
Accéder à : `https://ton-app.railway.app/`
Réponse attendue : `{"status": "ok", "app": "Portfolio Modèle — investir.blog"}`

Documentation API : `https://ton-app.railway.app/docs`

---

## Initialisation du compte admin

Après le premier déploiement, appeler **une seule fois** :
```
POST https://ton-app.railway.app/admin/setup?username=nathanael&password=MOT_DE_PASSE_FORT
```
Puis **supprimer ou commenter** cet endpoint dans `main.py`.

---

## Endpoints principaux

### Publics (sans auth)
| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/public/positions` | Positions actives + prix + P&L |
| GET | `/public/performance` | Métriques globales |
| GET | `/public/transactions` | Dernières transactions |
| POST | `/subscribers` | Inscription alertes email |

### Admin (JWT requis)
| Méthode | URL | Description |
|---------|-----|-------------|
| POST | `/admin/token` | Connexion → JWT |
| POST | `/admin/positions` | Ouvrir une position |
| POST | `/admin/transactions` | Ajouter une transaction |
| POST | `/admin/refresh-prices` | Forcer le refresh des prix |
| DELETE | `/admin/positions/{ticker}` | Clôturer une position |
| GET | `/admin/subscribers` | Liste des abonnés |

---

## Ajouter une position (exemple cURL)

```bash
# 1. Obtenir le token
TOKEN=$(curl -s -X POST https://ton-app.railway.app/admin/token \
  -d "username=nathanael&password=MOT_DE_PASSE" | jq -r .access_token)

# 2. Ajouter une action screener
curl -X POST https://ton-app.railway.app/admin/positions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "MSFT",
    "name": "Microsoft Corporation",
    "asset_type": "stock",
    "geography": "US",
    "sector": "Technology",
    "shares": 10,
    "avg_cost": 420.50,
    "currency": "USD",
    "weight_target": 8.0,
    "source": "screener",
    "screener_score": 82.4,
    "score_details": {
      "quality": 88, "value": 72, "momentum": 85,
      "growth": 79, "low_volatility": 71
    },
    "macro_signal": "Surpondération Tech US — signal macroETF avril 2026",
    "rationale": "Microsoft figure au top 5 du screener US avec un score qualité de 88/100...",
    "opened_at": "2026-03-18"
  }'

# 3. Ajouter un ETF macroETF
curl -X POST https://ton-app.railway.app/admin/positions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "XLK",
    "name": "Technology Select Sector SPDR",
    "asset_type": "etf",
    "geography": "US",
    "sector": "Technology",
    "shares": 50,
    "avg_cost": 225.00,
    "currency": "USD",
    "weight_target": 9.0,
    "source": "macroetf",
    "macro_signal": "Surpondération Tech US — momentum sectoriel positif",
    "rationale": "ETF sélectionné par macroETF.com sur signal de rotation sectorielle...",
    "opened_at": "2026-03-18"
  }'
```

---

## Phase suivante : Phase 2
Frontend public sur Netlify — dashboard de performance, tableau des positions, graphique valeur vs benchmarks.
