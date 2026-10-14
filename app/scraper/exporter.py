import json
from typing import List, Dict, Any
from app.models import ExtractedRecord, ScrapeStats

def export_records_to_json(records: List[ExtractedRecord]) -> str:
    """Serialize list of ExtractedRecord models to clean UTF-8 JSON string."""
    data = [record.model_dump() for record in records]
    return json.dumps(data, indent=2, ensure_ascii=False)

def export_full_job_json(records: List[ExtractedRecord], stats: ScrapeStats, target_url: str) -> str:
    """Serialize records along with extraction metadata stats."""
    payload = {
        "metadata": {
            "target_url": target_url,
            "pages_visited": stats.pages_visited,
            "records_extracted": stats.records_extracted,
            "duration_seconds": stats.duration_seconds,
            "timestamp": stats.end_time or stats.start_time,
            "errors": stats.errors
        },
        "records": [r.model_dump() for r in records]
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)

