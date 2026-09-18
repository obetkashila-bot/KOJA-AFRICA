# KOJA AFRICA End-to-End Service Engine V1
# Additive layer: does not replace existing KOJA services or Connect+.

KOJA_E2E_VERSION = '2026.09.18-V1'
KOJA_E2E_STATUSES = ('draft','published','requested','confirmed','paid','processing','fulfilling','completed','settled','cancelled','failed','refunded','disputed')
KOJA_E2E_FULFILLMENT = ('physical','digital','remote','in_person','live','booking')

def _e2e_id():
    return str(uuid.uuid4())

def _e2e_uid():
    u = current_user() or {}
    return clean(u.get('id'))

def _e2e_json(data, status=200):
    return jsonify(data), status

def _e2e_notify(user_id, kind, title, body, action_url=None, entity_type=None, entity_id=None):
    if not user_id:
        return None
    now = utc_now()
    row, err = db_insert('koja_e2e_notifications', {
        'id': _e2e_id(), 'user_id': user_id, 'kind': clean(kind) or 'system',
        'title': clean(title)[:180], 'body': clean(body)[:2000],
        'action_url': clean(action_url)[:1000] if action_url else None,
        'entity_type': clean(entity_type) if entity_type else None,
        'entity_id': clean(entity_id) if entity_id else None,
        'is_read': False, 'created_at': now, 'updated_at': now
    })
    return row

def _e2e_service(service_id):
    return first_row('koja_e2e_services', {'id': service_id}) if service_id else None

def _e2e_order(order_id):
    return first_row('koja_e2e_orders', {'id': order_id}) if order_id else None

def _e2e_can_order(order):
    uid = _e2e_uid()
    return bool(order and uid and (str(order.get('customer_id')) == str(uid) or str(order.get('provider_id')) == str(uid) or str(order.get('business_id')) == str(uid) or bool((current_user() or {}).get('is_admin'))))

def _e2e_transition(order, new_status, actor_id=None, note=None):
    if not order or new_status not in KOJA_E2E_STATUSES:
        return None, 'invalid_order_or_status'
    old = clean(order.get('status'))
    now = utc_now()
    updated, err = db_update('koja_e2e_orders', {'id': order.get('id')}, {
        'status': new_status, 'updated_at': now,
        'completed_at': now if new_status == 'completed' else order.get('completed_at'),
        'settled_at': now if new_status == 'settled' else order.get('settled_at')
    })
    if not updated:
        return None, err or 'order_update_failed'
    db_insert('koja_e2e_order_events', {
        'id': _e2e_id(), 'order_id': order.get('id'), 'from_status': old or None,
        'to_status': new_status, 'actor_id': actor_id or _e2e_uid(),
        'note': clean(note)[:2000] if note else None, 'created_at': now
    })
    return updated, None

def _e2e_create_order(service, customer_id, quantity=1, notes=None, delivery_mode=None):
    if not service:
        return None, 'service_not_found'
    try:
        qty = max(1, int(quantity or 1))
    except Exception:
        qty = 1
    unit = float(service.get('price') or 0)
    total = round(unit * qty, 2)
    oid = _e2e_id(); now = utc_now()
    row, err = db_insert('koja_e2e_orders', {
        'id': oid, 'service_id': service.get('id'),
        'customer_id': customer_id, 'provider_id': service.get('provider_id'),
        'business_id': service.get('business_id'), 'quantity': qty,
        'unit_amount': unit, 'gross_amount': total, 'currency': clean(service.get('currency')) or 'ZMW',
        'status': 'requested', 'fulfillment_mode': clean(delivery_mode) or clean(service.get('fulfillment_mode')) or 'digital',
        'notes': clean(notes)[:4000] if notes else None, 'created_at': now, 'updated_at': now
    })
    if not row:
        return None, err or 'order_create_failed'
    db_insert('koja_e2e_order_events', {'id': _e2e_id(), 'order_id': oid, 'from_status': None, 'to_status': 'requested', 'actor_id': customer_id, 'note': 'Order created', 'created_at': now})
    if service.get('provider_id') and str(service.get('provider_id')) != str(customer_id):
        _e2e_notify(service.get('provider_id'), 'order', 'New KOJA order', 'A customer placed a new order.', '/e2e/orders/'+oid, 'order', oid)
    return row, None

def _e2e_money(v):
    try: return round(float(v or 0), 2)
    except Exception: return 0.0

