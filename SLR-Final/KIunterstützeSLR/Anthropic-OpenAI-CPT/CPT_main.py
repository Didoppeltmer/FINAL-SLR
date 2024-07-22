import csv
import shutil
import os
from openai import OpenAI
from anthropic import Anthropic
from PyPDF2 import PdfReader
import time

# Konfiguration
CLAUDE_API_KEY = "YOUR ANTHROPIC API KEY"
GPT_API_KEY = "YOUR OPENAI API KEY"
INPUT_FOLDER = '../Verfügbare_PDFs'
OUTPUT_FOLDER = '../Konvertierbare_Texte'
OUTPUT_CSV = './CPToutput.csv'
OUTPUT_UNFORMATTED = './CPToutput_unformatted.csv'
PROCESSED_FOLDER = '../Verarbeitete_Texte'
USED_PDFS = '../Konvertierte_PDFs'
SYSTEM_PROMPT_PATH = '../system_prompt.txt'
VALIDATION_PROMPT = "../validation_prompt.txt"
MAIN_PROMPT = 'Here is a scientific article, please follow the output format exactly: <paper>{}</paper>'


# Initialisierung des OpenAI Clients
claudeclient = Anthropic(api_key=CLAUDE_API_KEY)
gptclient = OpenAI(api_key=GPT_API_KEY)

def ensure_directories_exist():
    """Stellt sicher, dass alle benötigten Verzeichnisse existieren."""
    for directory in [INPUT_FOLDER, OUTPUT_FOLDER, PROCESSED_FOLDER, USED_PDFS]:
        os.makedirs(directory, exist_ok=True)

def convert_pdf_to_text(pdf_path, output_path):
    """Konvertiert eine einzelne PDF-Datei in Text."""
    with open(pdf_path, 'rb') as pdf_file:
        pdf_reader = PdfReader(pdf_file)
        text = ''.join(page.extract_text() for page in pdf_reader.pages)

    with open(output_path, 'w', encoding='utf-8') as txt_file:
        txt_file.write(text)

def convert_all_pdfs():
    """Konvertiert alle PDF-Dateien im Eingabeordner sequentiell."""
    pdf_files = [f for f in os.listdir(INPUT_FOLDER) if f.lower().endswith('.pdf')]
    for filename in pdf_files:
        pdf_path = os.path.join(INPUT_FOLDER, filename)
        output_filename = os.path.splitext(filename)[0] + '.txt'
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)

        if os.path.exists(output_path):
            print(f'Die Datei {output_filename} existiert bereits. Überspringe Konvertierung.')
            continue

        convert_pdf_to_text(pdf_path, output_path)
        print(f'Die PDF-Datei {filename} wurde erfolgreich konvertiert.')

        processed_path = os.path.join(USED_PDFS, filename)
        shutil.move(pdf_path, processed_path)
        print(f"PDF-Datei {filename} wurde verschoben.")

def read_system_prompt():
    """Liest den Systempromt aus der Datei system_prompt.txt."""
    try:
        with open(SYSTEM_PROMPT_PATH, "r") as f:
            return f.read()
    except Exception as e:
        print(f"Error reading file {SYSTEM_PROMPT_PATH}: {e}")
        return None

def read_validation_prompt():
    """Liest den Validierungsprompt aus der Datei validation_prompt.txt."""
    try:
        with open(VALIDATION_PROMPT, "r") as f:
            return f.read()
    except Exception as e:
        print(f"Error reading file {VALIDATION_PROMPT}: {e}")
        return None

def send_text_to_gpt(text, prompt):
    """Sendet Text an die GPT API und gibt die Antwort zurück."""
    system_prompt = read_system_prompt()
    if not system_prompt:
        return None
    try:
        response = gptclient.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt.format(text)}
            ],
            max_tokens=2048,
            temperature=0.0
        )
        return response.choices[0].message.content if response.choices else None
    except Exception as e:
        print(f"Error in API request: {e}")
        return None

def validate_claude_response(initial_response, original_text):
    """Validiert die erste Antwort von Claude mit einer zweiten KI-Anfrage"""
    validation_prompt = read_validation_prompt()
    if not validation_prompt:
        return None
    try:
        response = claudeclient.messages.create(
            system=validation_prompt,
            max_tokens=1000,
            model="claude-3-5-sonnet-20240620",
            temperature=0.0,
            messages=[
                {"role": "user", "content": f"""Here is a scientific article: {original_text}
                    Here is a preliminary evaluation that you should critically evaluate again 
                    and output in the specified format: {initial_response}"""}
            ]
        )

        return response.content[0].text if response.content else None
    except Exception as e:
        print(f"Fehler bei der API-Anfrage: {e}")
        return None

def extract_formatted_output(text):
    """Extrahiert den formatierten Output aus dem KI-Antworttext."""
    cleaned_text = text.strip()
    cleaned_text = cleaned_text.strip('"')
    lines = cleaned_text.split('\n')

    for line in lines:
        line = line.strip()
        parts = line.split(',')
        if len(parts) == 12:
            if all(part.replace('.', '').isdigit() for part in parts[4:]):
                return line

    print("Konnte keinen gültigen formatierten Output finden.")
    return None

def save_unformatted_output(filename, content):
    """Speichert unformatierten Output in eine separate CSV-Datei."""
    with open(OUTPUT_UNFORMATTED, 'a', newline='', encoding='utf-8') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([filename, content])
    print(f'Unformatierter Output für {filename} wurde in {OUTPUT_UNFORMATTED} gespeichert.')

def process_text_file(filename):
    """Verarbeitet eine einzelne Textdatei."""
    txt_path = os.path.join(OUTPUT_FOLDER, filename)
    with open(txt_path, 'r', encoding='utf-8') as txt_file:
        text = txt_file.read()

    initial_result = send_text_to_gpt(text, MAIN_PROMPT)
    if initial_result:
        time.sleep(30)
        validated_result = validate_claude_response(initial_result, text)
        final_result = validated_result if validated_result else initial_result

        formatted_output = extract_formatted_output(final_result)
        if formatted_output:
            with open(OUTPUT_CSV, 'a', newline='', encoding='utf-8') as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow([formatted_output])
            print(f'Die Datei {filename} wurde erfolgreich verarbeitet und der formatierte Output extrahiert.')
        else:
            save_unformatted_output(filename, final_result)
            print(f'Konnte keinen gültigen formatierten Output für {filename} extrahieren. Unformatierter Output gespeichert.')

        processed_path = os.path.join(PROCESSED_FOLDER, filename)
        shutil.move(txt_path, processed_path)
        print(f"Datei {filename} wurde verarbeitet und verschoben.")
    else:
        print(f'Fehler bei der Verarbeitung der Datei {filename}. Kein Output verfügbar.')

def process_all_texts():
    """Verarbeitet alle Textdateien im Ausgabeordner sequentiell."""
    txt_files = [f for f in os.listdir(OUTPUT_FOLDER) if f.lower().endswith('.txt')]
    for filename in txt_files:
        process_text_file(filename)
        time.sleep(30)


def main():
    """Hauptfunktion zur Ausführung der Pipeline."""
    ensure_directories_exist()
    convert_all_pdfs()
    process_all_texts()

if __name__ == "__main__":
    main()
