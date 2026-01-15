import asyncio, time, aiohttp
import app.services.news_parser as news_parser

async def get_news_summary(hours: int = 24):

    if hours > 48:
        return f"Выбран слишком большой промежуток времени", 0

    async with aiohttp.ClientSession() as session:
        
        now = int(time.time())
        time_delta = hours * 3600 
        start_time = now - time_delta

        news_list = await news_parser.get_rbc_quote_news_period(session, start_time, now)

        if not news_list:
            return f"За последние {hours} ч. новостей не найдено.", 0
        
        final_news_content = []
        tasks = []

        for new in news_list:
            tasks.append(news_parser.get_new_content(new["link"], session))

        contents = await asyncio.gather(*tasks)

        for i, new in enumerate(news_list):
            title = new.get("title")
            date = new.get("date_str")
            text = contents[i]

            if not text:
                text = "Текст статьи недоступен"
            
            formatted_new = (
                f"Новость №{i+1}, {date}\n"
                f"Заголовок:\n{title}\n"
                f"Содержание:\n{text}\n"
            )

            final_news_content.append(formatted_new)

        result_news_summary = "\n\n".join(final_news_content)

        return result_news_summary, len(final_news_content)