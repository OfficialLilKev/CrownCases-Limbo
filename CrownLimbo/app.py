"""
CrownCases Limbo - Flask Backend
Serves the game and persists bet history to SQLite.
"""

from flask import Flask, request, jsonify, send_from_directory, g
import sqlite3
import hashlib
import hmac
import os
import secrets
import time
import math

app = Flask(__name__, static_folder="static")
DATABASE = "crowncases_limbo.db"

# ─── Database ──────────────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS players (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT    UNIQUE NOT NULL,
                balance     REAL    NOT NULL DEFAULT 1000.0,
                created_at  INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bets (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id       INTEGER NOT NULL REFERENCES players(id),
                bet_amount      REAL    NOT NULL,
                target_multi    REAL    NOT NULL,
                rolled_multi    REAL    NOT NULL,
                won             INTEGER NOT NULL,  -- 0 or 1
                pnl             REAL    NOT NULL,
                server_seed     TEXT    NOT NULL,
                server_seed_hash TEXT   NOT NULL,
                client_seed     TEXT    NOT NULL,
                nonce           INTEGER NOT NULL,
                created_at      INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS seeds (
                player_id       INTEGER PRIMARY KEY REFERENCES players(id),
                server_seed     TEXT    NOT NULL,
                server_seed_hash TEXT   NOT NULL,
                client_seed     TEXT    NOT NULL,
                nonce           INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_bets_player ON bets(player_id);
            CREATE INDEX IF NOT EXISTS idx_bets_created ON bets(created_at);
        """)
        db.commit()


# ─── Provably Fair Math ────────────────────────────────────────────────────────

def generate_server_seed() -> str:
    return secrets.token_hex(32)


def sha256_hash(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def hmac_sha256(key: str, message: str) -> str:
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()


def roll_to_multiplier(float_val: float) -> float:
    """
    Convert a [0,1) float to a multiplier with 5% house edge (95% RTP).
    Formula: multiplier = 0.95 / (1 - float_val)
    Proof:   P(win | target T) = P(0.95/(1-u) >= T) = P(u >= 1 - 0.95/T) = 0.95/T
    Examples: 2x=47.50%  3x=31.67%  5x=19.00%  10x=9.50%
              25x=3.80%  50x=1.90%  100x=0.95%  500x=0.19%
    """
    f = min(float_val, 0.999999)
    raw = 0.95 / (1.0 - f)
    return min(round(raw, 2), 1_000_000.0)


def compute_roll(server_seed: str, client_seed: str, nonce: int) -> float:
    """Return a float in [0,1) derived from HMAC-SHA256."""
    digest = hmac_sha256(server_seed, f"{client_seed}:{nonce}")
    uint32 = int(digest[:8], 16)
    return uint32 / 0x1_0000_0000


def win_chance(target_multi: float) -> float:
    """
    Returns win probability as a percentage for a given target multiplier.
    With 5% house edge (95% RTP): P(win) = 95 / target_multi
    """
    return min(95.0 / target_multi, 90.70)  # max ~90.7% at 1.09x


# ─── Player Helpers ────────────────────────────────────────────────────────────

def get_or_create_player(username: str):
    db = get_db()
    player = db.execute(
        "SELECT * FROM players WHERE username = ?", (username,)
    ).fetchone()

    if player is None:
        now = int(time.time())
        db.execute(
            "INSERT INTO players (username, balance, created_at) VALUES (?, 1000.0, ?)",
            (username, now),
        )
        player_id = db.execute(
            "SELECT id FROM players WHERE username = ?", (username,)
        ).fetchone()["id"]

        server_seed = generate_server_seed()
        db.execute(
            """INSERT INTO seeds (player_id, server_seed, server_seed_hash, client_seed, nonce)
               VALUES (?, ?, ?, ?, 0)""",
            (player_id, server_seed, sha256_hash(server_seed), secrets.token_hex(16)),
        )
        db.commit()
        player = db.execute(
            "SELECT * FROM players WHERE id = ?", (player_id,)
        ).fetchone()

    return player


def get_seeds(player_id: int):
    return get_db().execute(
        "SELECT * FROM seeds WHERE player_id = ?", (player_id,)
    ).fetchone()


# ─── API Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the game HTML file."""
    return send_from_directory(".", "limbo.html")


@app.route("/api/player", methods=["GET"])
def api_get_player():
    """Get or create a player. Pass ?username=YourName"""
    username = request.args.get("username", "guest").strip()[:32]
    player = get_or_create_player(username)
    seeds = get_seeds(player["id"])
    return jsonify({
        "id": player["id"],
        "username": player["username"],
        "balance": round(player["balance"], 8),
        "client_seed": seeds["client_seed"],
        "server_seed_hash": seeds["server_seed_hash"],
        "nonce": seeds["nonce"],
    })


@app.route("/api/seeds/client", methods=["POST"])
def api_update_client_seed():
    """Update client seed for a player."""
    data = request.get_json()
    player_id = data.get("player_id")
    new_seed = data.get("client_seed", secrets.token_hex(16))[:128]

    if not player_id:
        return jsonify({"error": "player_id required"}), 400

    db = get_db()
    db.execute(
        "UPDATE seeds SET client_seed = ?, nonce = 0 WHERE player_id = ?",
        (new_seed, player_id),
    )
    db.commit()
    return jsonify({"client_seed": new_seed})


@app.route("/api/bet", methods=["POST"])
def api_place_bet():
    """
    Place a bet.
    Body: { player_id, bet_amount, target_multi }
    Returns: { won, rolled_multi, payout, new_balance, server_seed (revealed), ... }
    """
    data = request.get_json()
    player_id = data.get("player_id")
    bet_amount = float(data.get("bet_amount", 0))
    target_multi = float(data.get("target_multi", 2.0))

    # ── Validate ──
    if not player_id:
        return jsonify({"error": "player_id required"}), 400

    db = get_db()
    player = db.execute(
        "SELECT * FROM players WHERE id = ?", (player_id,)
    ).fetchone()

    if player is None:
        return jsonify({"error": "Player not found"}), 404

    if bet_amount < 1.0:
        return jsonify({"error": "Minimum bet is $1.00"}), 400

    if bet_amount > 500.0:
        return jsonify({"error": "Maximum bet is $500.00"}), 400

    if bet_amount > player["balance"]:
        return jsonify({"error": "Insufficient balance"}), 400

    if target_multi < 1.09 or target_multi > 1_000_000:
        return jsonify({"error": "Multiplier must be between 1.09 and 1,000,000"}), 400

    seeds = get_seeds(player_id)
    server_seed = seeds["server_seed"]
    client_seed = seeds["client_seed"]
    nonce = seeds["nonce"]

    # ── Roll ──
    float_val = compute_roll(server_seed, client_seed, nonce)
    rolled_multi = roll_to_multiplier(float_val)
    won = rolled_multi >= target_multi

    # ── Settle ──
    if won:
        payout = round(bet_amount * target_multi, 8)
        pnl = round(payout - bet_amount, 8)
    else:
        payout = 0.0
        pnl = -bet_amount

    new_balance = round(player["balance"] - bet_amount + payout, 8)

    # ── Rotate seeds ──
    revealed_server_seed = server_seed
    revealed_server_seed_hash = seeds["server_seed_hash"]
    new_server_seed = generate_server_seed()
    new_server_seed_hash = sha256_hash(new_server_seed)
    new_nonce = nonce + 1

    now = int(time.time())

    db.execute(
        "UPDATE players SET balance = ? WHERE id = ?",
        (new_balance, player_id),
    )
    db.execute(
        """UPDATE seeds
           SET server_seed = ?, server_seed_hash = ?, nonce = ?
           WHERE player_id = ?""",
        (new_server_seed, new_server_seed_hash, new_nonce, player_id),
    )
    db.execute(
        """INSERT INTO bets
           (player_id, bet_amount, target_multi, rolled_multi, won, pnl,
            server_seed, server_seed_hash, client_seed, nonce, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            player_id, bet_amount, target_multi, rolled_multi, int(won), pnl,
            revealed_server_seed, revealed_server_seed_hash, client_seed,
            nonce, now,
        ),
    )
    db.commit()

    return jsonify({
        "won": won,
        "rolled_multi": rolled_multi,
        "target_multi": target_multi,
        "payout": payout,
        "pnl": pnl,
        "new_balance": new_balance,
        "chance": round(win_chance(target_multi), 8),
        # Provably fair reveal
        "revealed_server_seed": revealed_server_seed,
        "revealed_server_seed_hash": revealed_server_seed_hash,
        "client_seed": client_seed,
        "nonce": nonce,
        # New seeds
        "new_server_seed_hash": new_server_seed_hash,
        "new_nonce": new_nonce,
    })


@app.route("/api/verify", methods=["POST"])
def api_verify():
    """
    Verify a past roll server-side.
    Body: { server_seed, client_seed, nonce }
    Returns: { float_val, rolled_multi, server_seed_hash }
    """
    data = request.get_json()
    ss = data.get("server_seed", "")
    cs = data.get("client_seed", "")
    n = int(data.get("nonce", 0))

    if not ss or not cs:
        return jsonify({"error": "server_seed and client_seed are required"}), 400

    float_val = compute_roll(ss, cs, n)
    rolled_multi = roll_to_multiplier(float_val)
    return jsonify({
        "float_val": float_val,
        "rolled_multi": rolled_multi,
        "server_seed_hash": sha256_hash(ss),
    })


@app.route("/api/bets", methods=["GET"])
def api_bet_history():
    """Get bet history for a player. ?player_id=X&limit=50&offset=0"""
    player_id = request.args.get("player_id")
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    if not player_id:
        return jsonify({"error": "player_id required"}), 400

    rows = get_db().execute(
        """SELECT id, bet_amount, target_multi, rolled_multi, won, pnl,
                  server_seed, server_seed_hash, client_seed, nonce, created_at
           FROM bets WHERE player_id = ?
           ORDER BY created_at DESC
           LIMIT ? OFFSET ?""",
        (player_id, limit, offset),
    ).fetchall()

    return jsonify([dict(r) for r in rows])


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Aggregate stats for a player."""
    player_id = request.args.get("player_id")
    if not player_id:
        return jsonify({"error": "player_id required"}), 400

    db = get_db()
    row = db.execute(
        """SELECT
             COUNT(*)           AS total_bets,
             SUM(won)           AS wins,
             SUM(1 - won)       AS losses,
             SUM(bet_amount)    AS total_wagered,
             SUM(pnl)           AS net_pnl,
             MAX(rolled_multi)  AS best_multi,
             MAX(CASE WHEN won = 1 THEN target_multi END) AS best_win_multi
           FROM bets WHERE player_id = ?""",
        (player_id,),
    ).fetchone()

    player = db.execute(
        "SELECT balance FROM players WHERE id = ?", (player_id,)
    ).fetchone()

    return jsonify({
        **dict(row),
        "balance": player["balance"] if player else 0,
    })


@app.route("/api/leaderboard", methods=["GET"])
def api_leaderboard():
    """Top 10 players by net P&L."""
    rows = get_db().execute(
        """SELECT p.username, p.balance,
                  SUM(b.pnl) AS net_pnl,
                  COUNT(b.id) AS total_bets,
                  SUM(b.won) AS wins
           FROM players p
           JOIN bets b ON b.player_id = p.id
           GROUP BY p.id
           ORDER BY net_pnl DESC
           LIMIT 10"""
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# ─── Health ─────────────────────────────────────────────────────────────────────

@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "db": DATABASE})


# ─── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print("=" * 60)
    print("  CrownCases Limbo Server")
    print("  http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=True, port=5000)