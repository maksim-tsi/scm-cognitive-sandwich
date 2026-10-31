"""Chat-completion adapters and one local call journal. No credential discovery."""
from __future__ import annotations

import datetime as dt
import hashlib
import math
import multiprocessing as mp
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from stage2.runner.transport import MockTransport, strict_json

from tools.p4_world.world import canonical
from tools.p5_interactive.token_budget import account as account_prompt
from tools.p5_interactive.token_budget import message_bytes
from tools.padua_pilot.transport import _save, _worker

ROUTES = {
    'qwen': ('https://qwen.example.invalid/v1/chat/completions', 'qwen3.8-27b-ud-q4_k_m'),
    'deepseek': ('https://api.deepseek.com/chat/completions', 'deepseek-flash'),
    'mistral': ('https://api.mistral.ai/v1/chat/completions', 'mistral-small-2603'),
}


def utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def save_json(path: Path, obj: Any) -> None:
    _save(path, (canonical(obj) + '\n').encode())


class BudgetExhausted(RuntimeError):
    """Normal end of the authorized request/spending allowance; never retry."""


class IntegrityError(RuntimeError):
    """Do not continue when call accounting/evidence is uncertain."""


class Journal:
    """Persist BEFORE send; reopening never silently replays an unfinished call."""
    def __init__(self, root: Path, max_requests: int, spending_ceiling: float):
        if max_requests < 1 or not 0 <= spending_ceiling < 100:
            raise ValueError('Invalid explicit request/spending cap')
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.deadline: float = float('inf')
        self.path = root / 'calls.sqlite'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, max_requests INTEGER, ceiling REAL, stop TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, episode TEXT, route TEXT, status TEXT, reservation REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS identity (route TEXT PRIMARY KEY, model TEXT, fingerprint TEXT)')
            row = db.execute('SELECT max_requests,ceiling FROM settings WHERE id=1').fetchone()
            if row is None:
                db.execute('INSERT INTO settings VALUES (1,?,?,NULL)', (max_requests, spending_ceiling))
            elif row != (max_requests, spending_ceiling):
                raise IntegrityError('Existing journal limits cannot be replaced')

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5)
        db.execute('PRAGMA synchronous=FULL')
        return db

    def reserve(self, episode: str, route: str, cost: float) -> tuple[str, Path]:
        if not math.isfinite(cost) or cost < 0:
            raise ValueError('Negative reservation')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            limit, ceiling, stop = db.execute('SELECT max_requests,ceiling,stop FROM settings WHERE id=1').fetchone()
            pending = db.execute('SELECT COUNT(*) FROM calls WHERE status IN ("reserved","captured")').fetchone()[0]
            count, spent = db.execute('SELECT COUNT(*),COALESCE(SUM(reservation),0) FROM calls').fetchone()
            if stop or pending:
                raise IntegrityError('STOP or unfinished call; inspect same journal, do not replace it')
            if count >= limit or spent + cost > ceiling + 1e-12:
                raise BudgetExhausted('request_limit' if count >= limit else 'spending_limit')
            request_id = 'P5-' + uuid.uuid4().hex
            directory = self.root / request_id
            directory.mkdir()
            db.execute('INSERT INTO calls VALUES (?,?,?,?,?)', (request_id, episode, route, 'reserved', cost))
        return request_id, directory

    def captured(self, request_id: str) -> None:
        with self.connect() as db:
            if db.execute('UPDATE calls SET status="captured" WHERE id=? AND status="reserved"', (request_id,)).rowcount != 1:
                raise IntegrityError('Invalid capture transition')

    def processed(self, request_id: str) -> None:
        if not (self.root / request_id / 'step.json').is_file():
            raise IntegrityError('Durable step evidence required before processing completion')
        with self.connect() as db:
            if db.execute('UPDATE calls SET status="processed" WHERE id=? AND status="captured"', (request_id,)).rowcount != 1:
                raise IntegrityError('Invalid processing transition')

    def stop(self, reason: str) -> None:
        with self.connect() as db:
            db.execute('UPDATE settings SET stop=COALESCE(stop,?) WHERE id=1', (reason,))

    def bind_identity(self, route: str, model: str, fingerprint: str | None) -> dict[str, Any]:
        with self.connect() as db:
            previous = db.execute('SELECT model,fingerprint FROM identity WHERE route=?', (route,)).fetchone()
            if previous is None:
                db.execute('INSERT INTO identity VALUES (?,?,?)', (route, model, fingerprint))
            elif previous != (model, fingerprint) and route == 'deepseek':
                db.execute('UPDATE identity SET model=?,fingerprint=? WHERE route=?', (model, fingerprint, route))
            elif previous != (model, fingerprint):
                db.execute('UPDATE settings SET stop="observed_model_drift" WHERE id=1')
                # Commit before raising: a fresh process must see STOP.
                db.commit()
                raise IntegrityError('Observed model/fingerprint drift; retained response, pause collection')
        return {'observed_cohort': hashlib.sha256(canonical([route, model, fingerprint]).encode()).hexdigest()[:16],
                'observed_identity_changed': previous is not None and previous != (model, fingerprint)}


