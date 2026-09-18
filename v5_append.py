
# ============================================================
# KOJA E2E V5 — UNIVERSAL PLATFORM INTEGRATION
# Connects remaining transactional KOJA modules to the existing
# E2E backbone without replacing their source-of-truth workflows.
# Communications / Connect+ remains untouched.
# ============================================================
KOJA_E2E_VERSION = '2026.09.18-V5'

KOJA_E2E_V5_SOURCES = {
    'b2b_order': 'B2B Procurement',
    'business_store_order': 'Business Online Store',
    'global_trade': 'Global Import & Export',
    'business_live': 'Business Live / Training',
    'ai_credit_order': 'KOJA AI Credits',
}

def _e2e_v5_event(source_type, source_id, action, status=None, metadata=None):
    try:
        if table_exists('koja_e2e_automation_events'):
            db_insert('koja_e2e_automation_events', {
                'source_type': clean(source_type), 'source_id': str(source_id),
                'action': clean(action)[:120], 'source_status': clean(status)[:80] if status else None,
                'metadata': metadata or {}, 'created_at': utc_now()
            })
    except Exception:
        logger.exception('E2E V5 automation event failed')

def _e2e_v5_link(source_type, source_id, provider_id, business_id, customer_id, name, description, amount, currency='ZMW', mode='digital', quantity=1, notes=None):
    if not source_id:
        return None
    try:
        service, _ = _e2e_source_service(source_type, str(source_id), provider_id, business_id, name, description, amount, currency, mode)
        if not service:
            return None
        order, _ = _e2e_source_order(service, customer_id, source_type, str(source_id), max(1, int(quantity or 1)), notes, mode)
        if order:
            _e2e_v5_event(source_type, source_id, 'linked', order.get('status'), {'e2e_order_id': order.get('id')})
        return order
    except Exception:
        logger.exception('E2E V5 source link failed: %s/%s', source_type, source_id)
        return None

def _e2e_v5_sync_b2b(order):
    if not order or not order.get('id'): return None
    buyer=order.get('buyer_user_id')
    seller=order.get('seller_user_id')
    status=clean(order.get('order_status') or order.get('payment_status')).lower()
    mapping={'awaiting_payment':'requested','paid':'paid','in_progress':'processing','completed':'completed','cancelled':'cancelled'}
    e2e=_e2e_v5_link('b2b_order',order.get('id'),seller,order.get('seller_business_id'),buyer,
        'KOJA B2B Order','B2B procurement order',order.get('amount') or 0,order.get('currency') or 'ZMW','physical',1,'B2B order '+str(order.get('id')))
    if e2e and status in mapping:
        target=mapping[status]
        if clean(e2e.get('status')) != target:
            updated,err=_e2e_transition(e2e,target,note='Synchronized from KOJA B2B')
            e2e=updated or e2e
    if e2e:
        _e2e_sync_source_status('b2b_order',str(order.get('id')),e2e)
    return e2e

def _e2e_v5_sync_store(order):
    if not order or not order.get('id'): return None
    product=first_row('koja_business_products',{'id':order.get('product_id')}) or {}
    business_id=order.get('business_id') or product.get('business_id')
    mode='digital' if str(product.get('product_type') or 'physical').lower()=='digital' else ('physical' if str(order.get('fulfillment_method') or '')=='delivery' else 'in_person')
    status=clean(order.get('status')).lower()
    mapping={'pending':'requested','paid':'paid','processing':'processing','completed':'completed','cancelled':'cancelled','refunded':'refunded'}
    e2e=_e2e_v5_link('business_store_order',order.get('id'),business_id,business_id,order.get('buyer_id'),
        product.get('name') or 'Business Store Order','KOJA Business online-store order',order.get('total_amount') or 0,order.get('currency') or 'ZMW',mode,order.get('quantity') or 1,order.get('delivery_address'))
    if e2e and status in mapping and clean(e2e.get('status')) != mapping[status]:
        updated,err=_e2e_transition(e2e,mapping[status],note='Synchronized from KOJA Business Store')
        e2e=updated or e2e
    return e2e

