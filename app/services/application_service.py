"""
Application service for business logic
"""

from sqlalchemy.orm import Session
from typing import List, Optional
import json
from app.models.application import Application
from app.schemas.application import ApplicationCreate, ApplicationUpdate

class ApplicationService:
    """Application service class"""
    
    def __init__(self, db: Session):
        self.db = db

    def _normalize_documents_urls(self, app: Application) -> Application:
        """Ensure documents_urls is always a Python list"""
        if isinstance(app.documents_urls, str):
            try:
                app.documents_urls = json.loads(app.documents_urls)
            except json.JSONDecodeError:
                app.documents_urls = []
        elif app.documents_urls is None:
            app.documents_urls = []
        return app

    def get_application_by_id(self, application_id: int) -> Optional[Application]:
        app = self.db.query(Application).filter(Application.id == application_id).first()
        if app:
            app = self._normalize_documents_urls(app)
        return app

    def get_user_applications(self, user_id: int) -> List[Application]:
        apps = self.db.query(Application).filter(
            Application.applicant_id == user_id,
            Application.is_active == True
        ).all()
        return [self._normalize_documents_urls(a) for a in apps]

    def create_application(self, application_data: ApplicationCreate, user_id: int) -> Application:
        app = Application(
            property_id=application_data.property_id,
            message=application_data.message,
            move_in_date=application_data.move_in_date,
            lease_duration=application_data.lease_duration,
            annual_income=application_data.annual_income,
            credit_score=application_data.credit_score,
            employment_status=application_data.employment_status,
            employer_name=application_data.employer_name,
            phone=application_data.phone,
            alternate_email=application_data.alternate_email,
            documents_urls=application_data.documents_urls,
            applicant_id=user_id
        )
        self.db.add(app)
        self.db.commit()
        self.db.refresh(app)
        return self._normalize_documents_urls(app)

    def update_application(self, application_id: int, application_data: ApplicationUpdate) -> Optional[Application]:
        app = self.get_application_by_id(application_id)
        if not app:
            return None
        update_data = application_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(app, field, value)
        self.db.commit()
        self.db.refresh(app)
        return self._normalize_documents_urls(app)

    def delete_application(self, application_id: int) -> bool:
        app = self.get_application_by_id(application_id)
        if not app:
            return False
        app.is_active = False
        self.db.commit()
        return True
