from mailwright.telegram.markup import to_markup


def test_to_markup_builds_one_row():
    markup = to_markup([("✅ Approve", "act:approve:7"), ("❌ Reject", "act:reject:7")])
    row = markup.inline_keyboard[0]
    assert row[0].text == "✅ Approve"
    assert row[0].callback_data == "act:approve:7"
    assert row[1].callback_data == "act:reject:7"
