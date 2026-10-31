"""Opt-in message presentation and bounded deterministic reading; no hidden truth lookup.

Historical normalized packets are unchanged. The prose reader is a declared baseline/
admission component, not an independent reference annotator or a general NLP claim.
"""
from __future__ import annotations

import copy
import re
from decimal import ROUND_CEILING, Decimal
from typing import Any


def message_only(d: dict[str, Any]) -> bool:
    return d.get('presentation') == 'naturalistic-message-v1'


def wire_record(d: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(record)
    if message_only(d):
        result.pop('value', None)
    return result


def read_record(record: dict[str, Any]) -> dict[str, Any]:
    """Extract explicit positive assertions only, with no IDs/expected-answer access.

    Unit conversions are exact. Unsupported/ambiguous prose has value=None, never
    a guessed number. Ownership/time/supersession are checked separately as before.
    """
    result = copy.deepcopy(record)
    if 'value' in result:
        return result
    text = result.get('text', '')
    slot = result.get('slot', '')
    values: set[int] = set()
    if slot.startswith(('close_', 'open_')):
        verb = r'(?:finish(?:ed)? by|clear the bay by|completed no later than)' if slot.startswith('close_') else r'(?:do not begin service before|must not start before)'
        for hour, minute in re.findall(verb + r'\s+(\d{2}):(\d{2})\b', text, re.IGNORECASE):
            h, m = int(hour), int(minute)
            if 8 <= h <= 23 and m < 60:
                values.add((h - 8) * 3600 + m * 60)
    elif slot.startswith(('load_', 'payload_')):
        pattern = r'(?:certified (?:gross )?mass is|available payload is|weighs)\s+(\d+(?:\.\d+)?)\s*(kg|tonnes?|lb)\b'
        for number, unit in re.findall(pattern, text, re.IGNORECASE):
            value = Decimal(number) * (1000 if unit.lower().startswith('tonne') else Decimal('0.45359237') if unit.lower()=='lb' else 1)
            if unit.lower() == 'lb':
                values.add(int(value.to_integral_value(rounding=ROUND_CEILING)))
            elif value == int(value):
                values.add(int(value))
    elif slot.startswith('volume_'):
        for number in re.findall(r'packed volume is\s+(\d+(?:\.\d+)?)\s*ft[³3]', text, re.IGNORECASE):
            values.add(int((Decimal(number)*Decimal('28.316846592')).to_integral_value(rounding=ROUND_CEILING)))
    elif slot.startswith(('length_', 'width_', 'height_')):
        for dims in re.findall(r'are\s+(\d+(?:\.\d+)?)\s*[×x]\s*(\d+(?:\.\d+)?)\s*[×x]\s*(\d+(?:\.\d+)?)\s*inches', text, re.IGNORECASE):
            index={'length':0,'width':1,'height':2}[slot.split('_')[0]]
            values.add(int((Decimal(dims[index])*Decimal('25.4')).to_integral_value(rounding=ROUND_CEILING)))
    elif slot.startswith(('service_', 'travel_')):
        pattern = r'(?:allow|reserve|planning allowance is|travel time is)\s+(\d+)\s*(minutes?|seconds?)\b'
        for number, unit in re.findall(pattern, text, re.IGNORECASE):
            values.add(int(number) * (60 if unit.lower().startswith('minute') else 1))
    # Do not treat negated/hypothetical/example scalars as operative assertions.
    unsafe = re.search(r'\b(?:not\s+(?:allow|reserve)|if|example|might|would)\b', text, re.IGNORECASE)
    result['value'] = next(iter(values)) if len(values) == 1 and not unsafe else None
    return result
