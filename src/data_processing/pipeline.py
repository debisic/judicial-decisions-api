'''
This script downloads tar.gz files from a website, extracts XML files, processes them, 
and stores relevant data in a PostgreSQL database.

Libraries used:
- requests: to download files
- tarfile: to extract files
- xmltodict: to parse XML files
- sqlalchemy: to interact with the database
- BeautifulSoup: to scrape links to tar.gz files
- logging: for detailed logging of the process
'''

import os
import logging
import tarfile
import json
import time
import requests
import xmltodict
from requests.exceptions import RequestException
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_HOST = os.getenv("POSTGRES_HOST")
DB_PORT = os.getenv("POSTGRES_PORT")
DB_NAME = os.getenv("POSTGRES_DB")
print(
    f"DB_USER={DB_USER}, \
    DB_PASSWORD={DB_PASSWORD}, \
    DB_HOST={DB_HOST}, \
    DB_PORT={DB_PORT}, \
    DB_NAME={DB_NAME}"
    )

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
PROCESSED_LINKS_FILE = "processed_links.txt"
BATCH_SIZE = 10000  # Number of records to insert in one batch


def get_tar_gz_links(url):
    '''Extracts links to tar.gz files from the given URL.'''
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        links = [url + link.get('href') for link in soup.find_all('a') if link.get('href', '') \
                 .endswith('.tar.gz')]
        logging.info("Found %d tar.gz links on the page.", len(links))
        return links
    except RequestException as e:
        logging.error("HTTP error while fetching tar.gz links: %s", e)
    except AttributeError as e:
        logging.error("Error parsing HTML content: %s", e)
        return []


def download_file(url, dest_folder):
    '''Downloads a file from the given URL to the destination folder.'''
    try:
        if not os.path.exists(dest_folder):
            os.makedirs(dest_folder)
        local_filename = os.path.join(dest_folder, os.path.basename(url))
        with requests.get(url, stream=True, timeout=10) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        logging.info("Downloaded file: %s", local_filename)
        return local_filename
    except requests.Timeout:
        logging.error("Download timed out: %s", url)
        return None
    except requests.ConnectionError as e:
        logging.error("Connection error while downloading %s: %s", url, e)
        return None
    except requests.RequestException as e:
        logging.error("Error downloading file %s: %s", url, e)
        return None
    except OSError as e:
        logging.error("OS error while saving file %s: %s", url, e)
        return None


def extract_tar_gz(tar_gz_path, extract_folder):
    '''Extracts the contents of a tar.gz file to the extract folder.'''
    try:
        if not os.path.exists(extract_folder):
            os.makedirs(extract_folder)
        with tarfile.open(tar_gz_path, 'r:gz') as tar:
            tar.extractall(path=extract_folder)
        logging.info("Extracted %s to %s", tar_gz_path, extract_folder)
    except FileNotFoundError as e:
        logging.error("File not found: %s. Error: %s", tar_gz_path, e)
    except tarfile.TarError as e:
        logging.error("Error processing tar.gz file %s: %s", tar_gz_path, e)
    except PermissionError as e:
        logging.error("Permission error while accessing %s: %s", extract_folder, e)
    except OSError as e:
        logging.error("OS error while extracting %s: %s", tar_gz_path, e)


def clean_contenu(contenu):
    """Clean up the 'contenu' field by removing null values 
    from 'br' and cleaning excessive spaces and line breaks."""
    try:
        # Parse JSON content
        data = json.loads(contenu)
        # Remove 'null' values from "br" list if it exists
        if isinstance(data, dict) and "br" in data:
            del data["br"]
        # Convert back to a JSON string
        cleaned_json = json.dumps(data, ensure_ascii=False)
        return cleaned_json.strip()
    except json.JSONDecodeError:
        # If input is not valid JSON, just clean spaces and line breaks
        return contenu.strip()


def process_xml_files(directory, engine):
    '''Processes the XML files in the given directory 
    and saves the data to the database in batches.'''
    batch_records = []  # List to accumulate records for batch insertion

    for root, _, files in os.walk(directory):
        xml_files = [file for file in files if file.endswith('.xml')]
        for file in xml_files:
            file_path = os.path.join(root, file)
            start_time = time.time()  # Track processing time
            try:
                with open(file_path, 'r', encoding='utf-8') as xml_file:
                    xml_content = xml_file.read()
                    parsed_xml = xmltodict.parse(xml_content)
                    if time.time() - start_time > 30:  # Stop if processing takes too long
                        logging.error("Skipping file due to timeout: %s", file_path)
                        continue
                    # Extract and validate data
                    record = extract_record(parsed_xml)
                    if record:
                        batch_records.append(record)
                    # Insert batch if size limit is reached
                    if len(batch_records) >= BATCH_SIZE:
                        insert_batch_to_db(batch_records, engine)
                        batch_records = []  # Clear the batch after insertion

            except FileNotFoundError as e:
                logging.error("File not found: %s. Error: %s", file_path, e)
            except xmltodict.expat.ExpatError as e:
                logging.error("Error parsing XML file %s: %s", file_path, e)
            except ValueError as e:
                logging.error("value error processing file %s: %s", file_path, e)

    # Insert any remaining records in the batch
    if batch_records:
        insert_batch_to_db(batch_records, engine)


