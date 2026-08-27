import logging
import aiohttp
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger("news_parser")


async def get_rbc_quote_news_period(
    session: aiohttp.ClientSession,
    start_time: int,
    end_time: int,
    max_items: int = 50,
) -> list:
    url_template = (
        "https://www.rbc.ru/quote/ajax/get-news-feed/project/quote/lastDate/{}/limit/50"
    )

    current_cursor = end_time

    collected_news = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
    }

    # logger.info(f"Начинаем сбор с {datetime.fromtimestamp(end_time)} до {datetime.fromtimestamp(start_time)}")

    while True:
        url = url_template.format(current_cursor)

        try:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()

                items = data.get("items", [])

                if not items:
                    logger.info("API вернул пустой список. Новости закончились.")
                    break

                # logger.info(f"Скачана пачка: {len(items)} шт. Курсор (lastDate): {current_cursor}")

                stop_parsing = False
                last_item_date = 0

                for item in items:
                    pub_date = int(item.get("publish_date_t", 0))

                    last_item_date = pub_date

                    if pub_date > end_time:
                        continue

                    if pub_date < start_time:
                        stop_parsing = True
                        break

                    html_content = item.get("html", "")
                    if not html_content:
                        continue

                    soup_item = BeautifulSoup(html_content, "html.parser")

                    title_tag = soup_item.find(
                        "span", class_="g-inline-text-badges__text"
                    )
                    link_tag = soup_item.find("a")

                    if not title_tag:
                        title_tag = soup_item.find("span", class_="item__title")
                    if not link_tag:
                        link_tag = soup_item.find("a", class_="news-feed__item")

                    if title_tag and link_tag:
                        title = title_tag.get_text(strip=True)
                        link = link_tag.get("href")

                        collected_news.append(
                            {
                                "title": title,
                                "link": link,
                                #'date': pub_date,
                                "date_str": datetime.fromtimestamp(pub_date).strftime(
                                    "%Y-%m-%d %H:%M"
                                ),
                            }
                        )
                        if len(collected_news) >= max_items:
                            stop_parsing = True
                            break

                if stop_parsing:
                    # logger.info("Дошли до границы start_time. Остановка.")
                    break

                if last_item_date > 0 and last_item_date < current_cursor:
                    current_cursor = last_item_date
                else:
                    logger.warning("Курсор времени не сдвинулся. Принудительный сдвиг.")
                    current_cursor -= 1

                await asyncio.sleep(0.3)

        except Exception as e:
            logger.exception(f"Ошибка при запросе: {e}")
            break

    return collected_news


async def get_new_content(url: str, session: aiohttp.ClientSession) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }

    # logger.info("Отправляем запрос сайту")

    try:
        async with session.get(url, headers=headers) as response:
            response.raise_for_status()
            html_text = await response.text()

    except Exception as e:
        logger.error(f"Не удалось получить текст новости: {e}")
        return ""

    soup = BeautifulSoup(html_text, "html.parser")

    article_text = soup.find("div", class_="article__text")

    if not article_text:
        logger.warning(f"Не удалось найти содержание новости по ссылке: {url}")
        return ""

    trash_classes = [
        "article__inline-item",
        "pro-anons",
        "banner-advert",
        "article__special_container",
        "article__authors",
    ]

    for trash in article_text.find_all("div", class_=trash_classes):
        trash.decompose()

    paragraphs = article_text.find_all("p")

    text_parts = []
    for p in paragraphs:
        clean_p = p.get_text(separator=" ", strip=True)
        clean_p = " ".join(clean_p.split())
        if clean_p:
            text_parts.append(clean_p)

    full_text = "\n\n".join(text_parts)

    if not full_text:
        full_text = article_text.get_text(strip=True)

    return full_text
