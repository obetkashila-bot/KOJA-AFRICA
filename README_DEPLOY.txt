KOJA AFRICA — COMPLETE LATEST PACKAGE
Date: 2026-09-03

FIXES INCLUDED
1. Driver registration endpoint restored:
   /driver/register
2. Driver dashboard /driver can now redirect to driver_register safely.
3. Professional services registration and directory included.
4. /services no longer references missing doctor_register or tutor_register endpoints.
5. Universal professional profiles support many professions and admin approval.
6. Sender/receiver live GPS screens and participant-location APIs included.
7. Owner/admin live GPS and delivery tracking included.
8. Research Engine, citations, AI integration, SEO/Search Console features from the latest package included.

DEPLOY TO RENDER
1. Replace the GitHub app.py with this package's app.py.
2. Keep requirements.txt and Procfile.
3. Commit and push to the GitHub repository connected to Render.
4. Wait for Render to finish deploying.
5. Test:
   https://koja-africa.onrender.com/health
   https://koja-africa.onrender.com/services
   https://koja-africa.onrender.com/driver
   https://koja-africa.onrender.com/driver/register

DATABASE
Run KOJA_AFRICA_DATABASE.sql in Supabase SQL Editor if its latest tables/columns have not already been applied.
Do not delete existing production data just to apply this package.

NEW PROFESSIONAL SERVICES FEATURES (2026-09-03)
- All-profession registration: Lawyer, Accountant, Engineer, Architect, ICT/Developer, Designer, Consultant, Counsellor, Nurse, Pharmacist, Dentist, Nutritionist, Physiotherapist, Real Estate, Insurance, Financial Adviser, Teacher/Tutor, Doctor, Electrician, Plumber, Mechanic, Builder, Carpenter, Welder, Tailor, Beauty, Photographer, Writer/Editor/Translator, Marketing, Business Consultant and Other.
- Professional directory search by profession, name, qualification, service and service area.
- Professional profiles are visible in the directory only after approval.
- Each approved professional has buttons for Book, Ask Advice, Counselling, Chat, Voice Call and Video Call.
- Professional chat uses the KOJA database and refreshes messages automatically.
- Voice/video calls use browser WebRTC signaling. Users must allow microphone/camera permissions and both sides must keep the call page open.
- Run the updated KOJA_AFRICA_DATABASE.sql in Supabase to create professional_messages and professional_calls.
- If the database already has the tables, CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS will leave them in place.
