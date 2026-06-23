import re


TRANSACTION_PATTERN = re.compile(
    r"(?:支付)?交易号\s*[:：]?\s*[A-Za-z0-9_-]+",
    re.IGNORECASE,
)
MONEY_PATTERN = re.compile(
    r"(?:[¥￥]\s*)?\d+(?:\.\d+)?\s*(?:元|块钱|块)",
    re.IGNORECASE,
)
SYMBOL_MONEY_PATTERN = re.compile(r"[¥￥]\s*\d+(?:\.\d+)?")


def sanitize_memory_text(value: object) -> str:
    text = str(value or "")
    text = TRANSACTION_PATTERN.sub("", text)
    text = MONEY_PATTERN.sub("", text)
    text = SYMBOL_MONEY_PATTERN.sub("", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"([，,。；;])\1+", r"\1", text)
    return text.strip(" ，,。；;")