def _e2e_v5_sync_trade(trade):
    if not trade or not trade.get('id'): return None
    status=clean(trade.get('status')).lower()
    mapping={'draft':'draft','booked':'confirmed','processing':'processing','in_transit':'fulfilling','delivered':'completed','closed':'settled','cancelled':'cancelled'}
    e2e=_e2e_v5_link('global_trade',trade.get('id'),trade.get('created_by'),trade.get('business_id'),trade.get('created_by'),
        trade.get('title') or 'Global Trade Order','KOJA cross-border import/export transaction',trade.get('total_landed_cost') or trade.get('goods_value') or 0,trade.get('currency') or 'ZMW','physical',1,trade.get('notes'))
    if e2e and status in mapping and clean(e2e.get('status')) != mapping[status]:
        updated,err=_e2e_transition(e2e,mapping[status],note='Synchronized from KOJA Global Import & Export')
        e2e=updated or e2e
    return e2e

def _e2e_v5_sync_live(session):
    if not session or not session.get('id'): return None
    business_id=session.get('business_id'); host=session.get('created_by') or session.get('host_user_id')
    amount=session.get('price') or session.get('fee') or session.get('amount') or 0
    e2e=_e2e_v5_link('business_live',session.get('id'),host,business_id,host,session.get('title') or 'KOJA Live Session','KOJA live teaching/training/service session',amount,session.get('currency') or 'ZMW','live',1,session.get('description'))
    return e2e

def _e2e_v5_sync_ai_order(order):
    if not order or not order.get('id'): return None
    uid=order.get('user_id')
    e2e=_e2e_v5_link('ai_credit_order',order.get('id'),'','',uid,'KOJA AI Credits','AI credit purchase',order.get('amount') or 0,order.get('currency') or 'ZMW','digital',order.get('units') or 1,'AI credits purchase')
    if e2e and clean(order.get('status')).lower()=='paid' and clean(e2e.get('status'))!='paid':
        updated,err=_e2e_transition(e2e,'paid',note='Synchronized from KOJA Profit Engine')
        e2e=updated or e2e
    return e2e

def _e2e_v5_sync_all_for_user(uid):
    counts={'b2b':0,'store':0,'trade':0,'live':0,'ai':0}
    if not uid: return counts
    try:
        businesses=db_select('koja_businesses',{'owner_id':uid},limit=100) or []
        bids={str(x.get('id')) for x in businesses if x.get('id')}
        b2b=db_select('koja_b2b_v4_orders',{},order='created_at.desc',limit=1000) or []
        for x in b2b:
            if str(x.get('buyer_user_id'))==str(uid) or str(x.get('seller_user_id'))==str(uid) or str(x.get('buyer_business_id')) in bids or str(x.get('seller_business_id')) in bids:
                if _e2e_v5_sync_b2b(x): counts['b2b']+=1
        stores=db_select('koja_business_orders',{'buyer_id':uid},order='created_at.desc',limit=1000) or []
        for x in stores:
            if _e2e_v5_sync_store(x): counts['store']+=1
        trades=[]
        for bid in bids:
            trades += db_select('koja_global_trade_orders',{'business_id':bid},order='created_at.desc',limit=1000) or []
        seen=set()
        for x in trades:
            if str(x.get('id')) in seen: continue
            seen.add(str(x.get('id')))
            if _e2e_v5_sync_trade(x): counts['trade']+=1
        if table_exists('koja_business_live_sessions'):
            sessions=[]
            for bid in bids: sessions += db_select('koja_business_live_sessions',{'business_id':bid},order='created_at.desc',limit=500) or []
            for x in sessions:
                if _e2e_v5_sync_live(x): counts['live']+=1
        if table_exists('koja_profit_orders'):
            ai=db_select('koja_profit_orders',{'user_id':uid},order='created_at.desc',limit=500) or []
            for x in ai:
                if _e2e_v5_sync_ai_order(x): counts['ai']+=1
    except Exception:
        logger.exception('E2E V5 user sync failed')
    return counts

@app.route('/api/e2e/v5/sync', methods=['POST'])
@login_required
def e2e_v5_sync_api():
    uid=(current_user() or {}).get('id')
    counts=_e2e_v5_sync_all_for_user(uid)
    return _e2e_json({'ok':True,'version':KOJA_E2E_VERSION,'counts':counts})

@app.route('/api/e2e/v5/admin/sync', methods=['POST'])
@admin_required
def e2e_v5_admin_sync_api():
    users=db_select('profiles',{},limit=5000) or []
    total={'users':0,'b2b':0,'store':0,'trade':0,'live':0,'ai':0}
    for u in users:
        uid=u.get('id')
        if not uid: continue
        c=_e2e_v5_sync_all_for_user(uid); total['users']+=1
        for k in ('b2b','store','trade','live','ai'): total[k]+=c.get(k,0)
    return _e2e_json({'ok':True,'version':KOJA_E2E_VERSION,'counts':total})

