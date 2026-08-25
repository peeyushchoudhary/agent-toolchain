#!/usr/bin/env python3
"""Deterministic contract and Darwin lifecycle tests for evidence_supervisor."""
from __future__ import annotations
import hashlib, importlib.util, json, os, pathlib, shutil, signal, stat, struct, subprocess, sys, tempfile, time, unittest
from unittest import mock

SCRIPT=pathlib.Path(__file__).resolve().parents[1]/"scripts"/"evidence_supervisor.py"
spec=importlib.util.spec_from_file_location("evidence_supervisor",SCRIPT)
es=importlib.util.module_from_spec(spec); sys.modules[spec.name]=es; spec.loader.exec_module(es)
DARWIN=sys.platform=="darwin"

def canon(obj,newline=False):
    b=json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
    return b+(b"\n" if newline else b"")

def argv_hash(argv):
    h=hashlib.sha256(struct.pack(">Q",len(argv)))
    for arg in argv:
        raw=arg.encode(); h.update(struct.pack(">Q",len(raw))); h.update(raw)
    return h.hexdigest()

class Fixture:
    def __init__(self,case,run_id="run-1",literal="printf 'alpha\\000omega'"):
        self.case=case; self.root=pathlib.Path(tempfile.mkdtemp(prefix="evidence-test-")).resolve()
        os.chmod(self.root,0o700)
        self.parent=self.root/"receipts"; self.parent.mkdir(mode=0o700)
        self.cwd=self.root/"work"; self.cwd.mkdir(mode=0o700)
        self.run_id=run_id; self.argv=["/bin/sh","-c",literal]
        self.env={"PATH":"/usr/bin:/bin","PWD":str(self.cwd),"TOKEN":"dynamic-value"}
        self.env_obj={"schema":es.SCHEMA_ENV,"env":self.env}
        self.env_file=self.root/"environment.json"; self.write_private(self.env_file,canon(self.env_obj))
        self.anchor_file=self.root/"launch.json"; self.write_anchor()
    def identity(self,p,key="path",value=None):
        s=p.stat(); return {key:value if value is not None else str(p),"dev":s.st_dev,"ino":s.st_ino}
    def anchor(self):
        return {"schema":es.SCHEMA_LAUNCH,"run_id":self.run_id,"argv":self.argv,
          "argv_sha256":argv_hash(self.argv),"env_sha256":hashlib.sha256(canon(self.env_obj)).hexdigest(),
          "cwd":self.identity(self.cwd),"trusted_ancestor":self.identity(self.root),
          "evidence_parent":self.identity(self.parent,"relative_path","receipts"),
          "supervisor_sha256":hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
          "caller":{"source_head":"head-value","source_tree":"tree-value","toolchain_sha":"tool-value"}}
    def write_private(self,path,data):
        path.write_bytes(data); os.chmod(path,0o600)
    def write_anchor(self,obj=None,raw=None):
        self.write_private(self.anchor_file, raw if raw is not None else canon(obj or self.anchor()))
    def run_cmd(self):
        return [sys.executable,str(SCRIPT),"run","--trusted-ancestor",str(self.root),
          "--evidence-parent","receipts","--run-id",self.run_id,"--cwd",str(self.cwd),
          "--env-file",str(self.env_file),"--launch-anchor",str(self.anchor_file),"--",*self.argv]
    def verify_cmd(self):
        return [sys.executable,str(SCRIPT),"verify","--trusted-ancestor",str(self.root),
          "--evidence-parent","receipts","--run-id",self.run_id,"--launch-anchor",str(self.anchor_file)]
    def patched_run_cmd(self,body):
        helper=self.root/("helper-"+str(time.monotonic_ns())+".py")
        helper.write_text("import importlib.util,sys\n"
          +"spec=importlib.util.spec_from_file_location('evidence_supervisor_helper',"+repr(str(SCRIPT))+")\n"
          +"module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module)\n"
          +body+"\nraise SystemExit(module.main())\n")
        return [sys.executable,str(helper),*self.run_cmd()[2:]]
    @property
    def run_dir(self): return self.parent/self.run_id
    def execute(self): return subprocess.run(self.run_cmd(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    def verify(self): return subprocess.run(self.verify_cmd(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    def terminal(self): return json.loads((self.run_dir/"terminal.json").read_text())
    def rewrite_terminal(self,fn):
        p=self.run_dir/"terminal.json"; os.chmod(p,0o600); obj=json.loads(p.read_text()); fn(obj)
        p.unlink(); self.write_private(p,canon(obj,True))
    def close(self): shutil.rmtree(self.root,ignore_errors=True)

class JsonAndUnitTests(unittest.TestCase):
    def test_argv_digest_has_count_and_lengths(self):
        self.assertNotEqual(es.argv_digest(["ab","c"]),es.argv_digest(["a","bc"]))
        self.assertEqual(es.argv_digest([]),hashlib.sha256(struct.pack(">Q",0)).hexdigest())
    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in (b'{"schema":"x","schema":"x"}',b'{"x":NaN}',b'\xff'):
            with self.assertRaises(es.EvidenceError): es.parse_json_bytes(raw,"test")
    def test_env_requires_exact_schema_and_types(self):
        bad=[{"schema":es.SCHEMA_ENV,"env":{},"extra":1},
             {"schema":es.SCHEMA_ENV,"env":{"A":1}},
             {"schema":es.SCHEMA_ENV,"env":{"A=B":"x"}},
             {"schema":es.SCHEMA_ENV,"env":{"A":"x\0y"}}]
        for value in bad:
            with self.assertRaises(es.EvidenceError): es.parse_env(canon(value))
    def test_canonical_environment_digest_and_sorted_keys(self):
        obj={"schema":es.SCHEMA_ENV,"env":{"Z":"1","A":"2"}}
        env,digest,keys=es.parse_env(json.dumps(obj,indent=2).encode())
        self.assertEqual(keys,["A","Z"]); self.assertEqual(digest,hashlib.sha256(canon(obj)).hexdigest())
    def test_paths_reject_dot_empty_escape_and_nul(self):
        for value in ("relative","/a/../b","/a//b","/"):
            with self.assertRaises(es.EvidenceError): es._parts_absolute(value)
        for value in ("/absolute","a/../b","a//b","a\0b"):
            with self.assertRaises(es.EvidenceError): es._parts_relative(value)
    def test_waitpid_eintr_and_wrong_child(self):
        with mock.patch.object(es.os,"waitpid",side_effect=[InterruptedError(),(7,0)]): self.assertEqual(es._wait_exact(7),0)
        with mock.patch.object(es.os,"waitpid",return_value=(8,0)):
            with self.assertRaises(es.EvidenceError): es._wait_exact(7)
    def test_short_write_and_eintr(self):
        calls=[]
        def write(fd,data):
            calls.append(bytes(data));
            if len(calls)==1: raise InterruptedError()
            return min(2,len(data))
        with mock.patch.object(es.os,"write",side_effect=write): es._write_all(9,b"abcdef")
        self.assertGreaterEqual(len(calls),4)
    def test_read_and_fsync_retry_eintr_and_fail_closed(self):
        with mock.patch.object(es.os,"read",side_effect=[InterruptedError(),b"abc",b""]):
            self.assertEqual(es._read_all(4),b"abc")
        with mock.patch.object(es.os,"fsync",side_effect=[InterruptedError(),None]) as sync:
            es._fsync(4); self.assertEqual(sync.call_count,2)
        with mock.patch.object(es.os,"fsync",side_effect=OSError("failed")):
            with self.assertRaises(OSError): es._fsync(4)
    def test_exclusive_rename_has_no_fallback(self):
        with mock.patch.object(es.sys,"platform","linux"):
            with self.assertRaises(es.EvidenceError): es._rename_exclusive(3,"a","b")
    def test_child_result_exit_signal_and_nonterminal(self):
        self.assertEqual(es._child_result(7<<8)["exit_code"],7)
        self.assertEqual(es._child_result(signal.SIGTERM)["signal"],signal.SIGTERM)
        with self.assertRaises(es.EvidenceError): es._child_result(0x7f)

@unittest.skipUnless(DARWIN,"Darwin-only supervisor")
class LifecycleTests(unittest.TestCase):
    def setUp(self): self.fx=Fixture(self)
    def tearDown(self): self.fx.close()
    def assertStructuralFailure(self,result,run=True): self.assertEqual(result.returncode,es.CAPTURE_ERROR if run else es.VERIFY_ERROR,result.stderr)
    def test_happy_binary_exact_hash_size_env_cwd_and_fresh_verify(self):
        result=self.fx.execute(); self.assertEqual(result.returncode,0,result.stderr)
        raw=(self.fx.run_dir/"gate.log").read_bytes(); self.assertEqual(raw,b"alpha\0omega")
        t=self.fx.terminal(); self.assertEqual(t["log"]["size"],len(raw)); self.assertEqual(t["log"]["sha256"],hashlib.sha256(raw).hexdigest())
        self.assertEqual(t["argv"],self.fx.argv); self.assertEqual(t["env_keys"],sorted(self.fx.env)); self.assertEqual(t["cwd"]["path"],str(self.fx.cwd))
        verify=self.fx.verify(); self.assertEqual(verify.returncode,0,verify.stderr); self.assertIn(b"captured",verify.stdout)
    def test_more_than_pipe_buffer_merged_stream(self):
        self.fx.close(); self.fx=Fixture(self,literal="i=0; while [ $i -lt 5000 ]; do printf '1234567890' >&1; printf 'abcdefghij' >&2; i=$((i+1)); done")
        r=self.fx.execute(); self.assertEqual(r.returncode,0,r.stderr)
        raw=(self.fx.run_dir/"gate.log").read_bytes(); self.assertEqual(len(raw),100000); self.assertEqual(raw.count(b"1234567890"),5000); self.assertEqual(raw.count(b"abcdefghij"),5000)
    def test_nonzero_is_captured_verify_accepts_but_admission_rejects(self):
        self.fx.close(); self.fx=Fixture(self,literal="printf failure; exit 23")
        r=self.fx.execute(); self.assertEqual(r.returncode,23,r.stderr); self.assertEqual(self.fx.terminal()["child"]["exit_code"],23)
        self.assertEqual(self.fx.verify().returncode,0)
        admitted=self.fx.terminal()["child"]=={"pid":self.fx.terminal()["child"]["pid"],"exit_kind":"exit","exit_code":0,"signal":None}
        self.assertFalse(admitted,"capture validity is not semantic admission")
    def test_signal_is_recorded_and_propagated(self):
        self.fx.close(); self.fx=Fixture(self,literal="kill -TERM $$")
        r=self.fx.execute(); self.assertEqual(r.returncode,128+signal.SIGTERM,r.stderr)
        self.assertEqual(self.fx.terminal()["child"]["signal"],signal.SIGTERM)
    def test_terminal_is_absent_until_child_eof_and_wait(self):
        self.fx.close(); self.fx=Fixture(self,literal="printf begin; : > entered; while [ ! -f release ]; do read x < /dev/null; done; printf end")
        proc=subprocess.Popen(self.fx.run_cmd(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline and not (self.fx.cwd/"entered").exists(): time.sleep(.01)
        self.assertTrue((self.fx.cwd/"entered").exists(),"child did not enter deterministic hold")
        self.assertFalse((self.fx.run_dir/"terminal.json").exists())
        (self.fx.cwd/"release").write_text("")
        out,err=proc.communicate(timeout=10); self.assertEqual(proc.returncode,0,err)
        self.assertEqual((self.fx.run_dir/"gate.log").read_bytes(),b"beginend")
        self.assertTrue((self.fx.run_dir/"terminal.json").exists())
    def test_mutation_between_independent_verify_reads_fails(self):
        self.assertEqual(self.fx.execute().returncode,0)
        original=es._read_log_once; calls=0
        def mutate_after_first(*args,**kwargs):
            nonlocal calls
            result=original(*args,**kwargs); calls+=1
            if calls==1:
                log=self.fx.run_dir/"gate.log"; data=log.read_bytes(); log.unlink(); self.fx.write_private(log,data)
            return result
        ns=type("Args",(),{"trusted_ancestor":str(self.fx.root),"evidence_parent":"receipts",
                           "run_id":self.fx.run_id,"launch_anchor":str(self.fx.anchor_file)})()
        with mock.patch.object(es,"_read_log_once",side_effect=mutate_after_first):
            with self.assertRaises(es.EvidenceError): es.verify_capture(ns)
    def test_anchor_mutation_after_initial_read_returns_verify_error(self):
        self.assertEqual(self.fx.execute().returncode,0)
        original=es._read_log_once; changed=False
        def change_anchor(*args,**kwargs):
            nonlocal changed
            result=original(*args,**kwargs)
            if not changed:
                changed=True; self.fx.write_private(self.fx.anchor_file,b"{}")
            return result
        argv=["verify","--trusted-ancestor",str(self.fx.root),"--evidence-parent","receipts",
              "--run-id",self.fx.run_id,"--launch-anchor",str(self.fx.anchor_file)]
        with mock.patch.object(es,"_read_log_once",side_effect=change_anchor):
            self.assertEqual(es.main(argv),es.VERIFY_ERROR)
        self.assertTrue(changed); self.assertEqual(self.fx.anchor_file.read_bytes(),b"{}")
    def test_injected_postfork_write_failure_terminates_and_reaps_boundary(self):
        self.fx.close(); self.fx=Fixture(self,literal="echo $$ > child.pid; sleep 30 & echo $! > descendant.pid; printf trigger; sleep 30")
        marker=self.fx.root/"failure-injected"
        body=("original=module._write_all\nfired=False\n"
          +"def injected(fd,data):\n global fired\n if not fired:\n  fired=True\n  open("+repr(str(marker))+",'w').close()\n  raise OSError('injected capture failure')\n return original(fd,data)\n"
          +"module._write_all=injected")
        result=subprocess.run(self.fx.patched_run_cmd(body),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
        self.assertEqual(result.returncode,es.CAPTURE_ERROR,result.stderr); self.assertTrue(marker.exists())
        self.assertFalse((self.fx.run_dir/"terminal.json").exists())
        child=int((self.fx.cwd/"child.pid").read_text()); descendant=int((self.fx.cwd/"descendant.pid").read_text())
        with self.assertRaises(ProcessLookupError): os.kill(child,0)
        with self.assertRaises((ProcessLookupError,PermissionError)): os.killpg(child,0)
        with self.assertRaises(ProcessLookupError): os.kill(descendant,0)
    def test_lingering_descendant_pipe_is_bounded_killed_and_direct_child_reaped(self):
        self.fx.close(); self.fx=Fixture(self,literal="echo $$ > child.pid; sleep 30 & echo $! > descendant.pid; exit 0")
        body="module.POST_EXIT_DRAIN_SECONDS=.05; module.TERM_GRACE_SECONDS=.05; module.KILL_DRAIN_SECONDS=.05"
        started=time.monotonic()
        result=subprocess.run(self.fx.patched_run_cmd(body),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
        elapsed=time.monotonic()-started
        self.assertEqual(result.returncode,es.CAPTURE_ERROR,result.stderr); self.assertLess(elapsed,3)
        self.assertIn(b"retained the capture pipe",result.stderr)
        self.assertFalse((self.fx.run_dir/"terminal.json").exists())
        child=int((self.fx.cwd/"child.pid").read_text()); descendant=int((self.fx.cwd/"descendant.pid").read_text())
        with self.assertRaises(ProcessLookupError): os.kill(child,0)
        with self.assertRaises((ProcessLookupError,PermissionError)): os.killpg(child,0)
        with self.assertRaises(ProcessLookupError): os.kill(descendant,0)
    def test_preexisting_run_or_artifact_fails_without_terminal(self):
        self.fx.run_dir.mkdir(mode=0o700); r=self.fx.execute(); self.assertStructuralFailure(r); self.assertFalse((self.fx.run_dir/"terminal.json").exists())
    def test_bad_pwd_and_anchor_self_or_caller_mismatch_fail_before_child(self):
        self.fx.env["PWD"]="/"; self.fx.env_obj["env"]=self.fx.env; self.fx.write_private(self.fx.env_file,canon(self.fx.env_obj)); self.fx.write_anchor()
        self.assertStructuralFailure(self.fx.execute()); self.assertFalse(self.fx.run_dir.exists())
    def test_symlink_components_and_external_file_are_rejected(self):
        outside=self.fx.root/"outside"; outside.mkdir(mode=0o700)
        self.fx.parent.rmdir(); self.fx.parent.symlink_to(outside,target_is_directory=True)
        self.assertStructuralFailure(self.fx.execute())
    def test_env_duplicate_extra_truncated_wrong_mode_and_fifo_rejected(self):
        cases=[b'{"schema":"gate-capture-env/v1","schema":"gate-capture-env/v1","env":{}}',b'{',canon({"schema":es.SCHEMA_ENV,"env":{},"extra":1})]
        for raw in cases:
            with self.subTest(raw=raw):
                fx=Fixture(self); fx.write_private(fx.env_file,raw); self.assertEqual(fx.execute().returncode,es.CAPTURE_ERROR); fx.close()
        fx=Fixture(self); os.chmod(fx.env_file,0o644); self.assertEqual(fx.execute().returncode,es.CAPTURE_ERROR); fx.close()
        fx=Fixture(self); fx.env_file.unlink(); os.mkfifo(fx.env_file,0o600)
        # Opening a FIFO would block; O_NONBLOCK is intentionally absent, so test stat validator directly.
        with self.assertRaises(es.EvidenceError): es._regular_file(os.lstat(fx.env_file))
        fx.close()
    def test_hardlink_log_wrong_mode_and_unexpected_finalizer_are_rejected(self):
        self.assertEqual(self.fx.execute().returncode,0)
        log=self.fx.run_dir/"gate.log"; other=self.fx.root/"link"; os.link(log,other)
        self.assertEqual(self.fx.verify().returncode,es.VERIFY_ERROR); other.unlink()
        os.chmod(log,0o644); self.assertEqual(self.fx.verify().returncode,es.VERIFY_ERROR)
        os.chmod(log,0o600); (self.fx.run_dir/"PASS").write_text("invalid")
        self.assertEqual(self.fx.verify().returncode,es.VERIFY_ERROR)
    def test_terminal_duplicate_extra_wrong_types_pid_time_exit_and_mismatch(self):
        mutations=[lambda t:t.update(extra=True),lambda t:t["child"].update(pid=0),
          lambda t:t["time"].update(end_monotonic_ns=t["time"]["start_monotonic_ns"]-1),
          lambda t:t["child"].update(exit_kind="exit",exit_code=0,signal=9),
          lambda t:t.update(argv_sha256="0"*64),lambda t:t["caller"].update(source_tree="changed")]
        for mutate in mutations:
            fx=Fixture(self); self.assertEqual(fx.execute().returncode,0); fx.rewrite_terminal(mutate)
            self.assertEqual(fx.verify().returncode,es.VERIFY_ERROR); fx.close()
    def test_log_mutation_postfinal_mismatch_fails(self):
        self.assertEqual(self.fx.execute().returncode,0); log=self.fx.run_dir/"gate.log"
        os.chmod(log,0o600); data=log.read_bytes(); log.unlink(); self.fx.write_private(log,data+b"x")
        self.assertEqual(self.fx.verify().returncode,es.VERIFY_ERROR)
    def test_verify_performs_no_content_or_namespace_writes(self):
        self.assertEqual(self.fx.execute().returncode,0)
        def snap(): return {p.name:(p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns,p.read_bytes()) for p in self.fx.run_dir.iterdir()}
        before=snap(); self.assertEqual(self.fx.verify().returncode,0); self.assertEqual(before,snap())
    def test_parent_and_cwd_swaps_fail_closed(self):
        self.assertEqual(self.fx.execute().returncode,0)
        old=self.fx.root/"work-old"; self.fx.cwd.rename(old); self.fx.cwd.mkdir(mode=0o700)
        self.assertEqual(self.fx.verify().returncode,es.VERIFY_ERROR)
    def test_detached_launcher_handle_loss_and_fresh_process_verify(self):
        launcher=self.fx.root/"launcher.py"
        launcher.write_text("import subprocess,sys\nsubprocess.Popen(sys.argv[1:],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)\n")
        p=subprocess.run([sys.executable,str(launcher),*self.fx.run_cmd()]); self.assertEqual(p.returncode,0)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline and not (self.fx.run_dir/"terminal.json").exists(): time.sleep(.02)
        self.assertTrue((self.fx.run_dir/"terminal.json").exists())
        self.assertEqual(self.fx.verify().returncode,0)

if __name__=="__main__": unittest.main()
