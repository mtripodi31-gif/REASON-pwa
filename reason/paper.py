"""Deterministic Alpaca PAPER execution worker.

This module never selects trades and never calls a model. It only executes a
validated, durable Trade Card from Firestore against the configured paper
account. Live-money hosts and credentials are intentionally unsupported.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from .engine import parse

log = logging.getLogger("reason.paper")
PRIMARY = ("TQQQ", "SQQQ", "UPRO", "SPXU", "UDOW", "SDOW")
BENCHMARKS = ("SPY", "DIA", "QQQ")
FINAL_ORDER_STATES = {"filled", "canceled", "expired", "rejected", "replaced", "done_for_day"}


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _price(value: float) -> str:
    places = 2 if value >= 1 else 4
    return f"{round(value, places):.{places}f}"


@dataclass(frozen=True)
class WorkerSettings:
    project: str
    account_id: str
    key: str
    secret: str
    feed: str = "iex"
    execution_enabled: bool = False

    @classmethod
    def env(cls) -> "WorkerSettings":
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        account = os.environ.get("REASON_ACCOUNT_ID", "").strip()
        if not project or not account:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT and REASON_ACCOUNT_ID are required")
        key = os.environ.get("ALPACA_PAPER_KEY", "").strip()
        secret = os.environ.get("ALPACA_PAPER_SECRET", "").strip()
        if not key or not secret:
            from google.cloud import secretmanager

            client = secretmanager.SecretManagerServiceClient()
            def read(name: str) -> str:
                path = f"projects/{project}/secrets/{name}/versions/latest"
                return client.access_secret_version(request={"name": path}).payload.data.decode().strip()
            key, secret = read("alpaca-paper-key"), read("alpaca-paper-secret")
        return cls(project, account, key, secret,
            os.environ.get("REASON_MARKET_DATA_FEED", "iex").strip() or "iex",
            os.environ.get("REASON_EXECUTION_ENABLED", "false").lower() == "true")


class PaperError(Exception):
    pass


class SubmissionUnknown(PaperError):
    pass


class AlpacaPaper:
    TRADING = "https://paper-api.alpaca.markets"
    DATA = "https://data.alpaca.markets"

    def __init__(self, settings: WorkerSettings):
        self.settings = settings
        self.headers = {
            "APCA-API-KEY-ID": settings.key,
            "APCA-API-SECRET-KEY": settings.secret,
            "Content-Type": "application/json",
        }

    def _request(self, host: str, method: str, path: str, body=None, timeout=12):
        if host not in (self.TRADING, self.DATA) or not path.startswith("/"):
            raise ValueError("Broker destination not permitted")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(host + path, data=data, headers=self.headers, method=method)
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        try:
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read()).get("message", "request rejected")
            except Exception:
                detail = "request rejected"
            raise PaperError(f"Alpaca paper HTTP {exc.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TimeoutError("Alpaca paper request timed out or lost connectivity") from exc

    def snapshot(self):
        account = self._request(self.TRADING, "GET", "/v2/account")
        if account.get("id") != self.settings.account_id:
            raise PaperError("Paper account ID mismatch")
        positions = self._request(self.TRADING, "GET", "/v2/positions")
        orders = self._request(self.TRADING, "GET", "/v2/orders?status=open&limit=500&nested=true")
        return account, positions, orders

    def clock(self):
        return self._request(self.TRADING, "GET", "/v2/clock")

    def asset(self, symbol):
        return self._request(self.TRADING, "GET", "/v2/assets/" + urllib.parse.quote(symbol, safe=""))

    def recent_orders(self):
        return self._request(self.TRADING, "GET", "/v2/orders?status=all&limit=100&nested=true&direction=desc")

    def snapshots(self, symbols):
        symbols = sorted(set(symbols))[:30]
        if not symbols:
            return {}
        query = urllib.parse.urlencode({"symbols": ",".join(symbols), "feed": self.settings.feed})
        result = self._request(self.DATA, "GET", "/v2/stocks/snapshots?" + query)
        return result.get("snapshots", result)

    def by_client_id(self, client_id):
        query = urllib.parse.urlencode({"client_order_id": client_id})
        try:
            return self._request(self.TRADING, "GET", "/v2/orders:by_client_order_id?" + query)
        except PaperError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise

    def submit(self, payload):
        if not self.settings.execution_enabled:
            raise PaperError("Paper execution is disabled in worker configuration")
        client_id = payload["client_order_id"]
        existing = self.by_client_id(client_id)
        if existing:
            return existing
        try:
            return self._request(self.TRADING, "POST", "/v2/orders", payload, timeout=15)
        except TimeoutError:
            # A timeout is not proof that Alpaca rejected the order. Reconcile by
            # deterministic client ID before allowing any later retry.
            time.sleep(1)
            existing = self.by_client_id(client_id)
            if existing:
                return existing
            raise SubmissionUnknown(f"Unknown submission result for {client_id}") from None

    def cancel(self, order_id):
        if not self.settings.execution_enabled:
            raise PaperError("Paper execution is disabled in worker configuration")
        return self._request(self.TRADING, "DELETE", f"/v2/orders/{order_id}")


def market_evidence(broker: AlpacaPaper, symbols):
    snapshots = broker.snapshots(symbols)
    evidence = []
    for symbol in sorted(snapshots):
        item = snapshots[symbol] or {}
        trade, quote = item.get("latestTrade") or {}, item.get("latestQuote") or {}
        minute, daily, previous = item.get("minuteBar") or {}, item.get("dailyBar") or {}, item.get("prevDailyBar") or {}
        observed = trade.get("t") or quote.get("t") or minute.get("t")
        seed = json.dumps([symbol, observed, trade.get("p"), quote.get("bp"), quote.get("ap")], separators=(",", ":"))
        eid = "alpaca:" + broker.settings.feed + ":" + symbol + ":" + hashlib.sha256(seed.encode()).hexdigest()[:16]
        evidence.append({
            "id": eid, "kind": "alpaca_stock_snapshot", "feed": broker.settings.feed,
            "symbol": symbol, "observed_at": observed, "latest_trade": trade,
            "latest_quote": quote, "minute_bar": minute, "daily_bar": daily,
            "previous_daily_bar": previous,
        })
    return evidence


def latest_price(item):
    for section, key in (("latest_trade", "p"), ("latest_quote", "ap"), ("minute_bar", "c"), ("daily_bar", "c")):
        value = item.get(section, {}).get(key)
        if value is not None and float(value) > 0:
            return float(value)
    raise PaperError(f"No usable price for {item.get('symbol', 'symbol')}")


def client_order_id(card_id, symbol, side, role):
    digest = hashlib.sha256(f"{card_id}|{symbol}|{side}|{role}".encode()).hexdigest()[:24]
    return f"reason-{digest}"


class ExecutionWorker:
    """Polls durable state and reconciles one paper plan at a time."""

    def __init__(self, store, broker: AlpacaPaper, owner=None):
        self.store, self.broker = store, broker
        self.owner = owner or uuid.uuid4().hex

    def event(self, kind, message, **details):
        eid = uuid.uuid4().hex
        record = {"id": eid, "at": stamp(), "kind": kind, "message": message, **details}
        self.store.put("events", eid, record)
        return record

    def _record_error(self, message, uncertain=False, **details):
        eid = uuid.uuid4().hex
        record = {"id": eid, "at": stamp(), "component": "paper-worker", "message": message,
                  "order_uncertain": uncertain, **details}
        self.store.put("errors", eid, record)
        if uncertain:
            control = self.store.get("system", "control") or {}
            control.update(entries_paused=True, pause_reason="Order submission uncertain", at=stamp())
            self.store.put("system", "control", control)
        return record

    def _reconcile_fills(self):
        if not hasattr(self.broker,"recent_orders"):return
        def walk(order,owned=False):
            cid=str(order.get("client_order_id") or "");owned=owned or cid.startswith("reason-")
            if owned and order.get("status")=="filled":
                fill_id=str(order.get("id") or cid)
                record={"id":fill_id,"at":order.get("filled_at") or stamp(),"symbol":order.get("symbol"),
                    "side":order.get("side"),"qty":order.get("filled_qty") or order.get("qty"),
                    "price":order.get("filled_avg_price"),"client_order_id":cid,"broker_order_id":order.get("id")}
                if self.store.create("fills",fill_id,record):
                    self.event("fill",f"{str(record['side']).upper()} {record['qty']} {record['symbol']} filled",broker_order_id=record['broker_order_id'])
            for leg in order.get("legs") or []:walk(leg,owned)
        for order in self.broker.recent_orders() or []:walk(order)

    def _cancel_reason_orders(self, orders, symbol=None, entries_only=False):
        for order in orders:
            cid = str(order.get("client_order_id") or "")
            if not cid.startswith("reason-") or order.get("status") in FINAL_ORDER_STATES:
                continue
            if symbol and order.get("symbol") != symbol:
                continue
            if entries_only and order.get("order_class") == "oco":
                continue
            self.broker.cancel(order["id"])
            self.event("cancel", f"Canceled REASON order for {order.get('symbol')}", order_id=order["id"])

    def _submit(self, payload, card_id, role):
        intent_id = payload["client_order_id"]
        intent = {"at": stamp(), "status": "submitting", "card_id": card_id, "role": role,
                  "symbol": payload["symbol"], "side": payload["side"], "qty": payload["qty"],
                  "client_order_id": intent_id}
        created=self.store.create("order_intents", intent_id, intent)
        if not created:
            previous=self.store.get("order_intents",intent_id) or {}
            if previous.get("status")=="acknowledged":
                return {"id":previous.get("broker_order_id"),"status":previous.get("broker_status"),"client_order_id":intent_id}
            # A persisted uncertain/submitting intent is reconciled, never blindly
            # resubmitted across a worker restart.
            existing=self.broker.by_client_id(intent_id)
            if existing:
                previous.update(status="acknowledged",broker_order_id=existing.get("id"),broker_status=existing.get("status"),updated_at=stamp())
                self.store.put("order_intents",intent_id,previous)
                return existing
            if previous.get("status") in ("unknown","submitting"):
                return None
        try:
            order = self.broker.submit(payload)
        except SubmissionUnknown as exc:
            intent.update(status="unknown", error=str(exc), updated_at=stamp())
            self.store.put("order_intents", intent_id, intent)
            self._record_error(str(exc), uncertain=True, client_order_id=intent_id, card_id=card_id)
            return None
        except PaperError as exc:
            intent.update(status="rejected", error=str(exc), updated_at=stamp())
            self.store.put("order_intents", intent_id, intent)
            self._record_error(str(exc), client_order_id=intent_id, card_id=card_id)
            return None
        intent.update(status="acknowledged", broker_order_id=order.get("id"), broker_status=order.get("status"), updated_at=stamp())
        self.store.put("order_intents", intent_id, intent)
        self.event("order", f"{payload['side'].upper()} {payload['qty']} {payload['symbol']} submitted",
                   client_order_id=intent_id, broker_order_id=order.get("id"), card_id=card_id)
        return order

    def _close_all(self, account, positions, orders, control):
        self._cancel_reason_orders(orders)
        evidence = market_evidence(self.broker, [p["symbol"] for p in positions])
        by_symbol = {e["symbol"]: e for e in evidence}
        for position in positions:
            symbol, qty = position["symbol"], int(float(position["qty"]))
            if qty == 0:
                continue
            item = by_symbol.get(symbol)
            if not item:
                self._record_error(f"Close all waiting: no price for {symbol}")
                continue
            snap = item["latest_quote"]
            ref = float((snap.get("bp") if qty > 0 else snap.get("ap")) or latest_price(item))
            side = "sell" if qty > 0 else "buy"
            limit = ref * (0.995 if side == "sell" else 1.005)
            cid = client_order_id("close-all-" + str(control.get("generation", 0)), symbol, side, "close")
            payload = {"symbol": symbol, "qty": str(abs(qty)), "side": side, "type": "limit",
                       "limit_price": _price(limit), "time_in_force": "day", "extended_hours": False,
                       "client_order_id": cid, "position_intent": "sell_to_close" if qty > 0 else "buy_to_close"}
            self._submit(payload, "close-all", "close")
        self.event("control", "Close-all reconciliation submitted")

    def tick(self):
        if hasattr(self.store, "claim_lease") and not self.store.claim_lease(self.owner, 45):
            return {"status": "standby"}
        heartbeat = {"at": stamp(), "owner": self.owner, "status": "running",
                     "execution_enabled": self.broker.settings.execution_enabled}
        self.store.put("system", "worker", heartbeat)
        control = self.store.get("system", "control") or {"entries_paused": True, "close_all": False, "generation": 0}
        try:
            account, positions, orders = self.broker.snapshot()
            self._reconcile_fills()
            if account.get("id") != self.broker.settings.account_id:
                raise PaperError("Bound paper account changed")
            if control.get("close_all"):
                self._close_all(account, positions, orders, control)
                control.update(close_all=False, entries_paused=True, at=stamp())
                self.store.put("system", "control", control)
                return {"status": "close-all"}
            active = self.store.get("system", "active_card")
            if not active:
                return {"status": "idle"}
            card = active["card"]
            current = datetime.now(timezone.utc)
            expired = current >= parse(card["expires_at"])
            if expired:
                self._cancel_reason_orders(orders, entries_only=True)
                active.update(status="expired", updated_at=stamp())
                self.store.put("system", "active_card", active)
                self.event("expiry", f"Trade Card {card['card_id']} expired; exits remain at Alpaca", card_id=card["card_id"])
                return {"status": "expired"}
            market_open=bool(self.broker.clock().get("is_open")) if hasattr(self.broker,"clock") else True
            position_map = {p["symbol"]: int(float(p["qty"])) for p in positions}
            evidence = market_evidence(self.broker, [d["symbol"] for d in card["decisions"]])
            prices = {e["symbol"]: e for e in evidence}
            equity = float(account["equity"])
            open_reason = {o.get("symbol") for o in orders if str(o.get("client_order_id") or "").startswith("reason-")}
            results = []
            for decision in card["decisions"]:
                symbol = decision["symbol"]
                item = prices.get(symbol)
                if not item:
                    results.append({"symbol": symbol, "status": "blocked", "reason": "missing price"})
                    continue
                ref = latest_price(item)
                current_qty = position_map.get(symbol, 0)
                target_qty = math.floor(equity * float(decision["target_weight"]) / ref)
                if current_qty < 0 and target_qty > 0:
                    results.append({"symbol": symbol, "status": "blocked", "reason": "close inherited short before opening long"})
                    continue
                delta = target_qty - current_qty
                if delta == 0:
                    results.append({"symbol": symbol, "status": "at-target"})
                    continue
                risk_reducing = (current_qty > 0 and target_qty < current_qty) or (current_qty < 0 and target_qty == 0)
                if control.get("entries_paused") and not risk_reducing:
                    results.append({"symbol": symbol, "status": "paused"})
                    continue
                if not market_open and not risk_reducing:
                    results.append({"symbol": symbol, "status": "waiting-for-regular-market"})
                    continue
                entry = decision["entry"]
                triggered = entry["kind"] == "immediate" or (entry["kind"] == "above" and ref >= float(entry["price"])) or (entry["kind"] == "below" and ref <= float(entry["price"]))
                if not triggered:
                    results.append({"symbol": symbol, "status": "waiting", "price": ref})
                    continue
                if symbol in open_reason:
                    results.append({"symbol": symbol, "status": "working-order"})
                    continue
                if not risk_reducing and hasattr(self.broker,"asset"):
                    asset=self.broker.asset(symbol)
                    if asset.get("class")!="us_equity" or asset.get("status")!="active" or not asset.get("tradable"):
                        results.append({"symbol":symbol,"status":"blocked","reason":"asset is not an active tradable US equity"})
                        continue
                side = "buy" if delta > 0 else "sell"
                quote = item["latest_quote"]
                raw_limit = quote.get("ap") if side == "buy" else quote.get("bp")
                limit = float(raw_limit or ref) * (1.003 if side == "buy" else .997)
                role = "close" if risk_reducing else "entry"
                cid = client_order_id(card["card_id"], symbol, side, role)
                payload = {"symbol": symbol, "qty": str(abs(delta)), "side": side, "type": "limit",
                           "limit_price": _price(limit), "time_in_force": "day", "extended_hours": False,
                           "client_order_id": cid,
                           "position_intent": ("buy_to_close" if current_qty < 0 else "buy_to_open") if side == "buy" else "sell_to_close"}
                if not risk_reducing and side == "buy":
                    exits = decision.get("exits")
                    payload.update(order_class="bracket", take_profit={"limit_price": _price(float(exits["take"]))},
                                   stop_loss={"stop_price": _price(float(exits["stop"]))})
                order = self._submit(payload, card["card_id"], role)
                results.append({"symbol": symbol, "status": "submitted" if order else "failed", "client_order_id": cid})
            active.update(status="active", last_evaluated_at=stamp(), results=results)
            self.store.put("system", "active_card", active)
            self.store.put("system", "paper_snapshot", {
                "at": stamp(), "account": account, "positions": positions, "orders": orders,
                "revision": active.get("revision", ""), "changing_during_read": False})
            return {"status": "evaluated", "results": results}
        except Exception as exc:
            self._record_error(str(exc))
            heartbeat.update(status="error", message=str(exc), at=stamp())
            self.store.put("system", "worker", heartbeat)
            return {"status": "error"}


def run_forever(interval=10):
    from .cloud import FirestoreStore
    settings = WorkerSettings.env()
    if not settings.execution_enabled:
        raise RuntimeError("REASON_EXECUTION_ENABLED must be true for the paper worker")
    worker = ExecutionWorker(FirestoreStore(settings.project), AlpacaPaper(settings))
    log.warning("REASON paper worker started for bound account; no AI calls are made")
    while True:
        worker.tick()
        time.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    run_forever()
