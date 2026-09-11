import os, smtplib, importlib.util, importlib.machinery
from email.message import EmailMessage
from flask import request, jsonify, render_template_string

_loader = importlib.machinery.SourcelessFileLoader('koja_base_app', os.path.join(os.path.dirname(__file__), 'app_base.pyc'))
spec = importlib.util.spec_from_loader(_loader.name, _loader)
base = importlib.util.module_from_spec(spec)
_loader.exec_module(base)
app = base.app


def _contact(uid):
    try:
        u = base.find_user_by_id(uid) or {}
    except Exception:
        u = {}
    return u


def _send_email(uid, title, body):
    try:
        u=_contact(uid); to=str(u.get('email') or '').strip()
        host=os.getenv('SMTP_HOST','').strip(); port=int(os.getenv('SMTP_PORT','587') or 587)
        user=os.getenv('SMTP_USERNAME','').strip(); password=os.getenv('SMTP_PASSWORD','')
        sender=os.getenv('SMTP_FROM',user or 'notifications@koja-africa.com').strip()
        if not to or not host: return False
        msg=EmailMessage(); msg['Subject']=f'KOJA: {title}'; msg['From']=sender; msg['To']=to
        url=os.getenv('APP_BASE_URL','https://koja-africa.onrender.com').rstrip('/') + '/notifications'
        msg.set_content(f'{title}\n\n{body}\n\nOpen KOJA: {url}')
        with smtplib.SMTP(host,port,timeout=12) as smtp:
            if os.getenv('SMTP_TLS','true').lower()!='false': smtp.starttls()
            if user and password: smtp.login(user,password)
            smtp.send_message(msg)
        return True
    except Exception:
        return False


def _send_sms(uid, title, body):
    try:
        u=_contact(uid); phone=str(u.get('phone') or u.get('phone_number') or u.get('mobile') or '').strip()
        if not phone: return False
        text=f'KOJA: {title} - {body}'[:480]
        at_user=os.getenv('AT_USERNAME','').strip(); at_key=os.getenv('AT_API_KEY','').strip(); at_sender=os.getenv('AT_SENDER_ID','').strip()
        if at_user and at_key:
            r=base.requests.post('https://api.africastalking.com/version1/messaging',headers={'apiKey':at_key,'Accept':'application/json'},data={'username':at_user,'to':phone,'message':text,**({'from':at_sender} if at_sender else {})},timeout=15)
            return r.ok
        sid=os.getenv('TWILIO_ACCOUNT_SID','').strip(); token=os.getenv('TWILIO_AUTH_TOKEN','').strip(); frm=os.getenv('TWILIO_FROM_NUMBER','').strip()
        if sid and token and frm:
            r=base.requests.post(f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',auth=(sid,token),data={'From':frm,'To':phone,'Body':text},timeout=15)
            return r.ok
    except Exception:
        return False
    return False


def notify_user(uid,title,body,notification_type='system',related_id=None,url=None):
    if not uid or not base._notification_allowed(uid,notification_type): return None
    row,err=base.db_insert('koja_notifications',{'user_id':str(uid),'notification_type':notification_type,'title':title,'body':body,'related_id':related_id,'is_read':False,'created_at':base.utc_now()})
    if err or not row: return None
    p=base.first_row('koja_notification_preferences',{'user_id':str(uid)}) or {}
    if p.get('push_enabled',True): base._send_web_push(uid,title,body,url,notification_type)
    if p.get('email_enabled',True): _send_email(uid,title,body)
    if p.get('sms_enabled',True): _send_sms(uid,title,body)
    return row

base.notify_user = notify_user

@app.route('/api/notifications/contact-status')
@base.login_required
def notification_contact_status():
    uid=str(base.current_user()['id']); u=_contact(uid); p=base.first_row('koja_notification_preferences',{'user_id':uid}) or {}
    return jsonify(email=bool(u.get('email')),phone=bool(u.get('phone') or u.get('phone_number') or u.get('mobile')),email_enabled=bool(p.get('email_enabled',True)),sms_enabled=bool(p.get('sms_enabled',True)))

@app.route('/notification-settings', endpoint='notification_settings_v2')
@base.login_required
def notification_settings_v2():
    uid=str(base.current_user()['id']); p=base.first_row('koja_notification_preferences',{'user_id':uid}) or {}; u=_contact(uid)
    return base.render_page('Notification Settings', """
    <div class='card'><h2>Notification Settings</h2><p>Choose how KOJA contacts you about important activity.</p>
    <p class='small'>Email: {{ email or 'Not set' }}<br>Phone: {{ phone or 'Not set' }}</p>
    <form id='np'>
    <label><input type='checkbox' name='push_enabled' {% if p.get('push_enabled',True) %}checked{% endif %}> Phone/browser push notifications</label>
    <label><input type='checkbox' name='email_enabled' {% if p.get('email_enabled',True) %}checked{% endif %}> Email notifications</label>
    <label><input type='checkbox' name='sms_enabled' {% if p.get('sms_enabled',True) %}checked{% endif %}> SMS notifications</label>
    <label><input type='checkbox' name='sound_enabled' {% if p.get('sound_enabled',True) %}checked{% endif %}> Notification sound</label>
    <label><input type='checkbox' name='market_enabled' {% if p.get('market_enabled',True) %}checked{% endif %}> Market and orders</label>
    <label><input type='checkbox' name='delivery_enabled' {% if p.get('delivery_enabled',True) %}checked{% endif %}> Deliveries and drivers</label>
    <label><input type='checkbox' name='ai_enabled' {% if p.get('ai_enabled',True) %}checked{% endif %}> KOJA AI</label>
    <label><input type='checkbox' name='messages_enabled' {% if p.get('messages_enabled',True) %}checked{% endif %}> Messages and calls</label>
    <label><input type='checkbox' name='system_enabled' {% if p.get('system_enabled',True) %}checked{% endif %}> System and account</label>
    <button class='btn' type='submit'>Save settings</button></form><p id='status' class='small'></p>
    <hr><button class='btn secondary' type='button' onclick='enableKOJAPush()'>Enable phone/browser notifications</button></div>
    <script>
    const form=document.getElementById('np');form.onsubmit=async e=>{e.preventDefault();let o={};new FormData(form).forEach((v,k)=>o[k]=true);let r=await fetch('/api/notifications/preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o)});document.getElementById('status').textContent=r.ok?'Saved.':'Could not save settings.'};
    async function enableKOJAPush(){if(!('Notification'in window)){status.textContent='This browser does not support notifications.';return}let perm=await Notification.requestPermission();if(perm!=='granted'){status.textContent='Permission was not granted.';return}if(!('serviceWorker'in navigator)){status.textContent='Service workers are not supported.';return}let reg=await navigator.serviceWorker.register('/koja-sw.js');let key=await fetch('/api/notifications/vapid-public-key').then(r=>r.text());if(!key){status.textContent='Push service is not configured yet.';return}let sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:base64ToUint8(key)});await fetch('/api/notifications/subscribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(sub)});status.textContent='Phone/browser notifications enabled.'}function base64ToUint8(b){let p='='.repeat((4-b.length%4)%4),s=atob((b+p).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from([...s].map(c=>c.charCodeAt(0)))}
    </script>""",p=p,email=u.get('email') or '',phone=u.get('phone') or u.get('phone_number') or u.get('mobile') or '')

# Replace the existing view function used by the original endpoint.
app.view_functions['notification_settings'] = notification_settings_v2
