import re
from datetime import datetime, timedelta
import boto3 # AWS SDK for Python
from io import BytesIO # For handling image data in memory
from PIL import Image, ImageEnhance # For image manipulation
from typing import Union, List, Dict, Any # For type hinting
import os
import traceback # For detailed error logging

# --- ANSI Color Codes for Terminal Output ---
RESET = "\033[0m"
BOLD = "\033[1m"
RED_TEXT = "\033[91m"
DEBUG_COLOR = "\033[90m"
FINAL_HEADER_COLOR = "\033[94m"
FINAL_NAME_COLOR = "\033[94m"
FINAL_TIME_COLOR = "\033[96m"
EDIT_HEADER_COLOR = "\033[93m"
EDIT_NAME_COLOR = "\033[93m"
EDIT_TIME_COLOR = "\033[95m"

# --- Note Strings ---
EARLY_LEAVE_NOTE_EDIT = f"{RED_TEXT} (Early Leave?){RESET}"
EARLY_LEAVE_NOTE_FINAL = "🟠"

# --- AWS S3 and Textract Configuration ---
# !!! IMPORTANT: Replace these placeholders with your actual S3 bucket and image key !!!
S3_BUCKET_NAME = "YOUR_S3_BUCKET_NAME_HERE"
SOURCE_IMAGE_KEY = "YOUR_SOURCE_IMAGE_KEY_ON_S3.png" # e.g., "timesheets/image.png"

# Auto-generate processed image key name
if S3_BUCKET_NAME == "YOUR_S3_BUCKET_NAME_HERE" or SOURCE_IMAGE_KEY == "YOUR_SOURCE_IMAGE_KEY_ON_S3.png":
    print(f"{RED_TEXT}WARNING: S3 details are placeholders. Update them to run the script.{RESET}")
    PROCESSED_IMAGE_KEY = "processed_placeholder_image.png" # Default for safety
else:
    base_name, extension = os.path.splitext(SOURCE_IMAGE_KEY)
    PROCESSED_IMAGE_KEY = f"processed_{base_name}{extension}"

print(f"{DEBUG_COLOR}[DEBUG] Script Init: S3 Bucket: {S3_BUCKET_NAME}, Source Key: {SOURCE_IMAGE_KEY}, Processed Key: {PROCESSED_IMAGE_KEY}{RESET}")

# Initialize AWS clients for Textract and S3
try:
    textract_client = boto3.client("textract")
    s3_client = boto3.client("s3")
    print(f"{DEBUG_COLOR}[DEBUG] AWS clients initialized.{RESET}")
except Exception as e:
    print(f"{RED_TEXT}Error initializing AWS clients: {e}{RESET}\n{traceback.format_exc()}{RESET}")
    exit("AWS client initialization failed. Check credentials and configuration.")

# --- Textract Helper: Get Text from Block ---
def get_block_text(block_id: str, blocks_map: Dict[str, Dict]) -> str:
    block = blocks_map.get(block_id)
    if not block: return ""
    text = block.get("Text", "") # Get direct text if available
    if not text and "Relationships" in block: # If no direct text, check child blocks (e.g., WORDs in a LINE or CELL)
        child_text_parts = []
        for relationship in block["Relationships"]:
            if relationship["Type"] == "CHILD":
                for child_id in relationship["Ids"]:
                    child_text_parts.append(get_block_text(child_id, blocks_map))
        text = " ".join(child_text_parts).strip()
    return text

