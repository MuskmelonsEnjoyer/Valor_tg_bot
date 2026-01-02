import re

def clean_text(text: str) -> str:

    replacements = {
        r"<br\s*/?>": "\n",        # <br> или <br/> -> новая строка
        r"</div>": "\n",           # конец блока -> новая строка
        r"</p>": "\n",             # конец параграфа -> новая строка
        r"<li>": "•",             # элемент списка -> буллит
        r"</li>": "\n",            # конец элемента списка -> новая строка
        r"<ul>": "\n",             # начало списка -> отступ
        r"</ul>": "\n",            # конец списка -> отступ
    }
    
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    allowed_tags = r"(b|strong|i|em|u|ins|s|strike|del|code|pre|a)"

    clean_text = re.sub(r"</?(?!" + allowed_tags + r"\b)[^>]*>", "", text)

    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
    
    return clean_text.strip()