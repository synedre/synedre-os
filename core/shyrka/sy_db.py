"""
synedre/db.py — Helper connexion PostgreSQL pour agents sandbox.

Pourquoi ce fichier existe (cicatrice 2026-05-23, chantier #94) :
  Les sous-claude spawnés par sy_task_worker via atlas-spawn-claude.mjs tournent
  dans un contexte host Linux (pas dans Docker). Ils n'ont pas accès :
    - au hostname interne Docker `sy_postgres` (non résolvable depuis le host)
    - au socket Docker (permissions manquantes pour `docker exec sy_postgres psql`)

  Solution : le container sy_postgres expose son port 5432 sur 127.0.0.1:5433
  côté host. La connexion TCP localhost:5433 est accessible depuis tout process
  host, y compris un sous-claude spawné par le task worker.

  Ce helper `get_conn()` doit être préféré à tout `docker exec sy_postgres psql`
  dans les scripts Python utilisés par des agents. Il est autonome — il ne dépend
  pas de sy_entities/base.py (qui, lui, fait du docker exec pour les connexions).

Usage :
    from synedre.db import get_conn
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT now()")
        print(cur.fetchone())
    conn.close()

Variables d'environnement (toutes optionnelles sauf PG_PASSWORD) :
    PG_HOST      — défaut : localhost
    PG_PORT      — défaut : 5433  (port exposé du container sy_postgres)
    PG_USER      — défaut : claude_pg
    PG_DB        — défaut : sy_hub
    PG_PASSWORD  — REQUIS (lève KeyError si absente)

Ces vars sont injectées automatiquement par atlas-spawn-claude.mjs dans l'env
de chaque sous-claude spawné par le task worker (sauf PG_PASSWORD, héritée via
process.env du cron qui démarre sy_task_worker.py).
"""

import os
import psycopg2


def get_conn():
    """
    Retourne une connexion psycopg2 vers sy_postgres via TCP localhost:5433.

    Raises:
        KeyError: si PG_PASSWORD n'est pas défini dans l'environnement.
        psycopg2.OperationalError: si la connexion TCP échoue.
    """
    return psycopg2.connect(
        host=os.environ.get('PG_HOST', 'localhost'),
        port=int(os.environ.get('PG_PORT', '5433')),
        user=os.environ.get('PG_USER', 'claude_pg'),
        password=os.environ['PG_PASSWORD'],  # requis — lève KeyError si absent
        dbname=os.environ.get('PG_DB', 'sy_hub'),
    )
