"""Reproducible source-first authoring, no model outputs or P8 scenario import."""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path
from typing import Any

from tools.evaluation_cohort.final_cases import finalize
from tools.p5_interactive.operational_reference import (
    derive_reference,
)
from tools.p5_interactive.providers import save_json

ROOT = Path(__file__).resolve().parents[2].parent / "data"

DESIGNS = [
 ('Cross-dock receiving sequence', 'Coordinate the four booked drops; receiving schedules and outbound loading are binding.', 'FEASIBLE_PLAN'),
 ('Rack space reduces van payload', 'Allocate the sealed consignments after the refrigerated rack has been fitted.', 'FEASIBLE_PLAN'),
 ('Warehouse release versus packing estimate', 'Use the dispatch packet to allocate all consignments; a packing note accompanies the release.', 'FEASIBLE_PLAN'),
 ('Receiver appointment renewed in archive', 'Complete the four appointments on the booked run using available receiving records.', 'FEASIBLE_PLAN'),
 ('Three manifest revisions', 'Reconcile the loading release and assign the deliveries to the two vans.', 'FEASIBLE_PLAN'),
 ('Adjacent-run manifest', 'Allocate today’s outbound consignments; the desk packet contains records from two runs.', 'FEASIBLE_PLAN'),
 ('Unsigned second appointment', 'Both appointment-only receiving bays require individual booking acceptance before dispatch.', 'INSUFFICIENT'),
 ('Fleet-wide payload shortfall', 'Deliver all sealed consignments in one departure per vehicle; no replenishment or split consignments.', 'INFEASIBLE'),
 ('Cross-city deadline lower bound', 'Serve the early unloading appointment and every other mandatory delivery.', 'INFEASIBLE'),
 ('Five drops and optional driver request', 'Plan all five deliveries. The driver’s preferred visiting order is optional.', 'FEASIBLE_PLAN'),
 ('Archive-derived directed approach delay', 'Select a delivery order with the archived approach time and receiving deadline.', 'FEASIBLE_PLAN'),
 ('Approximate packing estimate and confirmed allowance', 'Plan unloading and payload allocation using the released booking records.', 'FEASIBLE_PLAN'),
 ('Competing receiver replacements', 'Dispatch needs the operative booking deadline; the receiver has sent two replacement sheets.', 'INSUFFICIENT'),
 ('Supported four-stop preservation', 'Review the existing four-stop plan and preserve it when it remains supported and feasible.', 'FEASIBLE_PLAN'),
 ('Pallet tare and unloading allowance', 'Allocate the sealed pallets and confirm enough unloading time for all five stops.', 'FEASIBLE_PLAN'),
 ('Opening and completion times in prose', 'Coordinate the four booked receiving windows, including a delayed opening.', 'FEASIBLE_PLAN'),
 ('Driver relay lacks receiving authority', 'The locked receiving bay requires positive booking-specific signed permission.', 'INSUFFICIENT'),
 ('Earlier-shift sheet with current archive', 'Complete this run’s four appointments using the receiving desk and archive.', 'FEASIBLE_PLAN'),
 ('Fleet workshop derating supersedes plate copy', 'Allocate deliveries after the workshop equipment change; read the fleet releases.', 'FEASIBLE_PLAN'),
 ('Available loading fact and unavailable receiving consent', 'Reconcile the consignment mass and the appointment-only receiving consent.', 'INSUFFICIENT'),
 ('Waiting is allowed but return shift is bounded', 'Plan four deliveries, allowing waiting at the opening time; vans must return before shift end.', 'FEASIBLE_PLAN'),
 ('Draft quantity note versus certified mass relay', 'The packing desk lists quantities; obtain authoritative loaded mass for vehicle assignment.', 'FEASIBLE_PLAN'),
 ('Dispatch allowances resolved by final release', 'Resolve the run-specific unloading allowance before committing the five-stop plan.', 'FEASIBLE_PLAN'),
 ('Next-day approval not yet released', 'A booking approval is listed in the document index; dispatch this run only with applicable permission.', 'INSUFFICIENT'),
 ('Two derated vehicles cannot carry mandatory cargo', 'Deliver all indivisible consignments using the two available vehicles; no extra departures.', 'INFEASIBLE'),
 ('Long service conflicts with hard finish time', 'Complete all four mandatory deliveries and respect the receiver completion deadline.', 'INFEASIBLE'),
 ('Another consignment at the same premises', 'Plan this manifest’s deliveries using booking-specific service records.', 'FEASIBLE_PLAN'),
 ('Five-stop preservation with optional estimate', 'Review the current five-stop plan. A rough coffee-break estimate is a nonbinding driver preference.', 'FEASIBLE_PLAN'),
]


