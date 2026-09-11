from pathlib import Path
p=Path('/mnt/data/corev3/app.py')
s=p.read_text()
marker="\n\n@app.route('/api/nextgen/ai/core/status', methods=['GET'])"
block=r'''

# ==================== KOJA AI CORE V3 — adaptive semantic memory + verified learning ====================
import math as _core_math

_CORE_V3_DIM=192

def _core_v3_vector(text):
    """Dependency-free hashed semantic fingerprint. Optional embeddings can replace this later."""
    vec=[0.0]*_CORE_V3_DIM
    toks=list(_core_tokens(text))
    for tok in toks:
        h=hashlib.sha256(tok.encode('utf-8','ignore')).digest()
        for j in range(3):
            idx=int.from_bytes(h[j*2:j*2+2],'big')%_CORE_V3_DIM
            sign=1.0 if h[6+j]%2 else -1.0
            vec[idx]+=sign*(1.0/(1.0+len(tok)*0.03))
    n=_core_math.sqrt(sum(x*x for x in vec)) or 1.0
    return [x/n for x in vec]

def _core_v3_similarity(a,b):
    return sum(x*y for x,y in zip(a,b))

def _core_v3_search(uid,query,limit=15):
    """Hybrid retrieval: lexical + hashed semantic similarity + recency/importance."""
    qv=_core_v3_vector(query); qtokens=_core_tokens(query); results=[]
    sources=[]
    if _core_v2_table('koja_ai_memories'):
        sources.append(('memory',db_select('koja_ai_memories',{'user_id':uid,'is_active':True},order='updated_at.desc',limit=300)))
    if _core_v2_table('koja_ai_file_memory'):
        sources.append(('file',db_select('koja_ai_file_memory',{'user_id':uid},order='updated_at.desc',limit=150)))
    if _core_v2_table('koja_ai_core_knowledge'):
        sources.append(('knowledge',db_select('koja_ai_core_knowledge',{'is_active':True},order='updated_at.desc',limit=300)))
    for kind,rows in sources:
        for r in rows:
            text=(r.get('memory') or r.get('title') or r.get('file_name') or '')+' '+(r.get('content') or '')
            toks=_core_tokens(text); lexical=len(qtokens&toks)/(max(1,len(qtokens))**0.5)
            semantic=_core_v3_similarity(qv,_core_v3_vector(text))
            bonus=(float(r.get('importance') or 0)/100.0) if kind=='memory' else (0.04 if r.get('is_verified') else 0)
            score=0.62*max(0,semantic)+0.38*lexical+bonus
            if score>0.08: results.append((score,kind,r))
    results.sort(key=lambda x:x[0],reverse=True)
    return results[:limit]

def _core_v3_extract_learning(prompt,answer,feedback):
    fb=clean(feedback)
    if not fb:return None
    if len(fb)<3:return None
    return clean(f"User feedback: {fb}\nTask context: {clean(prompt)[:1500]}\nObserved answer: {clean(answer)[:2500]}")[:7000]

def _core_v3_auto_graph(uid,prompt,answer=''):
    if not uid or not _core_v2_table('koja_ai_core_graph'): return
    text=clean(prompt)
    patterns=[
        (r'we are building\s+(.+?)(?:[.!?]|$)','KOJA project','builds'),
        (r'we are working on\s+(.+?)(?:[.!?]|$)','KOJA project','works_on'),
        (r'my project is\s+(.+?)(?:[.!?]|$)','user project','is'),
        (r'(?:call|name) it\s+(.+?)(?:[.!?]|$)','project','named'),
    ]
    for pat,entity,relation in patterns:
        m=_memory_re.search(pat,text,_memory_re.I)
        if m:
            target=clean(m.group(1))[:240]
            _core_v2_record_graph(uid,entity,'project',relation,target,'conversation')

def _core_v3_context(uid,prompt):
    hits=_core_v3_search(uid,prompt,15)
    if not hits:return ''
    blocks=[]
    for score,kind,r in hits:
        if kind=='memory':
            blocks.append(f"MEMORY ({score:.2f}): {clean(r.get('memory'))[:3500]}")
        elif kind=='file':
            blocks.append(f"FILE ({score:.2f}) — {clean(r.get('file_name'))}:\n{clean(r.get('content'))[:6500]}")
        else:
            blocks.append(f"KNOWLEDGE ({score:.2f}) — {clean(r.get('title'))}:\n{clean(r.get('content'))[:5500]}")
    return 'KOJA CORE V3 HYBRID SEMANTIC RETRIEVAL:\n'+'\n\n'.join(blocks)+'\n\n'

@app.route('/api/nextgen/ai/core/v3/status', methods=['GET'])
@login_required
def api_nextgen_ai_core_v3_status():
    uid=str((current_user() or {}).get('id') or '')
    return jsonify(ok=True,version='V3',semantic_engine='dependency-free hashed vectors',hybrid_retrieval=True,
        adaptive_learning=_core_v2_table('koja_ai_core_learnings'),knowledge_graph=_core_v2_table('koja_ai_core_graph'),
        evaluations=_core_v2_table('koja_ai_evaluations'),provider_health=_core_v2_table('koja_ai_provider_health'),
        file_memory=_core_v2_table('koja_ai_file_memory'),safe_self_builder=True)

@app.route('/api/nextgen/ai/core/v3/feedback', methods=['POST'])
@login_required
def api_nextgen_ai_core_v3_feedback():
    uid=str((current_user() or {}).get('id') or ''); d=request.get_json(silent=True) or {}
    prompt=clean(d.get('prompt')); answer=clean(d.get('answer')); feedback=clean(d.get('feedback')); score=d.get('score')
    if not feedback and score is None:return jsonify(error='Feedback or score is required.'),400
    if not _core_v2_table('koja_ai_evaluations'):return jsonify(error='Core evaluation storage is not installed.'),503
    try: score=float(score) if score is not None else None
    except Exception: score=None
    row,err=db_insert('koja_ai_evaluations',{'user_id':uid,'score':score,'feedback':feedback[:5000], 'is_verified':False,'created_at':utc_now()})
    learning=_core_v3_extract_learning(prompt,answer,feedback)
    if learning and _core_v2_table('koja_ai_core_learnings'):
        db_insert('koja_ai_core_learnings',{'user_id':uid,'learning':learning,'source':'user-feedback','is_verified':False,'created_at':utc_now()})
    return jsonify(ok=True,evaluation=row,learning_recorded=bool(learning))

@app.route('/api/nextgen/ai/core/v3/propose', methods=['POST'])
@login_required
def api_nextgen_ai_core_v3_propose():
    uid=str((current_user() or {}).get('id') or ''); d=request.get_json(silent=True) or {}
    goal=clean(d.get('goal'))
    if not goal:return jsonify(error='Goal is required.'),400
    proposal={
        'goal':goal[:3000],
        'steps':['Retrieve relevant KOJA memory and knowledge','Select verified tools/workflows','Attempt solution with available providers or Core tools','Evaluate result against the goal','Store only verified or explicitly approved learning'],
        'safety':['No arbitrary code execution','No silent production code changes','No automatic deployment','User/admin approval required before production changes']
    }
    if _core_v2_table('koja_ai_core_tasks'):
        db_insert('koja_ai_core_tasks',{'user_id':uid,'task_type':'self_improvement_proposal','prompt':goal[:12000],'result':json.dumps(proposal),'provider':'KOJA Core V3','status':'proposed','metadata':'{}','created_at':utc_now()})
    return jsonify(ok=True,proposal=proposal)
'''
if marker not in s: raise SystemExit('marker missing')
s=s.replace(marker,block+marker,1)
# Inject V3 context after V2 context in both endpoints.
s=s.replace("core_v2_context=_core_v2_context(str(uid),prompt)\n    tool_answer,tool_name=_core_v2_tool(prompt)","core_v2_context=_core_v2_context(str(uid),prompt)\n    core_v3_context=_core_v3_context(str(uid),prompt)\n    _core_v3_auto_graph(str(uid),prompt)\n    tool_answer,tool_name=_core_v2_tool(prompt)",2)
s=s.replace("base_prompt=core_v2_context+memory_context", "base_prompt=core_v3_context+core_v2_context+memory_context",1)
s=s.replace("prompt2=core_v2_context+memory_context", "prompt2=core_v3_context+core_v2_context+memory_context",1)
p.write_text(s)
