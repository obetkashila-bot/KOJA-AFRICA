"""Africa Now news page: search, sort, paging, region and subject filters, sections, publication times, escaping.
Uses fixed stories instead of the live feeds. Run from a directory that holds app.py."""
import sys
sys.path.insert(0, '/home/claude/koja_tests')
from harness import A
A.app.config['TESTING'] = True
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)

COUNTRIES = ['Zambia', 'Nigeria', 'Brazil', 'Japan', 'France', 'Kenya']
CATS = ['Politics & Government', 'Business & Markets', 'Technology', 'Health', 'Sports', 'Culture & Entertainment']
FIX = []
for i in range(30):
    cat = CATS[i % 6]
    title = 'Story %02d about %s' % (i, COUNTRIES[i % 6])
    if i == 5:
        title = '<script>x</script> Story 05'
    if i == 7:
        cat = 'Breaking'
    FIX.append({
        'id': str(i), 'title': title, 'summary': 'Summary %d' % i, 'category': cat, 'country': COUNTRIES[i % 6],
        'source_name': 'Test Wire', 'url': 'https://example.com/%d' % i, 'score': 100 - i,
        'published_at': ('2026-10-%02dT08:00:00Z' % (i + 1)) if i < 28 else None,
    })
A._nexus_safe_rows = lambda table, filters=None, order="", limit=100: list(FIX)
c = A.app.test_client()

# 1. Plain page: sections, paging, publication times
p1 = c.get('/nexus/news')
h1 = p1.get_data(as_text=True)
chk('page opens', p1.status_code == 200, p1.status_code)
chk('total count is shown', '(30)' in h1)
chk('breaking, trending and latest sections show on the first page', '>Breaking<' in h1 and '>Trending<' in h1 and '>Latest<' in h1)
chk('first page has a Load more link', 'Load more' in h1)
chk('publication date and time are shown', '2026-10-02 08:00' in h1)
chk('the publisher link is labelled with the source', 'Read at Test Wire' in h1)
chk('script in a headline is shown as text', '&lt;script&gt;x&lt;/script&gt;' in h1 and '<script>x</script>' not in h1)
p2 = c.get('/nexus/news?page=2').get_data(as_text=True)
chk('second page has the remaining 6 stories and no more Load more link', '(30)' in p2 and 'Load more' not in p2 and 'Story 29' in p2 and 'Story 00' not in p2)
chk('a bad page number shows page 1', c.get('/nexus/news?page=abc').get_data(as_text=True).count('Load more') == 1)

# 2. Search
hq = c.get('/nexus/news?q=Zambia').get_data(as_text=True)
chk('search finds only matching stories (5 Zambia stories)', '(5)' in hq)
chk('search hides the sections', '>Trending<' not in hq and '>Breaking<' not in hq)
chk('a search with no matches shows the empty message', 'No stories in this filter.' in c.get('/nexus/news?q=zzzzzz').get_data(as_text=True))

# 3. Subject filter (tabs match the collector categories by name)
hs = c.get('/nexus/news?category=Politics').get_data(as_text=True)
chk('subject Politics shows only politics stories (5)', '(5)' in hs)
chk('an unknown subject is ignored', '(30)' in c.get('/nexus/news?category=Nonsense').get_data(as_text=True))

# 4. Region filter
chk('region Africa shows Zambia, Nigeria and Kenya stories (15)', '(15)' in c.get('/nexus/news?region=Africa').get_data(as_text=True))
chk('region South America shows Brazil stories (5)', '(5)' in c.get('/nexus/news?region=South%20America').get_data(as_text=True))
chk('region Asia shows Japan stories (5)', '(5)' in c.get('/nexus/news?region=Asia').get_data(as_text=True))
chk('region Europe shows France stories (5)', '(5)' in c.get('/nexus/news?region=Europe').get_data(as_text=True))
chk('an unknown region is ignored', '(30)' in c.get('/nexus/news?region=Mars').get_data(as_text=True))

# 5. Sorting
new = c.get('/nexus/news?q=Story&sort=newest').get_data(as_text=True)
chk('newest first shows Story 27 on page 1 and Story 00 is not there', 'Story 27' in new and 'Story 00' not in new)
old = c.get('/nexus/news?q=Story&sort=oldest').get_data(as_text=True)
chk('oldest first shows Story 00 on page 1 and Story 27 is not there', 'Story 00' in old and 'Story 27' not in old)
chk('oldest first lists Story 00 before Story 01', old.index('Story 00') < old.index('Story 01'))
chk('an unknown sort falls back to relevance', '(30)' in c.get('/nexus/news?sort=random').get_data(as_text=True))

# 6. Region mapping
chk('Zambia maps to Africa', A._nexus_region_of({'country': 'Zambia'}) == 'Africa')
chk('a country code maps to its region', A._nexus_region_of({'country_code': 'FR'}) == 'Europe')
chk('Brazil maps to South America', A._nexus_region_of({'country': 'Brazil'}) == 'South America')
chk('an unknown country maps to International', A._nexus_region_of({'country': 'Narnia'}) == 'International')

print('RESULT: %d/%d passed' % (sum(res), len(res)))