def source_text(slot: str, value: int) -> str:
    if slot.startswith('close_'):
        return f'Receiving desk: unloading must be finished by {8 + value // 3600:02}:{value % 3600 // 60:02}. This sheet covers the booking named in the header.'
    if slot.startswith('open_'):
        return f'Receiving desk: do not begin service before {8 + value // 3600:02}:{value % 3600 // 60:02}. Waiting outside is permitted.'
    if slot.startswith('load_'):
        return f'Loading control: the sealed consignment’s certified gross mass is {value / 1000:g} tonnes, including pallets and packaging.'
    if slot.startswith('payload_'):
        return f'Fleet control: after fitted equipment the available payload is {value} kg. This is the usable cargo allowance, not the plate rating.'
    if slot.startswith('travel_'):
        return f'Road archive: the directed approach travel time is {value} seconds for the interval in the header. The reverse approach is a separate entry.'
    return f'Dispatch: reserve {value // 60} minutes for service on this booked delivery. This is the planning allowance, including paperwork.'


def build() -> list[dict[str, Any]]:
    matrix_path = ROOT / 'evidence/stage2/geography/distance-matrix.csv'
    rows = list(csv.DictReader(matrix_path.open()))
    sites = list(dict.fromkeys(r['destination'] for r in rows if r['origin'] == 'depot'))
    edges = {(r['origin'], r['destination']): r for r in rows}
    worlds = []
    for i, (title, instruction, expected) in enumerate(DESIGNS, 1):
        count = 5 if i in (10, 15, 23, 28) else 4
        chosen = ['depot'] + [sites[(i - 1 + j) % 12] for j in (0, 1, 4, 7, 9)[:count]]
        distance = [[0 if a == b else round(float(edges[a, b]['distance_m'])) for b in chosen] for a in chosen]
        travel = [[0 if a == b else int(edges[a, b]['time_20kmh_s']) for b in chosen] for a in chosen]
        d: dict[str, Any] = {
            'id': f'EVAL-{i:02}', 'interface': 'operational-v1', 'title': title,
            'instruction': instruction, 'epoch': 200, 'effective_time': 220,
            'presentation': 'normalized-facts-v1' if i <= 14 else 'naturalistic-message-v1',
            'public': {'entity': f'BOOKING-GROUP-{i:02}', 'scope': f'PADUA-RUN-{i:02}',
                'clock': 'routing seconds after08:00 Europe/Rome; source availability/validity are separate logical epochs',
                'current_parameters': {}, 'current_routes': [{'vehicle': 0, 'nodes': [0, *range(1, count), 0]}, {'vehicle': 1, 'nodes': [0, count, 0]}],
                'source_discovery': 'consult_released_candidate_updates', 'bindings': {}, 'required_slots': [], 'optional_slots': ['driver_preference'], 'channels': {},
                'site_mapping': dict(zip(['DEPOT', 'A', 'B', 'C', 'D', 'E'], chosen)),
                'authority_policy': {'dispatcher': 'assign exact planning allowances and relay certified warehouse/fleet records only',
                    'receiver': 'only verified receiving-desk booking acceptances can set receiving bounds',
                    'road_archive': 'only released archive entries supply directed travel times'},
                'snapshot_provenance': 'unbound loads/windows/fleet are disclosed synthetic assumptions; distances archived OSM-derived; times20km/h proxy'},
            'routing': {'depot': 0, 'distance_m': distance, 'time_s': travel, 'vehicle_capacities_kg': [100, 90],
                'shift_start_s': 0, 'shift_end_s': 10800,
                'orders': [{'node': n, 'demand_kg': 25 if n < 4 else 35, 'service_s': 300, 'open_s': 0, 'close_s': 7200} for n in range(1, count + 1)]},
            'records': [],
            'authoring': {'expected_outcome': expected, 'review_status': 'candidate_pending_single_researcher_review',
                'provenance': 'new naturalistic synthetic operating documents; no observed logistics messages or model-generated references',
                'geography': 'archived directed Padua matrix; no live road/traffic requests', 'mechanism_family': ''}}
        d['public']['presentation'] = d['presentation']

        def bind(slot: str, owner: str = 'dispatcher', *, user: str = 'unavailable', tool: str = 'unavailable', _d: dict[str, Any] = d) -> None:
            d = _d
            if slot in d['public']['bindings']:
                return
            prefix, name, _unit = slot.split('_', 2)
            if prefix in ('load', 'service', 'open', 'close'):
                path = ['orders', ord(name) - ord('A'), {'load': 'demand_kg', 'service': 'service_s', 'open': 'open_s', 'close': 'close_s'}[prefix]]
            elif prefix == 'payload':
                path = ['vehicle_capacities_kg', int(name)]
            else:
                path = ['time_s', ord(name[0]) - ord('A') + 1, ord(name[1]) - ord('A') + 1]
            target = d['routing']
            for k in path[:-1]:
                target = target[k]
            role = 'receiving_manager' if owner == 'receiver' else 'road_archive' if owner == 'road_archive' else 'warehouse_control' if prefix == 'load' else 'fleet_control' if prefix == 'payload' else 'dispatcher'
            d['public']['bindings'][slot] = {'path': path, 'owner': owner, 'unit': 'kg' if prefix in ('load', 'payload') else 'seconds',
                'permitted_issuer_roles': [role], 'required_assertion_kind': 'booking_acceptance' if owner == 'receiver' else 'certified_fact'}
            d['public']['required_slots'].append(slot)
            d['public']['current_parameters'][slot] = target[path[-1]]
            d['public']['channels'][slot] = {'user': user, 'tool': tool}

        def record(slot: str, value: int, suffix: str, *, owner: str = 'dispatcher', channel: str = 'public', _d: dict[str, Any] = d, _i: int = i, _bind: Any = bind, **changes: Any) -> str:
            d, i, bind = _d, _i, _bind
            bind(slot, owner)
            b = d['public']['bindings'][slot]
            rid = f'DOC-{i:02}-{suffix}'
            r = {'id': rid, 'slot': slot, 'value': value, 'owner': owner, 'verified': True, 'authority': 'confirmed', 'precision': 'confirmed',
                'entity': d['public']['entity'], 'scope': d['public']['scope'], 'available_at': 180, 'effective_from': 210, 'effective_to': 260,
                'channel': channel, 'issuer_role': b['permitted_issuer_roles'][0], 'assertion_kind': b['required_assertion_kind'],
                'source_document': rid, 'supersedes': [], 'text': source_text(slot, value)}
            r.update(changes)
            d['records'].append(r)
            return rid

        family = ''
        if i == 1:
            family = 'supported_multistop'
            record('open_B_s', 1800, 'B-OPEN', owner='receiver'); record('close_D_s', 4200, 'D-FINISH', owner='receiver')
        elif i == 2:
            family = 'resource_allocation'
            bind('load_A_kg', user='unknown'); bind('payload_0_kg', user='unknown')
            record('load_A_kg', 60, 'WEIGHBRIDGE', channel='user'); record('payload_0_kg', 80, 'RACK-CERT', channel='user')
        elif i == 3:
            family = 'authority'
            record('load_C_kg', 55, 'LOADING-RELEASE'); record('load_C_kg', 20, 'PACKER-NOTE', issuer_role='packing_clerk')
            record('service_D_s', 420, 'UNLOAD')
        elif i == 4:
            family = 'temporal'
            bind('close_C_s', 'receiver', tool='unknown')
            record('close_C_s', 1200, 'EXPIRED', owner='receiver', effective_to=219)
            record('close_C_s', 4800, 'RENEWED', owner='receiver', channel='tool')
            record('service_A_s', 600, 'SERVICE')
        elif i == 5:
            family = 'supersession'
            a = record('load_D_kg', 75, 'V1', available_at=150)
            b = record('load_D_kg', 50, 'V2', available_at=160, supersedes=[a])
            record('load_D_kg', 40, 'V3', available_at=190, supersedes=[a, b]); record('service_B_s', 540, 'SERVICE')
        elif i == 6:
            family = 'scope'
            record('load_B_kg', 45, 'TODAY'); record('load_B_kg', 95, 'ADJACENT-RUN', scope='PADUA-RETURN-LEG')
            record('close_A_s', 5400, 'ACCEPT', owner='receiver')
        elif i == 7:
            family = 'missing_permission'
            record('close_A_s', 5400, 'A-ACCEPT', owner='receiver'); bind('close_D_s', 'receiver')
            record('close_D_s', 5400, 'D-UNSIGNED', owner='receiver', verified=False)
            d['public']['appointment_rule'] = 'Positive signed booking-specific permission is indispensable for A and D; opening hours alone do not authorize either.'
        elif i == 8:
            family = 'infeasible_capacity'
            record('load_A_kg', 110, 'MASS-A'); record('load_B_kg', 110, 'MASS-B')
        elif i == 9:
            family = 'infeasible_time'
            record('service_A_s', 900, 'SERVICE'); record('close_A_s', 600, 'FINISH', owner='receiver')
        elif i == 10:
            family = 'optional_and_refusal'
            record('service_B_s', 360, 'ALLOWANCE'); record('load_E_kg', 30, 'WEIGHED')
            d['public']['driver_note'] = 'I would prefer E first, but any feasible order is acceptable; no answer is available about my preference.'
        elif i == 11:
            family = 'tool_archive'
            bind('travel_BD_s', 'road_archive', tool='unknown'); record('travel_BD_s', 2400, 'APPROACH', owner='road_archive', channel='tool')
            record('close_D_s', 3600, 'DEADLINE', owner='receiver')
        elif i == 12:
            family = 'precision'
            bind('service_C_s', user='unknown')
            record('service_C_s', 900, 'ESTIMATE', precision='approximate', text='Packing: approximately fifteen minutes may be needed at C.')
            record('service_C_s', 720, 'ALLOWANCE', channel='user'); record('load_D_kg', 50, 'WEIGHT')
        elif i == 13:
            family = 'authority_conflict'
            record('close_A_s', 120, 'RECEIVER-ONE', owner='receiver'); record('close_A_s', 5400, 'RECEIVER-TWO', owner='receiver')
            record('service_B_s', 480, 'ALLOWANCE')
        elif i == 14:
            family = 'supported_preservation'
            record('service_A_s', 300, 'EXISTING-SERVICE'); record('load_D_kg', 35, 'EXISTING-MASS')
        elif i == 15:
            family = 'units_and_allocation'
            record('load_A_kg', 65, 'GROSS-PALLET'); record('service_D_s', 660, 'UNLOADING')
        elif i == 16:
            family = 'window_interpretation'
            record('open_A_s', 2100, 'BAY-OPEN', owner='receiver'); record('close_C_s', 4200, 'C-COMPLETE', owner='receiver')
        elif i == 17:
            family = 'authority'
            bind('close_B_s', 'receiver'); record('close_B_s', 5400, 'DRIVER-PHOTO', owner='receiver', issuer_role='driver', verified=False)
            record('load_C_kg', 50, 'MASS')
            d['public']['appointment_rule'] = 'B requires positive signed booking-specific receiving permission. Driver recollection is not receiver consent.'
        elif i == 18:
            family = 'temporal'
            bind('close_D_s', 'receiver', tool='unknown'); record('close_D_s', 600, 'EARLY-SHIFT', owner='receiver', effective_from=100, effective_to=200)
            record('close_D_s', 5100, 'THIS-SHIFT', owner='receiver', channel='tool'); record('open_B_s', 900, 'B-OPEN', owner='receiver')
        elif i == 19:
            family = 'supersession'
            bind('payload_1_kg', tool='unknown')
            old = record('payload_1_kg', 110, 'PLATE-COPY', available_at=140)
            record('payload_1_kg', 75, 'WORKSHOP-RELEASE', channel='tool', supersedes=[old], available_at=190)
            record('load_C_kg', 55, 'C-WEIGHT')
        elif i == 20:
            family = 'compound_missing'
            bind('load_B_kg', user='unknown'); record('load_B_kg', 60, 'B-WEIGHT', channel='user'); bind('close_C_s', 'receiver')
            d['public']['appointment_rule'] = 'C is appointment-only. Individual signed receiving consent is indispensable and absent from accessible channels.'
        elif i == 21:
            family = 'waiting_and_shift'
            record('open_A_s', 2400, 'LATE-OPEN', owner='receiver'); bind('service_C_s', user='unknown')
            record('service_C_s', 600, 'C-ALLOWANCE', channel='user'); d['routing']['shift_end_s'] = 6600
        elif i == 22:
            family = 'authority'
            bind('load_D_kg', user='unknown'); record('load_D_kg', 15, 'PICK-COUNT', issuer_role='packing_clerk', assertion_kind='quantity_note')
            record('load_D_kg', 70, 'CERTIFIED-RELAY', channel='user'); record('payload_0_kg', 95, 'FLEET')
        elif i == 23:
            family = 'authority_conflict_resolved'
            bind('service_E_s', user='unknown')
            old = record('service_E_s', 900, 'DESK-A'); other = record('service_E_s', 420, 'DESK-B')
            record('service_E_s', 600, 'FINAL-RELEASE', channel='user', available_at=190, supersedes=[old, other]); record('open_C_s', 1200, 'C-OPEN', owner='receiver')
        elif i == 24:
            family = 'unreleased'
            bind('close_A_s', 'receiver', tool='unknown')
            record('close_A_s', 5400, 'TOMORROW', owner='receiver', channel='tool', available_at=201, effective_from=300, effective_to=350)
            record('load_D_kg', 45, 'D-WEIGHT')
            d['public']['appointment_rule'] = 'A needs individual signed acceptance for this run. An indexed future sheet grants no present consent.'
        elif i == 25:
            family = 'infeasible_capacity'
            record('payload_0_kg', 40, 'VAN-ZERO'); record('payload_1_kg', 40, 'VAN-ONE')
        elif i == 26:
            family = 'infeasible_time'
            record('service_D_s', 1200, 'D-ALLOWANCE'); record('close_D_s', 600, 'D-FINISH', owner='receiver')
        elif i == 27:
            family = 'scope'
            record('service_B_s', 480, 'THIS-CONSIGNMENT'); record('service_B_s', 1200, 'OTHER-CONSIGNMENT', entity='OTHER-BOOKING-SAME-PREMISES')
            record('load_C_kg', 45, 'C-MASS')
        elif i == 28:
            family = 'supported_preservation'
            record('service_C_s', 300, 'CURRENT-ALLOWANCE'); record('load_E_kg', 35, 'CURRENT-WEIGHT')
            d['public']['driver_note'] = 'The driver estimates about ten minutes for a personal break. This is optional and does not change service allowances.'
        d['authoring']['mechanism_family'] = family
        ref = derive_reference(d)
        if i in (14, 28):
            # Author the initial operational state from a feasible source-first witness,
            # not from admission/model answers. Other feasible changed plans remain valid.
            d['public']['current_routes'] = sorted([{'vehicle': r['vehicle'], 'nodes': r['nodes']} for r in ref['oracle']['routes']], key=lambda r: r['vehicle'])
        assert ref['outcome'] == expected, (d['id'], ref['outcome'], expected)
        worlds.append(d)
    return finalize(worlds)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=False)
    worlds = build()
    save_json(output / 'scenarios.json', worlds)
    save_json(output / 'references.json', [derive_reference(d) for d in worlds])
    sources = ['evidence/stage2/geography/distance-matrix.csv', 'evidence/stage2/geography/report.md', 'evidence/stage2/geography/summary.json']
    save_json(output / 'source-map.json', {'baseline': 'b4a215345a20549035c2a79d90112ad10eddbcc6',
        'source_files': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
        'source_derived': 'archived directed Padua distances/site IDs only; OpenStreetMap contributors ODbL; POI attribution in original audit',
        'derived': 'submatrices, rounded metres, independent finite routing references',
        'synthetic': 'all operational documents, loads, fleet, windows, source authority, clock epochs,20km/h travel proxy, depot',
        'unknown': 'actual deliveries, truck legality, source authenticity, calibrated travel times and human operational validity',
        'no_P8_scenario_import': True, 'no_subject_model_outputs_used': True})


if __name__ == '__main__':
    main()
