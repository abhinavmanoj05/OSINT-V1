"""
Logging configuration
"""
import logging
import sys
from pathlib import Path
from typing import Optional

# Create logs directory
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "app.log")
    ]
)

logger = logging.getLogger("crime_mapper")


class AuditLogger:
    """Audit logging for legal compliance"""
    
    def __init__(self):
        self.audit_handler = logging.FileHandler(LOG_DIR / "audit.log")
        self.audit_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(message)s")
        )
        self.audit_logger = logging.getLogger("audit")
        self.audit_logger.addHandler(self.audit_handler)
        self.audit_logger.setLevel(logging.INFO)
    
    def log_action(self, user_id: str, action: str, case_id: Optional[str] = None, details: dict = None):
        """Log an action for audit trail"""
        log_entry = f"USER:{user_id} | ACTION:{action}"
        if case_id:
            log_entry += f" | CASE:{case_id}"
        if details:
            log_entry += f" | DETAILS:{details}"
        self.audit_logger.info(log_entry)


audit_logger = AuditLogger()