@app.route('/api/e2e/services', methods=['GET'])
def e2e_services():
    q = clean(request.args.get('q'))
    rows = db_select('koja_e2e_services', {'status':'published'}, order='created_at.desc', limit=100) or []
    if q:
        qq=q.lower(); rows=[r for r in rows if qq in str(r.get('name','')).lower() or qq in str(r.get('description','')).lower()]
    return _e2e_json({'ok':True,'version':KOJA_E2E_VERSION,'services':rows})

@app.route('/api/e2e/services', methods=['POST'])
@login_required
def e2e_service_create():
    uid=_e2e_uid(); data=request.get_json(silent=True) or request.form
    mode=clean(data.get('fulfillment_mode')) or 'digital'
    if mode not in KOJA_E2E_FULFILLMENT: return _e2e_json({'ok':False,'error':'invalid_fulfillment_mode'},400)
    try: price=max(0,float(data.get('price') or 0))
    except Exception: price=0
    row,err=db_insert('koja_e2e_services', {'id':_e2e_id(),'provider_id':uid,'business_id':clean(data.get('business_id')) or None,'name':clean(data.get('name'))[:180],'description':clean(data.get('description'))[:5000],'category':clean(data.get('category'))[:100] or 'general','price':price,'currency':clean(data.get('currency')) or 'ZMW','fulfillment_mode':mode,'status':'published','created_at':utc_now(),'updated_at':utc_now()})
    return _e2e_json({'ok':bool(row),'service':row,'error':err},201 if row else 400)

@app.route('/api/e2e/orders', methods=['POST'])
@login_required
def e2e_order_create():
    data=request.get_json(silent=True) or request.form
    service=_e2e_service(clean(data.get('service_id')))
    row,err=_e2e_create_order(service,_e2e_uid(),data.get('quantity',1),data.get('notes'),data.get('fulfillment_mode'))
    return _e2e_json({'ok':bool(row),'order':row,'error':err},201 if row else 400)

@app.route('/api/e2e/orders/<order_id>', methods=['GET'])
@login_required
def e2e_order_get(order_id):
    order=_e2e_order(order_id)
    if not _e2e_can_order(order): return _e2e_json({'ok':False,'error':'not_found_or_forbidden'},404)
    events=db_select('koja_e2e_order_events',{'order_id':order_id},order='created_at.asc',limit=500) or []
    payment=first_row('koja_e2e_payments',{'order_id':order_id})
    fulfillment=first_row('koja_e2e_fulfillments',{'order_id':order_id})
    return _e2e_json({'ok':True,'order':order,'events':events,'payment':payment,'fulfillment':fulfillment})

@app.route('/api/e2e/orders/<order_id>/status', methods=['POST'])
@login_required
def e2e_order_status(order_id):
    order=_e2e_order(order_id)
    if not _e2e_can_order(order): return _e2e_json({'ok':False,'error':'forbidden'},403)
    data=request.get_json(silent=True) or request.form; new=clean(data.get('status'))
    allowed={'requested':{'confirmed','cancelled'},'confirmed':{'paid','cancelled'},'paid':{'processing','cancelled','refunded'},'processing':{'fulfilling','completed','cancelled'},'fulfilling':{'completed','disputed'},'completed':{'settled','disputed'},'disputed':{'refunded','settled'}}
    if new not in allowed.get(clean(order.get('status')),set()): return _e2e_json({'ok':False,'error':'invalid_transition','from':order.get('status'),'to':new},409)
    updated,err=_e2e_transition(order,new,note=data.get('note'))
    if updated:
        for uid in {order.get('customer_id'),order.get('provider_id'),order.get('business_id')}:
            if uid and str(uid)!=str(_e2e_uid()): _e2e_notify(uid,'order','Order updated','Order '+str(order_id)[:8]+' is now '+new+'.','/e2e/orders/'+order_id,'order',order_id)
    return _e2e_json({'ok':bool(updated),'order':updated,'error':err},200 if updated else 400)

@app.route('/api/e2e/orders/<order_id>/pay', methods=['POST'])
@login_required
def e2e_order_pay_record(order_id):
    order=_e2e_order(order_id)
    if not order or str(order.get('customer_id'))!=str(_e2e_uid()): return _e2e_json({'ok':False,'error':'forbidden'},403)
    if clean(order.get('status')) not in ('requested','confirmed'): return _e2e_json({'ok':False,'error':'order_not_payable'},409)
    data=request.get_json(silent=True) or request.form; ref=clean(data.get('payment_reference'))
    if not ref: return _e2e_json({'ok':False,'error':'payment_reference_required'},400)
    existing=first_row('koja_e2e_payments',{'payment_reference':ref})
    if existing: return _e2e_json({'ok':True,'payment':existing,'duplicate':True})
    pay,err=db_insert('koja_e2e_payments',{'id':_e2e_id(),'order_id':order_id,'user_id':_e2e_uid(),'provider':'flutterwave','payment_reference':ref,'amount':_e2e_money(order.get('gross_amount')),'currency':clean(order.get('currency')) or 'ZMW','status':'pending','created_at':utc_now(),'updated_at':utc_now()})
    return _e2e_json({'ok':bool(pay),'payment':pay,'error':err},201 if pay else 400)

