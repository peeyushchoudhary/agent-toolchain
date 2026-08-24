#!/usr/bin/env python3
"""Darwin-only durable capture of one literal ``/bin/sh -c`` execution.

The supervisor captures bytes and process status.  It does not decide whether the
command succeeded semantically.  ``supervisor_sha256`` is SHA-256 over the exact
bytes of this file; an external controller puts that value in the launch anchor.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as _dt
import errno
import hashlib
import json
import os
import re
import signal
import stat
import struct
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

CAPTURE_ERROR = 125
VERIFY_ERROR = 2
SCHEMA_ENV = "gate-capture-env/v1"
SCHEMA_LAUNCH = "gate-capture-launch/v1"
SCHEMA_TERMINAL = "gate-capture-terminal/v1"
RUN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)

class EvidenceError(Exception):
    pass

@dataclass(frozen=True)
class BoundDir:
    path: str
    fd: int
    dev: int
    ino: int
    uid: int
    mode: int

    def identity(self) -> dict[str, Any]:
        return {"path": self.path, "dev": self.dev, "ino": self.ino,
                "uid": self.uid, "mode": self.mode}


def _fail(message: str) -> None:
    raise EvidenceError(message)


def _mode(st: os.stat_result) -> int:
    return stat.S_IMODE(st.st_mode)


def _validate_dir_stat(st: os.stat_result, *, leaf: bool) -> None:
    if not stat.S_ISDIR(st.st_mode):
        _fail("path component is not a directory")
    uid = os.getuid()
    if st.st_uid not in (0, uid):
        _fail("directory has an untrusted owner")
    mode = _mode(st)
    if mode & 0o022:
        # Root-owned sticky traversal directories are the only writable exception.
        if not (st.st_uid == 0 and mode & stat.S_ISVTX):
            _fail("directory is group/world writable")
    if leaf and st.st_uid != uid:
        _fail("bound directory is not owned by the caller")


def _parts_absolute(path: str) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/") or path == "/":
        _fail("path must be an absolute non-root path")
    if "\x00" in path:
        _fail("NUL in path")
    parts = path.split("/")[1:]
    if any(p in ("", ".", "..") for p in parts):
        _fail("non-canonical absolute path")
    return parts


def _parts_relative(path: str) -> list[str]:
    if not isinstance(path, str) or path.startswith("/") or "\x00" in path:
        _fail("path must be relative")
    parts = path.split("/")
    if not parts or any(p in ("", ".", "..") for p in parts):
        _fail("non-canonical relative path")
    return parts


def _open_dir_chain(start_fd: int, parts: list[str], display: str) -> BoundDir:
    fd = os.dup(start_fd)
    try:
        for index, part in enumerate(parts):
            newfd = os.open(part, os.O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC,
                            dir_fd=fd)
            os.close(fd)
            fd = newfd
            _validate_dir_stat(os.fstat(fd), leaf=index == len(parts) - 1)
        st = os.fstat(fd)
        return BoundDir(display, fd, st.st_dev, st.st_ino, st.st_uid, _mode(st))
    except Exception:
        try: os.close(fd)
        except OSError: pass
        raise


def bind_absolute_dir(path: str) -> BoundDir:
    root = os.open("/", os.O_RDONLY | O_DIRECTORY | O_CLOEXEC)
    try:
        return _open_dir_chain(root, _parts_absolute(path), path)
    finally:
        os.close(root)


def bind_relative_dir(parent: BoundDir, rel: str) -> BoundDir:
    display = parent.path.rstrip("/") + "/" + rel
    return _open_dir_chain(parent.fd, _parts_relative(rel), display)


def _revalidate(bound: BoundDir) -> None:
    fresh = bind_absolute_dir(bound.path)
    try:
        if (fresh.dev, fresh.ino, fresh.uid, fresh.mode) != (bound.dev, bound.ino, bound.uid, bound.mode):
            _fail("bound directory identity changed")
        st = os.fstat(bound.fd)
        _validate_dir_stat(st, leaf=True)
        if (st.st_dev, st.st_ino, st.st_uid, _mode(st)) != (bound.dev, bound.ino, bound.uid, bound.mode):
            _fail("held directory identity changed")
    finally:
        os.close(fresh.fd)


def _strict_object(data: Any, keys: set[str], what: str) -> dict[str, Any]:
    if type(data) is not dict or set(data) != keys:
        _fail(f"invalid {what} fields")
    return data


def _no_constant(value: str) -> None:
    _fail("non-finite JSON number")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            _fail("duplicate JSON key")
        out[key] = value
    return out


def parse_json_bytes(raw: bytes, what: str) -> Any:
    try:
        text = raw.decode("utf-8", "strict")
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_no_constant)
    except EvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise EvidenceError(f"invalid {what} JSON: {exc}") from exc


def canonical(data: Any, newline: bool = False) -> bytes:
    try:
        raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise EvidenceError(f"cannot encode canonical JSON: {exc}") from exc
    return raw + (b"\n" if newline else b"")


def _read_all(fd: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        try:
            chunk = os.read(fd, 1024 * 1024)
        except InterruptedError:
            continue
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        try:
            n = os.write(fd, view)
        except InterruptedError:
            continue
        if n <= 0:
            _fail("short write made no progress")
        view = view[n:]


def _regular_file(st: os.stat_result, mode: Optional[int] = None) -> None:
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_nlink != 1:
        _fail("artifact is not a private single-link regular file")
    actual = _mode(st)
    if mode is not None and actual != mode:
        _fail("artifact mode is invalid")
    if actual & 0o077:
        _fail("artifact is not private")


def _open_external(path: str) -> tuple[int, os.stat_result]:
    parts = _parts_absolute(path)
    root = os.open("/", os.O_RDONLY | O_DIRECTORY | O_CLOEXEC)
    directory: Optional[BoundDir] = None
    try:
        directory = _open_dir_chain(root, parts[:-1], "/" + "/".join(parts[:-1]))
        fd = os.open(parts[-1], os.O_RDONLY | O_NOFOLLOW | O_CLOEXEC, dir_fd=directory.fd)
        st = os.fstat(fd)
        _regular_file(st)
        return fd, st
    finally:
        os.close(root)
        if directory: os.close(directory.fd)


def read_external(path: str, what: str) -> tuple[bytes, os.stat_result]:
    fd, before = _open_external(path)
    try:
        raw = _read_all(fd)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != \
           (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            _fail(f"{what} changed while read")
        return raw, after
    finally:
        os.close(fd)


def argv_digest(argv: list[str]) -> str:
    h = hashlib.sha256(struct.pack(">Q", len(argv)))
    for arg in argv:
        try: raw = arg.encode("utf-8", "strict")
        except UnicodeEncodeError as exc: raise EvidenceError("argv is not UTF-8") from exc
        h.update(struct.pack(">Q", len(raw)))
        h.update(raw)
    return h.hexdigest()


def _identity3(value: Any, path_key: str, what: str) -> dict[str, Any]:
    obj = _strict_object(value, {path_key, "dev", "ino"}, what)
    if type(obj[path_key]) is not str or type(obj["dev"]) is not int or type(obj["ino"]) is not int:
        _fail(f"invalid {what} types")
    return obj


def parse_env(raw: bytes) -> tuple[dict[str, str], str, list[str]]:
    obj = _strict_object(parse_json_bytes(raw, "environment"), {"schema", "env"}, "environment")
    if obj["schema"] != SCHEMA_ENV or type(obj["env"]) is not dict:
        _fail("invalid environment schema")
    env: dict[str, str] = {}
    for key, value in obj["env"].items():
        if type(key) is not str or not key or "=" in key or "\x00" in key or type(value) is not str or "\x00" in value:
            _fail("invalid environment entry")
        try: key.encode("utf-8", "strict"); value.encode("utf-8", "strict")
        except UnicodeEncodeError as exc: raise EvidenceError("environment is not UTF-8") from exc
        env[key] = value
    return env, hashlib.sha256(canonical(obj)).hexdigest(), sorted(env)


def parse_anchor(raw: bytes) -> dict[str, Any]:
    keys = {"schema", "run_id", "argv", "argv_sha256", "env_sha256", "cwd",
            "trusted_ancestor", "evidence_parent", "supervisor_sha256", "caller"}
    obj = _strict_object(parse_json_bytes(raw, "launch anchor"), keys, "launch anchor")
    if obj["schema"] != SCHEMA_LAUNCH or type(obj["run_id"]) is not str:
        _fail("invalid launch anchor schema")
    if type(obj["argv"]) is not list or any(type(x) is not str for x in obj["argv"]):
        _fail("invalid anchor argv")
    for key in ("argv_sha256", "env_sha256", "supervisor_sha256"):
        if type(obj[key]) is not str or not re.fullmatch(r"[0-9a-f]{64}", obj[key]): _fail(f"invalid {key}")
    _identity3(obj["cwd"], "path", "anchor cwd")
    _identity3(obj["trusted_ancestor"], "path", "anchor ancestor")
    _identity3(obj["evidence_parent"], "relative_path", "anchor evidence parent")
    caller = _strict_object(obj["caller"], {"source_head", "source_tree", "toolchain_sha"}, "caller")
    if any(type(v) is not str or not v for v in caller.values()): _fail("invalid caller")
    return obj


def source_sha256() -> str:
    with open(__file__, "rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def _match_anchor(anchor: dict[str, Any], run_id: str, argv: list[str], env_digest: str,
                  cwd: BoundDir, ancestor: BoundDir, parent: BoundDir, parent_rel: str) -> None:
    if anchor["run_id"] != run_id or anchor["argv"] != argv or anchor["argv_sha256"] != argv_digest(argv):
        _fail("launch anchor argv/run mismatch")
    if anchor["env_sha256"] != env_digest or anchor["supervisor_sha256"] != source_sha256():
        _fail("launch anchor environment/supervisor mismatch")
    expected = ((anchor["cwd"], "path", cwd), (anchor["trusted_ancestor"], "path", ancestor),
                (anchor["evidence_parent"], "relative_path", parent))
    for obj, key, bound in expected:
        path_value = parent_rel if key == "relative_path" else bound.path
        if obj != {key: path_value, "dev": bound.dev, "ino": bound.ino}:
            _fail("launch anchor path identity mismatch")


def _rename_exclusive(dirfd: int, old: str, new: str) -> None:
    if sys.platform != "darwin": _fail("evidence supervisor requires Darwin")
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        fn = libc.renameatx_np
    except (OSError, AttributeError) as exc:
        raise EvidenceError("renameatx_np unavailable") from exc
    fn.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    fn.restype = ctypes.c_int
    if fn(dirfd, old.encode(), dirfd, new.encode(), 0x00000004) != 0: # RENAME_EXCL
        err = ctypes.get_errno()
        raise EvidenceError(f"exclusive rename failed: {os.strerror(err)}")


def _fsync(fd: int) -> None:
    while True:
        try: os.fsync(fd); return
        except InterruptedError: continue


def _wait_exact(pid: int) -> int:
    while True:
        try:
            got, status = os.waitpid(pid, 0)
        except InterruptedError:
            continue
        if got != pid: _fail("waitpid returned the wrong child")
        return status


def _child_result(status: int) -> dict[str, Any]:
    if os.WIFEXITED(status):
        return {"exit_kind": "exit", "exit_code": os.WEXITSTATUS(status), "signal": None}
    if os.WIFSIGNALED(status):
        return {"exit_kind": "signal", "exit_code": None, "signal": os.WTERMSIG(status)}
    _fail("child did not reach a terminal state")


def _read_log_once(run_fd: int, expected_hash: str, expected_size: int,
                   expected_identity: Optional[Tuple[int, int]] = None) -> dict[str, Any]:
    fd = os.open("gate.log", os.O_RDONLY | O_NOFOLLOW | O_CLOEXEC, dir_fd=run_fd)
    try:
        before = os.fstat(fd); _regular_file(before, 0o600)
        h = hashlib.sha256(); size = 0
        while True:
            try: chunk = os.read(fd, 1024 * 1024)
            except InterruptedError: continue
            if not chunk: break
            h.update(chunk); size += len(chunk)
        after = os.fstat(fd); _regular_file(after, 0o600)
        fields = lambda s: (s.st_dev,s.st_ino,_mode(s),s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if fields(before) != fields(after): _fail("final log mutated during read")
        if size != expected_size or h.hexdigest() != expected_hash or after.st_size != expected_size:
            _fail("final log content mismatch")
        if expected_identity and (after.st_dev, after.st_ino) != expected_identity:
            _fail("final log identity mismatch")
        return {"name":"gate.log", "dev":after.st_dev, "ino":after.st_ino,
                "mode":_mode(after), "nlink":after.st_nlink, "size":size,
                "sha256":h.hexdigest()}
    finally: os.close(fd)


def _snapshot(fd: int) -> tuple[tuple[str,int,int,int,int,int], ...]:
    names = sorted(os.listdir(fd))
    result=[]
    for name in names:
        st=os.stat(name, dir_fd=fd, follow_symlinks=False)
        result.append((name,st.st_dev,st.st_ino,st.st_mode,st.st_size,st.st_mtime_ns))
    return tuple(result)


def _create_run(parent: BoundDir, run_id: str) -> BoundDir:
    if not RUN_RE.fullmatch(run_id): _fail("invalid run id")
    os.mkdir(run_id, 0o700, dir_fd=parent.fd)
    run = bind_relative_dir(parent, run_id)
    if run.mode != 0o700: _fail("run directory mode is invalid")
    return run


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def run_capture(args: argparse.Namespace) -> int:
    if sys.platform != "darwin": _fail("evidence supervisor requires Darwin")
    argv=args.command
    if len(argv) != 3 or argv[0] != "/bin/sh" or argv[1] != "-c":
        _fail("run accepts exactly /bin/sh -c LITERAL")
    ancestor=parent=cwd=run=None
    logfd=None
    try:
        ancestor=bind_absolute_dir(args.trusted_ancestor)
        parent=bind_relative_dir(ancestor,args.evidence_parent)
        cwd=bind_absolute_dir(args.cwd)
        env_raw,_=read_external(args.env_file,"environment")
        env,env_digest,env_keys=parse_env(env_raw)
        if env.get("PWD") != cwd.path: _fail("environment PWD does not equal bound cwd")
        anchor_raw,_=read_external(args.launch_anchor,"launch anchor")
        anchor=parse_anchor(anchor_raw)
        _match_anchor(anchor,args.run_id,argv,env_digest,cwd,ancestor,parent,args.evidence_parent)
        for b in (ancestor,parent,cwd): _revalidate(b)
        run=_create_run(parent,args.run_id)
        for b in (ancestor,parent,cwd,run): _revalidate(b)
        logfd=os.open("gate.log.partial",os.O_RDWR|os.O_CREAT|os.O_EXCL|O_NOFOLLOW|O_CLOEXEC,
                      0o600,dir_fd=run.fd)
        _regular_file(os.fstat(logfd),0o600)
        readfd,writefd=os.pipe()
        os.set_inheritable(readfd,False); os.set_inheritable(writefd,False)
        try:
            try:
                os.setsid()
            except PermissionError:
                # A launcher may already have made us a process-group or session leader.
                if os.getpgrp() != os.getpid():
                    raise
            signal.signal(signal.SIGHUP,signal.SIG_IGN)
            started_utc=_utc_now(); started_mono=time.monotonic_ns()
            pid=os.fork()
            if pid==0:
                try:
                    os.close(readfd)
                    os.fchdir(cwd.fd)
                    os.dup2(writefd,1); os.dup2(writefd,2)
                    if writefd not in (1,2): os.close(writefd)
                    maxfd=os.sysconf("SC_OPEN_MAX")
                    os.closerange(3,min(int(maxfd),1_048_576))
                    os.execve("/bin/sh",argv,env)
                except BaseException:
                    os._exit(127)
            os.close(writefd); writefd=-1
            h=hashlib.sha256(); count=0
            while True:
                try: chunk=os.read(readfd,65536)
                except InterruptedError: continue
                if not chunk: break
                _write_all(logfd,chunk); h.update(chunk); count+=len(chunk)
            os.close(readfd); readfd=-1
            status=_wait_exact(pid)
            ended_mono=time.monotonic_ns(); ended_utc=_utc_now()
        finally:
            for fd in (readfd,writefd):
                if fd >= 0:
                    try: os.close(fd)
                    except OSError: pass
        _fsync(logfd)
        st=os.fstat(logfd); _regular_file(st,0o600)
        if st.st_size != count: _fail("streamed log size mismatch")
        os.lseek(logfd,0,os.SEEK_SET)
        held=_read_all(logfd)
        if len(held)!=count or hashlib.sha256(held).hexdigest()!=h.hexdigest():
            _fail("streamed log hash mismatch")
        for b in (ancestor,parent,cwd,run): _revalidate(b)
        _rename_exclusive(run.fd,"gate.log.partial","gate.log"); _fsync(run.fd)
        for b in (ancestor,parent,cwd,run): _revalidate(b)
        log1=_read_log_once(run.fd,h.hexdigest(),count,(st.st_dev,st.st_ino))
        for b in (ancestor,parent,cwd,run): _revalidate(b)
        log2=_read_log_once(run.fd,h.hexdigest(),count,(st.st_dev,st.st_ino))
        if log1 != log2: _fail("independent log reads disagree")
        child=_child_result(status)
        terminal={"schema":SCHEMA_TERMINAL,"run_id":args.run_id,"state":"captured",
          "supervisor":{"pid":os.getpid(),"source_sha256":source_sha256()},
          "child":{"pid":pid,**child},
          "time":{"start_utc":started_utc,"end_utc":ended_utc,
                  "start_monotonic_ns":started_mono,"end_monotonic_ns":ended_mono},
          "argv":argv,"argv_sha256":argv_digest(argv),"env_keys":env_keys,"env_sha256":env_digest,
          "cwd":cwd.identity(),"trusted_ancestor":ancestor.identity(),
          "evidence_parent":{"relative_path":args.evidence_parent,"dev":parent.dev,"ino":parent.ino,
                             "uid":parent.uid,"mode":parent.mode},
          "run_dir":{"relative_path":args.run_id,"dev":run.dev,"ino":run.ino,"uid":run.uid,"mode":run.mode},
          "launch_anchor_sha256":hashlib.sha256(anchor_raw).hexdigest(),"log":log1,"caller":anchor["caller"]}
        data=canonical(terminal,newline=True)
        tfd=os.open("terminal.json.partial",os.O_WRONLY|os.O_CREAT|os.O_EXCL|O_NOFOLLOW|O_CLOEXEC,
                    0o600,dir_fd=run.fd)
        try: _write_all(tfd,data); _fsync(tfd); _regular_file(os.fstat(tfd),0o600)
        finally: os.close(tfd)
        for b in (ancestor,parent,cwd,run): _revalidate(b)
        _rename_exclusive(run.fd,"terminal.json.partial","terminal.json"); _fsync(run.fd)
        for b in (ancestor,parent,cwd,run): _revalidate(b)
        # Final reads bind both publications after the last directory sync.
        _read_log_once(run.fd,h.hexdigest(),count,(log1["dev"],log1["ino"]))
        traw,_=read_artifact(run.fd,"terminal.json")
        if traw != data: _fail("published terminal mismatch")
        print(f"captured: child {child['exit_kind']} " + str(child['exit_code'] if child['exit_kind']=='exit' else child['signal']))
        return child["exit_code"] if child["exit_kind"]=="exit" else 128+child["signal"]
    finally:
        if logfd is not None:
            try: os.close(logfd)
            except OSError: pass
        for b in (run,cwd,parent,ancestor):
            if b is not None:
                try: os.close(b.fd)
                except OSError: pass


def read_artifact(run_fd: int,name: str) -> tuple[bytes,os.stat_result]:
    fd=os.open(name,os.O_RDONLY|O_NOFOLLOW|O_CLOEXEC,dir_fd=run_fd)
    try:
        before=os.fstat(fd); _regular_file(before,0o600); raw=_read_all(fd); after=os.fstat(fd)
        fields=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mode,s.st_nlink,s.st_mtime_ns,s.st_ctime_ns)
        if fields(before)!=fields(after): _fail(f"{name} mutated during read")
        return raw,after
    finally: os.close(fd)


def _validate_terminal(t: Any) -> dict[str,Any]:
    keys={"schema","run_id","state","supervisor","child","time","argv","argv_sha256","env_keys",
          "env_sha256","cwd","trusted_ancestor","evidence_parent","run_dir","launch_anchor_sha256","log","caller"}
    t=_strict_object(t,keys,"terminal")
    if t["schema"]!=SCHEMA_TERMINAL or t["state"]!="captured": _fail("invalid terminal schema/state")
    if type(t["run_id"]) is not str or not RUN_RE.fullmatch(t["run_id"]): _fail("invalid terminal run id")
    sup=_strict_object(t["supervisor"],{"pid","source_sha256"},"supervisor")
    child=_strict_object(t["child"],{"pid","exit_kind","exit_code","signal"},"child")
    if (type(sup["pid"]) is not int or sup["pid"] <= 0 or type(child["pid"]) is not int
            or child["pid"] <= 0 or child["pid"] == sup["pid"]):
        _fail("invalid pid")
    if type(sup["source_sha256"]) is not str: _fail("invalid supervisor hash")
    if child["exit_kind"]=="exit":
        if type(child["exit_code"]) is not int or not 0<=child["exit_code"]<=255 or child["signal"] is not None: _fail("invalid exit result")
    elif child["exit_kind"]=="signal":
        if child["exit_code"] is not None or type(child["signal"]) is not int or not 1<=child["signal"]<128: _fail("invalid signal result")
    else: _fail("invalid exit kind")
    tm=_strict_object(t["time"],{"start_utc","end_utc","start_monotonic_ns","end_monotonic_ns"},"time")
    for k in ("start_utc","end_utc"):
        if type(tm[k]) is not str or not tm[k].endswith("Z"):
            _fail("invalid UTC time")
        try: _dt.datetime.fromisoformat(tm[k].replace("Z","+00:00"))
        except ValueError: _fail("invalid UTC time")
    if type(tm["start_monotonic_ns"]) is not int or type(tm["end_monotonic_ns"]) is not int or tm["end_monotonic_ns"]<tm["start_monotonic_ns"] or tm["end_utc"]<tm["start_utc"]: _fail("invalid time ordering")
    if (type(t["argv"]) is not list or len(t["argv"]) != 3 or t["argv"][0:2] != ["/bin/sh", "-c"]
            or any(type(x) is not str for x in t["argv"])
            or t["argv_sha256"] != argv_digest(t["argv"])):
        _fail("invalid terminal argv")
    if type(t["env_keys"]) is not list or any(type(x) is not str for x in t["env_keys"]) or t["env_keys"]!=sorted(set(t["env_keys"])): _fail("invalid env keys")
    for key in ("env_sha256","launch_anchor_sha256"):
        if type(t[key]) is not str or not re.fullmatch(r"[0-9a-f]{64}",t[key]): _fail(f"invalid {key}")
    for key,pathkey in (("cwd","path"),("trusted_ancestor","path"),("evidence_parent","relative_path"),("run_dir","relative_path")):
        obj=_strict_object(t[key],{pathkey,"dev","ino","uid","mode"},key)
        if type(obj[pathkey]) is not str or any(type(obj[x]) is not int for x in ("dev","ino","uid","mode")): _fail(f"invalid {key}")
    log=_strict_object(t["log"],{"name","dev","ino","mode","nlink","size","sha256"},"log")
    if log["name"]!="gate.log" or any(type(log[x]) is not int for x in ("dev","ino","mode","nlink","size")) or type(log["sha256"]) is not str: _fail("invalid log")
    caller=_strict_object(t["caller"],{"source_head","source_tree","toolchain_sha"},"caller")
    if any(type(x) is not str or not x for x in caller.values()): _fail("invalid caller")
    return t


def verify_capture(args: argparse.Namespace) -> int:
    if sys.platform!="darwin": _fail("evidence supervisor requires Darwin")
    ancestor=parent=run=cwd=None
    try:
        ancestor=bind_absolute_dir(args.trusted_ancestor); parent=bind_relative_dir(ancestor,args.evidence_parent)
        if not RUN_RE.fullmatch(args.run_id): _fail("invalid run id")
        run=bind_relative_dir(parent,args.run_id)
        before=_snapshot(run.fd)
        if {x[0] for x in before}!={"gate.log","terminal.json"}: _fail("unexpected run directory entries")
        anchor_raw,_=read_external(args.launch_anchor,"launch anchor"); anchor=parse_anchor(anchor_raw)
        traw,_=read_artifact(run.fd,"terminal.json"); terminal=_validate_terminal(parse_json_bytes(traw,"terminal"))
        if traw!=canonical(terminal,newline=True): _fail("terminal is not canonical")
        if anchor["run_id"]!=args.run_id or terminal["run_id"]!=args.run_id: _fail("run id mismatch")
        if hashlib.sha256(anchor_raw).hexdigest()!=terminal["launch_anchor_sha256"]: _fail("anchor digest mismatch")
        if anchor["supervisor_sha256"]!=source_sha256() or terminal["supervisor"]["source_sha256"]!=source_sha256(): _fail("supervisor source mismatch")
        if terminal["argv"]!=anchor["argv"] or terminal["argv_sha256"]!=anchor["argv_sha256"] or terminal["env_sha256"]!=anchor["env_sha256"] or terminal["caller"]!=anchor["caller"]: _fail("anchor/terminal mismatch")
        if anchor["trusted_ancestor"]!={"path":ancestor.path,"dev":ancestor.dev,"ino":ancestor.ino}: _fail("ancestor mismatch")
        if anchor["evidence_parent"]!={"relative_path":args.evidence_parent,"dev":parent.dev,"ino":parent.ino}: _fail("evidence parent mismatch")
        cwd=bind_absolute_dir(anchor["cwd"]["path"])
        if anchor["cwd"]!={"path":cwd.path,"dev":cwd.dev,"ino":cwd.ino}: _fail("cwd mismatch")
        identities=((terminal["cwd"],cwd),(terminal["trusted_ancestor"],ancestor))
        for obj,b in identities:
            if obj!=b.identity(): _fail("terminal directory identity mismatch")
        if terminal["evidence_parent"]!={"relative_path":args.evidence_parent,"dev":parent.dev,"ino":parent.ino,"uid":parent.uid,"mode":parent.mode}: _fail("terminal parent mismatch")
        if terminal["run_dir"]!={"relative_path":args.run_id,"dev":run.dev,"ino":run.ino,"uid":run.uid,"mode":run.mode}: _fail("terminal run directory mismatch")
        for b in (ancestor,parent,cwd,run): _revalidate(b)
        expected=terminal["log"]
        got1=_read_log_once(run.fd,expected["sha256"],expected["size"],(expected["dev"],expected["ino"]))
        if got1!=expected: _fail("terminal log identity mismatch")
        for b in (ancestor,parent,cwd,run): _revalidate(b)
        got2=_read_log_once(run.fd,expected["sha256"],expected["size"],(expected["dev"],expected["ino"]))
        if got2!=expected: _fail("second log read mismatch")
        for b in (ancestor,parent,cwd,run): _revalidate(b)
        if _snapshot(run.fd)!=before: _fail("run directory changed during verification")
        child=terminal["child"]
        print(f"captured: child {child['exit_kind']} " + str(child['exit_code'] if child['exit_kind']=='exit' else child['signal']))
        return 0
    finally:
        for b in (cwd,run,parent,ancestor):
            if b:
                try: os.close(b.fd)
                except OSError: pass


def parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="Darwin evidence capture supervisor")
    sub=p.add_subparsers(dest="action",required=True)
    run=sub.add_parser("run"); verify=sub.add_parser("verify")
    for q in (run,verify):
        q.add_argument("--trusted-ancestor",required=True); q.add_argument("--evidence-parent",required=True)
        q.add_argument("--run-id",required=True); q.add_argument("--launch-anchor",required=True)
    run.add_argument("--cwd",required=True); run.add_argument("--env-file",required=True)
    run.add_argument("command",nargs=argparse.REMAINDER)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args=parser().parse_args(argv)
    if args.action=="run" and args.command[:1]==["--"]: args.command=args.command[1:]
    try: return run_capture(args) if args.action=="run" else verify_capture(args)
    except EvidenceError as exc:
        print(f"evidence-supervisor: {exc}",file=sys.stderr)
        return CAPTURE_ERROR if args.action=="run" else VERIFY_ERROR
    except (OSError,ValueError) as exc:
        print(f"evidence-supervisor: structural failure: {exc}",file=sys.stderr)
        return CAPTURE_ERROR if args.action=="run" else VERIFY_ERROR

if __name__=="__main__":
    raise SystemExit(main())
