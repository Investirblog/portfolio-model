-- ============================================================
-- PORTFOLIO MODÈLE — investir.blog
-- Schéma PostgreSQL
-- ============================================================

-- Types énumérés
CREATE TYPE asset_type AS ENUM ('stock', 'etf');
CREATE TYPE transaction_type AS ENUM ('buy', 'sell', 'rebalance');
CREATE TYPE geography AS ENUM ('US', 'Europe', 'Canada');

-- ------------------------------------------------------------
-- POSITIONS : état actuel du portefeuille
-- ------------------------------------------------------------
CREATE TABLE positions (
    id              SERIAL PRIMARY KEY,
    ticker          VARCHAR(20) NOT NULL UNIQUE,
    name            VARCHAR(200) NOT NULL,
    asset_type      asset_type NOT NULL,          -- 'stock' ou 'etf'
    geography       geography NOT NULL,
    sector          VARCHAR(100),
    shares          NUMERIC(12,4) NOT NULL,        -- nombre de parts
    avg_cost        NUMERIC(12,4) NOT NULL,        -- prix moyen d'achat (USD/EUR)
    currency        VARCHAR(3) NOT NULL DEFAULT 'USD',
    weight_target   NUMERIC(5,2),                  -- pondération cible en %
    source          VARCHAR(50),                   -- 'screener' | 'macroetf' | 'manual'
    screener_score  NUMERIC(5,2),                  -- score global screener (0-100)
    score_details   JSONB,                         -- détail par facteur
    macro_signal    VARCHAR(200),                  -- contexte macro associé
    rationale       TEXT,                          -- raisonnement d'entrée (visible abonnés)
    opened_at       DATE NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- TRANSACTIONS : historique complet des mouvements
-- ------------------------------------------------------------
CREATE TABLE transactions (
    id              SERIAL PRIMARY KEY,
    ticker          VARCHAR(20) NOT NULL,
    transaction_type transaction_type NOT NULL,
    shares          NUMERIC(12,4) NOT NULL,
    price           NUMERIC(12,4) NOT NULL,        -- prix d'exécution
    currency        VARCHAR(3) NOT NULL DEFAULT 'USD',
    rationale       TEXT,                          -- raisonnement (visible abonnés)
    screener_score  NUMERIC(5,2),                  -- score au moment de la transaction
    macro_context   VARCHAR(200),                  -- état macro au moment de la transaction
    executed_at     DATE NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Index utile pour historique par ticker
CREATE INDEX idx_transactions_ticker ON transactions(ticker);
CREATE INDEX idx_transactions_date ON transactions(executed_at DESC);

-- ------------------------------------------------------------
-- PRIX : cache des derniers cours (mis à jour toutes les heures)
-- ------------------------------------------------------------
CREATE TABLE price_cache (
    ticker          VARCHAR(20) PRIMARY KEY,
    price           NUMERIC(12,4),
    currency        VARCHAR(3) NOT NULL DEFAULT 'USD',
    price_date      DATE,
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- BENCHMARKS : snapshots quotidiens S&P 500 et Stoxx 600
-- ------------------------------------------------------------
CREATE TABLE benchmark_snapshots (
    id              SERIAL PRIMARY KEY,
    benchmark       VARCHAR(20) NOT NULL,          -- 'SPY', 'SXXP'
    price           NUMERIC(12,4) NOT NULL,
    snapshot_date   DATE NOT NULL,
    UNIQUE(benchmark, snapshot_date)
);

-- ------------------------------------------------------------
-- PERFORMANCE : snapshots quotidiens de la valeur du portefeuille
-- (calculés et stockés chaque jour de bourse)
-- ------------------------------------------------------------
CREATE TABLE portfolio_snapshots (
    id              SERIAL PRIMARY KEY,
    total_value     NUMERIC(14,2) NOT NULL,        -- valeur totale en USD (base 100 000)
    cash            NUMERIC(14,2) NOT NULL DEFAULT 0,
    snapshot_date   DATE NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- ABONNÉS : inscrits pour recevoir les alertes email
-- ------------------------------------------------------------
CREATE TABLE subscribers (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    name            VARCHAR(100),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    subscribed_at   TIMESTAMPTZ DEFAULT NOW(),
    unsubscribed_at TIMESTAMPTZ,
    source          VARCHAR(50)                    -- 'substack' | 'direct' | 'landing'
);

CREATE INDEX idx_subscribers_email ON subscribers(email);
CREATE INDEX idx_subscribers_active ON subscribers(is_active);

-- ------------------------------------------------------------
-- EMAIL LOGS : traçabilité des envois
-- ------------------------------------------------------------
CREATE TABLE email_logs (
    id              SERIAL PRIMARY KEY,
    transaction_id  INTEGER REFERENCES transactions(id),
    subject         VARCHAR(300),
    recipients_count INTEGER,
    sent_at         TIMESTAMPTZ DEFAULT NOW(),
    status          VARCHAR(50)                    -- 'sent' | 'failed'
);

-- ------------------------------------------------------------
-- ADMIN : utilisateur unique pour le panel
-- ------------------------------------------------------------
CREATE TABLE admin_user (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(50) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- Trigger : mise à jour automatique de updated_at sur positions
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_positions_updated_at
    BEFORE UPDATE ON positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- DONNÉES INITIALES
-- Capital fictif de départ : 100 000 USD
-- Allocation cible : 65% actions screener / 35% ETF macro
-- ============================================================

-- Snapshot initial (à ajuster à la date réelle de lancement)
-- INSERT INTO portfolio_snapshots (total_value, cash, snapshot_date)
-- VALUES (100000.00, 100000.00, CURRENT_DATE);
