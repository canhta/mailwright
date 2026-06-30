from mailwright.telegram.auth import decode_action, encode_action, is_authorized


def test_is_authorized():
    assert is_authorized(111, [111, 222]) is True
    assert is_authorized(999, [111, 222]) is False
    assert is_authorized(111, []) is False  # fail closed


def test_codec_roundtrip():
    assert encode_action("approve", 7) == "act:approve:7"
    assert decode_action("act:approve:7") == ("approve", 7)
    assert decode_action("act:reject:42") == ("reject", 42)


def test_decode_rejects_garbage():
    assert decode_action("nonsense") is None
    assert decode_action("act:approve:notanint") is None
