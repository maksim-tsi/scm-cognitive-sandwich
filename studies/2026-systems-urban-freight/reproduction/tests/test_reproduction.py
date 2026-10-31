import copy
import hashlib
import json
import socket

import pytest
import reproduce as r


def packets():
    return r.load("results/r1/packets.json")


def world(packet):
    return next(a["definition"] for a in r.load("data/research/eval-op-v2/revision-1/assignments.json") if a["assignment_id"] == packet["assignment_id"])


def test_full_offline_reproduction():
    result = r.run()
    assert result["terminal_replays"] == 257
    assert {k: v["assigned"] for k, v in result["collections"].items()} == {"eval30": 120, "luna-eval30": 30, "r1": 110}


def test_proposal_tampering_fails_closed():
    packet = copy.deepcopy(next(p for p in packets() if p["status"] == "completed"))
    packet["decision"]["evidence"].append("FABRICATED")
    with pytest.raises(AssertionError):
        r.replay_packet(world(packet), packet)


def test_released_evidence_tampering_fails_closed():
    packet = copy.deepcopy(next(p for p in packets() if any(s["action"] == "ASK_USER" for s in p["steps"]) and p["status"] == "completed"))
    step = next(s for s in packet["steps"] if s["action"] == "ASK_USER")
    step["response"][0]["status"] = "FABRICATED_RELEASE"
    with pytest.raises(AssertionError):
        r.replay_packet(world(packet), packet)


def test_tool_witness_tampering_fails_closed():
    packet = copy.deepcopy(next(p for p in packets() if any(s["action"] == "CALL_TOOL" and s["arguments"]["tool"] == "plan_route" and s["response"].get("status") == "OK" for s in p["steps"]) and p["status"] == "completed"))
    step = next(s for s in packet["steps"] if s["action"] == "CALL_TOOL" and s["arguments"]["tool"] == "plan_route")
    step["response"]["route_check"]["valid"] = not step["response"]["route_check"]["valid"]
    with pytest.raises(AssertionError):
        r.replay_packet(world(packet), packet)


def test_network_denied_without_dispatch():
    with pytest.raises(RuntimeError, match="Network forbidden"):
        socket.create_connection(("example.invalid", 443))


def test_selected_texts_are_hash_bound():
    for path in (r.STUDY / "examples").glob("*.json"):
        for sample in json.loads(path.read_text()):
            assert hashlib.sha256(sample["original_final_text"].encode()).hexdigest() == sample["text_sha256"]


def test_protocol_prompts_have_no_reference_fields():
    for group, source in [("eval30", "data/research/evaluation/scenarios.json"), ("r1", "data/research/eval-op-v2/revision-1/assignments.json")]:
        inputs = r.load(source)
        worlds = {x["assignment_id"]: x["definition"] for x in inputs} if group == "r1" else {x["id"]: x for x in inputs}
        for name, messages in r.load(f"prompts/{group}-initial-messages.json").items():
            assert messages == __import__("tools.p5_interactive.operational", fromlist=["public_messages"]).public_messages(worlds[name], tools=True, user_answers=True)