@app.route('/api/e2e/orders/<order_id>/fulfillment', methods=['POST'])
@login_required
def e2e_fulfillment(order_id):
    order=_e2e_order(order_id)
    if not _e2e_can_order(order): return _e2e_json({'ok':False,'error':'forbidden'},403)
    data=request.get_json(silent=True) or request.form
    row,err=db_insert('koja_e2e_fulfillments',{'id':_e2e_id(),'order_id':order_id,'mode':clean(data.get('mode')) or order.get('fulfillment_mode'),'status':'requested','tracking_code':clean(data.get('tracking_code')) or ('KMD-'+uuid.uuid4().hex[:10].upper()),'driver_id':clean(data.get('driver_id')) or None,'address':clean(data.get('address'))[:1000] if data.get('address') else None,'confirmation_code':clean(data.get('confirmation_code')) or uuid.uuid4().hex[:6].upper(),'created_at':utc_now(),'updated_at':utc_now()})
    return _e2e_json({'ok':bool(row),'fulfillment':row,'error':err},201 if row else 400)

@app.route('/api/e2e/orders/<order_id>/review', methods=['POST'])
@login_required
def e2e_review(order_id):
    order=_e2e_order(order_id)
    if not order or str(order.get('customer_id'))!=str(_e2e_uid()) or clean(order.get('status')) not in ('completed','settled'): return _e2e_json({'ok':False,'error':'review_not_allowed'},403)
    data=request.get_json(silent=True) or request.form
    try: rating=max(1,min(5,int(data.get('rating') or 5)))
    except Exception: rating=5
    row,err=db_insert('koja_e2e_reviews',{'id':_e2e_id(),'order_id':order_id,'reviewer_id':_e2e_uid(),'provider_id':order.get('provider_id'),'rating':rating,'review':clean(data.get('review'))[:4000],'created_at':utc_now()})
    return _e2e_json({'ok':bool(row),'review':row,'error':err},201 if row else 400)

@app.route('/api/e2e/orders/<order_id>/dispute', methods=['POST'])
@login_required
def e2e_dispute(order_id):
    order=_e2e_order(order_id)
    if not _e2e_can_order(order): return _e2e_json({'ok':False,'error':'forbidden'},403)
    data=request.get_json(silent=True) or request.form
    row,err=db_insert('koja_e2e_disputes',{'id':_e2e_id(),'order_id':order_id,'opened_by':_e2e_uid(),'reason':clean(data.get('reason'))[:200],'description':clean(data.get('description'))[:5000],'status':'open','created_at':utc_now(),'updated_at':utc_now()})
    if row: _e2e_transition(order,'disputed',note='Dispute opened')
    return _e2e_json({'ok':bool(row),'dispute':row,'error':err},201 if row else 400)

@app.route('/api/e2e/notifications', methods=['GET'])
@login_required
def e2e_notifications():
    rows=db_select('koja_e2e_notifications',{'user_id':_e2e_uid()},order='created_at.desc',limit=100) or []
    return _e2e_json({'ok':True,'notifications':rows,'unread':sum(1 for r in rows if not r.get('is_read'))})

@app.route('/api/e2e/notifications/<notification_id>/read', methods=['POST'])
@login_required
def e2e_notification_read(notification_id):
    row,err=db_update('koja_e2e_notifications',{'id':notification_id,'user_id':_e2e_uid()},{'is_read':True,'updated_at':utc_now()})
    return _e2e_json({'ok':bool(row),'notification':row,'error':err},200 if row else 404)

@app.route('/api/e2e/earnings', methods=['GET'])
@login_required
def e2e_earnings():
    rows=db_select('koja_e2e_earnings',{'provider_id':_e2e_uid()},order='created_at.desc',limit=500) or []
    gross=sum(_e2e_money(x.get('gross_amount')) for x in rows); fees=sum(_e2e_money(x.get('koja_fee')) for x in rows); net=sum(_e2e_money(x.get('net_amount')) for x in rows)
    return _e2e_json({'ok':True,'earnings':rows,'summary':{'gross':gross,'koja_fees':fees,'net':net,'currency':'ZMW'}})
