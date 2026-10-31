"""Researcher-approved final amendments and two source-first physical scenarios."""
from __future__ import annotations

import copy
from fractions import Fraction
from typing import Any


def ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def finalize(worlds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for d in worlds:
        d['public']['payload_interpretation'] = 'vehicle_capacities_kg is residual available cargo allowance for this run after equipment/other commitments, not rated vehicle payload'
        d['authoring']['review_status'] = 'researcher_approved_final_amendments_before_inference'
    d = worlds[7]
    d['title'] = 'Indivisible load partition impossibility'
    for o, mass in zip(d['routing']['orders'], [70, 60, 25, 35]):
        o['demand_kg'] = mass
    for r, mass in zip(d['records'], [70, 60]):
        r['value'] = mass; r['text'] = f'Warehouse release: certified gross mass is {mass} kg including packaging.'
    d = worlds[8]
    lower = copy.deepcopy(d['routing']['time_s'])
    for k in range(len(lower)):
        for a in range(len(lower)):
            for b in range(len(lower)):
                lower[a][b] = min(lower[a][b], lower[a][k] + lower[k][b])
    close = 600 + ((lower[0][1] - 1) // 60) * 60
    d['records'][0].update(value=600, text='Dispatch: reserve 10 minutes for service at A.')
    d['records'][1].update(value=close, text=f'Receiving manager: unloading must be finished by {8+close//3600:02}:{close%3600//60:02}.')
    worlds[2]['records'][1]['text'] = 'Packing clerk: the packed consignment weighs 20 kg according to my signed desk note. No warehouse weighing release is attached.'
    worlds[11]['records'][0]['text'] = 'Packing desk: service may take approximately fifteen minutes; this is an estimate, not a confirmed planning allowance.'
    worlds[21]['records'][0]['text'] = 'Packing clerk: fifteen cartons are listed on the picking sheet. This quantity note does not report certified gross mass.'
    worlds[12]['public']['booking_version_semantics'] = 'The two receiver sheets are conflicting alternative booking versions, not cumulative independent bounds. Neither establishes precedence or supersession.'
    worlds[18]['records'][0]['text'] = 'Fleet control, pre-workshop release: available payload is 110 kg under the earlier equipment configuration. Refer to the document index for subsequent releases.'
    worlds[18]['title'] = 'Workshop release supersedes pre-workshop allowance'

    def new(n: int, base: dict[str, Any], presentation: str, title: str, instruction: str) -> dict[str, Any]:
        result = copy.deepcopy(base); result.update(id=f'EVAL-{n}', title=title, instruction=instruction, presentation=presentation)
        result['public'].update(entity=f'BOOKING-GROUP-{n}', scope=f'PADUA-RUN-{n}', presentation=presentation,
                                current_parameters={}, bindings={}, required_slots=[], channels={})
        result['records'] = []
        result['authoring'].update(expected_outcome='FEASIBLE_PLAN', mechanism_family='imperial_volume_clearance' if n==29 else 'qualified_cold_chain')
        return result

    def record(d: dict[str, Any], slot: str, value: int, path: list[Any], text: str, suffix: str, unit: str) -> None:
        rid = f'DOC-{d["id"][-2:]}-{suffix}'
        d['public']['bindings'][slot] = {'path':path, 'owner':'dispatcher','unit':unit,
            'permitted_issuer_roles':['warehouse_control'], 'required_assertion_kind':'certified_fact'}
        d['public']['required_slots'].append(slot); d['public']['channels'][slot]={'user':'unavailable','tool':'unavailable'}
        obj=d['routing']
        for part in path[:-1]: obj=obj[part]
        d['public']['current_parameters'][slot]=obj[path[-1]]
        d['records'].append({'id':rid,'slot':slot,'value':value,'owner':'dispatcher','verified':True,'authority':'confirmed','precision':'confirmed',
            'entity':d['public']['entity'],'scope':d['public']['scope'],'available_at':180,'effective_from':210,'effective_to':260,
            'channel':'public','issuer_role':'warehouse_control','assertion_kind':'certified_fact','source_document':f'ORIGINAL-{d["id"]}', 'supersedes':[], 'text':text})

    d = new(29, worlds[15], 'naturalistic-message-v1', 'UK import with upright oversized crate',
        'Allocate the four sealed consignments to the Italian carrier vehicles and plan all booked deliveries using the original shipping documents and carrier specifications.')
    d['routing']['vehicle_capacities_kg']=[100,90]
    d['routing'].update(vehicle_volumes_l=[1800,1400],loading_width_mm=[1000,1100],loading_height_mm=[1000,1000])
    for o,mass,vol in zip(d['routing']['orders'],[25,35,30,8],[500,650,600,500]):
        o.update(demand_kg=mass,volume_l=vol,service_s=300,open_s=0,close_s=7200)
    d['routing']['orders'][0]['upright_dimensions_mm']=[1000,900,900]
    text='UK packing certificate, crate A: certified gross mass is 170 lb; packed volume is 40 ft³; external dimensions (length × width × height) are 48 × 40 × 36 inches. Rigid crate: keep upright, no tilting or dismantling; horizontal rotation is permitted. Values include packaging.'
    values=[ceil_fraction(Fraction(170)*Fraction(45359237,100000000)),ceil_fraction(Fraction(40)*Fraction(28316846592,1000000000)),ceil_fraction(Fraction(48)*Fraction(254,10)),ceil_fraction(Fraction(40)*Fraction(254,10)),ceil_fraction(Fraction(36)*Fraction(254,10))]
    for slot,value,path,unit in zip(['load_A_kg','volume_A_l','length_A_mm','width_A_mm','height_A_mm'],values,
        [['orders',0,'demand_kg'],['orders',0,'volume_l'],['orders',0,'upright_dimensions_mm',0],['orders',0,'upright_dimensions_mm',1],['orders',0,'upright_dimensions_mm',2]],['kg','litres','mm','mm','mm']):
        record(d,slot,value,path,text,slot.upper(),unit)
    d['public']['metric_planning_contract']='Integer kg, litres and mm; round cargo requirements upward at the final unit boundary, never round capacities upward. Clearance allows horizontal rotation only; aggregate volume is necessary but not a3D packing guarantee.'
    d['public']['carrier_specification']='Verified applicable carrier sheet: residual cargo allowances100/90kg, usable cargo volumes1.8/1.4m³; clear loading widths1000/1100mm and heights1000/1000mm. Other consignments are documented packable within these apertures.'
    d['authoring']['physical_reference']={'exact_mass_kg':'77.11070290','exact_volume_m3':'1.132673863680','exact_dimensions_mm':['1219.2','1016','914.4'],'rounded_requirements':[78,1133,1220,1016,915],'constants':'1lb=0.45359237kg;1ft³=0.028316846592m³;1inch=25.4mm; exact definitions; final ceilings only'}
    worlds.append(d)

    d = new(30, worlds[0], 'normalized-facts-v1', 'Qualified pharmaceutical and chilled-food runs',
        'Allocate the two medicine and two chilled-food consignments to qualified carrier vehicles and complete all four deliveries under the applicable batch transport instructions.')
    for o,mass in zip(d['routing']['orders'],[20,15,25,30]):
        o.update(demand_kg=mass,service_s=300,open_s=0,close_s=7200)
    d['routing']['vehicle_capacities_kg']=[100,90]
    for o in d['routing']['orders']:o['allowed_vehicles']=[0] if o['node']<=2 else [1]
    d['public']['transport_documents']=[
      {'id':'QUALITY-30-BATCH','verified':True,'issuer':'carrier_quality_manager','available_at':180,'effective_from':210,'effective_to':260,'scope':d['public']['scope'],
       'text':'For these specified medicine batches M1/M2 and food batches F1/F2, shared transportation has not been validated. This run must not co-load either medicine batch with either food batch. This is carrier quality policy, not a universal statutory ban.'},
      {'id':'QUALIFICATION-30-FLEET','verified':True,'issuer':'carrier_quality_manager','available_at':180,'effective_from':210,'effective_to':260,
       'text':'Vehicle0: mapped, monitored and qualified for medicine transport at+2…+8°C; food transport is separately qualified at0…+4°C. Vehicle1: monitored food qualification0…+4°C only; no medicine transport qualification. Both are refrigerated. Medicines M1/M2 require+2…+8°C; foods F1/F2 require0…+4°C.'}]
    d['public']['eligibility_derivation']='M1/M2 must use vehicle0 (medicine-qualified). All consignments are mandatory. Batch-specific no-co-loading policy therefore requires F1/F2 on vehicle1, which is food-qualified. allowed_vehicles encodes this documented run-specific implication, not temperature overlap alone.'
    record(d,'service_A_s',300,['orders',0,'service_s'],'Dispatch: reserve5 minutes for service at A.','SERVICE','seconds')
    record(d,'load_C_kg',25,['orders',2,'demand_kg'],'Loading control: certified gross mass is25kg.','MASS','kg')
    d['authoring']['regulatory_basis']={'GDP':'EU GDP2013/C343/01 Chapter9: required transport conditions, suitable qualified equipment, risk-based procedures; no universal food co-loading ban','food':'Regulation(EC)852/2004 AnnexII ChapterIV: contamination protection, separation where necessary, appropriate temperatures/monitoring; no universal medicine/food co-loading ban'}
    worlds.append(d)
    return worlds
