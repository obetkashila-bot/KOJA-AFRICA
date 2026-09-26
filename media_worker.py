"""KOJA AFRICA Media Processing Worker V5.

Run as a separate Render Background Worker:
    python media_worker.py

It converts uploaded videos into adaptive HLS and writes the master URL back
onto public.koja_public_posts. The web service never receives movie bytes.
"""
import os, time, json, uuid, shutil, subprocess, tempfile, logging
from pathlib import Path
from urllib.parse import quote
import requests
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log=logging.getLogger('koja-media-worker')
SB=os.getenv('SUPABASE_URL','').rstrip('/')
KEY=os.getenv('SUPABASE_SERVICE_KEY','') or os.getenv('SUPABASE_SECRET_KEY','') or os.getenv('SUPABASE_KEY','')
SOURCE_BUCKET=os.getenv('SUPABASE_STORAGE_BUCKET','koja-files')
HLS_BUCKET=os.getenv('KOJA_HLS_BUCKET','koja-media-hls')
QUEUE=os.getenv('KOJA_MEDIA_PROCESSING_QUEUE','koja_media_processing_jobs')
POLL=float(os.getenv('KOJA_MEDIA_WORKER_POLL_SECONDS','5') or 5)
MAX_ATTEMPTS=int(os.getenv('KOJA_MEDIA_MAX_ATTEMPTS','3') or 3)

def headers(extra=None):
    h={'apikey':KEY,'Content-Type':'application/json'}
    if KEY and not KEY.startswith('sb_secret_'): h['Authorization']='Bearer '+KEY
    if extra: h.update(extra)
    return h

def rest(table): return f'{SB}/rest/v1/{quote(table,safe="")}'
def storage(bucket,path): return f'{SB}/storage/v1/object/{quote(bucket,safe="")}/{quote(path,safe="/")}'

def select(table, params):
    r=requests.get(rest(table),headers=headers(),params=params,timeout=30); r.raise_for_status(); d=r.json(); return d if isinstance(d,list) else []

def update(table, filters, payload):
    params={k:'eq.'+str(v) for k,v in filters.items()}
    r=requests.patch(rest(table),headers=headers({'Prefer':'return=representation'}),params=params,json=payload,timeout=30)
    r.raise_for_status(); return r.json() if r.text else []

def upload(bucket,path,data,mime):
    r=requests.put(storage(bucket,path),headers=headers({'Content-Type':mime,'x-upsert':'true'}),data=data,timeout=120)
    r.raise_for_status()

def download(bucket,path,target):
    with requests.get(storage(bucket,path),headers=headers(),stream=True,timeout=120) as r:
        r.raise_for_status()
        with open(target,'wb') as f:
            for chunk in r.iter_content(1024*1024):
                if chunk: f.write(chunk)

def ffprobe_height(src):
    try:
        r=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=height','-of','default=nw=1:nk=1',src],capture_output=True,text=True,timeout=60)
        return int((r.stdout or '0').strip() or 0)
    except Exception: return 0

def run_ffmpeg(src,outdir,height):
    outdir.mkdir(parents=True,exist_ok=True)
    playlist=outdir/'index.m3u8'
    seg=str(outdir/'seg_%05d.ts')
    cmd=['ffmpeg','-y','-hide_banner','-loglevel','error','-i',src,'-map','0:v:0','-map','0:a:0?','-vf',f'scale=w=-2:h={height}:force_original_aspect_ratio=decrease','-c:v','libx264','-preset',os.getenv('KOJA_FFMPEG_PRESET','veryfast'),'-crf',os.getenv('KOJA_FFMPEG_CRF','22'),'-c:a','aac','-b:a','128k','-ar','48000','-ac','2','-f','hls','-hls_time','6','-hls_playlist_type','vod','-hls_segment_filename',seg,str(playlist)]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=int(os.getenv('KOJA_FFMPEG_TIMEOUT','21600')))
    if p.returncode!=0: raise RuntimeError((p.stderr or 'ffmpeg failed')[-3000:])
    return playlist

