#!/usr/bin/env python3
"""
chat-search — единый поиск по истории чатов Claude Code и Codex.

Хранит индекс в SQLite FTS5 с токенайзером unicode61 — он корректно
разбирает кириллицу, в отличие от готовых Rust-решений.

Команды:
  search   — найти чаты по запросу (группирует попадания по сессиям)
  show     — показать диалог целиком
  index    — обновить индекс (инкрементально, по времени изменения файлов)
  stats    — что лежит в индексе

Поиск — действие по умолчанию, слово search можно не писать:
  chat-search "сегментация оптик"
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
DATA_DIR = Path(
    os.environ.get("CHAT_SEARCH_DIR", HOME / "Library/Application Support/chat-search")
)
DB_PATH = DATA_DIR / "index.db"

# Источники: (агент, корневая папка). Cursor намеренно не индексируем.
SOURCES = [
    ("claude", HOME / ".claude/projects"),
    ("codex", HOME / ".codex/sessions"),
]

CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")

# Служебные врезки харнесса — это не разговор, в индексе от них один шум.
NOISE = re.compile(
    r"<(ide_opened_file|ide_selection|system-reminder|command-message|command-name|"
    r"local-command-stdout|task-notification)>.*?</\1>",
    re.DOTALL,
)


# ─────────────────────────── схема ───────────────────────────

def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            mtime INTEGER NOT NULL,
            size INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            path TEXT PRIMARY KEY,
            agent TEXT NOT NULL,
            cwd TEXT,
            title TEXT,
            started TEXT,
            ended TEXT,
            msgs INTEGER DEFAULT 0
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS msg USING fts5(
            path UNINDEXED,
            agent UNINDEXED,
            role UNINDEXED,
            ts UNINDEXED,
            body,
            tokenize='unicode61',
            prefix='2 3 4'
        );
    """)
    return con


# ─────────────────────────── разбор файлов ───────────────────────────

