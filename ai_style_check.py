"""KOJA AI answer style: the chat instructions carry the honesty and shape rules and a language rule. Run from the project folder."""
import sys
sys.path.insert(0, '/home/claude/koja_tests')
from harness import A
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)
sysmsg = A._ai_chat_system("Answer directly in a concise conversational style.")
chk('the instructions keep the no-invented-facts rule', 'Do not invent citations' in sysmsg)
chk('the instructions keep the uncertainty rule', 'say so plainly' in sysmsg)
chk('answers lead with the direct answer', 'Lead with the direct answer' in sysmsg)
chk('how-to answers get numbered steps', 'numbered steps' in sysmsg)
chk('maths and science show working with units', 'show the working step by step' in sysmsg and 'units' in sysmsg)
chk('the user language is respected', 'same language the user writes in' in sysmsg)
chk('filler openings are banned', "Great question" in sysmsg)
chk('the chosen variation is included', "Answer directly in a concise conversational style." in sysmsg)
chk('no variation adds nothing extra', 'Answer directly' not in A._ai_chat_system(""))
chk('the module pointer is kept', 'KOJA Research Engine' in sysmsg)
print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
