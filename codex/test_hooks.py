import json, os, pathlib, subprocess, sys, tempfile, unittest
SCRIPT = pathlib.Path(__file__).with_name('enforce.py')
class Hooks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=pathlib.Path(self.tmp.name); self.cwd=self.root/'project'; self.cwd.mkdir(); self.env={**os.environ,'UX_UI_HOOK_DATA':str(self.root/'state')}; self.file=self.cwd/'screen.html'; self.file.write_text('<button>Save</button>')
 def tearDown(self): self.tmp.cleanup()
 def event(self,event,session='test',call='call',tool='Bash'):
  r=subprocess.run([sys.executable,str(SCRIPT)],cwd=self.cwd,env=self.env,input=json.dumps({'hook_event_name':event,'session_id':session,'cwd':str(self.cwd),'tool_use_id':call,'tool_name':tool,'tool_input':{'command':'test'}}),capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stderr); return json.loads(r.stdout)
 def change(self,text='<button>Continue</button>',tool='Bash'):
  self.event('PreToolUse',tool=tool); self.file.write_text(text); return self.event('PostToolUse',tool=tool)
 def verify(self,body):
  return subprocess.run([sys.executable,str(SCRIPT),'verify','--session','test','--files',str(self.file),'--',sys.executable,'-c',body],cwd=self.cwd,env=self.env,capture_output=True,text=True)
 def test_no_changes(self):
  self.event('PreToolUse'); self.event('PostToolUse'); self.assertEqual(self.event('Stop'),{})
 def test_shell_and_patch_detection(self):
  for tool in ['Bash','apply_patch','mcp__fs__write']:
   self.change('<button>'+tool+'</button>',tool); self.assertEqual(self.event('Stop')['decision'],'block')
 def test_new_file(self):
  self.event('PreToolUse'); (self.cwd/'new.tsx').write_text('export default () => <button>Save</button>'); self.event('PostToolUse'); self.assertEqual(self.event('Stop')['decision'],'block')
 def test_static_failure(self):
  self.assertEqual(self.change('<select><option>Bad</option></select>')['decision'],'block')
 def test_session_isolation(self):
  self.change(); self.assertEqual(self.event('Stop',session='other'),{})
 def test_real_validation_and_expiration(self):
  self.change(); r=self.verify("from pathlib import Path; from html.parser import HTMLParser; p=Path('screen.html'); HTMLParser().feed(p.read_text()); assert '<button>Continue</button>' == p.read_text()")
  self.assertEqual(r.returncode,0,r.stdout+r.stderr); self.assertEqual(self.event('Stop'),{})
  self.file.write_text('<button>Changed again</button>'); self.assertEqual(self.event('Stop')['decision'],'block')
 def test_failed_and_skipped_validation(self):
  self.change()
  for body in ['raise SystemExit(1)',"print('SKIPPED: browser unavailable')"]:
   self.assertNotEqual(self.verify(body).returncode,0); self.assertEqual(self.event('Stop')['decision'],'block')
 def test_validation_mutation(self):
  self.change(); self.assertNotEqual(self.verify("from pathlib import Path; Path('screen.html').write_text('<button>Mutated</button>')").returncode,0)
 def test_deleted_file(self):
  self.change(); self.file.unlink(); self.assertEqual(self.event('Stop'),{})
 def test_non_ui(self):
  self.event('PreToolUse'); (self.cwd/'notes.md').write_text('hello'); self.event('PostToolUse'); self.assertEqual(self.event('Stop'),{})
 def test_project_isolation(self):
  self.change(); self.cwd=self.root/'other'; self.cwd.mkdir(); self.assertEqual(self.event('Stop'),{})
 def test_session_context(self):
  self.assertIn('additionalContext',self.event('SessionStart')['hookSpecificOutput'])
if __name__=='__main__': unittest.main(verbosity=2)
