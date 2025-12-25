# E:\cla-rule-extractor\apps\api\src\validators\pdf_validator.py
import os
import magic  # You'll need to install python-magic-bin for Windows
from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError


class PDFValidator:
    """Handles PDF validation and password detection"""

    @staticmethod
    def validate_pdf(file_path):
        """
        Validates if a file is a valid PDF and checks for password protection

        Args:
            file_path (str): Path to the PDF file

        Returns:
            dict: Validation result with status and details
        """
        validation_result = {
            'is_valid': False,
            'is_password_protected': False,
            'error_message': None,
            'page_count': 0,
            'file_size': 0,
            'file_type': None
        }

        # Check 1: File exists
        if not os.path.exists(file_path):
            validation_result['error_message'] = "❌ File not found. Please check the file path."
            return validation_result

        # Check 2: File is not empty
        file_size = os.path.getsize(file_path)
        validation_result['file_size'] = file_size

        if file_size == 0:
            validation_result['error_message'] = "❌ The file is empty. Please upload a valid PDF."
            return validation_result

        # Check 3: File extension check
        if not file_path.lower().endswith('.pdf'):
            validation_result['error_message'] = (
                "❌ Invalid file extension. Please upload a file with .pdf extension."
            )
            return validation_result

        # Check 4: File signature (magic bytes) check
        try:
            import magic
            mime = magic.Magic(mime=True)
            file_type = mime.from_file(file_path)
            validation_result['file_type'] = file_type

            if file_type != 'application/pdf':
                validation_result['error_message'] = (
                    f"❌ Invalid file type: {file_type}. "
                    "The file appears to be a {file_type.split('/')[-1].upper()} file, not a PDF."
                )
                return validation_result
        except ImportError:
            # Fallback: check first bytes manually
            with open(file_path, 'rb') as f:
                header = f.read(4)
                if header != b'%PDF':
                    validation_result['error_message'] = (
                        "❌ Invalid PDF file signature. "
                        "The file does not start with PDF header bytes."
                    )
                    return validation_result

        # Check 5: PDF structure validation
        try:
            with open(file_path, 'rb') as file:
                reader = PdfReader(file)

                # Try to access metadata
                try:
                    _ = reader.metadata
                    validation_result['is_password_protected'] = False
                    validation_result['page_count'] = len(reader.pages)
                    validation_result['is_valid'] = True

                except Exception as e:
                    error_msg = str(e).lower()
                    if "password" in error_msg or "encrypted" in error_msg:
                        validation_result['is_password_protected'] = True
                        validation_result['error_message'] = (
                            "🔒 This PDF is password protected. "
                            "Please enter the password to continue."
                        )
                    else:
                        validation_result['error_message'] = (
                            f"❌ PDF appears to be corrupted: {str(e)}"
                        )

        except PdfReadError as e:
            validation_result['error_message'] = (
                f"❌ Invalid PDF structure: {str(e)}. "
                "This might be a corrupted PDF file."
            )
        except Exception as e:
            validation_result['error_message'] = (
                f"❌ Error reading PDF: {str(e)}"
            )

        return validation_result

    @staticmethod
    def try_password(file_path, password):
        """
        Attempt to open a password-protected PDF

        Args:
            file_path (str): Path to the PDF file
            password (str): Password to try

        Returns:
            dict: Result with status and details
        """
        result = {
            'success': False,
            'error_message': None,
            'page_count': 0
        }

        try:
            with open(file_path, 'rb') as file:
                reader = PdfReader(file)

                if reader.is_encrypted:
                    if reader.decrypt(password):
                        result['success'] = True
                        result['page_count'] = len(reader.pages)
                    else:
                        result['error_message'] = "❌ Incorrect password. Please try again."
                else:
                    result['error_message'] = "⚠️ This PDF is not password protected."

        except Exception as e:
            result['error_message'] = f"❌ Error: {str(e)}"

        return result


def validate_pdf_file(file_path):
    """
    Convenience function for quick PDF validation

    Args:
        file_path (str): Path to the PDF file

    Returns:
        tuple: (is_valid, message, details)
    """
    result = PDFValidator.validate_pdf(file_path)

    if result['is_valid']:
        return True, f"✅ Valid PDF ({result['page_count']} pages)", result
    elif result['is_password_protected']:
        return False, result['error_message'], result
    else:
        return False, result['error_message'], result
