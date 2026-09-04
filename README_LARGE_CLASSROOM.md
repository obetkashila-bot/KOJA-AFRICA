# KOJA AFRICA — Large Classroom / LiveKit SFU

The KOJA Live Classroom uses LiveKit SFU for scalable media instead of a peer-to-peer mesh.

## Render environment variables
LIVEKIT_URL=wss://YOUR-PROJECT.livekit.cloud
LIVEKIT_API_KEY=YOUR_API_KEY
LIVEKIT_API_SECRET=YOUR_API_SECRET
KOJA_LIVE_MAX_PARTICIPANTS=500

Keep the API secret only in Render environment variables. Never put it in browser code.

## Supabase
Run `teacher_large_classroom.sql` in Supabase SQL Editor.

## Included
- Teacher host mode
- Student viewer/listener mode by default
- Teacher camera, microphone and screen sharing
- Student raise hand
- Approve student to speak / return to viewer
- Teacher mute audio and remove participant
- Lower-hand moderation
- Participant list and live status
- Class chat, Q&A-style messages and teacher announcements
- Attendance records with join/leave times
- LiveKit room capacity enforcement
- Protected class access: teacher or a student with a matching teacher booking
- Automatic LiveKit reconnect handling in the browser
- Mobile-responsive classroom UI
- Explicit LiveKit room creation/deletion

A configured LiveKit Cloud or correctly provisioned self-hosted LiveKit deployment is required. Render hosts the KOJA Flask application; it is not the SFU itself.
