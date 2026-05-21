# Migrate LLM Engine to Google Gemini

This plan outlines the steps to replace Groq's `llama-3.3-70b-versatile` model with Google's `gemini-3.1-pro-preview` for both the Category Classification engine and the Conversational RAG engine. 

*(Note: We will keep Groq configured strictly for the Whisper audio transcription step, as Gemini does not provide a direct Whisper equivalent via this API).*

## User Review Required

> [!IMPORTANT]
> **API Key Setup:** You will need to generate a free API key from [Google AI Studio](https://aistudio.google.com) and add it to your `.env` file as `GEMINI_API_KEY`. Are you ready to proceed with generating and adding this key?

> [!WARNING]
> **Dependency Addition:** We will be installing the official `google-genai` pip package to the backend virtual environment.

## Open Questions

None currently.

## Proposed Changes

---

### Backend Dependencies & Config

#### [MODIFY] [requirements.txt](file:///Users/deeptijain/Desktop/Deepti/Projects/ReelMind/backend/requirements.txt)
- Add `google-genai>=0.3.0` to the project dependencies.

#### [MODIFY] [config.py](file:///Users/deeptijain/Desktop/Deepti/Projects/ReelMind/backend/config.py)
- Add `GEMINI_API_KEY: str | None = None` to the `Settings` class so it can be loaded from the environment variables.

#### [MODIFY] [.env.example](file:///Users/deeptijain/Desktop/Deepti/Projects/ReelMind/backend/.env.example)
- Add `GEMINI_API_KEY=AIza...` placeholder.

---

### AI Services

#### [MODIFY] [classifier.py](file:///Users/deeptijain/Desktop/Deepti/Projects/ReelMind/backend/services/classifier.py)
- Replace the `Groq` client import with `from google import genai`.
- Define a strict `pydantic.BaseModel` schema representing the classification output (`category_id`, `confidence`, `alternative_ids`).
- Replace `client.chat.completions.create` with `client.models.generate_content` using `gemini-3.1-pro-preview`.
- Remove the manual JSON parsing and retry logic, as Gemini guarantees schema alignment via `response_schema`.

#### [MODIFY] [rag.py](file:///Users/deeptijain/Desktop/Deepti/Projects/ReelMind/backend/services/rag.py)
- Replace the Groq implementation with the Google GenAI client.
- Update `_hyde_and_extract_filters` to use Gemini structured outputs for the `{"hypothetical_doc": "...", "filters": ...}` JSON schema.
- Update `_generate` to format the system instructions, RAG context, and chat history into the native Gemini message format.

---

### Test Suite

#### [MODIFY] [test_classifier.py](file:///Users/deeptijain/Desktop/Deepti/Projects/ReelMind/backend/tests/test_classifier.py)
- Update the mock patches from mocking `groq.Groq` to mocking `google.genai.Client`.
- Adjust mock return payloads to match Gemini's `GenerateContentResponse` structure.

#### [MODIFY] [test_rag.py](file:///Users/deeptijain/Desktop/Deepti/Projects/ReelMind/backend/tests/test_rag.py)
- Update RAG API client mocks from Groq to Google GenAI.

## Verification Plan

### Automated Tests
- Run `pytest backend/tests/test_classifier.py backend/tests/test_rag.py` to ensure all edge cases (missing keys, structured output validation, API failures) pass.

### Manual Verification
- You will need to start the FastAPI server locally, pass a test reel URL via the Share Extension (or cURL), and verify the Celery worker successfully calls Gemini for classification. 
- Test the chatbot in the iOS app to ensure it responds accurately using the Gemini RAG pipeline.
