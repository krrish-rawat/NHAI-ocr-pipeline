import os
import io
import json
import fitz
import time
from PIL import Image
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from src.schemas import DocumentExtraction, DebarmentRecord

# Load the API key from your environment
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))

MODEL_NAME = 'gemini-2.5-flash'

def convert_pdf_to_pil_images(pdf_path: str) -> list:
    """
    Renders PDF pages as high-res images to bypass broken Hindi text encodings.
    Returns a list of PIL Image objects ready for Gemini's vision model.
    """
    doc = fitz.open(pdf_path)
    pil_images = []
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        zoom_matrix = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=zoom_matrix)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        pil_images.append(img)
        
    doc.close()
    return pil_images

def extract_fields_from_pdf(filepath: str, retries: int = 3) -> list[DebarmentRecord]:
    """
    Takes pictures of the PDF and passes them to the Gemini Multimodal LLM,
    forcing the output to perfectly match our Pydantic schema list. Includes auto-retries.
    """
    images = convert_pdf_to_pil_images(filepath)
    
    prompt = """
    You are an expert data extractor analyzing official Indian government debarment notices. 
    These documents are provided as images and may contain a mix of English and Hindi text.
    
    CRITICAL INSTRUCTIONS:
    1. Scan the images for the requested data fields.
    2. IMPORTANT: A single document may list MULTIPLE people (e.g., in a table). Extract a separate record for EVERY valid person found.
    3. If a date is written in Hindi, translate the month to English and format strictly as YYYY-MM-DD.
    4. If any field is missing from the document for a specific person, use 'Null'.
    5. SHARED CONTEXT: If a piece of information (project name, state, consultant name) is stated in a merged table cell or document header, apply it to EVERY individual's record.
    6. STRICT FILTERING (CRITICAL): Tables often list both approved and rejected candidates. Look at the 'Remarks' column. You MUST ONLY extract individuals facing negative action (e.g., 'Not Found Suitable', 'Not Recommended', 'Absent', 'not attended', 'recommended for replacement'). IGNORE individuals marked as 'Found Suitable' or 'Recommended'.
    7. MULTIPLE LETTERS: If the PDF contains multiple appended letters, ensure the dates you extract correspond directly to the letter that orders the debarment/rejection for the specific people you are extracting.
    
    --- NEW RULE FOR CALCULATING END DATES ---
    8. DEBARMENT PERIOD & DATE MATH: The 'effective_upto' date is rarely written in the table itself. You MUST read the paragraphs preceding or following the table (e.g., 'during the last 3 months', 'debarred for 1 year'). Extract this text period, map it carefully to the correct individuals, and CALCULATE the 'effective_upto' date by adding the period to their 'effective_from' (or interaction) date. Different people may have different periods mentioned in the text.
    """
    
    model = genai.GenerativeModel(MODEL_NAME)
    payload = [prompt] + images
    
    for attempt in range(retries):
        try:
            response = model.generate_content(
                payload,
                generation_config=GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=DocumentExtraction,
                    temperature=0.0
                )
            )
            data_dict = json.loads(response.text)
            
            extracted_records = data_dict.get("records", [])
            return [DebarmentRecord(**record) for record in extracted_records]
            
        except Exception as e:
            if attempt == retries - 1:
                error_type = type(e).__name__
                error_msg = str(e)
                raise ValueError(f"{error_type}: {error_msg}")
            
            # Wait 3 seconds before retrying to let the API cooldown
            time.sleep(3)
