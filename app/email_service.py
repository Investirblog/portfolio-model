# ============================================================
# email_service.py — Envoi d'emails via Resend
# ============================================================
import httpx
import logging
from typing import List
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

RESEND_API = "https://api.resend.com/emails"


def send_transaction_alert(
    ticker: str,
    transaction_type: str,
    shares: float,
    price: float,
    currency: str,
    rationale: str,
    executed_at: str,
    recipients: List[str],
) -> bool:
    """
    Envoie une alerte email a tous les abonnes actifs
    lors d'un mouvement dans le portefeuille.
    """
    if not recipients:
        logger.info("Aucun abonne actif, email non envoye")
        return True

    if not settings.resend_api_key:
        logger.warning("RESEND_API_KEY non configuree")
        return False

    type_fr = {
        "buy": "Achat",
        "sell": "Vente",
        "rebalance": "Rebalancement"
    }.get(transaction_type, transaction_type)

    subject = f"[Portefeuille Modele] {type_fr} — {ticker}"

    rationale_block = f"""
    <tr>
      <td style="padding:16px 24px;border-top:1px solid #1f2330;">
        <p style="margin:0 0 8px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#8891a8;">Raisonnement</p>
        <p style="margin:0;font-size:14px;color:#c8d0e0;line-height:1.6;">{rationale}</p>
      </td>
    </tr>""" if rationale else ""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0d0f14;font-family:'Helvetica Neue',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0f14;padding:40px 20px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#13161d;border:1px solid rgba(255,255,255,0.1);border-radius:8px;overflow:hidden;">

        <!-- Header -->
        <tr>
          <td style="background:#13161d;padding:24px;border-bottom:2px solid #b8f04a;">
            <p style="margin:0;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;color:#b8f04a;">investir.blog</p>
            <p style="margin:4px 0 0;font-size:18px;font-weight:700;color:#eef0f6;">Mouvement dans le Portefeuille Modele</p>
          </td>
        </tr>

        <!-- Type badge -->
        <tr>
          <td style="padding:24px 24px 0;">
            <span style="display:inline-block;padding:4px 14px;border-radius:4px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;background:{'rgba(74,222,128,0.12)' if transaction_type=='buy' else 'rgba(248,113,113,0.12)'};color:{'#4ade80' if transaction_type=='buy' else '#f87171'};">{type_fr}</span>
          </td>
        </tr>

        <!-- Details -->
        <tr>
          <td style="padding:16px 24px 0;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding:12px 0;border-bottom:1px solid #1f2330;">
                  <span style="font-size:12px;color:#8891a8;text-transform:uppercase;letter-spacing:0.08em;">Ticker</span><br>
                  <span style="font-size:22px;font-weight:700;color:#eef0f6;font-family:'Courier New',monospace;">{ticker}</span>
                </td>
              </tr>
              <tr>
                <td style="padding:12px 0;border-bottom:1px solid #1f2330;">
                  <span style="font-size:12px;color:#8891a8;text-transform:uppercase;letter-spacing:0.08em;">Prix d execution</span><br>
                  <span style="font-size:18px;font-weight:600;color:#eef0f6;font-family:'Courier New',monospace;">{price:,.2f} {currency}</span>
                </td>
              </tr>
              <tr>
                <td style="padding:12px 0;border-bottom:1px solid #1f2330;">
                  <span style="font-size:12px;color:#8891a8;text-transform:uppercase;letter-spacing:0.08em;">Nombre de parts</span><br>
                  <span style="font-size:18px;font-weight:600;color:#eef0f6;font-family:'Courier New',monospace;">{shares:,.4f}</span>
                </td>
              </tr>
              <tr>
                <td style="padding:12px 0;">
                  <span style="font-size:12px;color:#8891a8;text-transform:uppercase;letter-spacing:0.08em;">Date</span><br>
                  <span style="font-size:16px;color:#eef0f6;">{executed_at}</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        {rationale_block}

        <!-- CTA -->
        <tr>
          <td style="padding:24px;text-align:center;border-top:1px solid #1f2330;">
            <a href="https://portfolio.investir.blog" style="display:inline-block;padding:12px 28px;background:#b8f04a;color:#0d0f14;font-weight:700;font-size:13px;text-decoration:none;border-radius:4px;text-transform:uppercase;letter-spacing:0.08em;">Voir le portefeuille</a>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:16px 24px;border-top:1px solid #1f2330;text-align:center;">
            <p style="margin:0;font-size:11px;color:#636b82;">
              Vous recevez cet email car vous etes abonne aux alertes du Portefeuille Modele investir.blog.<br>
              <a href="https://portfolio.investir.blog/unsubscribe" style="color:#8891a8;">Se desabonner</a>
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

    # Envoi en batch (max 50 par appel Resend)
    success = True
    for i in range(0, len(recipients), 50):
        batch = recipients[i:i+50]
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(
                    RESEND_API,
                    headers={
                        "Authorization": f"Bearer {settings.resend_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": f"Investir.blog <{settings.email_from}>",
                        "to": batch,
                        "subject": subject,
                        "html": html,
                    }
                )
                if resp.status_code not in (200, 201):
                    logger.error(f"Erreur Resend: {resp.text}")
                    success = False
                else:
                    logger.info(f"Email envoye a {len(batch)} abonnes")
        except Exception as e:
            logger.error(f"Erreur envoi email: {e}")
            success = False

    return success
