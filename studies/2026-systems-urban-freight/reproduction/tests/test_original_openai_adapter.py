import unittest
from tools.openai_extension.adapter import build_request, parse_response


def response(text):
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
    }


class AdapterTest(unittest.TestCase):
    def test_transcript_is_explicit_and_stateless(self):
        messages = [
            {"role": "system", "content": "Return JSON"},
            {"role": "user", "content": "case"},
            {
                "role": "assistant",
                "content": '{"action":"CALL_TOOL","tool":"x","arguments":{"arbitrary":7}}',
            },
            {"role": "user", "content": "tool observation"},
        ]
        body = build_request(messages)
        self.assertEqual(body["input"][2], {**messages[2], "phase": "final_answer"})
        self.assertEqual(body["input"][0], messages[0])
        self.assertFalse(body["store"])
        self.assertNotIn("previous_response_id", body)
        self.assertEqual(body["text"]["format"]["type"], "json_object")

    def test_preserves_raw_dynamic_action(self):
        raw = '{"action":"CALL_TOOL","tool":"lookup","arguments":{"unanticipated":{"x":[1,2]}}}'
        self.assertEqual(parse_response(response(raw))[0], raw)
        self.assertEqual(
            parse_response(response(raw))[1]["arguments"]["unanticipated"]["x"], [1, 2]
        )

    def test_rejects_ambiguous_and_invalid(self):
        for e in [
            dict(response("{}"), status="incomplete"),
            response('{"x":1,"x":2}'),
            response('{"x":NaN}'),
            response('{"x":1e999}'),
            response("[]"),
            {"status": "completed", "output": []},
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "refusal", "refusal": "no"}],
                    }
                ],
            },
        ]:
            with self.subTest(e=e), self.assertRaises((ValueError, TypeError)):
                parse_response(e)


if __name__ == "__main__":
    unittest.main()


def test_final_phase_selection_and_ambiguity():
    import copy
    import pytest

    final = response('{"action":"ASK_USER","questions":[]}')
    commentary = copy.deepcopy(final["output"][0])
    commentary["phase"] = "commentary"
    commentary["content"][0]["text"] = '{"action":"CALL_TOOL"}'
    combined = copy.deepcopy(final)
    combined["output"].insert(0, commentary)
    assert parse_response(combined)[1]["action"] == "ASK_USER"
    for output in (
        [commentary],
        [final["output"][0], final["output"][0]],
        [{**final["output"][0], "phase": None}],
    ):
        bad = copy.deepcopy(final)
        bad["output"] = output
        with pytest.raises(ValueError):
            parse_response(bad)
    for bad in (
        response("{bad"),
        {"status": "incomplete", "output": final["output"]},
        {
            "status": "completed",
            "output": [
                dict(final["output"][0], content=[{"type": "refusal", "refusal": "no"}])
            ],
        },
    ):
        with pytest.raises(ValueError):
            parse_response(bad)
