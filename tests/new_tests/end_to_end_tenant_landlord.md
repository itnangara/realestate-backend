✅ REALISTIC END-TO-END TEST PLAN
Covers 2 landlords, onboarding, approval, properties, tenants, applications, maintenance.

This is written for someone with zero IT knowledge.
They just follow steps like a script.

⭐ PHASE 1 — CREATE ACCOUNTS
Step 1: Create Landlord Account A

Open the app.

Click Create Account / Register.

Choose Landlord.

Fill in:

First name

Last name

Email

Password

Expected:

Account is created.

You are guided into onboarding.

Step 2: Complete Onboarding for Landlord A

Fill in required landlord fields (business info, KYC, whatever is needed).

Submit.

Expected:

You see “Waiting for approval” or similar.

You cannot access landlord features until approval.

Step 3: Create Landlord Account B

Repeat the exact same steps for a second landlord.

Expected:

Account B also enters “Pending approval.”

⭐ PHASE 2 — ADMIN APPROVAL
Step 4: Log in as Admin

Admin logs in to admin dashboard.

Opens Pending Landlords.

Expected:

Both Landlord A and Landlord B appear in the list.

Step 5: Approve both Landlords

Approve Landlord A.

Approve Landlord B.

Expected:

Status changes to “Approved.”

Both can now log in fully.

⭐ PHASE 3 — LANDLORD JOURNEYS
Step 6: Landlord A logs in

Landlord A signs in after approval.

Expected:

They land on the landlord dashboard.

Currently 0 properties.

Step 7: Landlord B logs in

Same as above.

Expected:

Landlord B also sees 0 properties.

⭐ PHASE 4 — CREATE PROPERTIES
Step 8: Landlord A creates 4 properties

For each property:

Click Add Property.

Fill in simple details.

Save.

Do this 4 times.

Expected:

Landlord A sees 4 properties.

Landlord B sees 0 properties.

Landlord A can edit/delete their own 4 properties.

Landlord B should NOT see any of them.

Step 9: Landlord B creates 7 properties

Same process, but Landlord B creates 7 properties.

Expected:

Landlord B sees 7 properties.

Landlord A sees only their own 4.

No mixing of property lists.

🔍 Critical test:
Switch back and forth between accounts and ensure they never see each other’s properties.

⭐ PHASE 5 — TENANTS & APPLICATIONS
Step 10: Register Tenant Accounts

Create 2 tenants:

Tenant X

Tenant Y

Both complete onboarding.

Expected:

They can browse available properties (if that’s in your system).

Step 11: Tenant X applies to 2 properties (owned by Landlord A)

Tenant X:

Opens property list.

Selects 2 of the 4 that belong to Landlord A.

Submits applications.

Expected:

Applications succeed.

In Landlord A dashboard → Applications tab → shows exactly 2 applications.

In Landlord B dashboard → Applications tab → shows 0.

Step 12: Tenant Y applies to 3 properties (owned by Landlord B)

Same flow:

Tenant Y chooses 3 of the 7 properties owned by Landlord B.

Applies.

Expected:

Landlord B sees 3 applications.

Landlord A sees none.

⭐ PHASE 6 — LEASE CREATION
Step 13: Landlord A accepts 1 application from Tenant X

Flow:

Landlord A → Applications

Open one of Tenant X’s applications

Click Accept → create lease

Expected:

A lease is created.

Landlord A sees 1 active lease.

Tenant X sees 1 active lease.

Landlord B sees 0 leases.

Step 14: Landlord B accepts 2 applications from Tenant Y

Same process.

Expected:

Landlord B: sees 2 active leases.

Tenant Y: sees 2 active leases.

No crossover.

⭐ PHASE 7 — MAINTENANCE REQUESTS
Step 15: Tenants file maintenance requests

Tenant X:

Files 1 request for their property (owned by Landlord A)

Tenant Y:

Files 2 requests for their two properties (owned by Landlord B)

Expected:

Landlord A → sees 1 request.

Landlord B → sees 2 requests.

No mixing.

Step 16: Landlords update maintenance

Landlord A:

Updates request to “In Progress.”

Landlord B:

Updates one to “Resolved.”

Expected:

Status updates correctly.

Tenants see updated status.

No permission errors.

⭐ PHASE 8 — PERMISSION TESTING
Step 17: Try to access things from the wrong account

Have Landlord A try to open:

Property from B

Application from B

Lease from B

Maintenance from B

Expected:

“Not authorized” or redirect

No crashes

No data leak

And vice versa for Landlord B.

⭐ PHASE 9 — QUICK SAFETY TESTS
Refresh pages

Everything should reload correctly.

Fast switching

Going from tenants → leases → property details shouldn’t cause errors.

Deleting property

Landlord should only delete their properties.