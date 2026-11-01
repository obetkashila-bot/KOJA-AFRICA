"""SEO from the attached app: sitemap lists only public pages (no login-only workspaces) and the title/description text is the one agreed."""
import sys
sys.path.insert(0, '/home/claude/koja_tests')
from harness import A
A.app.config['TESTING'] = True
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)
c = A.app.test_client()
sm = c.get('/sitemap.xml')
xml = sm.get_data(as_text=True)
chk('sitemap is served', sm.status_code == 200 and '<urlset' in xml, sm.status_code)
for private in ['/documents', '/professionals', '/doctors', '/teachers']:
    chk('sitemap leaves out %s' % private, '<loc>%s%s</loc>' % (A.SITE_URL, private) not in xml)
chk('sitemap has no synthetic lastmod', '<lastmod>' not in xml)
chk('sitemap includes the public news channels page', '/news/channels' in xml)
home = c.get('/').get_data(as_text=True)
chk('home title uses the agreed wording', 'Jobs, Scholarships, Study Materials, AI Tools &amp; Business' in home or 'Jobs, Scholarships, Study Materials, AI Tools & Business' in home)
chk('home description uses the agreed wording', 'Find scholarships, jobs, study materials' in home)
print('RESULT: %d/%d passed' % (sum(res), len(res)))
