import io
import os
import re
import zipfile
import xml.etree.ElementTree as ET

ALLOWED_KNOWLEDGE_EXTENSIONS = {'.pdf', '.xlsx', '.xls', '.docx', '.doc'}
MAX_EXTRACTED_CHARS = 12000


def validate_knowledge_file(uploaded_file):
    """
    Valida que el archivo subido sea únicamente PDF, Excel (.xlsx, .xls) o Word (.docx, .doc).
    Retorna (is_valid: bool, error_message: str, ext: str).
    """
    if not uploaded_file:
        return False, "No se seleccionó ningún archivo.", ""

    filename = getattr(uploaded_file, 'name', '') or ''
    ext = os.path.splitext(filename)[1].lower().strip()

    if ext not in ALLOWED_KNOWLEDGE_EXTENSIONS:
        return (
            False,
            f"Formato '{ext or 'desconocido'}' no permitido. Solo se aceptan archivos PDF (.pdf), Excel (.xlsx, .xls) y Word (.docx, .doc).",
            ext
        )

    # Límite máximo de tamaño (5 MB)
    max_bytes = 5 * 1024 * 1024
    if getattr(uploaded_file, 'size', 0) > max_bytes:
        return False, "El archivo supera el tamaño máximo permitido de 5 MB.", ext

    return True, "", ext


def _extract_pdf_text(file_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for page in reader.pages:
            txt = page.extract_text() or ""
            if txt.strip():
                pages_text.append(txt.strip())
        if pages_text:
            return "\n\n".join(pages_text)
    except Exception:
        pass

    # Fallback nativo básico si pypdf no está disponible en algún entorno
    try:
        raw_str = file_bytes.decode('latin-1', errors='ignore')
        matches = re.findall(r'\(([^()]{3,})\)', raw_str)
        cleaned = [m for m in matches if any(c.isalpha() for c in m)]
        return "\n".join(cleaned)
    except Exception:
        return ""


def _extract_excel_text(file_bytes: bytes) -> str:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
        sheets_output = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows_text = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip() != ""]
                if cells:
                    rows_text.append(" | ".join(cells))
            if rows_text:
                sheets_output.append(f"[Hoja: {sheet_name}]\n" + "\n".join(rows_text))
        wb.close()
        return "\n\n".join(sheets_output)
    except Exception:
        return ""


def _extract_docx_text(file_bytes: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            if 'word/document.xml' not in zf.namelist():
                return ""
            xml_content = zf.read('word/document.xml')
        tree = ET.fromstring(xml_content)
        paragraphs = []
        for elem in tree.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag == 'p':
                texts = []
                for child in elem.iter():
                    c_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    if c_tag == 't' and child.text:
                        texts.append(child.text)
                line = "".join(texts).strip()
                if line:
                    paragraphs.append(line)
        return "\n".join(paragraphs)
    except Exception:
        # Fallback para archivos .doc antiguos
        try:
            text = file_bytes.decode('utf-8', errors='ignore')
            clean_lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 3]
            return "\n".join(clean_lines)
        except Exception:
            return ""


def extract_text_from_knowledge_file(uploaded_file) -> str:
    """
    Extrae y normaliza el contenido textual de un archivo PDF, Excel o Word
    para integrarlo al contexto del bot.
    """
    is_valid, _, ext = validate_knowledge_file(uploaded_file)
    if not is_valid:
        return ""

    uploaded_file.seek(0)
    file_bytes = uploaded_file.read()
    uploaded_file.seek(0)

    extracted = ""
    if ext == '.pdf':
        extracted = _extract_pdf_text(file_bytes)
    elif ext in ('.xlsx', '.xls'):
        extracted = _extract_excel_text(file_bytes)
    elif ext in ('.docx', '.doc'):
        extracted = _extract_docx_text(file_bytes)

    # Limpiar espacios múltiples y truncar de forma segura
    extracted = re.sub(r'\n{3,}', '\n\n', (extracted or '').strip())
    if len(extracted) > MAX_EXTRACTED_CHARS:
        extracted = extracted[:MAX_EXTRACTED_CHARS] + "..."

    return extracted
