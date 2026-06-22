import logging
from dotenv import load_dotenv
load_dotenv()

import os
import csv
import re
import hashlib
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.extractor import extract_fields_from_pdf

# Suppress PyPDF2 structural warnings
logging.getLogger("PyPDF2").setLevel(logging.ERROR)

INPUT_DIR = "./data/input_pdfs" 
OUTPUT_FILE = "./data/output_data/extracted_records.csv"
MAX_WORKERS = 3  

FIELDNAMES = [
    'source_file', 'name', 'dob', 'INFRACON_ID', 'position', 
    'project_name', 'project_state', 'debarment_order_date', 
    'effective_from', 'effective_upto', 'status', 'failure_reason'
]

def get_file_hash(filepath):
    """Generates an MD5 hash of the file to detect exact duplicates."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()

def process_single_pdf(filepath, filename):
    """Worker function to process one PDF, returning a list of rows."""
    try:
        records = extract_fields_from_pdf(filepath)
        
        if not records:
            raise ValueError("Model returned no records for this document.")

        rows = []
        for record in records:
            data_row = record.model_dump()
            data_row['source_file'] = filename
            data_row['status'] = "Success"
            data_row['failure_reason'] = ""
            rows.append(data_row)
            
        return rows
        
    except Exception as error:
        error_str = str(error)
        if "429" in error_str or "ResourceExhausted" in error_str:
            error_str = "API Rate Limit Exceeded (429). Try lowering MAX_WORKERS."
            
        print(f"   [!] Worker Error on {filename}: {error_str}")
        
        return [{
            'source_file': filename, 'name': '', 'dob': '', 'INFRACON_ID': '',
            'position': '', 'project_name': '', 'project_state': '',
            'debarment_order_date': '', 'effective_from': '', 'effective_upto': '',
            'status': "Failed", 'failure_reason': error_str
        }]

def sort_csv_naturally(csv_filepath):
    """Sorts the CSV logically and exports a color-coded Excel report."""
    try:
        df = pd.read_csv(csv_filepath)
        
        def extract_row_number(filename):
            match = re.search(r'\d+', str(filename))
            return int(match.group()) if match else 0
            
        df['temp_sort_key'] = df['source_file'].apply(extract_row_number)
        df = df.sort_values('temp_sort_key').drop('temp_sort_key', axis=1)
        
        df.to_csv(csv_filepath, index=False)
        
        def highlight_errors(row):
            if row.get('status') == 'Failed':
                return ['background-color: #ffcccc'] * len(row)
                
            styles = []
            error_phrases = ["not found", "not stated", "not explicitly stated", "not mentioned", "no id", "failed", "null"]
            
            for val in row:
                if isinstance(val, str) and any(phrase in val.lower() for phrase in error_phrases):
                    styles.append('background-color: #ffe6e6; color: #a00000; font-weight: bold;')
                else:
                    styles.append('')
            return styles

        excel_filepath = csv_filepath.replace('.csv', '.xlsx')
        styled_df = df.style.apply(highlight_errors, axis=1)
        styled_df.to_excel(excel_filepath, index=False, engine='openpyxl')
        
        print(f"✅ Created color-coded Excel report: {excel_filepath}")
        
    except Exception as e:
        print(f"⚠️ Could not sort or format report: {e}")

def run_pipeline():
    if not os.path.exists(INPUT_DIR):
        print(f"Error: Directory '{INPUT_DIR}' not found.")
        return

    all_pdf_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith('.pdf')]
    if not all_pdf_files:
        print(f"No PDF files found in '{INPUT_DIR}'. Please add some!")
        return

    print("Scanning for duplicate files...")
    unique_pdf_files = []
    seen_hashes = set()
    
    for filename in all_pdf_files:
        filepath = os.path.join(INPUT_DIR, filename)
        file_hash = get_file_hash(filepath)
        
        if file_hash not in seen_hashes:
            seen_hashes.add(file_hash)
            unique_pdf_files.append(filename)
        else:
            print(f"⏭️ Skipping exact duplicate: {filename}")

    print(f"Found {len(unique_pdf_files)} unique files to process out of {len(all_pdf_files)} total.\n")
    
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    file_exists = os.path.isfile(OUTPUT_FILE)

    success_count = 0
    fail_count = 0

    with open(OUTPUT_FILE, mode='a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES, extrasaction='ignore')
        
        if not file_exists:
            writer.writeheader()

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_pdf = {
                executor.submit(process_single_pdf, os.path.join(INPUT_DIR, filename), filename): filename 
                for filename in unique_pdf_files
            }
            
            for future in as_completed(future_to_pdf):
                filename = future_to_pdf[future]
                try:
                    result_rows = future.result()
                    
                    for row in result_rows:
                        writer.writerow(row)
                    csvfile.flush() 
                    
                    if result_rows and result_rows[0]['status'] == "Success":
                        success_count += len(result_rows)
                        print(f"✅ Processed: {filename} ({len(result_rows)} records)")
                    else:
                        fail_count += 1
                        print(f"❌ Failed: {filename}")
                except Exception as exc:
                    print(f"💥 Critical Error on {filename}: {exc}")

    print(f"\nExtraction Complete")
    print("Organizing CSV rows chronologically")
    sort_csv_naturally(OUTPUT_FILE)
    
    print(f"✅ Successful Individual Extractions: {success_count}")
    print(f"❌ Failed Documents: {fail_count}")
    print("✅ Pipeline finished successfully.")

if __name__ == "__main__":
    run_pipeline()