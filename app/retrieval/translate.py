
from google.cloud import translate
import os
client = translate.TranslationServiceClient()

API_ID = os.environ["GOOGLE_TRANSLATE_PROJECT_ID"]

os.environ.setdefault(
    "GOOGLE_APPLICATION_CREDENTIALS",
    os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
)

def translate_text(text: str) -> translate.Translation:
    
    PARENT = f"projects/{API_ID}"

    response = client.translate_text(
        parent=PARENT,
        contents=[text],
        target_language_code="en",
    )

    return response.translations[0].translated_text