from mailwright.owa.replies import render_link_reply, render_status_reply


def test_link_reply_has_url_and_auto_marker():
    text = render_link_reply("PROD-7", "https://x/browse/PROD-7")
    assert "PROD-7" in text and "https://x/browse/PROD-7" in text
    assert "automated message" in text.lower()


def test_status_reply_mentions_status():
    text = render_status_reply("PROD-7", "https://x/browse/PROD-7", "Done")
    assert "Done" in text and "PROD-7" in text
    assert "automated message" in text.lower()