class ScriptedClient:
    """Synthetic or recorded ORIGINAL envelopes, same path as HTTP after capture."""
    kind = 'offline_recorded_or_synthetic'

    def __init__(self, responses: list[bytes | dict[str, Any]]):
        self.responses = iter(responses)

    def send(self, body: bytes, request_id: str, directory: Path) -> tuple[str, int | None]:
        response = next(self.responses)
        if isinstance(response, dict):
            raw = response.get('raw', b'')
            status = response['status']
        else:
            raw, status = response, 'complete'
        _save(directory / 'response.bin', raw)
        save_json(directory / 'http.json', {'synthetic': True, 'http_status': 200 if status == 'complete' else None})
        return status, 200 if status == 'complete' else None


class HttpClient:
    """Actual executable adapter, not invoked on a real route during P5."""
    kind = 'https_chat_completions'

    def __init__(self, route: str, secret: str, *, ca_file: str | None = None,
                 test_url: str | None = None, total_timeout: float = 300):
        if route not in ROUTES or not secret or '\n' in secret or '\r' in secret:
            raise ValueError('Known route and in-memory credential required')
        self.route = route
        self.url, self.secret, self.ca_file = ROUTES[route][0], secret, ca_file
        if test_url is not None:
            p = urlsplit(test_url)
            if p.hostname != '127.0.0.1' or p.scheme != 'http' or p.query or p.fragment or p.username:
                raise ValueError('Only explicit synthetic loopback override allowed')
            self.url = test_url
            self.kind = 'synthetic_loopback_http'
        elif total_timeout != 300:
            raise ValueError('Production timeout fixed at300s')
        self.total_timeout = total_timeout
        self.deadline: float = float('inf')

    def _pace(self) -> None:
        if self.route == 'mistral':
            time.sleep(1.0)  # Owner-requested pacing; no retry and no native tool calls.

    def send(self, body: bytes, request_id: str, directory: Path) -> tuple[str, int | None]:
        self._pace()
        context = mp.get_context('spawn')
        receive, send = context.Pipe(duplex=False)
        child = context.Process(target=_worker, args=(self.url, body, request_id, self.secret,
                                                     self.ca_file, str(directory), send))
        started = time.monotonic()
        remaining = getattr(self, 'deadline', float('inf')) - time.time()
        hard_timeout = min(self.total_timeout, max(0.0, remaining))
        child.start()
        send.close()
        connected = False
        try:
            while child.is_alive():
                if time.monotonic() - started > (hard_timeout if connected else min(15, hard_timeout)):
                    break
                if receive.poll(0.02):
                    try:
                        event = receive.recv()
                        connected = connected or event == 'connected'
                    except EOFError:
                        break
                child.join(0.01)
        finally:
            if child.is_alive():
                child.terminate()
            child.join(2)
            if child.is_alive():
                child.kill()
                child.join()
            receive.close()
        http = directory / 'http.json'
        code = strict_json(http.read_bytes())['http_status'] if http.exists() else None
        if (directory / 'child-complete.json').exists():
            return 'complete', code
        # Dispatch-intent is persisted before the POST. Never retry an uncertain call.
        return ('unknown_completion' if (directory / 'dispatch.intent').exists() else 'transport_failure'), code


def request(route: str, messages: list[dict[str, str]], *, profile: str = 'json-only') -> bytes:
    model = ROUTES[route][1]
    # Serialization and context are distinct limits; long Qwen histories are counted exactly.
    message_bytes(messages)
    body: dict[str, Any] = {'model': model, 'messages': messages, 'temperature': 0,
                            'max_tokens': 2048, 'stream': False, 'response_format': {'type': 'json_object'},
                            'tools': [], 'tool_choice': 'none'}
    from tools.p5_interactive import (
        provider_deepseek,
        provider_mistral,
        provider_qwen,
    )
    if profile not in ('json-only','native-structured-v1','native-structured-no-unique-v1'):raise ValueError('Unknown explicit experimental profile')
    schema=None
    if profile=='native-structured-no-unique-v1' and route!='mistral':raise ValueError('Explicit no-unique profile is Mistral-only')
    if profile!='json-only' and route!='deepseek':
        from tools.p5_interactive.operational import SCHEMA
        schema=SCHEMA
    builder={'qwen':provider_qwen.build_request,'deepseek':provider_deepseek.build_request,'mistral':provider_mistral.build_request}[route]
    body=provider_mistral.build_request(body,schema,omit_uniqueness=True) if profile=='native-structured-no-unique-v1' else builder(body,schema)
    raw = canonical(body).encode()
    account_prompt(route, raw)  # Before reservation/dispatch; cached for capture metadata.
    return raw


