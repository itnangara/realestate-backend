"""
Application service for business logic
"""

from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.application import Application
from app.schemas.application import ApplicationCreate, ApplicationUpdate

class ApplicationService:
    """Application service class"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_application_by_id(self, application_id: int) -> Optional[Application]:
        """Get application by ID"""
        return self.db.query(Application).filter(Application.id == application_id).first()
    
    def get_user_applications(self, user_id: int) -> List[Application]:
        """Get all applications for a user"""
        return self.db.query(Application).filter(
            Application.applicant_id == user_id,
            Application.is_active == True
        ).all()
    
    def get_property_applications(self, property_id: int) -> List[Application]:
        """Get all applications for a property"""
        return self.db.query(Application).filter(
            Application.property_id == property_id,
            Application.is_active == True
        ).all()
    
    def create_application(self, application_data: ApplicationCreate, user_id: int) -> Application:
        """Create a new application"""
        # Create application object
        application = Application(
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
            applicant_id=user_id
        )
        
        # Add to database
        self.db.add(application)
        self.db.commit()
        self.db.refresh(application)
        
        return application
    
    def update_application(self, application_id: int, application_data: ApplicationUpdate) -> Optional[Application]:
        """Update an application"""
        application = self.get_application_by_id(application_id)
        if not application:
            return None
        
        # Update fields
        update_data = application_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(application, field, value)
        
        self.db.commit()
        self.db.refresh(application)
        
        return application
    
    def delete_application(self, application_id: int) -> bool:
        """Soft delete an application"""
        application = self.get_application_by_id(application_id)
        if not application:
            return False
        
        application.is_active = False
        self.db.commit()
        return True
    
    def get_applications_by_status(self, status: str) -> List[Application]:
        """Get applications by status"""
        return self.db.query(Application).filter(
            Application.status == status,
            Application.is_active == True
        ).all()


