import google.generativeai as genai
import os
import dotenv
import json
import logging
import asyncio

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
dotenv.load_dotenv()

# --- Configure Gemini API ---
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    logger.error("GEMINI_API_KEY not found in environment variables.")
    genai.configure(api_key="DUMMY_KEY_FOR_INITIALIZATION") 
else:
    try:
        genai.configure(api_key=API_KEY)
    except Exception as e:
        logger.error(f"Failed to configure Gemini API: {e}")

# --- Generation Configuration ---
DEFAULT_GENERATION_CONFIG = genai.types.GenerationConfig(
    temperature=0.5, 
)

JSON_GENERATION_CONFIG = genai.types.GenerationConfig(
    response_mime_type="application/json",
    temperature=0.2 
)

# --- Safety Settings ---
SAFETY_SETTINGS = {
    genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
    genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
    genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_NONE,
    genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
}

# --- Gemini Model Interaction ---
MODEL_NAME = "gemini-1.5-pro-latest"

async def call_gemini(prompt: str, expect_json: bool = False, retries: int = 3, delay: int = 5):
    if not API_KEY or API_KEY == "DUMMY_KEY_FOR_INITIALIZATION":
        logger.error("Gemini API key not configured. Cannot make API call.")
        return None

    generation_config = JSON_GENERATION_CONFIG if expect_json else DEFAULT_GENERATION_CONFIG

    model = genai.GenerativeModel(
        MODEL_NAME,
        generation_config=generation_config,
        safety_settings=SAFETY_SETTINGS
    )

    for attempt in range(retries):
        try:
            logger.info(f"Calling Gemini API (Attempt {attempt + 1}/{retries}). Expect JSON: {expect_json}")
            response = await model.generate_content_async(prompt)

            if not response.parts:
                 logger.warning("Gemini response has no parts.")
                 if response.prompt_feedback:
                     logger.warning(f"Prompt Feedback: {response.prompt_feedback}")
                 return None 

            response_text = response.text
            logger.info("Gemini API call successful.")

            if expect_json:
                try:
                    return json.loads(response_text)
                except json.JSONDecodeError as json_e:
                    logger.error(f"Failed to decode Gemini response as JSON: {json_e}")
                    logger.debug(f"Raw response: {response_text}")
                    if attempt == retries - 1:
                        return None
            else:
                return response_text 

        except Exception as e:
            logger.error(f"Error calling Gemini API (Attempt {attempt + 1}/{retries}): {e}")
            if attempt == retries - 1:
                logger.error("Max retries reached. Returning None.")
                return None
            logger.info(f"Retrying in {delay} seconds...")
            await asyncio.sleep(delay)

    return None 

# Example usage (can be run standalone for testing if needed)
async def main_test():
    test_prompt = "Write a short story about a robot learning to paint."
    print(f"Testing with prompt: {test_prompt}")
    response = await call_gemini(test_prompt)
    if response:
        print("\n--- Response Text ---")
        print(response)
    else:
        print("\nFailed to get response.")

    test_json_prompt = "Create a JSON object with two keys: 'name' (string) and 'age' (integer). Use 'Bob' and 30."
    print(f"\nTesting with JSON prompt: {test_json_prompt}")
    json_response = await call_gemini(test_json_prompt, expect_json=True)
    if json_response:
        print("\n--- Response JSON ---")
        print(json.dumps(json_response, indent=2))
    else:
        print("\nFailed to get JSON response.")

if __name__ == "__main__":
    asyncio.run(main_test())
