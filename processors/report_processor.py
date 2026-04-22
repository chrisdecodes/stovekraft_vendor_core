
import time
import requests
import zipfile
import gzip
import io
import json
import csv
import os
import structlog
from datetime import datetime

log = structlog.get_logger()

class ReportProcessor:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def download_report(self, document_data: dict) -> str:
        url = document_data["url"]
        compression = document_data.get("compressionAlgorithm")

        log.info("downloading_report", url=url, compression=compression)
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        raw = response.content

        if compression == "GZIP":
            raw = gzip.decompress(raw)
        elif compression == "ZIP":
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                name = z.namelist()[0]
                raw = z.read(name)

        return raw.decode("utf-8")

    def parse_report(self, text: str, report_type: str) -> list[dict]:
        """Parses report text based on format. Handles JSON, JSONL, and CSV/TSV."""
        text = text.strip()
        if not text:
            return []

        # 1. Try single JSON object
        if text.startswith('{') or text.startswith('['):
            try:
                data = json.loads(text)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    # Some Amazon reports wrap the data in a key (e.g. 'salesByMarketplace')
                    for key in data:
                        if isinstance(data[key], list):
                            return data[key]
                    return [data] # Fallback: return the dict as a single row
            except Exception:
                pass

        # 2. Try JSONL
        try:
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        except (json.JSONDecodeError, TypeError):
            pass

        # 3. Try TSV (common for inventory reports)
        try:
            reader = csv.DictReader(io.StringIO(text), delimiter="\t")
            rows = list(reader)
            if rows and len(rows[0]) > 1:
                return rows
        except Exception:
            pass

        # 4. Fallback to CSV
        try:
            reader = csv.DictReader(io.StringIO(text))
            return list(reader)
        except Exception:
            return [{"raw": text}]

    def save_to_csv(self, rows: list[dict], store_id: str, report_type: str) -> str:
        if not rows:
            return ""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{store_id}_{report_type}_{timestamp}.csv"
        file_path = os.path.join(self.output_dir, filename)

        keys = set()
        for row in rows:
            if isinstance(row, dict):
                # Filter out None keys to avoid sorting errors
                keys.update([str(k) for k in row.keys() if k is not None])
        
        if not keys:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(str(rows))
            return file_path

        fieldnames = sorted(list(keys))

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)

        log.info("report_saved_to_csv", path=file_path, row_count=len(rows))
        return file_path

    def save_raw_report(self, content: str, store_id: str, report_type: str, is_error: bool = False) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = "ERROR_" if is_error else "RAW_"
        filename = f"{prefix}{store_id}_{report_type}_{timestamp}.txt"
        file_path = os.path.join(self.output_dir, filename)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        log.info("raw_report_saved", path=file_path, is_error=is_error)
        return file_path