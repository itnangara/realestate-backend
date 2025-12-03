"""
Script to create test properties for Landlord A and Landlord B
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.database import SessionLocal
from app.models.user import User
from app.models.property import Property, PropertyType, PropertyStatus, ListingType
from app.models.user_property import UserProperty, RelationshipType
from datetime import datetime

def create_properties():
    db = SessionLocal()
    try:
        # Get landlords
        landlord_a = db.query(User).filter(User.email == 'landlord-a@test.com').first()
        landlord_b = db.query(User).filter(User.email == 'landlord-b@test.com').first()
        
        if not landlord_a:
            print("ERROR: Landlord A not found")
            return
        if not landlord_b:
            print("ERROR: Landlord B not found")
            return
            
        print(f"Landlord A ID: {landlord_a.id}")
        print(f"Landlord B ID: {landlord_b.id}")
        
        # Create 4 properties for Landlord A
        properties_a = [
            {
                "title": "Landlord A Property 1",
                "city": "New York",
                "address": "123 Main St",
                "state": "NY",
                "zip_code": "10001",
                "rent_price": 1500,
                "bedrooms": 2,
                "bathrooms": 1,
            },
            {
                "title": "Landlord A Property 2",
                "city": "Los Angeles",
                "address": "456 Oak Ave",
                "state": "CA",
                "zip_code": "90001",
                "rent_price": 2000,
                "bedrooms": 3,
                "bathrooms": 2,
            },
            {
                "title": "Landlord A Property 3",
                "city": "Chicago",
                "address": "789 Elm St",
                "state": "IL",
                "zip_code": "60601",
                "rent_price": 1200,
                "bedrooms": 1,
                "bathrooms": 1,
            },
            {
                "title": "Landlord A Property 4",
                "city": "Houston",
                "address": "321 Pine Rd",
                "state": "TX",
                "zip_code": "77001",
                "rent_price": 1800,
                "bedrooms": 2,
                "bathrooms": 2,
            },
        ]
        
        # Create 7 properties for Landlord B
        properties_b = [
            {
                "title": "Landlord B Property 1",
                "city": "Miami",
                "address": "111 Beach Blvd",
                "state": "FL",
                "zip_code": "33101",
                "rent_price": 2500,
                "bedrooms": 3,
                "bathrooms": 2,
            },
            {
                "title": "Landlord B Property 2",
                "city": "Seattle",
                "address": "222 Rain St",
                "state": "WA",
                "zip_code": "98101",
                "rent_price": 2200,
                "bedrooms": 2,
                "bathrooms": 1,
            },
            {
                "title": "Landlord B Property 3",
                "city": "Boston",
                "address": "333 Harbor Ave",
                "state": "MA",
                "zip_code": "02101",
                "rent_price": 2800,
                "bedrooms": 4,
                "bathrooms": 3,
            },
            {
                "title": "Landlord B Property 4",
                "city": "Denver",
                "address": "444 Mountain Dr",
                "state": "CO",
                "zip_code": "80201",
                "rent_price": 1900,
                "bedrooms": 2,
                "bathrooms": 2,
            },
            {
                "title": "Landlord B Property 5",
                "city": "Phoenix",
                "address": "555 Desert Way",
                "state": "AZ",
                "zip_code": "85001",
                "rent_price": 1600,
                "bedrooms": 2,
                "bathrooms": 1,
            },
            {
                "title": "Landlord B Property 6",
                "city": "Atlanta",
                "address": "666 Peach St",
                "state": "GA",
                "zip_code": "30301",
                "rent_price": 1700,
                "bedrooms": 3,
                "bathrooms": 2,
            },
            {
                "title": "Landlord B Property 7",
                "city": "Portland",
                "address": "777 Forest Ln",
                "state": "OR",
                "zip_code": "97201",
                "rent_price": 2100,
                "bedrooms": 2,
                "bathrooms": 2,
            },
        ]
        
        # Create properties for Landlord A
        print("\nCreating properties for Landlord A...")
        for prop_data in properties_a:
            property = Property(
                title=prop_data["title"],
                description=f"Beautiful property in {prop_data['city']}",
                property_type=PropertyType.HOUSE,
                listing_type=ListingType.FOR_RENT,
                status=PropertyStatus.ACTIVE,
                address=prop_data["address"],
                city=prop_data["city"],
                state=prop_data["state"],
                zip_code=prop_data["zip_code"],
                country="USA",
                rent_price=prop_data["rent_price"],
                bedrooms=prop_data["bedrooms"],
                bathrooms=prop_data["bathrooms"],
                square_feet=1000 + (prop_data["bedrooms"] * 200),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(property)
            db.flush()
            
            # Create UserProperty link
            user_property = UserProperty(
                user_id=landlord_a.id,
                property_id=property.id,
                relationship_type=RelationshipType.LANDLORD,
                created_at=datetime.utcnow(),
            )
            db.add(user_property)
            print(f"  ✓ Created: {prop_data['title']} (ID: {property.id})")
        
        # Create properties for Landlord B
        print("\nCreating properties for Landlord B...")
        for prop_data in properties_b:
            property = Property(
                title=prop_data["title"],
                description=f"Beautiful property in {prop_data['city']}",
                property_type=PropertyType.HOUSE,
                listing_type=ListingType.FOR_RENT,
                status=PropertyStatus.ACTIVE,
                address=prop_data["address"],
                city=prop_data["city"],
                state=prop_data["state"],
                zip_code=prop_data["zip_code"],
                country="USA",
                rent_price=prop_data["rent_price"],
                bedrooms=prop_data["bedrooms"],
                bathrooms=prop_data["bathrooms"],
                square_feet=1000 + (prop_data["bedrooms"] * 200),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(property)
            db.flush()
            
            # Create UserProperty link
            user_property = UserProperty(
                user_id=landlord_b.id,
                property_id=property.id,
                relationship_type=RelationshipType.LANDLORD,
                created_at=datetime.utcnow(),
            )
            db.add(user_property)
            print(f"  ✓ Created: {prop_data['title']} (ID: {property.id})")
        
        db.commit()
        print("\n✅ Successfully created all properties!")
        print(f"   Landlord A: 4 properties")
        print(f"   Landlord B: 7 properties")
        
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    create_properties()

