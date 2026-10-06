import json
import time

from google import genai

from config import GEMINI_API_KEY


client = genai.Client(api_key=GEMINI_API_KEY)


def analyze_resume(resume: str, vacancy: str) -> dict:
    prompt = f"""
Ты AI-ассистент по поиску работы.

Сравни резюме кандидата с вакансией.

Не придумывай опыт или навыки, которых нет в резюме.

Определи:
- процент соответствия от 0 до 100;
- подходящие навыки;
- недостающие навыки;
- рекомендации по улучшению резюме;
- короткое сопроводительное письмо.

РЕЗЮМЕ:
{resume}

ВАКАНСИЯ:
{vacancy}
"""

    models = [
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-pro-preview",
    ]

    last_error = None

    for model in models:
        for attempt in range(3):
            try:
                print(f"Пробуем {model}, попытка {attempt + 1}")

                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": {
                            "type": "object",
                            "properties": {
                                "match_percentage": {
                                    "type": "integer"
                                },
                                "matching_skills": {
                                    "type": "array",
                                    "items": {
                                        "type": "string"
                                    }
                                },
                                "missing_skills": {
                                    "type": "array",
                                    "items": {
                                        "type": "string"
                                    }
                                },
                                "recommendations": {
                                    "type": "array",
                                    "items": {
                                        "type": "string"
                                    }
                                },
                                "cover_letter": {
                                    "type": "string"
                                }
                            },
                            "required": [
                                "match_percentage",
                                "matching_skills",
                                "missing_skills",
                                "recommendations",
                                "cover_letter"
                            ]
                        }
                    }
                )

                return json.loads(response.text)

            except Exception as error:
                last_error = error

                print(f"Ошибка {model}: {error}")

                if attempt < 2:
                    time.sleep(2 ** attempt)

        print(f"{model} недоступна. Пробуем следующую модель.")

    raise Exception(
        f"Все модели Gemini недоступны: {last_error}"
    )