@app.route('/e2e/universal')
@login_required
def e2e_v5_universal_dashboard():
    uid=(current_user() or {}).get('id')
    counts=_e2e_v5_sync_all_for_user(uid)
    links=db_select('koja_e2e_source_links',{},order='created_at.desc',limit=500) or []
    own=[]
    for link in links:
        order=_e2e_order(link.get('order_id')) if link.get('order_id') else None
        if not order: continue
        if str(order.get('customer_id'))==str(uid) or str(order.get('provider_id'))==str(uid) or (current_user() or {}).get('is_admin'):
            own.append({'source_type':link.get('source_type'),'source_id':link.get('source_id'),'status':order.get('status'),'amount':order.get('gross_amount') or order.get('unit_price') or 0,'currency':order.get('currency') or 'ZMW','created_at':order.get('created_at')})
    return render_page('KOJA Universal E2E',r'''
<div class="hero"><h1>KOJA Universal E2E</h1><p>One lifecycle across Market, Business, B2B, Global Trade, Professional Services, Live services, AI credits and delivery.</p><form method="post" action="{{ url_for('e2e_v5_sync_api') }}"><button class="btn">Synchronize My KOJA Services</button></form></div>
<div class="grid">{% for k,v in counts.items() %}<div class="card"><h3>{{ k|upper }}</h3><h2>{{ v }}</h2><p>records synchronized</p></div>{% endfor %}</div>
<div class="card"><h2>Universal Transactions</h2><table><tr><th>Source</th><th>Source ID</th><th>Status</th><th>Amount</th><th>Created</th></tr>{% for x in own[:200] %}<tr><td>{{ x.source_type }}</td><td>{{ x.source_id }}</td><td>{{ x.status }}</td><td>{{ money(x.amount,x.currency) }}</td><td>{{ x.created_at }}</td></tr>{% else %}<tr><td colspan="5">No linked E2E transactions yet.</td></tr>{% endfor %}</table></div>
''',counts=counts,own=own,money=market_money)

# Automatic post-flow synchronization. These wrappers do not replace the source route;
# they observe its result and attach the resulting record to E2E.
def _e2e_v5_wrap_endpoint(endpoint, finder, syncer):
    try:
        old=app.view_functions.get(endpoint)
        if not old or getattr(old,'_e2e_v5_wrapped',False): return
        @wraps(old)
        def wrapped(*args,**kwargs):
            response=old(*args,**kwargs)
            try:
                row=finder(*args,**kwargs)
                if row: syncer(row)
            except Exception: logger.exception('E2E V5 wrapper failed for %s',endpoint)
            return response
        wrapped._e2e_v5_wrapped=True
        app.view_functions[endpoint]=wrapped
    except Exception:
        logger.exception('E2E V5 wrapper install failed for %s',endpoint)

_e2e_v5_wrap_endpoint('b2bv4_payment_callback',
    lambda *a,**kw: (lambda ref: first_row('koja_b2b_v4_orders',{'payment_reference':ref}) if ref else None)(clean(request.args.get('tx_ref') or request.args.get('reference'))),
    _e2e_v5_sync_b2b)
_e2e_v5_wrap_endpoint('business_store_payment_callback',
    lambda *a,**kw: first_row('koja_business_orders',{'payment_reference':clean(request.args.get('tx_ref') or request.args.get('reference'))}) or None,
    _e2e_v5_sync_store)
_e2e_v5_wrap_endpoint('b2bv4_order_complete',
    lambda order_id=None,*a,**kw: first_row('koja_b2b_v4_orders',{'id':order_id}),
    _e2e_v5_sync_b2b)
_e2e_v5_wrap_endpoint('global_import_export_create',
    lambda business_id,*a,**kw: (db_select('koja_global_trade_orders',{'business_id':business_id},order='created_at.desc',limit=1) or [None])[0],
    _e2e_v5_sync_trade)
_e2e_v5_wrap_endpoint('global_import_export_update',
    lambda business_id,trade_id,*a,**kw: first_row('koja_global_trade_orders',{'id':trade_id,'business_id':business_id}),
    _e2e_v5_sync_trade)

