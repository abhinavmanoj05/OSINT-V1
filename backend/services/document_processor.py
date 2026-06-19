"""
Document processing with OCR and entity extraction
"""
import re
import time
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

import pdfplumber
from PIL import Image

from backend.models.document import (
    OCRResult, ExtractedEntity, DocumentProcessingResult, DocumentMetadata
)


@dataclass
class ProcessingConfig:
    ocr_engine: str = "paddle"  # paddle, tesseract
    extract_tables: bool = True
    extract_entities: bool = True
    languages: List[str] = None
    
    def __post_init__(self):
        if self.languages is None:
            self.languages = ["en", "hi"]  # English and Hindi


class DocumentProcessor:
    """
    Process documents: PDFs and images with OCR and entity extraction
    """
    
    # Regex patterns for Indian entities
    PATTERNS = {
        "PHONE": r'(?:\+91[\-\s]?)?[0]?(?:\d{10}|\d{5}[\-\s]\d{5})',
        "EMAIL": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        "UPI": r'[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+',
        "AADHAAR": r'\d{4}[\s-]?\d{4}[\s-]?\d{4}',
        "PAN": r'[A-Z]{5}[0-9]{4}[A-Z]{1}',
        "BANK_ACCOUNT": r'\d{9,18}',
        "IFSC": r'[A-Z]{4}0[A-Z0-9]{6}',
        "AMOUNT": r'(?:Rs\.?|₹|INR)\s*[\d,]+(?:\.\d{2})?',
        "URL": r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+',
        "DOMAIN": r'\b[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',
        "LOCATION": r'\b(India|Kerala|Delhi|Mumbai|Bangalore|New York|London|Dubai)\b',
        "AFFILIATION": r'([A-Z][a-zA-Z\s]+(?:College|University|Company|Inc\.|Ltd\.|LLC))',
        "POTENTIAL_NAME": r'(?:Mr\.|Mrs\.|Ms\.|Dr\.)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)'
    }
    
    def __init__(self, config: Optional[ProcessingConfig] = None):
        self.config = config or ProcessingConfig()
        try:
            self.ocr = self._initialize_ocr()
        except Exception as e:
            print(f"Error initializing OCR: {e}")
            self.ocr = None
        
    def _initialize_ocr(self):
        """Initialize OCR engine"""
        if self.config.ocr_engine == "paddle":
            try:
                from paddleocr import PaddleOCR
                return PaddleOCR(
                    use_angle_cls=True,
                    lang='en',
                    show_log=False
                )
            except Exception as e:
                print(f"PaddleOCR not available or failed to init: {e}, falling back to Tesseract")
                self.config.ocr_engine = "tesseract"
        
        if self.config.ocr_engine == "tesseract":
            try:
                import pytesseract
                # Test tesseract availability
                pytesseract.get_tesseract_version()
                return pytesseract
            except Exception as e:
                print(f"Tesseract not available: {e}")
                self.config.ocr_engine = "none"
        
        return None
    
    async def process_document(self, file_path: str, mime_type: str) -> DocumentProcessingResult:
        """
        Process a document file
        """
        start_time = time.time()
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        # Get metadata
        metadata = self._get_metadata(file_path, mime_type)
        
        ocr_results = []
        extracted_entities = []
        
        try:
            if mime_type == "application/pdf":
                ocr_results = await self._process_pdf(file_path)
            elif mime_type.startswith("image/"):
                ocr_results = await self._process_image(file_path)
        except Exception as e:
            print(f"Error processing {mime_type}: {e}")
            # Continue with empty OCR results if processing fails
        
        # Extract entities from OCR text using regex
        all_text = " ".join([r.text for r in ocr_results])
        extracted_entities = self._extract_entities(all_text)
        
        # LLM Semantic Analysis
        llm_analysis = None
        if self.config.extract_entities and len(all_text.strip()) > 0:
            try:
                from backend.services.llm_comprehension import get_provider_singleton
                llm_provider = get_provider_singleton()
                if llm_provider:
                    llm_analysis = await llm_provider.analyze_document(all_text)
            except Exception as e:
                print(f"Error in LLM document analysis: {e}")
        
        processing_time = time.time() - start_time
        
        return DocumentProcessingResult(
            document_id=str(file_path.stem),
            metadata=metadata,
            ocr_results=ocr_results,
            extracted_entities=extracted_entities,
            llm_analysis=llm_analysis,
            processing_time=processing_time,
            status="completed"
        )
    
    def _get_metadata(self, file_path: Path, mime_type: str) -> DocumentMetadata:
        """Extract file metadata"""
        stat = file_path.stat()
        return DocumentMetadata(
            filename=file_path.name,
            file_type=mime_type,
            file_size=stat.st_size,
            created_date=None,
            modified_date=None
        )
    
    async def _process_pdf(self, file_path: Path) -> List[OCRResult]:
        """Process PDF file"""
        results = []
        
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                # Try to extract text directly first
                text = page.extract_text()
                
                if text and len(text.strip()) > 10:
                    results.append(OCRResult(
                        text=text,
                        confidence=0.95,
                        page_number=i + 1
                    ))
                else:
                    # Fall back to OCR on page image
                    page_image = page.to_image(resolution=150)
                    img_path = file_path.parent / f"temp_page_{i}.png"
                    page_image.save(img_path)
                    
                    ocr_result = await self._process_image(img_path)
                    if ocr_result:
                        results.extend(ocr_result)
                    
                    img_path.unlink(missing_ok=True)
        
        return results
    
    async def _process_image(self, file_path: Path) -> List[OCRResult]:
        """Process image file with OCR"""
        results = []
        
        if not self.ocr:
            print("No OCR engine initialized")
            return results
            
        if self.config.ocr_engine == "paddle":
            ocr_data = self.ocr.ocr(str(file_path), cls=True)
            if ocr_data and ocr_data[0]:
                for line in ocr_data[0]:
                    if line:
                        text = line[1][0]
                        confidence = line[1][1]
                        bbox = line[0]
                        results.append(OCRResult(
                            text=text,
                            confidence=confidence,
                            bounding_box=[int(c) for coord in bbox for c in coord[:2]],
                            page_number=1
                        ))
        else:
            # Tesseract
            import pytesseract
            image = Image.open(file_path)
            text = pytesseract.image_to_string(image)
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            
            confidences = [int(c) for c in data['conf'] if int(c) > 0]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            results.append(OCRResult(
                text=text,
                confidence=avg_confidence / 100,
                page_number=1
            ))
        
        return results
    
    def _extract_entities(self, text: str) -> List[ExtractedEntity]:
        """Extract entities from text using regex patterns"""
        entities = []
        
        for entity_type, pattern in self.PATTERNS.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                context_start = max(0, match.start() - 50)
                context_end = min(len(text), match.end() + 50)
                context = text[context_start:context_end]
                
                entities.append(ExtractedEntity(
                    entity_type=entity_type,
                    value=match.group(),
                    confidence=0.8,
                    context=context,
                    position={"start": match.start(), "end": match.end()}
                ))
        
        # Remove duplicates
        seen = set()
        unique_entities = []
        for e in entities:
            key = (e.entity_type, e.value)
            if key not in seen:
                seen.add(key)
                unique_entities.append(e)
        
        return unique_entities