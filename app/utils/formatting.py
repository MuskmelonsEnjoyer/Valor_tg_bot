from decimal import Decimal
import re


def format_money(value: Decimal) -> str:
    # Форматирует: 12345.678 -> "12 345.68"
    return f"{value:,.2f}".replace(",", " ")


def clean_text(text: str) -> str:
    replacements = {
        r"<br\s*/?>": "\n",  # <br> или <br/> -> новая строка
        r"</div>": "\n",  # конец блока -> новая строка
        r"</p>": "\n",  # конец параграфа -> новая строка
        r"<li>": "•",  # элемент списка -> буллит
        r"</li>": "\n",  # конец элемента списка -> новая строка
        r"<ul>": "\n",  # начало списка -> отступ
        r"</ul>": "\n",  # конец списка -> отступ
    }

    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    allowed_tags = r"(b|strong|i|em|u|ins|s|strike|del|code|pre|a)"

    clean_text = re.sub(r"</?(?!" + allowed_tags + r"\b)[^>]*>", "", text)

    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)

    return clean_text.strip()

def format_date(date_str: str | None) -> str:
    """Преобразует дату из 2026-11-25 в 25.11.2026 с защитой от пустых значений."""
    if not date_str or "-" not in date_str:
        return "Н/Д"
    return ".".join(date_str.split("-")[::-1])