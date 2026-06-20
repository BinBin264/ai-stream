from app.models.domain import LiveComment


def _clean_text(text: str) -> str:
    return " ".join((text or "").strip().split())


def parse_comment_events(payload: dict, default_live_id: str) -> list[LiveComment]:
    """Extract comment events from Meta webhook payload.

    The real Graph payload varies by subscription field. This parser accepts the
    common entry/changes shape and keeps unknown events harmless.
    """
    comments: list[LiveComment] = []
    for entry in payload.get("entry", []):
        page_id = entry.get("id")
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            text = _clean_text(value.get("message") or value.get("text") or "")
            if not text:
                continue
            user = value.get("from", {}).get("name") or value.get("user_name") or "Facebook User"
            comment_id = value.get("comment_id") or value.get("id")
            live_id = value.get("live_id") or value.get("video_id") or default_live_id
            comments.append(
                LiveComment(
                    live_id=live_id,
                    live_session_id=live_id,
                    facebook_page_id=str(page_id) if page_id else None,
                    facebook_comment_id=comment_id,
                    external_comment_id=comment_id,
                    external_parent_comment_id=value.get("parent_id"),
                    user_name=user,
                    text=text,
                    priority=_comment_priority(text),
                )
            )
    return comments


def _comment_priority(text: str) -> int:
    score = 0
    if "?" in text:
        score += 10
    if len(text) <= 120:
        score += 3
    return score