def _text(content):
    """Достаёт читаемый текст из message.content любой формы."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict) and b.get("type") in ("text", "input_text"):
                t = b.get("text")
                if isinstance(t, str):
                    out.append(t)
        return "\n".join(out)
    return ""


def parse(path: Path, agent: str):
    """Отдаёт (cwd, [(role, ts, body), ...]) для одного файла сессии."""
    cwd = None
    rows = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue

                if cwd is None:
                    c = d.get("cwd") or (d.get("payload") or {}).get("cwd")
                    if isinstance(c, str):
                        cwd = c

                ts = d.get("timestamp") or ""

                if agent == "claude":
                    if d.get("type") not in ("user", "assistant"):
                        continue
                    body = _text((d.get("message") or {}).get("content"))
                    role = d["type"]
                else:  # codex
                    p = d.get("payload") or {}
                    if d.get("type") == "event_msg" and p.get("type") in (
                        "user_message",
                        "agent_message",
                    ):
                        body = p.get("message") or ""
                        role = "user" if p["type"] == "user_message" else "assistant"
                    elif d.get("type") == "response_item" and p.get("type") == "message":
                        body = _text(p.get("content"))
                        role = p.get("role") or "assistant"
                    else:
                        continue

                body = NOISE.sub(" ", body or "").strip()
                if not body or body.startswith("<"):
                    continue
                rows.append((role, ts, body))
    except Exception:
        return None, []
    return cwd, rows


def title_of(rows):
    """Заголовок сессии = первая реплика человека."""
    for role, _ts, body in rows:
        if role == "user":
            t = " ".join(body.split())
            return t[:120]
    return ""


# ─────────────────────────── индексация ───────────────────────────

def cmd_index(args):
    con = connect()
    known = {p: (m, s) for p, m, s in con.execute("SELECT path, mtime, size FROM files")}
    seen = set()
    t0 = time.time()
    added = updated = 0
    total_msgs = 0

    for agent, root in SOURCES:
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            sp = str(path)
            seen.add(sp)
            try:
                st = path.stat()
            except OSError:
                continue
            cur = (int(st.st_mtime), st.st_size)
            if not args.rebuild and known.get(sp) == cur:
                continue

            cwd, rows = parse(path, agent)
            if not rows:
                continue

            # Файл изменился — выбрасываем его старые строки и кладём новые.
            con.execute("DELETE FROM msg WHERE path = ?", (sp,))
            con.executemany(
                "INSERT INTO msg (path, agent, role, ts, body) VALUES (?,?,?,?,?)",
                [(sp, agent, r, ts, b) for r, ts, b in rows],
            )
            con.execute(
                "INSERT OR REPLACE INTO sessions (path, agent, cwd, title, started, ended, msgs)"
                " VALUES (?,?,?,?,?,?,?)",
                (sp, agent, cwd, title_of(rows), rows[0][1], rows[-1][1], len(rows)),
            )
            con.execute(
                "INSERT OR REPLACE INTO files (path, mtime, size) VALUES (?,?,?)",
                (sp, cur[0], cur[1]),
            )
            if sp in known:
                updated += 1
            else:
                added += 1
            total_msgs += len(rows)

    # Файлы, которых больше нет на диске, убираем из индекса.
    gone = [p for p in known if p not in seen]
    for p in gone:
        con.execute("DELETE FROM msg WHERE path = ?", (p,))
        con.execute("DELETE FROM sessions WHERE path = ?", (p,))
        con.execute("DELETE FROM files WHERE path = ?", (p,))

    con.commit()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()

    msg = (
        f"новых: {added}, обновлено: {updated}, удалено: {len(gone)}, "
        f"сообщений записано: {total_msgs}, {time.time() - t0:.1f}с"
    )
    if args.json:
        print(json.dumps({"added": added, "updated": updated, "removed": len(gone),
                          "messages": total_msgs, "seconds": round(time.time() - t0, 1)},
                         ensure_ascii=False))
    else:
        print(msg)


# ─────────────────────────── запрос ───────────────────────────

def build_query(words, mode="and"):
    """
    Собирает FTS5-запрос. Для русского обрезает окончание и ищет по началу
    слова: «сегментации» → «сегмента*», иначе не найдёт «сегментация».
    """
    terms = []
    for w in words:
        w = w.strip()
        if not w:
            continue
        if w.startswith('"') or w.endswith("*"):
            terms.append(w)
            continue
        clean = re.sub(r'["\'()^:]', "", w)
        if not clean:
            continue
        if CYRILLIC.search(clean):
            # Русские окончания: «сегментации» → «сегмента*», «бренд» → «бренд*».
            if len(clean) >= 6:
                terms.append(f'"{clean[:-2]}"*')
            elif len(clean) >= 4:
                terms.append(f'"{clean}"*')
            else:
                terms.append(f'"{clean}"')
        elif len(clean) >= 8:
            terms.append(f'"{clean[:-1]}"*')
        else:
            terms.append(f'"{clean}"')
    joiner = " OR " if mode == "any" else " AND "
    return joiner.join(terms)


def cmd_search(args):
    con = connect()
    q = args.query if args.raw else build_query(args.query.split(), "any" if args.any else "and")
    if not q:
        print("пустой запрос", file=sys.stderr)
        return 2

    where = ["msg MATCH ?"]
    params = [q]
    if args.agent:
        where.append("agent = ?")
        params.append(args.agent)
    if args.days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
        where.append("ts >= ?")
        params.append(cutoff)

    sql = f"""
        SELECT path, agent, role, ts,
               snippet(msg, 4, '[', ']', '…', 18) AS sn,
               rank
        FROM msg
        WHERE {' AND '.join(where)}
        ORDER BY rank
        LIMIT ?
    """
    params.append(args.scan)

    try:
        hits = list(con.execute(sql, params))
    except sqlite3.OperationalError as e:
        print(f"не разобрал запрос: {e}", file=sys.stderr)
        return 2

    # Группируем попадания по сессиям — нужен чат, а не отдельная строка.
    groups = {}
    for path, agent, role, ts, sn, rank in hits:
        g = groups.setdefault(path, {"agent": agent, "hits": 0, "snips": [], "ts": ts})
        g["hits"] += 1
        if len(g["snips"]) < args.snippets:
            g["snips"].append({"role": role, "ts": ts, "text": " ".join(sn.split())})
        if ts and ts > (g["ts"] or ""):
            g["ts"] = ts

    meta = {}
    if groups:
        qs = ",".join("?" * len(groups))
        for p, cwd, title, started, msgs in con.execute(
            f"SELECT path, cwd, title, started, msgs FROM sessions WHERE path IN ({qs})",
            list(groups),
        ):
            meta[p] = {"cwd": cwd, "title": title, "started": started, "msgs": msgs}

    ordered = sorted(groups.items(), key=lambda kv: kv[1]["hits"], reverse=True)[: args.limit]
    con.close()

    out = []
    for path, g in ordered:
        m = meta.get(path, {})
        out.append({
            "session": path,
            "agent": g["agent"],
            "project": m.get("cwd"),
            "title": m.get("title"),
            "date": (g["ts"] or m.get("started") or "")[:10],
            "hits": g["hits"],
            "messages": m.get("msgs"),
            "snippets": g["snips"],
        })

    if args.json:
        print(json.dumps({"query": q, "sessions": out}, ensure_ascii=False, indent=2))
        return 0

    if not out:
        print(f"ничего не нашлось (запрос: {q})")
        return 1
    print(f"запрос: {q} — сессий: {len(out)}\n")
    for r in out:
        proj = (r["project"] or "").replace(str(HOME), "~")
        print(f"[{r['agent']}] {r['date']}  попаданий: {r['hits']}")
        if r["title"]:
            print(f"  {r['title']}")
        if proj:
            print(f"  проект: {proj}")
        for s in r["snippets"]:
            print(f"    · {s['text']}")
        print(f"  открыть: chat-search show {r['session']}\n")
    return 0


# ─────────────────────────── просмотр ───────────────────────────

def cmd_show(args):
    con = connect()
    path = args.session
    if not os.path.exists(path):
        row = con.execute(
            "SELECT path FROM sessions WHERE path LIKE ? LIMIT 1", (f"%{path}%",)
        ).fetchone()
        if not row:
            print("сессия не найдена", file=sys.stderr)
            return 2
        path = row[0]

    info = con.execute(
        "SELECT agent, cwd, title, started, msgs FROM sessions WHERE path = ?", (path,)
    ).fetchone()
    rows = list(
        con.execute(
            "SELECT role, ts, body FROM msg WHERE path = ? ORDER BY rowid", (path,)
        )
    )
    con.close()

    if args.json:
        print(json.dumps({
            "session": path,
            "agent": info[0] if info else None,
            "project": info[1] if info else None,
            "title": info[2] if info else None,
            "messages": [{"role": r, "ts": t, "text": b} for r, t, b in rows],
        }, ensure_ascii=False, indent=2))
        return 0

    if info:
        print(f"{info[0]} · {(info[1] or '').replace(str(HOME), '~')} · {(info[3] or '')[:16]}")
        print(f"{info[2] or ''}\n{'─' * 70}")
    for role, ts, body in rows:
        who = "ТЫ " if role == "user" else "AI "
        text = body if args.full else body[: args.chars]
        if not args.full and len(body) > args.chars:
            text += f"… [+{len(body) - args.chars} символов]"
        print(f"\n{who}{(ts or '')[:16]}\n{text}")
    return 0


def cmd_stats(args):
    con = connect()
    tot = con.execute("SELECT count(*) FROM msg").fetchone()[0]
    ses = con.execute("SELECT count(*) FROM sessions").fetchone()[0]
    by = list(con.execute("SELECT agent, count(*) FROM sessions GROUP BY agent"))
    rng = con.execute("SELECT min(started), max(ended) FROM sessions").fetchone()
    size = DB_PATH.stat().st_size / 1e6 if DB_PATH.exists() else 0
    con.close()
    if args.json:
        print(json.dumps({"messages": tot, "sessions": ses, "by_agent": dict(by),
                          "from": rng[0], "to": rng[1], "db_mb": round(size, 1)},
                         ensure_ascii=False))
    else:
        print(f"сообщений: {tot}, сессий: {ses}, база: {size:.0f} МБ")
        for a, n in by:
            print(f"  {a}: {n}")
        if rng[0]:
            print(f"период: {(rng[0] or '')[:10]} — {(rng[1] or '')[:10]}")


# ─────────────────────────── CLI ───────────────────────────

def main():
    ap = argparse.ArgumentParser(prog="chat-search", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("index", help="обновить индекс")
    p.add_argument("--rebuild", action="store_true", help="перестроить всё с нуля")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("search", help="найти чаты")
    p.add_argument("query")
    p.add_argument("--agent", choices=["claude", "codex"])
    p.add_argument("--days", type=int, help="только за последние N дней")
    p.add_argument("--limit", type=int, default=10, help="сколько сессий показать")
    p.add_argument("--scan", type=int, default=400, help="сколько попаданий разобрать")
    p.add_argument("--snippets", type=int, default=2, help="цитат на сессию")
    p.add_argument("--any", action="store_true", help="любое слово вместо всех")
    p.add_argument("--raw", action="store_true", help="запрос как есть, синтаксис FTS5")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("show", help="показать диалог целиком")
    p.add_argument("session", help="путь к файлу сессии или его кусок")
    p.add_argument("--full", action="store_true", help="не обрезать длинные сообщения")
    p.add_argument("--chars", type=int, default=1200)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("stats", help="что в индексе")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_stats)

    # Поиск — действие по умолчанию: `chat-search "сегментация"` вместо
    # `chat-search search "сегментация"`.
    argv = sys.argv[1:]
    if argv and argv[0] not in {"index", "search", "show", "stats"} and not argv[0].startswith("-"):
        argv = ["search"] + argv

    args = ap.parse_args(argv)
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
