"""Changed installer paths and incomplete deployment; no administrator writes."""
import json,os,pwd,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import install_local_roles as installer
ROOT=Path(__file__).resolve().parents[1]

class Checks(unittest.TestCase):
 def test_actual_system_tools_and_gpasswd_help(self):
  tools=installer.check_system_tools()
  self.assertEqual(tools['gpasswd'],'/usr/bin/gpasswd')
  result=subprocess.run([tools['gpasswd'],'--help'],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=5)
  self.assertEqual(result.returncode,0);self.assertIn('--members',result.stdout)
 def test_run_resolves_old_bad_path_to_verified_helper(self):
  with patch.object(installer.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'ok','')) as invoke:
   self.assertEqual(installer.run(['/usr/sbin/gpasswd','-M','pgnn-s0','pgnn-gate']),'ok')
   self.assertEqual(invoke.call_args.args[0],['/usr/bin/gpasswd','-M','pgnn-s0','pgnn-gate'])
 def test_missing_helper_stops_before_preflight_and_account_mutations(self):
  original=installer.system_tool
  def missing(name):
   if name=='gpasswd':raise RuntimeError('ADMIN_HELPER_MISSING: gpasswd')
   return original(name)
  with patch.object(installer.os,'geteuid',return_value=0),patch.object(installer,'system_tool',side_effect=missing),patch.object(installer,'git') as git,patch.object(installer,'account') as account,patch.object(installer,'secure_dir') as layout,patch.object(installer.subprocess,'run') as invoke:
   with self.assertRaisesRegex(RuntimeError,'ADMIN_HELPER_MISSING'):installer.preflight()
   git.assert_not_called();account.assert_not_called();layout.assert_not_called();invoke.assert_not_called()
 def test_path_cannot_select_operator_writable_executable(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'gpasswd';path.write_text('#!/bin/sh\nexit 99\n');path.chmod(0o755)
   with patch.dict(os.environ,PATH=folder):self.assertEqual(installer.system_tool('gpasswd'),'/usr/bin/gpasswd')
   with patch.object(installer,'TOOL_DIRS',(Path(folder),)):
    with self.assertRaisesRegex(RuntimeError,'Unsafe|Untrusted'):installer.system_tool('gpasswd')
 def test_verify_absent_or_partial_migration_reports_incomplete(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(installer,'BASE',Path(folder)),patch.object(installer,'run') as invoke:
   with self.assertRaisesRegex(RuntimeError,'INSTALLATION_NOT_COMPLETE'):installer.verify()
   admin=Path(folder)/'admin';admin.mkdir();(admin/'migration.json').write_text('{"state_files":[]}')
   with self.assertRaisesRegex(RuntimeError,'INSTALLATION_NOT_COMPLETE'):installer.verify()
   invoke.assert_not_called()
 def test_existing_six_accounts_are_reused_without_useradd(self):
  accounts={role:pwd.getpwnam('pgnn-'+role) for role in installer.ROLES}
  self.assertEqual(len({entry.pw_uid for entry in accounts.values()}),6)
  with patch.object(installer,'run') as invoke:
   for role,entry in accounts.items():self.assertEqual(installer.account(role),entry)
   invoke.assert_not_called()

if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
 directory=ROOT/'results/local-page';directory.mkdir(parents=True,exist_ok=True)
 document=dict(status='PASS_INSTALLER_DEPENDENCY_RECOVERY' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),actual_helpers=installer.check_system_tools(),scope='Real read-only helper discovery and gpasswd --help; synthetic missing dependency/partial state; real existing account reuse with mutation calls mocked',administrator_writes=False,training=False)
 (directory/'installer-recovery-tests.json').write_text(json.dumps(document,indent=2)+'\n');sys.exit(0 if result.wasSuccessful() else 1)