def extract_record(parsed_xml):
    '''Extracts and validates a single record from the parsed XML.'''
    try:
        text_id = parsed_xml.get('TEXTE_JURI_JUDI', {}).get('META', {}) \
            .get('META_COMMUN', {}).get('ID')
        titre = parsed_xml.get('TEXTE_JURI_JUDI', {}).get('META', {}) \
            .get('META_SPEC', {}).get('META_JURI', {}).get('TITRE')
        chambre = parsed_xml.get('TEXTE_JURI_JUDI', {}).get('META', {}) \
            .get('META_SPEC', {}).get('META_JURI_JUDI', {}).get('FORMATION')
        # Validate and clean 'chambre'
        chambre = chambre.strip() if chambre else None
        contenu = clean_contenu(json.dumps(parsed_xml
            .get('TEXTE_JURI_JUDI', {}).get('TEXTE', {}).get('BLOC_TEXTUEL', {}).get('CONTENU')))
        return {
                "text_id": text_id,
                "titre": titre,
                "chambre": chambre,
                "contenu": contenu
        }
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        logging.error("Error extracting record: %s", e)
        return None


def insert_batch_to_db(batch_records, engine):
    '''Inserts a batch of records into the database.'''
    try:
        with engine.connect() as connection:
            query = text("""
                INSERT INTO court_history (text_id, titre, chambre, contenu) 
                VALUES (:text_id, :titre, :chambre, :contenu)
                         ON CONFLICT (text_id, titre, chambre) DO NOTHING
            """)
            connection.execute(query, batch_records)
            connection.commit()
            logging.info("Inserted batch of %d records into the database.", len(batch_records))
    except Exception as e:
        logging.error("****Error inserting batch to database****: %s", e)


def load_processed_links():
    '''Loads the list of processed links from the file.'''
    if os.path.exists(PROCESSED_LINKS_FILE):
        with open(PROCESSED_LINKS_FILE, 'r', encoding='utf-8') as file:
            return set(file.read().splitlines())
    return set()


def save_processed_link(link):
    '''Saves a processed link to the file.'''
    with open(PROCESSED_LINKS_FILE, 'a', encoding='utf-8') as file:
        file.write(link + '\n')


def main():
    '''Main function that orchestrates the entire process.'''
    logging.info("====Starting the pipeline====")
    start_time = time.time()
    base_url = "https://echanges.dila.gouv.fr/OPENDATA/CASS/"
    dest_folder = "downloads"
    extract_folder = "extracted_files"

    # Load previously processed links
    processed_links = load_processed_links()

    # Get tar.gz links from the website
    tar_gz_links = get_tar_gz_links(base_url)

    if tar_gz_links:
        engine = create_engine(DATABASE_URL) # Create a database engine
        with engine.begin() as connection:   # Ensure table exists before inserting data
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS court_history (
                    text_id VARCHAR(255),
                    titre TEXT,
                    chambre TEXT, 
                    contenu TEXT,
                    CONSTRAINT unique_record UNIQUE (text_id, titre, chambre)                 
                )
            """))
            logging.info("Checked/Created the 'court_history' table.")

            # Create a GIN index for full-text search
            connection.execute(text("""
                CREATE INDEX IF NOT EXISTS court_history_tsv_idx 
                ON court_history 
                USING gin(to_tsvector('french', titre || ' ' || chambre || ' ' || contenu))
            """))
            logging.info("Checked/Created the 'court_history_tsv_idx' index.")

        for link in tar_gz_links:
            if link in processed_links:
                logging.info("Skipping already processed link: %s", link)
                continue

            logging.info("====Processing file====: %s", link)
            tar_gz_path = download_file(link, dest_folder)
            if tar_gz_path:
                extract_tar_gz(tar_gz_path, extract_folder)
                process_xml_files(extract_folder, engine)
                save_processed_link(link)

        logging.info("====Pipeline completed successfully====.")
        end_time = time.time()
        logging.info("Total time taken: %s seconds", end_time - start_time)
    else:
        logging.warning("****No tar.gz links found. Pipeline terminated****.")


if __name__ == "__main__":
    main()
