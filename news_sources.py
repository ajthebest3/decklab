"""Personal RSS headlines: diversified sources, multi-format parsing, full-archive search."""
import html,re,time,xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

EXTRA_FEEDS=[
 ('Mint Markets','https://www.livemint.com/rss/markets','india'),
 ('Mint Companies','https://www.livemint.com/rss/companies','india'),
 ('Economic Times Stocks','https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms','india'),
 ('Business Standard Markets','https://www.business-standard.com/rss/markets-106.rss','india'),
 ('France 24 Business','https://www.france24.com/en/business/rss','world'),
 ('Moneycontrol Markets','https://www.moneycontrol.com/rss/marketreports.xml','india'),
 ('Moneycontrol Business','https://www.moneycontrol.com/rss/business.xml','india'),
 ('CNBC Asia','https://www.cnbc.com/id/19832390/device/rss/rss.html','asia'),
 ('CNBC Europe','https://www.cnbc.com/id/19794221/device/rss/rss.html','europe'),
 ('CNBC Finance','https://www.cnbc.com/id/10000664/device/rss/rss.html','markets'),
 ('Nikkei Asia','https://asia.nikkei.com/rss/feed/nar','asia'),
 ('DW Business','https://rss.dw.com/rdf/rss-en-bus','europe'),
 ('Federal Reserve','https://www.federalreserve.gov/feeds/press_all.xml','macro'),
 ('ECB Press','https://www.ecb.europa.eu/rss/press.html','macro'),
 ('Bank of Japan','https://www.boj.or.jp/en/rss/whatsnew.xml','macro'),
]
TOPICS={'BBC Business':'markets','CNBC Markets':'markets','CoinDesk':'crypto','Economic Times':'india','BBC World':'world','BBC Asia':'asia','Guardian Business':'markets','Guardian World':'world','Al Jazeera':'world',**{name:topic for name,url,topic in EXTRA_FEEDS}}
def parse_feed(payload):
 root=ET.fromstring(payload);out=[]
 for entry in root.iter():
  if entry.tag.rsplit('}',1)[-1] not in ('item','entry'):continue
  values={};link=''
  for child in entry:
   tag=child.tag.rsplit('}',1)[-1];text=''.join(child.itertext()).strip()
   if tag=='link' and child.attrib.get('href') and child.attrib.get('rel','alternate')=='alternate':link=child.attrib['href']
   if text:values.setdefault(tag,text)
  title=html.unescape(re.sub('<[^>]*>','',values.get('title',''))).strip();link=link or values.get('link','');published=values.get('pubDate') or values.get('published') or values.get('updated') or values.get('date') or ''
  if not title or not link.startswith(('https://','http://')):continue
  try:ts=parsedate_to_datetime(published).timestamp()
  except (ValueError,TypeError,OverflowError):
   try:ts=datetime.fromisoformat(published.replace('Z','+00:00')).timestamp()
   except (ValueError,TypeError,OverflowError):ts=0
  out.append({'title':title[:500],'url':link,'published':published,'published_ts':ts})
  if len(out)>=75:break
 if not out:raise ValueError('Feed contained no usable headlines')
 return out
def news_archive(c,rows,params):
 get=lambda key,default='':params.get(key,[default])[0]
 q=get('q').strip()[:100];source=get('source');topic=get('topic');page=max(0,min(100000,int(get('page','0'))));limit=max(1,min(100,int(get('limit','40'))));where=[];args=[]
 for token in q.split()[:6]:where.append('title LIKE ?');args.append('%'+token+'%')
 if source:where.append('source=?');args.append(source)
 if topic and topic!='all':
  sources=[name for name,value in TOPICS.items() if value==topic or (topic=='markets' and value in ('markets','india')) or (topic=='asia' and value=='india')]
  if sources:where.append('source IN ('+','.join('?'*len(sources))+')');args.extend(sources)
  else:where.append('0')
 clause=' WHERE '+' AND '.join(where) if where else ''
 count=c.execute('SELECT COUNT(*) FROM news'+clause,args).fetchone()[0]
 items=rows(c,'SELECT * FROM news'+clause+' ORDER BY published_ts DESC,seen DESC LIMIT ? OFFSET ?',(*args,limit,page*limit))
 return {'items':items,'total':count,'archive_total':c.execute('SELECT COUNT(*) FROM news').fetchone()[0],'sources':rows(c,'SELECT source,COUNT(*) AS count FROM news GROUP BY source ORDER BY source'),'page':page,'limit':limit,'topics':['all','india','world','asia','europe','markets','crypto','macro'],'note':'Selected publisher headlines and official releases, not every market story or full articles.'}