# --- Image Pre-processing for OCR ---
def enhance_image_for_ocr(bucket: str, source_key: str, destination_key: str) -> bool:
    print(f"{DEBUG_COLOR}[DEBUG] Enhancing image: s3://{bucket}/{source_key} -> s3://{bucket}/{destination_key}{RESET}")
    if bucket == "YOUR_S3_BUCKET_NAME_HERE" or source_key == "YOUR_SOURCE_IMAGE_KEY_ON_S3.png":
        print(f"{RED_TEXT}Image processing skipped: S3 placeholders active.{RESET}")
        return False

    try:
        print(f"Downloading s3://{bucket}/{source_key}...")
        image_object = s3_client.get_object(Bucket=bucket, Key=source_key)
        original_image = Image.open(BytesIO(image_object["Body"].read()))
        print(f"Image downloaded. Original Mode: {original_image.mode}")

        # Convert to RGB for consistent processing if not already Grayscale (L) or RGB
        if original_image.mode not in ('RGB', 'L'):
            original_image = original_image.convert('RGB')
            print(f"{DEBUG_COLOR}[DEBUG] Converted image to RGB.{RESET}")
        elif original_image.mode == 'RGBA': # Remove alpha channel if present
             original_image = original_image.convert('RGB')
             print(f"{DEBUG_COLOR}[DEBUG] Converted RGBA to RGB (removed alpha).{RESET}")

        print("Applying contrast & brightness enhancements...")
        enhancer_contrast = ImageEnhance.Contrast(original_image)
        enhanced_image = enhancer_contrast.enhance(1.5)
        enhancer_brightness = ImageEnhance.Brightness(enhanced_image)
        enhanced_image = enhancer_brightness.enhance(1.2)
        print("Enhancements applied.")

        buffer = BytesIO()
        save_format = "JPEG" # Default save format
        if destination_key.lower().endswith(".png"): save_format = "PNG"
        elif destination_key.lower().endswith((".tiff", ".tif")): save_format = "TIFF"
        
        enhanced_image.save(buffer, format=save_format)
        buffer.seek(0)
        print(f"{DEBUG_COLOR}[DEBUG] Processed image ready in {save_format} format.{RESET}")

        print(f"Uploading processed image to s3://{bucket}/{destination_key}...")
        s3_client.put_object(Bucket=bucket, Key=destination_key, Body=buffer, ContentType=f'image/{save_format.lower()}')
        print("Processed image uploaded to S3.")
        return True
    except Exception as e:
        print(f"{RED_TEXT}Error in image processing/S3 upload: {e}{RESET}\n{traceback.format_exc()}{RESET}")
        return False

# --- Time String Correction ---
def correct_time_format(text: str) -> Union[str, None]:
    # (This function is your specific logic for fixing common OCR errors in time strings)
    print(f"{DEBUG_COLOR}[DEBUG] correct_time_format input: '{text}'{RESET}")
    # ... (rest of function is the same as your last version) ...
    original_text_lower = text.strip().lower()
    if original_text_lower == "to": print(f"{DEBUG_COLOR}[DEBUG] Corrected 'to' to '10:00'{RESET}"); return "10:00"
    if original_text_lower == "ii": print(f"{DEBUG_COLOR}[DEBUG] Corrected 'ii' to '11:00'{RESET}"); return "11:00"
    if original_text_lower == "/1": print(f"{DEBUG_COLOR}[DEBUG] Corrected '/1' to '11:00'{RESET}"); return "11:00"
    if original_text_lower == ">":  print(f"{DEBUG_COLOR}[DEBUG] Corrected '>' to '07:00'{RESET}"); return "07:00"
    processed_text = original_text_lower
    replacements = {'|': '1', '!': '1', 'i': '1', 'l': '1', 'o': '0', 'O': '0', 'S': '5', 'B': '8', '.': ':', ',': ':', ';': ':'}
    for char, replacement in replacements.items():
        if char in processed_text: processed_text = processed_text.replace(char, replacement)
    if re.fullmatch(r'\d{1,2}:\d{2}', processed_text):
        try:
            h, m = map(int, processed_text.split(':'))
            if 0 <= h <= 23 and 0 <= m <= 59: return f"{h:02d}:{m:02d}"
        except ValueError: pass
    if re.fullmatch(r'\d{4}', processed_text):
        try:
            h = int(processed_text[:2]); m = int(processed_text[2:])
            if 0 <= h <= 23 and 0 <= m <= 59: return f"{h:02d}:{m:02d}"
        except ValueError: pass
    if re.fullmatch(r'\d{3}', processed_text):
        try:
            h = int(processed_text[0]); m = int(processed_text[1:])
            if 0 <= h <= 23 and 0 <= m <= 59: return f"{h:02d}:{m:02d}"
        except ValueError: pass
    if re.fullmatch(r'\d{1,2}', processed_text):
        try:
            hour_val = int(processed_text)
            if 1 <= hour_val <= 23: return f"{hour_val:02d}:00"
        except ValueError: pass
    print(f"{DEBUG_COLOR}[DEBUG] No correction pattern matched for '{text}'. Result: None.{RESET}")
    return None

