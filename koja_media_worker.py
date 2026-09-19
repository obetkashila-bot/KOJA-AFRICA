"""KOJA Media V6 HLS worker.

Run on a worker/server with FFmpeg installed. It converts one published video
into HLS renditions (360p/480p/720p/1080p, limited by source resolution),
uploads the HLS tree to Supabase Storage, then writes media_hls_url back to
koja_public_posts.

Environment:
  SUPABASE_URL
  SUPABASE_SERVICE_KEY (or SUPABASE_SECRET_KEY/SUPABASE_KEY)
  KOJA_MEDIA_HLS_BUCKET=koja-media-stream   # make this bucket public for direct HLS playback
  KOJA_MEDIA_SOURCE_BUCKET=koja-files
  KOJA_MEDIA_JOB_ID=<optional>
  KOJA_MEDIA_POST_ID=<optional>

Requires: requests, python-dotenv, ffmpeg and ffprobe binaries.
"""
import os, sys, tempfile, subprocess, shutil, mimetypes
from pathlib import Path
import requests
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL=os.getenv('SUPABASE_URL','').rstrip('/')
KEY=os.getenv('SUPABASE_SECRET_KEY') or os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')
HLS_BUCKET=os.getenv('KOJA_MEDIA_HLS_BUCKET','koja-media-stream')
SOURCE_BUCKET=os.getenv('KOJA_MEDIA_SOURCE_BUCKET','koja-files')
if not SUPABASE_URL or not KEY:
    raise SystemExit('SUPABASE_URL and service key are required')
HEAD={'apikey':KEY,'Authorization':f'Bearer {KEY}'}

def db_get(path, params=None):
    r=requests.get(f'{SUPABASE_URL}/rest/v1/{path}',headers=HEAD,params=params or {},timeout=30); r.raise_for_status(); return r.json()
def db_patch(path, params, data):
    h={**HEAD,'Content-Type':'application/json','Prefer':'return=minimal'}
    r=requests.patch(f'{SUPABASE_URL}/rest/v1/{path}',headers=h,params=params,json=data,timeout=30); r.raise_for_status()
def storage_download(path, out):
    r=requests.get(f'{SUPABASE_URL}/storage/v1/object/{SOURCE_BUCKET}/{path}',headers=HEAD,stream=True,timeout=120); r.raise_for_status()
    with open(out,'wb') as f:
        for chunk in r.iter_content(1024*1024):
            if chunk:f.write(chunk)
def storage_upload(path, local):
    ct=mimetypes.guess_type(str(local))[0] or 'application/octet-stream'
    h={**HEAD,'Content-Type':ct,'x-upsert':'true'}
    with open(local,'rb') as f:
        r=requests.post(f'{SUPABASE_URL}/storage/v1/object/{HLS_BUCKET}/{path}',headers=h,data=f,timeout=120)
    r.raise_for_status()
def public_url(path):
    return f'{SUPABASE_URL}/storage/v1/object/public/{HLS_BUCKET}/{path}'

def probe(src):
    out=subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=width,height,duration','-of','json',src],text=True)
    import json
    j=json.loads(out); vs=next((x for x in j.get('streams',[]) if x.get('width')),{}); return int(vs.get('width') or 0),int(vs.get('height') or 0),float(vs.get('duration') or 0)

def process(post_id):
    posts=db_get('koja_public_posts',{'select':'id,media_url,is_published','id':f'eq.{post_id}'})
    if not posts: raise RuntimeError('Post not found')
    post=posts[0]; value=post.get('media_url') or ''
    prefix=f'{SUPABASE_URL}/storage/v1/object/public/{SOURCE_BUCKET}/'
    if value.startswith(prefix): path=value[len(prefix):]
    else:
        marker=f'/storage/v1/object/{SOURCE_BUCKET}/'
        if marker in value:path=value.split(marker,1)[1]
        else:path=value.lstrip('/')
    with tempfile.TemporaryDirectory(prefix='koja-hls-') as td:
        td=Path(td); src=td/'source'; storage_download(path,src)
        w,h,dur=probe(src); max_h=max(360,min(1080,h or 360)); rend=[x for x in (360,480,720,1080) if x<=max_h]
        if not rend: rend=[360]
        out=td/'hls'; out.mkdir()
        variants=[]
        for rh in rend:
            # Keep source aspect ratio and force even dimensions.
            vdir=out/f'{rh}p'; vdir.mkdir()
            playlist=vdir/'index.m3u8'
            vf=f'scale=-2:{rh}:force_original_aspect_ratio=decrease'
            subprocess.run(['ffmpeg','-y','-i',str(src),'-vf',vf,'-c:v','libx264','-preset','veryfast','-profile:v','main','-crf','22','-c:a','aac','-b:a','128k','-ac','2','-g','96','-keyint_min','96','-sc_threshold','0','-hls_time','4','-hls_playlist_type','vod','-hls_segment_filename',str(vdir/'seg_%05d.ts'),str(playlist)],check=True)
            variants.append((rh,vdir))
        master=out/'master.m3u8'
        with open(master,'w') as f:
            f.write('#EXTM3U\n#EXT-X-VERSION:3\n')
            for rh,vdir in variants:
                bw={360:800000,480:1400000,720:2800000,1080:5000000}[rh]
                rw=max(2, int(round(w * rh / max(h,1))) // 2 * 2); f.write(f'#EXT-X-STREAM-INF:BANDWIDTH={bw},RESOLUTION={rw}x{rh}\n{rh}p/index.m3u8\n')
        base=f'koja-hls/{post_id}'
        for file in out.rglob('*'):
            if file.is_file(): storage_upload(f'{base}/{file.relative_to(out).as_posix()}',file)
        master_url=public_url(f'{base}/master.m3u8')
        db_patch('koja_public_posts',{'id':f'eq.{post_id}'},{'media_hls_url':master_url,'media_master_url':master_url,'media_processing_status':'ready','media_processing_error':None,'media_duration_seconds':dur,'media_processed_at':'now()'})
        return master_url

if __name__=='__main__':
    post=os.getenv('KOJA_MEDIA_POST_ID') or (sys.argv[1] if len(sys.argv)>1 else '')
    if not post: raise SystemExit('Usage: KOJA_MEDIA_POST_ID=<uuid> python koja_media_worker.py')
    print(process(post))
