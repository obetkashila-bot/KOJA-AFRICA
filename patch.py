from pathlib import Path
p=Path('/mnt/data/koja_v39/KOJA_AFRICA_V39_BASE.py')
s=p.read_text()
s=s.replace('APP_VERSION = "2026.09.03-RESEARCH-V2"','APP_VERSION = "2026.09.05-V39-COMMUNICATIONS"')
# Add group call tables to connect SQL
needle="""create index if not exists koja_calls_caller_idx on public.koja_calls(caller_id,status,created_at desc);\n"""
insert=needle+"""create table if not exists public.koja_group_call_participants (\n call_id uuid not null references public.koja_calls(id) on delete cascade,\n user_id uuid not null, status text not null default 'invited', joined_at timestamptz, primary key(call_id,user_id)\n);\ncreate index if not exists koja_group_call_participants_user_idx on public.koja_group_call_participants(user_id,status);\n"""
s=s.replace(needle,insert)
# Replace connect page with richer group controls
old="""<div class=\"card\"><h3>Recent Chats</h3>{% for c in conversations %}<a class=\"card\" style=\"display:block;text-decoration:none;color:inherit\" href=\"{{ url_for('connect_chat',conversation_id=c.id) }}\"><strong>{{ c._other_name }}</strong><div class=\"small\">{{ c._last }}</div></a>{% else %}<p>No chats yet. Find a KOJA user to start.</p>{% endfor %}</div>"""
new="""<div class=\"card\"><div class=\"actions\"><h3 style=\"margin-right:auto\">Recent Chats</h3><a class=\"btn\" href=\"{{ url_for('connect_group_new') }}\">➕ New Group</a></div>{% for c in conversations %}<a class=\"card\" style=\"display:block;text-decoration:none;color:inherit\" href=\"{{ url_for('connect_chat',conversation_id=c.id) }}\"><strong>{{ c._other_name }}</strong><div class=\"small\">{{ c._last }}</div></a>{% else %}<p>No chats yet. Find a KOJA user to start.</p>{% endfor %}</div>"""
s=s.replace(old,new)
# Replace chat HTML script area with aligned bubbles, attachments, group calls
start="""return render_page('KOJA Chat',r'''"""
idx=s.index(start, s.index("def connect_chat"))
end_marker="""''',conversation_id=conversation_id,name=_profile_name(other_id) if other_id else c.get('name','KOJA Chat'))"""
end=s.index(end_marker,idx)+len(end_marker)
replacement="""return render_page('KOJA Chat',r'''<div class=\"card\"><a href=\"{{ url_for('connect') }}\">← Connect</a><h2>💬 {{ name }}</h2><p class=\"small\">Sent messages appear on the right. Received messages appear on the left.</p></div><div class=\"card\" id=\"messages\" style=\"min-height:300px;max-height:55vh;overflow:auto\"></div><div class=\"card\"><form id=\"sendForm\"><input id=\"text\" autocomplete=\"off\" placeholder=\"Write a message…\"><button>Send</button></form><form id=\"fileForm\" enctype=\"multipart/form-data\" style=\"margin-top:8px\"><input id=\"file\" type=\"file\" accept=\"image/*,.pdf,.doc,.docx,.txt,.webp,.audio/*\"><button type=\"submit\">📎 Photo / File</button></form><div class=\"grid\"><button type=\"button\" id=\"voiceNote\">🎙️ Voice message</button><a class=\"btn\" href=\"{{ url_for('connect_call',user_id=other_id,mode='voice') }}\">📞 Voice Call</a><a class=\"btn\" href=\"{{ url_for('connect_call',user_id=other_id,mode='video') }}\">🎥 Video Call</a>{% if c.get('conversation_type')=='group' %}<a class=\"btn\" href=\"{{ url_for('connect_group_call',conversation_id=conversation_id,mode='video') }}\">👥 Group Video</a><a class=\"btn secondary\" href=\"{{ url_for('connect_group_call',conversation_id=conversation_id,mode='voice') }}\">👥 Group Voice</a>{% endif %}</div></div><script>const cid={{ conversation_id|tojson }},me={{ user.id|tojson }};const box=document.getElementById('messages');const text=document.getElementById('text');function esc(v){return String(v??'').replace(/[&<>\\\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\\\"':'&quot;',"'":'&#39;'}[c]));}async function load(){let r=await fetch('/api/connect/messages/'+cid);if(!r.ok)return;let d=await r.json();box.innerHTML=d.messages.map(m=>{let mine=String(m.sender_id)===String(me);let body=m.message_type==='text'?'<div>'+esc(m.body)+'</div>':(m.file_url?'<div><a target=\"_blank\" rel=\"noopener\" href=\"'+esc(m.file_url)+'\">'+esc(m.body||m.message_type)+'</a></div>':'<div>'+esc(m.body)+'</div>');return '<div style=\"display:flex;justify-content:'+(mine?'flex-end':'flex-start')+';margin:7px 0\"><div style=\"max-width:78%;padding:10px 13px;border-radius:16px;background:var(--card);border:1px solid var(--border);text-align:left\"><strong>'+esc(mine?'You':m.sender_name)+'</strong>'+body+'<div class=\"small\">'+esc(m.created_at||'')+'</div></div></div>'}).join('');box.scrollTop=box.scrollHeight;}document.getElementById('sendForm').onsubmit=async e=>{e.preventDefault();let v=text.value.trim();if(!v)return;let r=await fetch('/api/connect/messages/'+cid,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:v})});if(r.ok){text.value='';load();}};document.getElementById('fileForm').onsubmit=async e=>{e.preventDefault();let f=document.getElementById('file').files[0];if(!f)return;let fd=new FormData();fd.append('file',f);let r=await fetch('/api/connect/messages/'+cid+'/upload',{method:'POST',body:fd});if(r.ok){document.getElementById('file').value='';load();}else alert('File could not be sent.');};load();setInterval(load,2000);let rec,parts=[];document.getElementById('voiceNote').onclick=async()=>{try{let st=await navigator.mediaDevices.getUserMedia({audio:true});rec=new MediaRecorder(st);parts=[];rec.ondataavailable=e=>parts.push(e.data);rec.onstop=async()=>{let b=new Blob(parts,{type:'audio/webm'});let fd=new FormData();fd.append('file',b,'voice.webm');await fetch('/api/connect/messages/'+cid+'/upload',{method:'POST',body:fd});st.getTracks().forEach(t=>t.stop());load();};rec.start();setTimeout(()=>rec&&rec.state==='recording'&&rec.stop(),60000);}catch(e){alert('Microphone permission is required.');}};</script>''',conversation_id=conversation_id,name=_profile_name(other_id) if other_id else c.get('name','KOJA Chat'))"""
s=s[:idx]+replacement+s[end:]
# Replace upload function to accept images/files/audio
old_start=s.index("@app.route('/api/connect/messages/<conversation_id>/upload'")
old_end=s.index("@app.route('/connect/status'",old_start)
new_upload="""@app.route('/api/connect/messages/<conversation_id>/upload',methods=['POST'])\n@login_required\ndef connect_upload(conversation_id):\n    uid=current_user()['id']\n    if not _conversation_member(conversation_id,uid):return jsonify(error='Forbidden'),403\n    f=request.files.get('file')\n    if not f or not f.filename:return jsonify(error='No file'),400\n    data=f.read()\n    if len(data)>15*1024*1024:return jsonify(error='File too large (15 MB maximum)'),413\n    name=secure_filename(f.filename) or ('upload-'+uuid.uuid4().hex)\n    ext=os.path.splitext(name)[1].lower()\n    allowed={'.webm','.wav','.mp3','.m4a','.ogg','.jpg','.jpeg','.png','.webp','.pdf','.doc','.docx','.txt'}\n    if ext not in allowed:return jsonify(error='Unsupported file type'),400\n    mime=f.mimetype or 'application/octet-stream'\n    path=f'connect/files/{uuid.uuid4().hex}{ext}'\n    r=requests.post(sb_storage_url(path),headers=sb_headers({'Content-Type':mime,'x-upsert':'true'}),data=data,timeout=60)\n    if not r.ok:return jsonify(error=r.text[:500]),500\n    mt='audio' if mime.startswith('audio/') else ('image' if mime.startswith('image/') else 'file')\n    row,err=db_insert('koja_messages',{'id':str(uuid.uuid4()),'conversation_id':conversation_id,'sender_id':uid,'message_type':mt,'file_url':sb_storage_url(path),'body':name if mt=='file' else ('Voice message' if mt=='audio' else name),'created_at':utc_now()})\n    return jsonify(message=row) if not err else (jsonify(error=err),500)\n\n"""
s=s[:old_start]+new_upload+s[old_end:]
# Add group routes before status
marker="@app.route('/connect/status',methods=['GET','POST'])"
group_routes=r'''@app.route('/connect/group/new',methods=['GET','POST'])
@login_required
def connect_group_new():
    uid=current_user()['id']
    if request.method=='POST':
        name=clean(request.form.get('name')) or 'KOJA Group'
        ids=[x for x in request.form.getlist('user_id') if x and x!=uid]
        ids=list(dict.fromkeys(ids))
        if not ids:return redirect(url_for('connect_group_new'))
        c,err=db_insert('koja_conversations',{'id':str(uuid.uuid4()),'conversation_type':'group','created_by':uid,'name':name,'created_at':utc_now(),'updated_at':utc_now()})
        if err:return 'Could not create group: '+str(err),500
        cid=c['id']
        for member in [uid]+ids:
            if find_user_by_id(member):db_insert('koja_conversation_members',{'conversation_id':cid,'user_id':member,'role':'admin' if member==uid else 'member','joined_at':utc_now()})
        return redirect(url_for('connect_chat',conversation_id=cid))
    q=clean(request.args.get('q')); people=[]
    if q:
        for col in ('email','full_name','name'):
            for x in db_select('profiles',filters={col:f'ilike.*{q}*'},limit=30):
                if str(x.get('id'))!=str(uid) and not any(str(p.get('id'))==str(x.get('id')) for p in people):people.append(x)
    return render_page('New KOJA Group',r'''<div class="card"><h2>👥 Create KOJA Group</h2><form method="get"><input name="q" value="{{ q }}" placeholder="Search people"><button>Search</button></form><form method="post"><input name="name" placeholder="Group name" required>{% for p in people %}<label style="display:block;margin:10px 0"><input type="checkbox" name="user_id" value="{{ p.id }}"> {{ p.get('full_name') or p.get('name') or p.get('email') }}</label>{% endfor %}<button class="btn">Create Group</button></form></div>''',people=people,q=q)

@app.route('/connect/group-call/<conversation_id>')
@login_required
def connect_group_call(conversation_id):
    uid=current_user()['id']; mode=clean(request.args.get('mode','video'))
    if mode not in ('voice','video') or not _conversation_member(conversation_id,uid):abort(403)
    members=db_select('koja_conversation_members',filters={'conversation_id':conversation_id},limit=50)
    others=[m.get('user_id') for m in members if str(m.get('user_id'))!=str(uid)]
    return render_page('KOJA Group Call',r'''<div class="card"><h2>👥 KOJA Group {{ mode|title }} Call</h2><p>Group call room. Select Start to invite all group members.</p><div id="state">Ready</div><button id="start" class="btn">Start Group Call</button><button id="hang" class="btn danger">End</button><div id="peers"></div></div><script>const cid={{ conversation_id|tojson }},mode={{ mode|tojson }};let calls=[];document.getElementById('start').onclick=async()=>{let r=await fetch('/api/connect/group-call/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:cid,mode})});let d=await r.json();if(!r.ok){state.textContent=d.error||'Could not start group call';return}calls=d.calls||[];state.textContent='Invited '+calls.length+' participant(s). Each participant receives an incoming call.';};document.getElementById('hang').onclick=async()=>{for(const c of calls)await fetch('/api/connect/call/end/'+c.id,{method:'POST'});state.textContent='Group call ended';};</script>''',conversation_id=conversation_id,mode=mode)

@app.route('/api/connect/group-call/create',methods=['POST'])
@login_required
def connect_group_call_create():
    uid=current_user()['id']; d=request.get_json(silent=True) or {}; cid=clean(d.get('conversation_id')); mode=d.get('mode','video')
    if mode not in ('voice','video') or not _conversation_member(cid,uid):return jsonify(error='Forbidden'),403
    members=db_select('koja_conversation_members',filters={'conversation_id':cid},limit=50); calls=[]
    for m in members:
        callee=m.get('user_id')
        if not callee or str(callee)==str(uid):continue
        row,err=db_insert('koja_calls',{'id':str(uuid.uuid4()),'conversation_id':cid,'caller_id':uid,'callee_id':callee,'mode':mode,'status':'ringing','created_at':utc_now()})
        if not err and row:
            db_insert('koja_group_call_participants',{'call_id':row['id'],'user_id':callee,'status':'invited'})
            db_insert('koja_notifications',{'user_id':callee,'notification_type':'group_call','title':f'Incoming group {mode} call','body':f'{_profile_name(uid)} started a group call.','related_id':row['id']});calls.append(row)
    return jsonify(calls=calls)

'''
s=s.replace(marker,group_routes+marker)
# status media upload: add separate endpoint and link in UI
s=s.replace("<form method=\"post\"><textarea name=\"text\" maxlength=\"1000\" placeholder=\"Share an update…\"></textarea><button>Post Status</button></form>","<form method=\"post\"><textarea name=\"text\" maxlength=\"1000\" placeholder=\"Share an update…\"></textarea><button>Post Status</button></form><form method=\"post\" enctype=\"multipart/form-data\" action=\"{{ url_for('connect_status_media') }}\"><input type=\"file\" name=\"file\" accept=\"image/*,video/*\"><button>📷 Photo / Video Status</button></form>")
# insert media status endpoint
marker2="@app.route('/connect/answer/<call_id>')"
media_route=r'''@app.route('/connect/status/media',methods=['POST'])
@login_required
def connect_status_media():
    uid=current_user()['id']; f=request.files.get('file')
    if not f or not f.filename:return redirect(url_for('connect_status'))
    data=f.read()
    if len(data)>15*1024*1024:return redirect(url_for('connect_status'))
    name=secure_filename(f.filename) or 'status'; ext=os.path.splitext(name)[1].lower(); allowed={'.jpg','.jpeg','.png','.webp','.mp4','.webm'}
    if ext not in allowed:return redirect(url_for('connect_status'))
    mime=f.mimetype or 'application/octet-stream'; path=f'connect/status/{uuid.uuid4().hex}{ext}'
    r=requests.post(sb_storage_url(path),headers=sb_headers({'Content-Type':mime,'x-upsert':'true'}),data=data,timeout=60)
    if r.ok:db_insert('koja_statuses',{'id':str(uuid.uuid4()),'user_id':uid,'text_content':'','media_url':sb_storage_url(path),'media_type':'video' if mime.startswith('video/') else 'image','visibility':'contacts','expires_at':(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat(),'created_at':utc_now()})
    return redirect(url_for('connect_status'))

'''
s=s.replace(marker2,media_route+marker2)
p.write_text(s)
print('patched',len(s.splitlines()))
