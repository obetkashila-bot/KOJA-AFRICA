import os, io, json, time, shutil, tempfile, subprocess, logging
from pathlib import Path
from urllib.parse import quote
import requests
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
log=logging.getLogger('koja-media-worker')

SUPABASE_URL=os.getenv('SUPABASE_URL','').rstrip('/')
SUPABASE_SERVICE_ROLE_KEY=os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_SERVICE_KEY')
STORAGE_BUCKET=os.getenv('STORAGE_BUCKET','koja-files')
POLL_SECONDS=int(os.getenv('KOJA_MEDIA_WORKER_POLL_SECONDS','10'))

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError('SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY/SUPABASE_SERVICE_KEY are required.')

HEAD={'apikey':SUPABASE_SERVICE_ROLE_KEY,'Authorization':f'Bearer {SUPABASE_SERVICE_ROLE_KEY}'}

def storage_url(path):
    return f"{SUPABASE_URL}/storage/v1/object/{quote(STORAGE_BUCKET,safe='')}/{quote(path,safe='/')}"

def db_url(table): return f"{SUPABASE_URL}/rest/v1/{table}"

def select_jobs(limit=3):
    params={'select':'id,media_url,media_type,media_hls_ready,media_processing_status','media_type':'eq.video','is_published':'eq.true','limit':str(limit),'order':'created_at.asc'}
    r=requests.get(db_url('koja_public_posts'),headers=HEAD,params=params,timeout=30); r.raise_for_status()
    return [x for x in r.json() if not x.get('media_hls_ready') and (x.get('media_processing_status') or 'pending') not in ('processing',)]

def update(post_id, payload):
    h={**HEAD,'Content-Type':'application/json','Prefer':'return=minimal'}
    r=requests.patch(db_url('koja_public_posts'),headers=h,params={'id':f'eq.{post_id}'},json=payload,timeout=30)
    r.raise_for_status()

def download_source(path,dst):
    with requests.get(storage_url(path),headers=HEAD,stream=True,timeout=120) as r:
        r.raise_for_status()
        with open(dst,'wb') as f:
            for chunk in r.iter_content(1024*1024):
                if chunk:f.write(chunk)

def ffprobe_size(src):
    p=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,duration','-of','json',src],capture_output=True,text=True,check=True)
    st=(json.loads(p.stdout).get('streams') or [{}])[0]
    return int(st.get('width') or 640), int(st.get('height') or 360), float(st.get('duration') or 0)

def run(cmd):
    log.info('ffmpeg: %s',' '.join(cmd))
    p=subprocess.run(cmd,capture_output=True,text=True)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout)[-5000:])

def upload_file(local,path,mime):
    h={**HEAD,'Content-Type':mime,'x-upsert':'true'}
    with open(local,'rb') as f:
        r=requests.put(storage_url(path),headers=h,data=f,timeout=180)
    r.raise_for_status()

def process(job):
    pid=job['id']; source=str(job.get('media_url') or '').lstrip('/')
    if source.startswith(STORAGE_BUCKET+'/'): source=source[len(STORAGE_BUCKET)+1:]
    if not source or source.startswith('http://') or source.startswith('https://'):
        raise RuntimeError('Unsupported media_url; expected a Supabase Storage path.')
    update(pid,{'media_processing_status':'processing','media_processing_error':None})
    with tempfile.TemporaryDirectory(prefix='koja-hls-') as td:
        td=Path(td); src=td/'source.bin'; out=td/'hls'; out.mkdir()
        download_source(source,src)
        width,height,duration=ffprobe_size(src)
        targets=[360,480,720,1080]
        targets=[h for h in targets if h<=height]
        if not targets: targets=[min(360,max(144,height))]
        variants=[]
        for h in targets:
            # Keep source aspect ratio, constrain height, and make dimensions even.
            w=max(2,int(round((width*h/height)/2)*2))
            name=f'{h}p'; vd=out/name; vd.mkdir()
            playlist=vd/'index.m3u8'
            run(['ffmpeg','-y','-i',str(src),'-vf',f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2','-c:v','libx264','-preset','veryfast','-profile:v','main','-crf','23','-maxrate',f'{max(500,h*5)}k','-bufsize',f'{max(750,h*8)}k','-c:a','aac','-b:a','96k','-ar','48000','-f','hls','-hls_time','4','-hls_playlist_type','vod','-hls_flags','independent_segments','-hls_segment_filename',str(vd/'seg_%05d.ts'),str(playlist)])
            variants.append((h,w,playlist))
        master=out/'master.m3u8'
        lines=['#EXTM3U','#EXT-X-VERSION:3','#EXT-X-INDEPENDENT-SEGMENTS']
        bitrates={360:700000,480:1100000,720:2200000,1080:4500000}
        for h,w,pl in variants:
            lines += [f'#EXT-X-STREAM-INF:BANDWIDTH={bitrates.get(h,h*5000)},RESOLUTION={w}x{h},NAME="{h}p"',f'{h}p/index.m3u8']
        master.write_text('\n'.join(lines)+'\n')
        base=f'media-hls/{pid}'
        for local in out.rglob('*'):
            if local.is_file():
                rel=local.relative_to(out).as_posix()
                mime='application/vnd.apple.mpegurl' if local.suffix=='.m3u8' else 'video/mp2t'
                upload_file(local,f'{base}/{rel}',mime)
        update(pid,{'media_hls_ready':True,'media_hls_url':f'{base}/master.m3u8','media_processing_status':'ready','media_processing_error':None,'media_duration':duration,'media_processed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
        log.info('processed %s: %s',pid,[x[0] for x in variants])

def main():
    while True:
        try:
            jobs=select_jobs()
            if not jobs: time.sleep(POLL_SECONDS); continue
            for job in jobs:
                try: process(job)
                except Exception as e:
                    log.exception('processing failed for %s',job.get('id'))
                    try:update(job['id'],{'media_processing_status':'error','media_processing_error':str(e)[:2000]})
                    except Exception: log.exception('status update failed')
        except Exception: log.exception('worker poll failed')
        time.sleep(POLL_SECONDS)

if __name__=='__main__': main()
