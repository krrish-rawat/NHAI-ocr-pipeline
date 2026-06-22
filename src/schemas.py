# schemas.py
from pydantic import BaseModel, Field
from typing import List

class DebarmentRecord(BaseModel):
    name: str = Field(
        description="Exact name of the individual. The document might use different headers such as 'Name of the Individual', 'Name of Key Personnel'. Extract the actual person/entity name. If missing, output: 'Null'."
    )
    dob: str = Field(
        description="Date of birth. The document may use ANY date format (DD/MM/YYYY, MM-DD-YY) or language (e.g., Hindi text 'मार्च'). You MUST standardize and output STRICTLY as YYYY-MM-DD. If missing, output: 'Null'."
    )
    INFRACON_ID: str = Field(
        description="Unique identifier. Scan near the person's name for headers like 'INFRACON ID', 'INFRACON ID/EMAIL', INFRACON ID(Email) ,'INFRACON  user ID' or ' EMAIL'. If genuinely missing, output: 'Null'."
    )
    position: str = Field(
        description="Exact position or designation. Look for synonyms like 'Designation' (eg. Resident cum Highway Engineer-II) or it will be stated in Subject: ... was selected as 'Designation'. If missing, output: 'Null'."
    )
    project_name: str = Field(
        description="Name of the specific Project, Highway, or Stretch. If missing, output: 'Null'."
    )
    project_state: str = Field(
        description="The specific State or region associated with the project. If missing, output: 'Null'."
    )
    debarment_order_date: str = Field(
        description="The date of the specific official order/letter that dictates the debarment or rejection for this individual. WARNING: If the PDF contains multiple letters, use the date from the letter that directly governs the table this person is in, NOT just the first date in the PDF. Output STRICTLY in DD-MM-YYYY. If missing, output: 'Null'."
    )
    effective_from: str = Field(
        description="The start date from which the debarment is enforced , in some pdfs this may be written as if not present there it will be like ... under the column 'Date of Interview' or 'Date of Interaction' . It may be written in English or Hindi. Translate and output STRICTLY in DD-MM-YYYY format. If missing, output: 'Null'."
    )
    effective_upto: str = Field(
        description="The end date until which the debarment is effective. Output STRICTLY in DD-MM-YYYY format. IF NO EXACT DATE IS GIVEN: in the paragraph  look for a debarment period (e.g., '3 months ', '1 year ', 'lifetime')  or Look for outcome of any Interaction Meeting held within '03 months' for the same positions and calculate the end date by adding it to the 'effective_from' date. If neither exist, output: 'Null'."
    )

class DocumentExtraction(BaseModel):
    records: List[DebarmentRecord] = Field(
        description="A list of ALL individuals or personnel found in the document. If a table lists multiple people, you MUST extract a separate complete record for EACH person."
    )