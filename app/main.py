# ============================================================
# main.py — Application FastAPI principale
# Portfolio Modèle — investir.blog
# ============================================================
from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import date
from typing import List, Optional
import logging

from app.config import get_settings
from app.database import get_db, engine
from app.models import Base, Position, Transaction, Subscriber, AdminUser
from app.schemas import (
    PositionCreate, PositionPublic, PositionDetail,
    TransactionCreate, TransactionPublic, TransactionDetail,
    PerformanceSummary,
    SubscriberCreate, SubscriberOut,
    Token,
)
from app.email_service import send_transaction_alert
from app.services import (
    refresh_prices, get_cached_price,
    calculate_portfolio_performance,
    save_daily_snapshot,
)
from app.auth import hash_password, verify_password, create_access_token, get_admin_user

# Création des tables au démarrage
Base.metadata.create_all(bind=engine)

settings = get_settings()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Portfolio Modèle — investir.blog",
    description="API du portefeuille modèle public de la newsletter investir.blog",
    version="1.0.0",
)

# CORS — allow_origins=["*"] pour compatibilite maximale
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ENDPOINTS PUBLICS — accessibles sans authentification
# ============================================================

@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "app": "Portfolio Modèle — investir.blog"}


@app.get("/public/positions", response_model=List[PositionPublic], tags=["Public"])
def get_public_positions(db: Session = Depends(get_db)):
    """
    Liste des positions actives — version publique (sans raisonnement).
    Enrichie avec prix actuel, P&L et poids réel.
    """
    positions = db.query(Position).filter(Position.is_active == True).order_by(Position.id).all()

    # Calcul valeur totale pour les poids
    total_value = 0.0
    position_values = {}
    for p in positions:
        price = get_cached_price(db, p.ticker) or float(p.avg_cost)
        val = float(p.shares) * price
        position_values[p.id] = (price, val)
        total_value += val

    result = []
    for p in positions:
        price, val = position_values[p.id]
        pnl_pct = (price - float(p.avg_cost)) / float(p.avg_cost) * 100
        weight_actual = (val / total_value * 100) if total_value > 0 else 0

        pos_dict = {
            "id": p.id,
            "ticker": p.ticker,
            "name": p.name,
            "asset_type": p.asset_type,
            "geography": p.geography,
            "sector": p.sector,
            "shares": float(p.shares),
            "avg_cost": float(p.avg_cost),
            "currency": p.currency,
            "weight_target": float(p.weight_target) if p.weight_target else None,
            "source": p.source,
            "opened_at": p.opened_at,
            "is_public": p.is_public if p.is_public is not None else False,
            "current_price": round(price, 2),
            "current_value": round(val, 2),
            "pnl_pct": round(pnl_pct, 2),
            "weight_actual": round(weight_actual, 2),
        }
        result.append(pos_dict)

    return result


@app.get("/public/performance", response_model=PerformanceSummary, tags=["Public"])
def get_performance(db: Session = Depends(get_db)):
    """Métriques globales de performance — publiques."""
    return calculate_portfolio_performance(db)


@app.get("/public/transactions", response_model=List[TransactionPublic], tags=["Public"])
def get_public_transactions(
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Dernières transactions — version publique (sans raisonnement)."""
    return db.query(Transaction).order_by(
        Transaction.executed_at.desc()
    ).limit(limit).all()


# ============================================================
# ENDPOINTS ABONNÉS — nécessitent un token JWT
# ============================================================

@app.get("/subscriber/positions", response_model=List[PositionDetail], tags=["Subscriber"])
def get_subscriber_positions(
    db: Session = Depends(get_db),
    current_admin=Depends(get_admin_user)   # TODO: remplacer par auth abonné en Phase 3
):
    """
    Positions avec raisonnement complet, scores et signal macro.
    Phase 3 : différencier auth admin / auth abonné.
    """
    positions = db.query(Position).filter(Position.is_active == True).all()
    total_value = sum(
        float(p.shares) * (get_cached_price(db, p.ticker) or float(p.avg_cost))
        for p in positions
    )

    result = []
    for p in positions:
        price = get_cached_price(db, p.ticker) or float(p.avg_cost)
        val = float(p.shares) * price
        pnl_pct = (price - float(p.avg_cost)) / float(p.avg_cost) * 100
        weight_actual = (val / total_value * 100) if total_value > 0 else 0

        result.append({
            "id": p.id,
            "ticker": p.ticker,
            "name": p.name,
            "asset_type": p.asset_type,
            "geography": p.geography,
            "sector": p.sector,
            "shares": float(p.shares),
            "avg_cost": float(p.avg_cost),
            "currency": p.currency,
            "weight_target": float(p.weight_target) if p.weight_target else None,
            "source": p.source,
            "opened_at": p.opened_at,
            "is_public": p.is_public if p.is_public is not None else False,
            "current_price": round(price, 2),
            "current_value": round(val, 2),
            "pnl_pct": round(pnl_pct, 2),
            "weight_actual": round(weight_actual, 2),
            "screener_score": float(p.screener_score) if p.screener_score else None,
            "score_details": p.score_details,
            "macro_signal": p.macro_signal,
            "rationale": p.rationale,
        })

    return result


@app.get("/subscriber/transactions", response_model=List[TransactionDetail], tags=["Subscriber"])
def get_subscriber_transactions(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_admin=Depends(get_admin_user)
):
    """Historique complet des transactions avec raisonnement."""
    return db.query(Transaction).order_by(
        Transaction.executed_at.desc()
    ).limit(limit).all()


# ============================================================
# ENDPOINTS ADMIN — gestion du portefeuille
# ============================================================

@app.post("/admin/token", response_model=Token, tags=["Admin"])
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Connexion admin — retourne un JWT."""
    user = db.query(AdminUser).filter(
        AdminUser.username == form_data.username
    ).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants incorrects",
        )
    token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}


