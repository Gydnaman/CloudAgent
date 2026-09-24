from fastapi import HTTPException


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, run_id: str | None = None):
        detail = {"code": code, "message": message}
        if run_id:
            detail["run_id"] = run_id
        super().__init__(status_code=status_code, detail=detail)