# --- Main Script ---
if __name__ == "__main__":
    print(f"{DEBUG_COLOR}[DEBUG] Main script execution starting.{RESET}")

    # Validate S3 configuration
    if S3_BUCKET_NAME == "YOUR_S3_BUCKET_NAME_HERE" or \
       SOURCE_IMAGE_KEY == "YOUR_SOURCE_IMAGE_KEY_ON_S3.png" or \
       not S3_BUCKET_NAME or not SOURCE_IMAGE_KEY:
        print(f"{RED_TEXT}{BOLD}Execution Aborted: S3 configuration incomplete.{RESET}")
        print(f"{RED_TEXT}Update S3_BUCKET_NAME and SOURCE_IMAGE_KEY variables.{RESET}")
        exit("S3 configuration required.")

    print(f"\n{EDIT_HEADER_COLOR}--- Stage 1: Image Processing & S3 Upload ---{RESET}")
    if not enhance_image_for_ocr(S3_BUCKET_NAME, SOURCE_IMAGE_KEY, PROCESSED_IMAGE_KEY):
        exit("Image processing/upload failed. Aborting.")

    print(f"\n{EDIT_HEADER_COLOR}--- Stage 2: AWS Textract Analysis ---{RESET}")
    print(f"Analyzing s3://{S3_BUCKET_NAME}/{PROCESSED_IMAGE_KEY} with Textract...")
    textract_params = {
        "Document": {"S3Object": {"Bucket": S3_BUCKET_NAME, "Name": PROCESSED_IMAGE_KEY}},
        "FeatureTypes": ["TABLES", "FORMS"] # Ask Textract for table and form data
    }
    
    blocks = []
    block_map = {}
    try:
        textract_response = textract_client.analyze_document(**textract_params)
        blocks = textract_response.get("Blocks", [])
        print(f"Textract analysis complete. Received {len(blocks)} blocks.")
        if not blocks: print(f"{RED_TEXT}Warning: Textract returned 0 blocks.{RESET}")
    except Exception as e:
        print(f"{RED_TEXT}Textract API call failed: {e}{RESET}\n{traceback.format_exc()}{RESET}")
        exit("Textract analysis failed. Check IAM permissions and S3 object.")

    block_map = {block["Id"]: block for block in blocks} # For quick block lookup by ID
    print(f"{DEBUG_COLOR}[DEBUG] Textract block map created for {len(block_map)} blocks.{RESET}")

    table_rows = {} # Stores cell data: table_rows[row_idx][col_idx] = cell_block
    table_blocks = [b for b in blocks if b.get("BlockType") == "TABLE"] # Find all tables
    print(f"{DEBUG_COLOR}[DEBUG] Found {len(table_blocks)} TABLE blocks in Textract response.{RESET}")

    if table_blocks:
        main_table = table_blocks[0] # Assume first table is the target
        print(f"{DEBUG_COLOR}[DEBUG] Processing first table (ID: {main_table.get('Id', 'N/A')}).{RESET}")
        
        cell_blocks = []
        if "Relationships" in main_table: # Cells are children of TABLE blocks
            for rel in main_table["Relationships"]:
                if rel["Type"] == "CHILD":
                    for cell_id in rel["Ids"]:
                        cell = block_map.get(cell_id)
                        if cell and cell.get("BlockType") == "CELL":
                            cell_blocks.append(cell)
        print(f"{DEBUG_COLOR}[DEBUG] Extracted {len(cell_blocks)} CELL blocks.{RESET}")
        
        for cell in cell_blocks: # Organize cells by Textract's RowIndex and ColumnIndex
            r_idx, c_idx = cell["RowIndex"], cell["ColumnIndex"]
            if r_idx not in table_rows: table_rows[r_idx] = {}
            table_rows[r_idx][c_idx] = cell
        print(f"{DEBUG_COLOR}[DEBUG] Organized cells into {len(table_rows)} rows.{RESET}")
    else:
        print(f"{RED_TEXT}No TABLE structures detected by Textract. Time extraction may fail.{RESET}")

    # --- Data Extraction & Calculation Logic ---
    KNOWN_NAMES = [
        "katie", "lochlahn", "izzy", "iz", "summer", "julia", "curtis",
        "sam", "beks", "sophia", "owen", "debi", "jake", "molly", "gabby", "bek", 
        "lochlan", "wil", "mally", "saphia", "awen"
    ]
    name_data = {} # Final structured data: name_data[Name] = {"total_hours": X, "pairs": [...]}
    
    IN_TIMES_FOR_NOTE = ["10:00", "10:15", "10:30", "10:45", "11:00", "11:15", "11:30", "11:45", "12:00"]
    OUT_TIMES_FOR_NOTE = ["10:00", "10:15", "10:30", "10:45", "11:00", "11:15", "11:30", "11:45", "12:00"]
    FORCED_OVERNIGHT_SHIFTS = { # Handles specific pre-defined overnight shifts
        ("11:00", "12:00"): (13.0, EARLY_LEAVE_NOTE_EDIT, EARLY_LEAVE_NOTE_FINAL),
        ("11:45", "12:00"): (12.25, EARLY_LEAVE_NOTE_EDIT, EARLY_LEAVE_NOTE_FINAL)
    }

    def _create_datetime_with_context(time_str: str, is_pm: bool) -> datetime:
        # (This function is your specific logic for creating datetime objects with AM/PM context)
        dt = datetime.strptime(time_str, "%H:%M")
        if dt.hour == 0 and is_pm: dt = dt.replace(hour=12) 
        elif 1 <= dt.hour <= 11 and is_pm: dt = dt.replace(hour=dt.hour + 12) 
        elif dt.hour == 12 and not is_pm: dt = dt.replace(hour=0) 
        return dt

    def _parse_user_input_time(time_str_with_ampm: str) -> Union[datetime, None]:
        # (This function is your specific logic for parsing user-entered times with AM/PM)
        print(f"{DEBUG_COLOR}[DEBUG] _parse_user_input_time input: '{time_str_with_ampm}'{RESET}")
        # ... (rest of function is the same as your last version) ...
        time_str_with_ampm = time_str_with_ampm.strip().upper()
        match = re.fullmatch(r'(\d{1,2}:\d{2})\s*(AM|PM)', time_str_with_ampm)
        if match:
            time_part, ampm_part = match.group(1), match.group(2)
            try:
                dt = datetime.strptime(time_part, "%H:%M")
                if ampm_part == "PM" and dt.hour < 12: dt = dt.replace(hour=dt.hour + 12)
                elif ampm_part == "AM" and dt.hour == 12: dt = dt.replace(hour=0)
                return dt
            except ValueError: return None
        return None


    print(f"\n{EDIT_HEADER_COLOR}--- Stage 3: Extracting & Calculating Hours from Textract Table Data ---{RESET}")
    # Iterate through rows identified by Textract (1-based index)
    for r_idx in sorted(table_rows.keys()):
        print(f"{DEBUG_COLOR}[DEBUG] Processing Table RowIndex: {r_idx}{RESET}")
        # Assumes name is in the first column (ColumnIndex 1 from Textract)
        name_cell_block = table_rows[r_idx].get(1) 
        
        if name_cell_block:
            # Get text from the name cell
            name_text_raw = get_block_text(name_cell_block["Id"], block_map).strip()
            name_text_norm = name_text_raw.lower() # For matching against KNOWN_NAMES
            print(f"{DEBUG_COLOR}[DEBUG]   Name Cell (Row {r_idx}, Col 1): Raw='{name_text_raw}', Norm='{name_text_norm}'{RESET}")

            if name_text_norm in KNOWN_NAMES:
                name = name_text_norm.capitalize()
                print(f"{DEBUG_COLOR}[DEBUG]   Recognized Name: '{name}'{RESET}")
                ordered_row_elements = [] # Stores extracted times/labels in order for this row
                
                # Iterate through columns in this row (from Textract, 1-based index)
                cols_for_this_row = table_rows[r_idx]
                for c_idx in sorted(cols_for_this_row.keys()):
                    if c_idx > 1: # Skip the name column itself
                        current_cell_block = cols_for_this_row[c_idx]
                        raw_cell_text = get_block_text(current_cell_block["Id"], block_map).strip()
                        print(f"{DEBUG_COLOR}[DEBUG]     Col {c_idx} Raw Text: '{raw_cell_text}'{RESET}")
                        
                        # Clean and parse cell text for times or IN/OUT labels
                        cleaned_text = re.sub(r'[^0-9A-Za-z\s:]', '', raw_cell_text.replace('>', '07:00')).upper()
                        print(f"{DEBUG_COLOR}[DEBUG]     Col {c_idx} Cleaned Text: '{cleaned_text}'{RESET}")
                        if not cleaned_text.strip(): continue # Skip empty cells

                        # Regex to find times (HH:MM, HHHH, HMM) or single/double digits (hours), or IN/OUT labels
                        time_label_pattern = r'\b\d{1,2}:\d{2}\b|\b\d{3,4}\b|\b(?:1[0-2]|[1-9])\b|\b(?:IN|OUT|II|TO)\b|\/\d{1,2}\b'
                        parts = re.findall(time_label_pattern, cleaned_text)
                        print(f"{DEBUG_COLOR}[DEBUG]     Col {c_idx} Regex Parts: {parts}{RESET}")

                        for part in parts:
                            fixed_time = correct_time_format(part)
                            if fixed_time:
                                ordered_row_elements.append({"type": "time", "value": fixed_time})
                            elif part in ["IN", "OUT", "II", "TO"]: # "II" and "TO" might be OCR errors for 11, 10 or IN/OUT
                                ordered_row_elements.append({"type": "label", "value": part})
                
                print(f"{DEBUG_COLOR}[DEBUG]   For '{name}', Ordered Elements from Row: {ordered_row_elements}{RESET}")

                # Pair up IN and OUT times from the extracted elements
                all_in_times, all_out_times = [], []
                current_in_time, pending_in_label, pending_out_label = None, False, False
                for element in ordered_row_elements: # Process labels and times to form pairs
                    # (Pairing logic unchanged - it's your specific implementation)
                    # ... (rest of pairing logic from your script) ...
                    if element["type"] == "label":
                        label_value = element["value"]
                        if label_value == "IN": pending_in_label = True; pending_out_label = False
                        elif label_value == "OUT": pending_out_label = True; pending_in_label = False
                    elif element["type"] == "time":
                        if pending_in_label:
                            current_in_time = element["value"]
                            pending_in_label, pending_out_label = False, False 
                        elif pending_out_label and current_in_time:
                            all_in_times.append(current_in_time)
                            all_out_times.append(element["value"])
                            current_in_time, pending_out_label, pending_in_label = None, False, False 
                        else: 
                            if current_in_time is None: current_in_time = element["value"]
                            else:
                                all_in_times.append(current_in_time)
                                all_out_times.append(element["value"])
                                current_in_time = None
                if current_in_time: print(f"{RED_TEXT}Warn: Unmatched IN time '{current_in_time}' for {name}. Ignored.{RESET}")
                print(f"{DEBUG_COLOR}[DEBUG]   For '{name}', IN Times: {all_in_times}, OUT Times: {all_out_times}{RESET}")

                # Calculate hours for each IN/OUT pair
                name_session_times = []
                for i in range(min(len(all_in_times), len(all_out_times))):
                    in_str, out_str = all_in_times[i], all_out_times[i]
                    note_edit, note_final = "", ""
                    try:
                        # Check for forced overnight shifts first
                        forced_data = FORCED_OVERNIGHT_SHIFTS.get((in_str, out_str))
                        if forced_data:
                            hours, note_edit, note_final = forced_data
                            name_session_times.append((in_str, out_str, hours, note_edit, note_final))
                            print(f"{DEBUG_COLOR}[DEBUG]     Pair ({in_str}-{out_str}): Used FORCED_OVERNIGHT, Hours: {hours}{RESET}")
                            continue
                        
                        # Create datetime objects, trying different AM/PM interpretations
                        # (AM/PM heuristic logic unchanged - it's your specific implementation)
                        # ... (rest of AM/PM heuristic, candidate selection, and hour calculation from your script) ...
                        t1a = _create_datetime_with_context(in_str, False); t1p = _create_datetime_with_context(in_str, True)  
                        t2a = _create_datetime_with_context(out_str, False); t2p = _create_datetime_with_context(out_str, True)  
                        t2an = t2a + timedelta(days=1); t2pn = t2p + timedelta(days=1) 
                        candidates = [(t1a, t2a), (t1a, t2p)]
                        if t1p < t2p : candidates.append((t1p,t2p)) 
                        candidates.extend([(t1p, t2an), (t1p, t2pn)])
                        best_secs = float('inf'); chosen_pair = None
                        for t1, t2 in candidates:
                            secs = (t2-t1).total_seconds()
                            if 0 < secs <= 14 * 3600 and secs < best_secs: best_secs = secs; chosen_pair = (t1, t2)
                        
                        if chosen_pair:
                            mins = int(best_secs // 60); f_hrs = mins // 60; l_mins = mins % 60
                            r_hrs = f_hrs + 0.25 * ((l_mins + 7) // 15)
                            print(f"{DEBUG_COLOR}[DEBUG]     Pair ({in_str}-{out_str}): Chosen interpretation {chosen_pair[0].strftime('%H:%M')}-{chosen_pair[1].strftime('%H:%M %Y-%m-%d')}, Hours: {r_hrs}{RESET}")
                            if in_str in IN_TIMES_FOR_NOTE and out_str in OUT_TIMES_FOR_NOTE and datetime.strptime(in_str, "%H:%M") < datetime.strptime(out_str, "%H:%M"):
                                note_edit, note_final = EARLY_LEAVE_NOTE_EDIT, EARLY_LEAVE_NOTE_FINAL
                            name_session_times.append((in_str, out_str, r_hrs, note_edit, note_final))
                        else: print(f"{RED_TEXT}Warn: No valid shift duration for {name} ({in_str}-{out_str}). Pair skipped.{RESET}")
                    except ValueError as ve: print(f"{RED_TEXT}Error parsing pair for {name} ({in_str}-{out_str}): {ve}{RESET}")
                
                name_data[name] = {"total_hours": round(sum(p[2] for p in name_session_times), 2), "pairs": name_session_times}
                print(f"{DEBUG_COLOR}[DEBUG]   Finished '{name}'. Total Hours: {name_data[name]['total_hours']}, Pairs: {len(name_session_times)}{RESET}")
            else: # Name not in KNOWN_NAMES
                if name_text_raw.strip(): print(f"{DEBUG_COLOR}[DEBUG]   Name '{name_text_norm}' (Raw: '{name_text_raw}') not in KNOWN_NAMES. Row {r_idx} skipped.{RESET}")
        else: # No name cell found in the expected column
            print(f"{DEBUG_COLOR}[DEBUG]   No name cell in Col 1 for Row {r_idx}. Skipping.{RESET}")

    # --- Interactive Editing Feature ---
    # (This section is unchanged from your original logic)
    print(f"\n{EDIT_HEADER_COLOR}--- Stage 4: Review and Edit Calculated Hours ---{RESET}")
    editable_shifts = []
    shift_counter = 0
    for name_key_e in sorted(name_data.keys()):
        if name_data[name_key_e]['pairs']:
            for i_e, pair_item_e in enumerate(name_data[name_key_e]['pairs']):
                shift_counter += 1; editable_shifts.append({'id': shift_counter, 'person': name_key_e, 'original_person_data_index': i_e, 'in_time_str': pair_item_e[0], 'out_time_str': pair_item_e[1], 'hours': pair_item_e[2], 'note_for_edit': pair_item_e[3], 'note_for_final': pair_item_e[4]})
    print(f"{DEBUG_COLOR}[DEBUG] Generated {len(editable_shifts)} editable shifts.{RESET}")

    def display_editable_shifts(shifts: List[Dict[str, Any]]):
        print(f"\n{EDIT_HEADER_COLOR}{'='*60}\n             Current Shifts for Editing:\n{'='*60}{RESET}")
        if not shifts: print(f"{RED_TEXT}No shifts to display.{RESET}"); return
        print(f"  {BOLD}{EDIT_HEADER_COLOR}No. Name      IN Time    → OUT Time   Hrs  Note{RESET}")
        print(f"  {BOLD}{EDIT_HEADER_COLOR}--- --------- -------------------- ---- ----{RESET}")
        for s in shifts: print(f"{EDIT_HEADER_COLOR}{s['id']: >3}.{RESET} {EDIT_NAME_COLOR}{s['person']:<9}{RESET}: {EDIT_TIME_COLOR}IN {s['in_time_str']:<7} → OUT {s['out_time_str']:<7}{RESET} = {EDIT_HEADER_COLOR}{s['hours']:>4.1f}{RESET} {EDIT_TIME_COLOR}hrs{RESET}{s['note_for_edit']}")
        print(f"{EDIT_HEADER_COLOR}{'='*60}{RESET}")

    while True:
        display_editable_shifts(editable_shifts)
        if not editable_shifts: print(f"{EDIT_HEADER_COLOR}No shifts to edit. Proceeding.{RESET}"); break
        edit_choice = input(f"\n{EDIT_HEADER_COLOR}Shift No. to edit, or 'done': {RESET}").strip().lower()
        if edit_choice == 'done': break
        try:
            chosen_id = int(edit_choice)
            sel_s = next((s for s in editable_shifts if s['id'] == chosen_id), None) # Find shift by ID
            if sel_s:
                # (Edit logic for selected shift unchanged - it's your specific implementation)
                # ... (rest of edit logic from your script) ...
                actual_idx = editable_shifts.index(sel_s)
                print(f"\nEditing: {sel_s['person']} IN {sel_s['in_time_str']} → OUT {sel_s['out_time_str']}")
                new_in = input(f"{EDIT_TIME_COLOR}New IN (HH:MM AM/PM) or Enter to keep: {RESET}").strip()
                new_out = input(f"{EDIT_TIME_COLOR}New OUT (HH:MM AM/PM) or Enter to keep: {RESET}").strip()
                p_in = _parse_user_input_time(new_in) if new_in else (_parse_user_input_time(f"{sel_s['in_time_str']} AM") or _parse_user_input_time(f"{sel_s['in_time_str']} PM"))
                p_out = _parse_user_input_time(new_out) if new_out else (_parse_user_input_time(f"{sel_s['out_time_str']} PM") or _parse_user_input_time(f"{sel_s['out_time_str']} AM"))
                if not p_in or not p_out: print(f"{RED_TEXT}Invalid edit times. Try again.{RESET}"); continue
                tmp_out = p_out + timedelta(days=1) if p_out <= p_in else p_out
                secs = (tmp_out - p_in).total_seconds()
                if secs <=0: print(f"{RED_TEXT}Invalid duration. Try again.{RESET}"); continue
                mins=int(secs//60); f_hrs=mins//60; l_mins=mins%60
                re_hrs = f_hrs + 0.25*((l_mins+7)//15)
                n_e, n_f = "", ""
                e_in_s = p_in.strftime("%H:%M"); e_out_s = p_out.strftime("%H:%M")
                f_edit = FORCED_OVERNIGHT_SHIFTS.get((e_in_s, e_out_s))
                if f_edit: _, n_e, n_f = f_edit
                elif e_in_s in IN_TIMES_FOR_NOTE and e_out_s in OUT_TIMES_FOR_NOTE and datetime.strptime(e_in_s,"%H:%M") < datetime.strptime(e_out_s,"%H:%M"): n_e, n_f = EARLY_LEAVE_NOTE_EDIT, EARLY_LEAVE_NOTE_FINAL
                editable_shifts[actual_idx].update({'in_time_str': e_in_s, 'out_time_str': e_out_s, 'hours': re_hrs, 'note_for_edit': n_e, 'note_for_final': n_f})
                name_data[sel_s['person']]['pairs'][sel_s['original_person_data_index']] = (e_in_s, e_out_s, re_hrs, n_e, n_f)
                name_data[sel_s['person']]['total_hours'] = round(sum(p[2] for p in name_data[sel_s['person']]['pairs']), 2)
                print(f"{FINAL_TIME_COLOR}Shift updated.{RESET}")
            else: print(f"{RED_TEXT}Invalid shift number.{RESET}")
        except ValueError: print(f"{RED_TEXT}Invalid input.{RESET}")
        except Exception as e_edit: print(f"{RED_TEXT}Edit error: {e_edit}{RESET}\n{traceback.format_exc()}{RESET}")

    # --- Final Summary Output ---
    print(f"\n{FINAL_HEADER_COLOR}{'='*40}\n             📋 Final Weekly Hours Summary:\n{'='*40}{RESET}\n")
    if not name_data: print(f"{RED_TEXT}No data to summarize.{RESET}")
    for name_key_final in sorted(name_data.keys()):
        total_final = name_data[name_key_final]['total_hours']
        print(f"{BOLD}{FINAL_NAME_COLOR}{name_key_final}{RESET}: {FINAL_TIME_COLOR}{total_final}{RESET} {FINAL_TIME_COLOR}hrs{RESET}")
        if name_data[name_key_final]['pairs']:
            for in_t, out_t, hrs_t, _, note_f_t in name_data[name_key_final]['pairs']:
                print(f"   • {FINAL_TIME_COLOR}IN {in_t} → OUT {out_t}{RESET} = {FINAL_TIME_COLOR}{hrs_t:>4.1f}{RESET} hrs{note_f_t}")
        else: print(f"   {EDIT_TIME_COLOR}(No pairs found for this person){RESET}")
        print() # Blank line for readability
    print(f"{FINAL_HEADER_COLOR}--- Analysis Complete ---{RESET}")

    print(f"{DEBUG_COLOR}[DEBUG] End of script.{RESET}")