@app.post("/admin/setup", tags=["Admin"])
def setup_admin(username: str, password: str, db: Session = Depends(get_db)):
    """
    Crée le compte admin initial.
    À appeler UNE SEULE FOIS après déploiement — puis désactiver cet endpoint.
    """
    existing = db.query(AdminUser).first()
    if existing:
        raise HTTPException(status_code=400, detail="Admin déjà configuré.")
    admin = AdminUser(username=username, hashed_password=hash_password(password))
    db.add(admin)
    db.commit()
    return {"message": f"Admin '{username}' créé avec succès."}


@app.post("/admin/positions", response_model=PositionPublic, tags=["Admin"])
def create_position(
    payload: PositionCreate,
    db: Session = Depends(get_db),
    current_admin=Depends(get_admin_user)
):
    """Ouvre une nouvelle position dans le portefeuille."""
    existing = db.query(Position).filter(
        Position.ticker == payload.ticker,
        Position.is_active == True
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"{payload.ticker} déjà en portefeuille.")

    position = Position(**payload.model_dump())
    db.add(position)

    # Transaction d'achat automatique
    transaction = Transaction(
        ticker=payload.ticker,
        transaction_type="buy",
        shares=payload.shares,
        price=payload.avg_cost,
        currency=payload.currency,
        rationale=payload.rationale,
        screener_score=payload.screener_score,
        macro_context=payload.macro_signal,
        executed_at=payload.opened_at,
    )
    db.add(transaction)
    db.commit()
    db.refresh(position)

    return {
        "id": position.id,
        "ticker": position.ticker,
        "name": position.name,
        "asset_type": position.asset_type,
        "geography": position.geography,
        "sector": position.sector,
        "shares": float(position.shares),
        "avg_cost": float(position.avg_cost),
        "currency": position.currency,
        "weight_target": float(position.weight_target) if position.weight_target else None,
        "source": position.source,
        "opened_at": position.opened_at,
        "current_price": float(position.avg_cost),
        "current_value": float(position.shares) * float(position.avg_cost),
        "pnl_pct": 0.0,
        "weight_actual": None,
    }


@app.post("/admin/transactions", response_model=TransactionPublic, tags=["Admin"])
def add_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    current_admin=Depends(get_admin_user)
):
    """
    Enregistre une transaction (renforcement, vente partielle, vente totale).
    Met à jour la position automatiquement.
    """
    position = db.query(Position).filter(
        Position.ticker == payload.ticker,
        Position.is_active == True
    ).first()

    if not position:
        raise HTTPException(status_code=404, detail=f"Position {payload.ticker} introuvable.")

    if payload.transaction_type == "buy":
        # Mise à jour prix moyen pondéré
        total_shares = float(position.shares) + payload.shares
        total_cost = (float(position.shares) * float(position.avg_cost)) + \
                     (payload.shares * payload.price)
        position.shares = total_shares
        position.avg_cost = total_cost / total_shares

    elif payload.transaction_type == "sell":
        new_shares = float(position.shares) - payload.shares
        if new_shares < 0:
            raise HTTPException(status_code=400, detail="Vente supérieure aux parts détenues.")
        if new_shares == 0:
            position.is_active = False
        else:
            position.shares = new_shares

    transaction = Transaction(**payload.model_dump())
    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    # Envoi email aux abonnes actifs
    try:
        subscribers = db.query(Subscriber).filter(Subscriber.is_active == True).all()
        emails = [s.email for s in subscribers]
        if emails:
            send_transaction_alert(
                ticker=payload.ticker,
                transaction_type=payload.transaction_type,
                shares=float(payload.shares),
                price=float(payload.price),
                currency=payload.currency,
                rationale=payload.rationale or "",
                executed_at=str(payload.executed_at),
                recipients=emails,
            )
            # Log email
            from app.models import EmailLog
            log = EmailLog(
                transaction_id=transaction.id,
                subject=f"[Portefeuille Modele] {payload.transaction_type} - {payload.ticker}",
                recipients_count=len(emails),
                status="sent"
            )
            db.add(log)
            db.commit()
    except Exception as e:
        logger.error(f"Erreur envoi email: {e}")

    return transaction


