"""Single-attempt HTTP client with durable evidence and hard process deadlines.

No credential discovery, redirects, proxy environment, endpoint fallback or retry.
The module has no CLI and importing it never dispatches a request.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import http.client
import json
import multiprocessing as mp
import os
import re
import sqlite3
import ssl
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 1048576


class ResponseLimitExceeded(ValueError):
    pass

from stage2.evidence_layer.runtime import packet_hash
from stage2.runner.protocol import serialize_request
from stage2.runner.transport import MockTransport, strict_json
from stage2.runner.workflow import run_offline_episode


def _utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _save(path: Path, raw: bytes) -> None:
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(path.parent)


def _worker(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError('Live HTTP dispatch disabled: public package is offline-only')


class HttpTransport:
    """One exact request per prebound development fixture, <=5 persistent attempts.

    Any failed/unfinished/unknown attempt halts automatic continuation. A restart
    never replays a prepared/sent request. Reconciliation is deliberately manual.
    Credentials must be supplied in memory by a separately authorized caller.
    """
    max_retries = 0

    def __init__(self, url: str, root: Path, fixtures: dict[str, bytes], *,
                 ca_file: str | None = None, connect_timeout: float = 15,
                 total_timeout: float = 300, test_loopback_http: bool = False):
        parsed = urlsplit(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Endpoint must not contain credentials/query/fragment')
        if parsed.scheme == 'https' and (
            parsed.hostname != 'qwen.example.invalid' or parsed.port not in {None, 443}
        ) and not (test_loopback_http and parsed.hostname == '127.0.0.1'):
            raise ValueError('Pinned HTTPS origin required')
        if parsed.path != '/v1/chat/completions':
            raise ValueError('Exact chat-completions path required')
        if parsed.scheme != 'https' and not (
            test_loopback_http and parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
        ):
            raise ValueError('Verified HTTPS required outside loopback tests')
        if not test_loopback_http and (connect_timeout, total_timeout) != (15, 300):
            raise ValueError('Production timeouts must remain exactly15/300 seconds')
        if not 0 < connect_timeout <= total_timeout <= 300:
            raise ValueError('Invalid bounded timeout policy')
        if not 1 <= len(fixtures) <= 5 or any(not k.startswith('DEV-') for k in fixtures):
            raise ValueError('At most five explicitly bound development fixtures')
        for fixture_id, raw in fixtures.items():
            body = strict_json(raw)
            if serialize_request(body) != raw:
                raise ValueError('Canonical exact public payload required')
            packet = strict_json(body['messages'][1]['content'].encode())
            if packet['case_id'] != fixture_id:
                raise ValueError('Fixture/payload ID mismatch; article input forbidden')
        self.url, self.root, self.fixtures = url, root, dict(fixtures)
        self.ca_file, self.connect_timeout, self.total_timeout = ca_file, connect_timeout, total_timeout
        root.mkdir(parents=True, exist_ok=True)
        self.database = root / 'attempts.sqlite'
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS attempts (request_id TEXT PRIMARY KEY, '
                       'fixture_id TEXT UNIQUE, request_hash TEXT, started TEXT, status TEXT, '
                       'unknown_completion INTEGER)')
            db.execute('CREATE TABLE IF NOT EXISTS run_state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), '
                       'status TEXT NOT NULL CHECK(status IN ("ACTIVE","STOPPED")), '
                       'reason TEXT, request_id TEXT)')
            state = db.execute('SELECT status FROM run_state WHERE singleton=1').fetchone()
            if state is None:
                legacy = db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0] > 0
                db.execute('INSERT INTO run_state VALUES (1,?,?,NULL)',
                           ('STOPPED' if legacy else 'ACTIVE', 'legacy_run_state_missing' if legacy else None))
            db.execute('CREATE TABLE IF NOT EXISTS finalizations (request_id TEXT PRIMARY KEY, evidence_hashes TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS binding (name TEXT PRIMARY KEY, value TEXT)')
            binding = serialize_request({'url': url, 'connect_timeout': connect_timeout,
                'total_timeout': total_timeout,
                'ca_sha256': hashlib.sha256(Path(ca_file).read_bytes()).hexdigest() if ca_file else None,
                'fixtures': {
                k: hashlib.sha256(v).hexdigest() for k, v in fixtures.items()}}).decode()
            prior = db.execute('SELECT value FROM binding WHERE name="profile"').fetchone()
            if prior is not None and prior[0] != binding:
                raise ValueError('Cannot rebind an existing pilot ledger')
            db.execute('INSERT OR IGNORE INTO binding VALUES ("profile",?)', (binding,))

    def send(self, fixture_id: str, request_id: str, request_bytes: bytes, *, secret: str) -> dict[str, Any]:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', request_id):
            raise ValueError('Unsafe request ID')
        if not secret or '\r' in secret or '\n' in secret:
            raise ValueError('Nonempty in-memory bearer value required')
        if self.fixtures.get(fixture_id) != request_bytes:
            raise ValueError('Request differs from frozen development fixture')
        start_utc, start = _utc(), time.monotonic()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            blocked = self._run_blocker(db)
            if blocked is None and db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0] >= 5:
                blocked = 'Five-attempt ceiling exhausted'
            if blocked is None:
                db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?)', (
                    request_id, fixture_id, hashlib.sha256(request_bytes).hexdigest(), start_utc, 'prepared', 1))
        # Commit any discovered STOP before raising; exception rollback cannot erase the veto.
        if blocked is not None:
            raise ValueError(blocked)
        directory = self.root / request_id
        directory.mkdir(exist_ok=False)
        _save(directory / 'request.bin', request_bytes)
        context = mp.get_context('spawn')
        parent, child = context.Pipe(duplex=False)
        process = context.Process(target=_worker, args=(self.url, request_bytes, request_id,
                                  secret, self.ca_file, str(directory), child))
        connected, timeout = False, False
        process.start()
        child.close()
        while process.is_alive():
            remaining = min(start + self.total_timeout,
                            start + self.connect_timeout if not connected else float('inf')) - time.monotonic()
            if remaining <= 0:
                timeout = True
                process.terminate()
                process.join(1)
                if process.is_alive():
                    process.kill()
                    process.join()
                break
            if parent.poll(min(remaining, 0.02)):
                try:
                    phase = parent.recv()
                except EOFError:
                    break
                if phase == 'connected':
                    connected = True
        process.join(1)
        if process.is_alive():
            process.kill()
            process.join()
            timeout = True
        parent.close()
        dispatched = (directory / 'dispatch.intent').exists()
        raw_path = directory / 'response.bin'
        raw = raw_path.read_bytes() if raw_path.exists() else None
        received = (directory / 'child-complete.json').exists()
        http_meta = json.loads((directory / 'http.json').read_bytes()) if (directory / 'http.json').exists() else {}
        content_encoding = {k.lower(): v for k, v in http_meta.get('headers', [])}.get('content-encoding', 'identity')
        child_error = json.loads((directory / 'child-error.json').read_bytes()) if (directory / 'child-error.json').exists() else {}
        if child_error.get('error_type') == 'ResponseLimitExceeded':
            status = 'response_limit_exceeded'
        elif timeout:
            status = 'timeout_unknown_completion' if dispatched else 'timeout_connect'
        elif not received:
            status = 'transport_error'
        elif http_meta.get('http_status') != 200:
            status = 'http_error'
        elif content_encoding.lower() != 'identity':
            status = 'unsupported_content_encoding'
        else:
            status = 'complete'
        event = {'status': 'complete', 'raw_response_bytes': raw}
        if status == 'complete':
            capture = MockTransport([event]).send(request_id, request_bytes)
        else:
            capture = MockTransport([{'status': 'transport_error', 'raw_response_bytes': raw}]).send(request_id, request_bytes)
            capture['status'] = status
        capture.update(transport_kind='http_single_attempt', clock_source='utc_and_monotonic',
                       started_at=start_utc, finished_at=_utc(), duration_s=time.monotonic() - start,
                       dispatched=dispatched, unknown_completion=dispatched and (
                           not received or http_meta.get('http_status') != 200
                           or capture.get('finish_reason') not in {'stop', 'length'}),
                       http=http_meta, network_error_type=child_error.get('error_type'),
                       response_capture_ceiling=MAX_RESPONSE_BYTES, deadline_seconds=self.total_timeout,
                       connect_deadline_seconds=self.connect_timeout, redirects=0, retries=0)
        if status == 'complete' and capture['status'] == 'complete':
            expected = json.loads(request_bytes)['model']
            if capture['model'] != expected:
                capture['status'] = 'model_identity_mismatch'
        capture.update(fixture_id=fixture_id, may_have_dispatched=dispatched,
                       request_sha256=hashlib.sha256(request_bytes).hexdigest(),
                       raw_response_sha256=hashlib.sha256(raw).hexdigest() if raw is not None else None,
                       assistant_content_sha256=hashlib.sha256(capture['assistant_content_bytes']).hexdigest()
                       if isinstance(capture.get('assistant_content_bytes'), bytes) else None)
        # Whole payload/error response is retained. No headers containing credentials.
        persisted = {k: v for k, v in capture.items() if not isinstance(v, bytes)}
        _save(directory / 'capture.json', serialize_request(persisted))
        if isinstance(capture.get('assistant_content_bytes'), bytes):
            _save(directory / 'assistant.bin', capture['assistant_content_bytes'])
        with self._connect() as db:
            db.execute('UPDATE attempts SET status=?,unknown_completion=? WHERE request_id=?',
                       ('response_captured' if capture['status'] == 'complete' else capture['status'],
                        int(capture['unknown_completion']), request_id))
            if capture['status'] != 'complete':
                self._latch_stop(db, 'capture_failure:' + capture['status'], request_id)
        return capture


    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database)
        db.execute('PRAGMA synchronous=FULL')
        return db

    _REQUIRED_EVIDENCE = frozenset({
        'request.bin', 'response.bin', 'assistant.bin', 'capture.json',
        'http.json', 'child-complete.json', 'dispatch.intent', 'workflow.json',
    })

    def _latch_stop(self, db: sqlite3.Connection, reason: str, request_id: str | None) -> None:
        # No reset/clear operation. Preserve the first durable STOP reason.
        db.execute('INSERT INTO run_state VALUES (1,"STOPPED",?,?) '
                   'ON CONFLICT(singleton) DO UPDATE SET status="STOPPED",reason=excluded.reason,'
                   'request_id=excluded.request_id WHERE run_state.status IS NOT "STOPPED"', (reason, request_id))

    def _decision_stop_reason(self, directory: Path) -> str | None:
        """Frozen replay derives decisions; an editable workflow is not its own authority."""
        capture = strict_json((directory / 'capture.json').read_bytes())
        capture.update(request_bytes=(directory / 'request.bin').read_bytes(),
                       raw_response_bytes=(directory / 'response.bin').read_bytes(),
                       assistant_content_bytes=(directory / 'assistant.bin').read_bytes())
        body = strict_json(capture['request_bytes'])
        packet = strict_json(body['messages'][1]['content'].encode())
        recorded = strict_json((directory / 'workflow.json').read_bytes())
        expected = run_offline_episode(packet, capture)
        # Only outer provenance labels differ in the accepted session adapter.
        ignored = {'classification', 'frozen_workflow_classification'}
        if {k: v for k, v in recorded.items() if k not in ignored} != {
            k: v for k, v in expected.items() if k not in ignored
        }:
            raise ValueError('Stored workflow disagrees with frozen replay')
        if expected.get('capture_status') != 'complete' or expected.get('same_original_s2_s3') is not True:
            return 'workflow_qualification_failure'
        for lane in ('S2', 'S3'):
            result = expected['lanes'][lane]
            if (result.get('attempt_status') != 'accepted'
                or result.get('admission', {}).get('admitted') is not True
                or result.get('admission', {}).get('output_contract', {}).get('valid') is not True):
                return 'policy_rejected_original:' + lane
        return None

    def _prior_blocker(self, db: sqlite3.Connection) -> tuple[str, str, bool] | None:
        rows = db.execute('SELECT a.request_id,a.status,a.request_hash,f.evidence_hashes '
                          'FROM attempts a LEFT JOIN finalizations f ON a.request_id=f.request_id').fetchall()
        for request_id, status, request_hash, encoded in rows:
            if status != 'complete' or encoded is None:
                return request_id, 'Prior failed/unfinished/legacy attempt requires review; no retry', status not in {
                    'prepared', 'response_captured'}
            try:
                hashes = strict_json(encoded.encode())
                if not isinstance(hashes, dict) or set(hashes) != self._REQUIRED_EVIDENCE:
                    raise ValueError('Incomplete finalization')
                directory = self.root / request_id
                if hashes['request.bin'] != request_hash or any(
                    not (directory / name).is_file()
                    or hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest
                    for name, digest in hashes.items()
                ):
                    raise ValueError('Changed finalization evidence')
                reason = self._decision_stop_reason(directory)
                if reason:
                    return request_id, reason, True
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                return request_id, 'Prior completion evidence invalid; review required', True
        return None

    def _run_blocker(self, db: sqlite3.Connection) -> str | None:
        state = db.execute('SELECT status FROM run_state WHERE singleton=1').fetchone()
        if state is None or state[0] not in {'ACTIVE', 'STOPPED'}:
            self._latch_stop(db, 'run_state_missing_or_invalid', None)
            return 'Pilot run STOP: state missing/invalid; review required'
        if state[0] == 'STOPPED':
            return 'Pilot run STOP: continuation prohibited; review required'
        prior = self._prior_blocker(db)
        if prior is not None:
            request_id, reason, terminal = prior
            if terminal:
                self._latch_stop(db, reason, request_id)
            return reason
        return None

    def _require_prior_finalized(self, db: sqlite3.Connection) -> None:
        """Read-only guard retained for offline inspection; send also persists STOP."""
        state = db.execute('SELECT status FROM run_state WHERE singleton=1').fetchone()
        prior = self._prior_blocker(db)
        if state is None or state[0] != 'ACTIVE' or prior is not None:
            raise ValueError('Prior attempt or pilot run STOP requires review; no retry')

    def finalize(self, request_id: str) -> None:
        """Second phase: durable workflow evidence, then atomic receipt + complete.

        This never dispatches or retries. Any exception/crash before commit leaves
        response_captured (or the original failure), which blocks later sends.
        """
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', request_id):
            raise ValueError('Unsafe request ID')
        directory = self.root / request_id
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT fixture_id,request_hash,status,unknown_completion '
                             'FROM attempts WHERE request_id=?', (request_id,)).fetchone()
            if row is None or row[2] != 'response_captured' or row[3] != 0:
                raise ValueError('Only known captured responses can finalize')
            fixture_id, request_hash = row[0], row[1]
            hashes = {}
            for name in sorted(self._REQUIRED_EVIDENCE):
                path = directory / name
                with path.open('rb') as stream:
                    raw = stream.read()
                    os.fsync(stream.fileno())
                hashes[name] = hashlib.sha256(raw).hexdigest()
            capture = strict_json((directory / 'capture.json').read_bytes())
            workflow = strict_json((directory / 'workflow.json').read_bytes())
            original_hash = hashes['assistant.bin']
            proposal = strict_json((directory / 'assistant.bin').read_bytes())
            proposal_hash = packet_hash(proposal)
            if (hashes['request.bin'] != request_hash
                or self.fixtures.get(fixture_id) != (directory / 'request.bin').read_bytes()
                or capture.get('status') != 'complete'
                or capture.get('unknown_completion') is not False
                or capture.get('request_id') != request_id
                or capture.get('fixture_id') != fixture_id
                or capture.get('request_sha256') != request_hash
                or capture.get('raw_response_sha256') != hashes['response.bin']
                or capture.get('assistant_content_sha256') != original_hash
                or workflow.get('case_id') != fixture_id
                or workflow.get('capture_status') != 'complete'
                or workflow.get('same_original_s2_s3') is not True
                or workflow.get('original_sha256') != original_hash
                or capture.get('parsed_output') != proposal
                or any(workflow.get('lanes', {}).get(lane, {}).get('proposal_hash') != proposal_hash
                       for lane in ('S2', 'S3'))):
                raise ValueError('Workflow/capture qualification evidence inconsistent')
            stop_reason = self._decision_stop_reason(directory)
            _sync_directory(directory)
            _sync_directory(self.root)
            db.execute('INSERT INTO finalizations VALUES (?,?)',
                       (request_id, serialize_request(hashes).decode()))
            updated = db.execute('UPDATE attempts SET status="complete" '
                                 'WHERE request_id=? AND status="response_captured"', (request_id,))
            if updated.rowcount != 1:
                raise ValueError('Attempt changed before finalization')
            if stop_reason is not None:
                self._latch_stop(db, stop_reason, request_id)
            # Context-manager commit atomically persists receipt and complete.
