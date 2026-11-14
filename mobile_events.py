"""Private Android notification feed backed by the existing durable event journal."""
import json


def notification(c, row):
    kind, message = row['kind'], row['message']
    category, title, route = None, '', 'alerts'
    if kind == 'alert_triggered' or (kind == 'alert' and ' crossed ' in message):
        category, title = 'price', 'Price alert triggered'
    elif kind == 'order':
        category, title, route = 'orders', 'Paper order filled', 'portfolio'
    elif kind == 'demo':
        category, title, route = 'demo', 'DeckLab · virtual execution', 'demo'
    elif kind == 'chat':
        try: details = json.loads(row['details'] or '{}')
        except (ValueError, TypeError): details = {}
        if details.get('state') in ('completed', 'failed'):
            category, title, route = 'chat', 'Your AI chat has an update', 'chat'
            message = row['message'] + '. Open AI Chat to read the reply.'
    elif kind == 'research':
        try: details = json.loads(row['details'] or '{}')
        except (ValueError, TypeError): details = {}
        brief_id = details.get('brief_id')
        if brief_id is not None:
            brief = c.execute('SELECT state,result FROM research_briefs WHERE id=?', (brief_id,)).fetchone()
            if brief and brief['state'] == 'completed':
                category, title, route = 'research', 'Your market brief is ready', 'research'
                try: message = json.loads(brief['result']).get('summary') or message
                except (ValueError, TypeError): pass
            elif brief and brief['state'] == 'failed':
                category, title, route = 'research', 'Market research needs attention', 'research'
                message = 'The latest brief could not finish. Open Research for provider status.'
    if not category: return None
    return {'id': row['id'], 'ts': row['ts'], 'category': category,
            'title': title, 'body': message[:350], 'route': route}


def batch(c, after=None):
    if after is None:
        records = list(c.execute('SELECT * FROM events ORDER BY id DESC LIMIT 500'))[::-1]
    else:
        if after < 0 or after > 9223372036854775807: raise ValueError('Invalid event cursor')
        records = list(c.execute('SELECT * FROM events WHERE id>? ORDER BY id LIMIT 100', (after,)))
    items = [item for row in records if (item := notification(c, row))]
    cursor = records[-1]['id'] if records else (after or 0)
    return {'items': items[-50:] if after is None else items, 'cursor': cursor}