def capture(journal: Journal, client: Any, route: str, episode: str,
            messages: list[dict[str, str]]) -> tuple[dict[str, Any], str, Path]:
    body = request(route, messages, profile=getattr(client,'experimental_profile','json-only'))
    # Reserve the full configured input/output envelope, even on a failed/unknown request.
    prompt_accounting = account_prompt(route, body)
    input_envelope = prompt_accounting['input_reservation_envelope']
    input_rate, output_rate = (0.15, 0.60) if route == 'mistral' else (0.30, 1.20)
    peak_charge_bound = (input_envelope * input_rate + 2048 * output_rate) / 1_000_000
    # Request-specific bounded envelope, rounded UP to cents; no cache discounts.
    cost = math.ceil(peak_charge_bound * 100) / 100 if route in ('deepseek','mistral') and isinstance(client, HttpClient) else 0.0
    if time.time() >= getattr(journal, 'deadline', float('inf')):
        raise BudgetExhausted('wall_clock_limit')
    request_id, directory = journal.reserve(episode, route, cost)
    _save(directory / 'request.bin', body)
    started = utc()
    try:
        status, code = client.send(body, request_id, directory)
    except Exception:
        journal.stop('transport_or_persistence_exception')
        raise  # No exception text is written; original bytes are retained if present.
    raw_path = directory / 'response.bin'
    raw = raw_path.read_bytes() if raw_path.exists() else b''
    result = MockTransport([{'status': 'complete', 'raw_response_bytes': raw}]).send(request_id, body)
    if status != 'complete':
        result.update(status=status, unknown_completion=status == 'unknown_completion', parsed_output=None)
    elif code != 200:
        result.update(status='http_error', parsed_output=None)
    usage = result.get('usage')
    invalid_usage = isinstance(usage, dict) and any(type(usage.get(k, 0)) is not int or usage.get(k, 0) < 0 for k in ('prompt_tokens', 'completion_tokens'))
    if invalid_usage:
        result.update(status='malformed_envelope', parsed_output=None, error='invalid_usage_metadata')
    elif isinstance(usage, dict) and (usage.get('prompt_tokens', 0) > 12288 or usage.get('completion_tokens', 0) > 2048):
        result.update(status='token_budget_exceeded', parsed_output=None)
        journal.stop('reported_token_budget_violation')
    result.update(started_at=started, finished_at=utc(), requested_model=ROUTES[route][1],
                  prompt_accounting=prompt_accounting, reservation_input_tokens=input_envelope, reservation_output_tokens=2048, peak_charge_bound_usd=peak_charge_bound, committed_reservation_usd=cost,
                  provider_route=route, client_kind=client.kind, transport_kind=client.kind, http_status=code, response_capture_present=raw_path.exists(),
                  request_sha256=hashlib.sha256(body).hexdigest(), response_sha256=hashlib.sha256(raw).hexdigest())
    if getattr(client,'experimental_profile','json-only')!='json-only':
        result['experimental_profile']=client.experimental_profile
    # Nonfinite numeric spellings such as1e999 are a model/envelope failure,
    # not a reason to lose the capture or leave a successful call in the journal.
    try:
        canonical({k: v for k, v in result.items() if not isinstance(v, bytes)})
    except (ValueError, TypeError):
        result.update(status='malformed_json', parsed_output=None, usage=None, error='nonfinite_or_nonserializable_response')
    if result['status'] == 'complete':
        model = result['model']
        if route in ('qwen','mistral') and (not isinstance(model, str) or model != ROUTES[route][1]):
            save_json(directory / 'capture.json', {k: v for k, v in result.items() if not isinstance(v, bytes)})
            journal.captured(request_id)
            journal.stop('model_identity_mismatch')
            raise IntegrityError('Model identity mismatch; original evidence retained')
        try:
            result.update(journal.bind_identity(route, model, result['system_fingerprint']))
        except IntegrityError:
            save_json(directory / 'capture.json', {k: v for k, v in result.items() if not isinstance(v, bytes)})
            journal.captured(request_id)
            raise
    save_json(directory / 'capture.json', {k: v for k, v in result.items() if not isinstance(v, bytes)})
    journal.captured(request_id)
    if result['unknown_completion']:
        journal.stop('unknown_completion')
    return result, request_id, directory


def envelope(event: Any, route: str = 'qwen') -> bytes:
    """Authored synthetic envelope, no invented measured token usage."""
    return canonical({'id': 'synthetic-response', 'model': ROUTES[route][1],
                      'system_fingerprint': 'synthetic-fixture', 'usage': None,
                      'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': canonical(event)}}]}).encode()
