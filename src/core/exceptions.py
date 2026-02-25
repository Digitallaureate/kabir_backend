from fastapi import HTTPException

class AppError(HTTPException):
    """Base for all app errors"""
    pass

# Data / Firestore
class DocumentNotFoundError(AppError):
    def __init__(self, doc_id: str | None = None, collection: str | None = None):
        msg = "Document not found"
        if doc_id and collection:
            msg = f"{collection} document with ID '{doc_id}' not found"
        super().__init__(status_code=404, detail=msg)

class FirestoreWriteError(AppError):
    def __init__(self, error: str = "Failed to write document"):
        super().__init__(status_code=500, detail=error)

# Auth
class AuthenticationError(AppError):
    def __init__(self, message: str = "Invalid or missing authentication"):
        super().__init__(status_code=401, detail=message)

class AuthorizationError(AppError):
    def __init__(self, message: str = "You are not authorized to perform this action"):
        super().__init__(status_code=403, detail=message)

# Validation / Business
class ValidationError(AppError):
    def __init__(self, message: str = "Invalid request data"):
        super().__init__(status_code=400, detail=message)
