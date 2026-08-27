import asyncio
import time
import aiohttp
import app.services.news_parser as news_parser


<<<<<<< HEAD
async def get_news_summary(hours: int = 24):
    if hours > 48:
        return "Выбран слишком большой промежуток времени", 0

    async with aiohttp.ClientSession() as session:
=======
async def get_news_summary(hours: int = 24, max_news: int = 20):
    if hours <= 0 or hours > 48:
        return "Допустимый промежуток времени: от 1 до 48 часов", 0

    timeout = aiohttp.ClientTimeout(total=30, connect=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
>>>>>>> f04103d (version 1.0.0)
        now = int(time.time())
        time_delta = hours * 3600
        start_time = now - time_delta

        news_list = await news_parser.get_rbc_quote_news_period(
<<<<<<< HEAD
            session, start_time, now
=======
            session, start_time, now, max_items=max_news
>>>>>>> f04103d (version 1.0.0)
        )

        if not news_list:
            return f"За последние {hours} ч. новостей не найдено.", 0

        final_news_content = []
        tasks = []
<<<<<<< HEAD

        for new in news_list:
            tasks.append(news_parser.get_new_content(new["link"], session))
=======
        semaphore = asyncio.Semaphore(5)

        async def load_content(url: str) -> str:
            async with semaphore:
                return await news_parser.get_new_content(url, session)

        for new in news_list:
            tasks.append(load_content(new["link"]))
>>>>>>> f04103d (version 1.0.0)

        contents = await asyncio.gather(*tasks)

        for i, new in enumerate(news_list):
            title = new.get("title")
            date = new.get("date_str")
<<<<<<< HEAD
            text = contents[i]
=======
            text = contents[i][:10_000]
>>>>>>> f04103d (version 1.0.0)

            if not text:
                text = "Текст статьи недоступен"

            formatted_new = (
                f"Новость №{i + 1}, {date}\nЗаголовок:\n{title}\nСодержание:\n{text}\n"
            )

            final_news_content.append(formatted_new)

        result_news_summary = "\n\n".join(final_news_content)

        return result_news_summary, len(final_news_content)