@app.post("/admin/refresh-prices", tags=["Admin"])
def admin_refresh_prices(
    db: Session = Depends(get_db),
    current_admin=Depends(get_admin_user)
):
    """Force le refresh des prix et enregistre un snapshot quotidien."""
    positions = db.query(Position).filter(Position.is_active == True).all()
    tickers = [p.ticker for p in positions] + ["SPY", "SXXP.MI"]
    prices = refresh_prices(db, tickers)

    # Snapshot portefeuille
    total_value = sum(
        float(p.shares) * prices.get(p.ticker, float(p.avg_cost))
        for p in positions
    )
    save_daily_snapshot(db, total_value)

    return {"message": f"{len(prices)} prix mis à jour.", "total_value": round(total_value, 2)}


@app.delete("/admin/positions/{ticker}", tags=["Admin"])
def close_position(
    ticker: str,
    db: Session = Depends(get_db),
    current_admin=Depends(get_admin_user)
):
    """Clôture une position (is_active = False)."""
    position = db.query(Position).filter(
        Position.ticker == ticker.upper(),
        Position.is_active == True
    ).first()
    if not position:
        raise HTTPException(status_code=404, detail=f"Position {ticker} introuvable.")
    position.is_active = False
    db.commit()
    return {"message": f"Position {ticker} clôturée."}


# ============================================================
# ABONNÉS
# ============================================================

@app.post("/subscribers", response_model=SubscriberOut, tags=["Subscribers"])
def subscribe(payload: SubscriberCreate, db: Session = Depends(get_db)):
    """Inscription aux alertes email — verifie le code abonne."""
    # Verification du code abonne (stocke dans le champ name)
    if not payload.name or payload.name.strip().upper() != settings.subscriber_code.upper():
        raise HTTPException(status_code=403, detail="Code abonne invalide.")
    existing = db.query(Subscriber).filter(Subscriber.email == payload.email).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.unsubscribed_at = None
            db.commit()
            return existing
        raise HTTPException(status_code=400, detail="Email deja inscrit.")
    subscriber = Subscriber(**payload.model_dump())
    db.add(subscriber)
    db.commit()
    db.refresh(subscriber)
    return subscriber


@app.delete("/subscribers/{email}", tags=["Subscribers"])
def unsubscribe(email: str, db: Session = Depends(get_db)):
    """Désinscription."""
    sub = db.query(Subscriber).filter(Subscriber.email == email).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Email introuvable.")
    sub.is_active = False
    from datetime import datetime
    sub.unsubscribed_at = datetime.utcnow()
    db.commit()
    return {"message": "Désinscription effectuée."}


@app.get("/admin/subscribers", response_model=List[SubscriberOut], tags=["Admin"])
def list_subscribers(
    db: Session = Depends(get_db),
    current_admin=Depends(get_admin_user)
):
    """Liste des abonnés actifs."""
    return db.query(Subscriber).filter(Subscriber.is_active == True).all()

# ============================================================
# ENDPOINT CRON — appelé par cron-job.org chaque jour
# Authentification par clé secrète fixe (pas JWT)
# ============================================================

@app.post("/cron/refresh", tags=["Cron"])
def cron_refresh_prices(
    x_cron_secret: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Refresh des prix déclenché par un scheduler externe (cron-job.org).
    Passer le header : X-Cron-Secret: <valeur de CRON_SECRET>
    """
    if x_cron_secret != settings.cron_secret:
        raise HTTPException(status_code=403, detail="Acces non autorise")

    positions = db.query(Position).filter(Position.is_active == True).all()
    tickers = [p.ticker for p in positions] + ["SPY", "SXXP.MI"]
    prices = refresh_prices(db, tickers)

    total_value = sum(
        float(p.shares) * prices.get(p.ticker, float(p.avg_cost))
        for p in positions
    )
    save_daily_snapshot(db, total_value)

    return {
        "message": f"{len(prices)} prix mis a jour.",
        "total_value": round(total_value, 2),
        "tickers_updated": list(prices.keys())
    }
