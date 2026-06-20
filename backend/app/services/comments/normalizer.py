import re
import unicodedata


class CommentNormalizer:
    replacements = {
        "chot": "chốt",
        "ck": "chốt",
        "lay": "lấy",
        "sz": "size",
        "mau": "màu",
        "mầu": "màu",
        "do": "đỏ",
        "den": "đen",
        "vang": "vàng",
        "xanh": "xanh",
    }

    def normalize(self, text: str) -> str:
        value = unicodedata.normalize("NFC", text or "").strip().lower()
        value = re.sub(r"(\d+)\s*c\b", r"\1 cái", value)
        value = re.sub(r"[^\w\sÀ-ỹ]", " ", value)
        words = [self.replacements.get(word, word) for word in value.split()]
        return " ".join(words)


comment_normalizer = CommentNormalizer()
