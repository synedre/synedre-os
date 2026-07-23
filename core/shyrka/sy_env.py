"""
sy_env — Chargement centralisé des variables d'environnement.

Usage dans tout sy_*.py :
    from sy_env import load_env
    load_env()

Charge .env (Docker/partagé) puis .env.host (host-only, override).
Les scripts Python tournent sur le HOST, donc .env.host a la priorité
(ex: DB_PORT=3307 override le DB_PORT absent du .env nettoyé).

"""

from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def load_env():
    """Charge .env.host puis .env (sans override de l'os.environ existant).

    Ordre de priorité (du plus fort au plus faible) :
      1. Variables déjà présentes dans os.environ (subprocess overrides, cron exports)
      2. .env.host (spécificités host — ports, credentials machine-locaux)
      3. .env (valeurs partagées Docker/shyrka)

    Charger .env.host en premier (override=False) garantit que les vars
    subprocess/cron priment sur .env.host, tout en gardant .env.host
    prioritaire sur .env (car .env est chargé ensuite, override=False,
    et ne touche pas ce qu'on vient de mettre depuis .env.host).
    """
    load_dotenv(ROOT / ".env.host", override=False)
    load_dotenv(ROOT / ".env", override=False)
