import json

g  = json.load(open('swagger_templates/ref1_groove.json'))
ws = g['word_slots']

print('First 5 word slots:')
for s in ws[:5]:
    print(f"  word {s['word_idx']} -> time {s['time']}s, phrase {s['phrase_idx']}, on_beat {s['on_beat']}")

print()
print('First section key:', g['section_keys'][0])
print('Tempo:', g['tempo'])
print('Total word slots:', len(ws))
print('Total beats:', len(g['beat_times']))
print('Total phrases:', len(g['phrases']))
print('Total breaths:', len(g['breaths']))