def process(job):
    post_id=str(job['post_id']); source=job['source_path']; attempt=int(job.get('attempts') or 0)+1
    update(QUEUE,{'id':job['id']},{'status':'processing','attempts':attempt,'progress':2,'started_at':time.strftime('%Y-%m-%dT%H:%M:%SZ'),'updated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ'),'error':None})
    update('koja_public_posts',{'id':post_id},{'processing_status':'processing','processing_progress':2,'processing_error':None,'updated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ')})
    with tempfile.TemporaryDirectory(prefix='koja-media-') as td:
        root=Path(td); src=root/'source'; download(SOURCE_BUCKET,source,src)
        update(QUEUE,{'id':job['id']},{'progress':10,'updated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ')}); update('koja_public_posts',{'id':post_id},{'processing_progress':10,'updated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ')})
        source_h=ffprobe_height(str(src)); targets=[360,480,720,1080]; targets=[h for h in targets if not source_h or h<=source_h]
        if not targets: targets=[360]
        # Never upscale beyond the source when ffprobe succeeds.
        variant_dirs=[]
        for i,h in enumerate(targets):
            d=root/f'{h}p'; run_ffmpeg(str(src),d,h); variant_dirs.append((h,d)); pct=15+int(55*(i+1)/len(targets)); update(QUEUE,{'id':job['id']},{'progress':pct,'updated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ')}); update('koja_public_posts',{'id':post_id},{'processing_progress':pct,'updated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ')})
        # Upload variant playlists/segments.
        for h,d in variant_dirs:
            for f in d.iterdir():
                mime='application/vnd.apple.mpegurl' if f.suffix=='.m3u8' else 'video/mp2t'
                upload(HLS_BUCKET,f'posts/{post_id}/{h}p/{f.name}',open(f,'rb'),mime)
        master_lines=['#EXTM3U','#EXT-X-VERSION:3']
        bandwidths={360:800000,480:1400000,720:2800000,1080:5000000}
        resolutions={360:'640x360',480:'854x480',720:'1280x720',1080:'1920x1080'}
        for h,_ in variant_dirs:
            master_lines += [f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidths[h]},RESOLUTION={resolutions[h]},NAME="{h}p"',f'{h}p/index.m3u8']
        master=root/'master.m3u8'; master.write_text('\n'.join(master_lines)+'\n')
        upload(HLS_BUCKET,f'posts/{post_id}/master.m3u8',open(master,'rb'),'application/vnd.apple.mpegurl')
        master_path=f'posts/{post_id}/master.m3u8'
        now=time.strftime('%Y-%m-%dT%H:%M:%SZ')
        update('koja_public_posts',{'id':post_id},{'media_master_url':master_path,'processing_status':'ready','processing_progress':100,'processing_error':None,'processed_at':now,'updated_at':now})
        update(QUEUE,{'id':job['id']},{'status':'completed','progress':100,'output_path':master_path,'completed_at':now,'updated_at':now})

def loop():
    if not SB or not KEY: raise RuntimeError('SUPABASE_URL and SUPABASE_SERVICE_KEY/SUPABASE_SECRET_KEY are required.')
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'): raise RuntimeError('ffmpeg and ffprobe are required. Add ffmpeg to the worker image/runtime.')
    log.info('KOJA Media Worker started. queue=%s',QUEUE)
    while True:
        try:
            jobs=select(QUEUE,{'status':'eq.queued','order':'created_at.asc','limit':'1'})
            if not jobs: time.sleep(POLL); continue
            job=jobs[0]
            try: process(job)
            except Exception as exc:
                log.exception('Job %s failed',job.get('id'))
                attempts=int(job.get('attempts') or 0)+1; status='queued' if attempts<MAX_ATTEMPTS else 'failed'; err=str(exc)[-3000:]; now=time.strftime('%Y-%m-%dT%H:%M:%SZ')
                update(QUEUE,{'id':job['id']},{'status':status,'attempts':attempts,'error':err,'updated_at':now})
                update('koja_public_posts',{'id':job.get('post_id')},{'processing_status':status,'processing_progress':0 if status=='queued' else int(job.get('progress') or 0),'processing_error':err,'updated_at':now})
                time.sleep(min(30,2**attempts))
        except Exception:
            log.exception('Worker loop error'); time.sleep(10)

if __name__=='__main__': loop()
