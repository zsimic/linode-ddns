import json
import os
import subprocess
import sys


TESTS = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(TESTS)
LINODE_DDNS = os.path.join(PROJECT, "linode-ddns.py")
TEST_TOKEN = "1234567890123456789012345678901234567890123456789012345678901234"

SAMPLE_ROUTE = """
default via 1.2.3.1 dev eth0 proto zebra
1.2.3.0/23 dev eth0 proto kernel scope link src 1.2.3.5
192.168.1.0/24 dev eth1 proto kernel scope link src 192.168.1.1
192.168.2.0/24 dev eth2 proto kernel scope link src 192.168.2.1 linkdown
"""

SAMPLE_MOCK = {
    "domains": {"data": [{"id": 1, "domain": "d1.com", "status": "active"}, {"id": 2, "domain": "d2.com", "status": "active"}]},
    "records": {"data": [{"id": 3, "name": "home", "target": "1.2.3.4"}, {"id": 4, "name": "www", "target": "1.2.3.4"}]},
    "/bin/ip": SAMPLE_ROUTE,
    "/bin/hostname": "test-router",
}


class ScriptTester(object):
    def __init__(self, base):
        self.base = base
        self.current = None
        self.cfg_folder = None
        self.cfg_path = None
        self.env = None

    def __repr__(self):
        return self.current or self.base

    def gen_cfg(self, cfg_path, env=None, **kwargs):
        self.current = cfg_path
        self.cfg_folder = os.path.join(self.base, cfg_path)
        self.cfg_path = os.path.join(self.cfg_folder, "linode-ddns.json")
        self.env = env
        if kwargs:
            if not os.path.isdir(self.cfg_folder):
                os.mkdir(self.cfg_folder)

            with open(self.cfg_path, "w") as fh:
                json.dump(kwargs, fh)

    @property
    def current_config(self):
        with open(self.cfg_path) as fh:
            return json.load(fh)

    def run_linode_ddns(self, args):
        cmd = [sys.executable, LINODE_DDNS]
        if "-c" not in args:
            cmd.append("-c")
            cmd.append(self.cfg_folder)

        cmd.extend(args)
        env = None
        if self.env:
            env = dict(os.environ)
            env.update(self.env)

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        output, error = p.communicate()
        if isinstance(output, bytes):
            output = output.decode("utf-8")

        if isinstance(error, bytes):
            error = error.decode("utf-8")

        output = "%s\n%s" % (output, error)
        return output.strip(), p.returncode

    def expect_failure(self, *args):
        output, exit_code = self.run_linode_ddns(args)
        assert exit_code != 0
        return output

    def expect_success(self, *args):
        output, exit_code = self.run_linode_ddns(args)
        assert exit_code == 0
        return output


def pop_file(path, delete=True):
    with open(path) as fh:
        lines = list(fh.readlines())

    if delete:
        os.unlink(path)

    return "\n".join(lines)


def test_setup(tmpdir):
    tmpdir = str(tmpdir)
    st = ScriptTester(tmpdir)

    # Verify that with an empty config, user gets asked
    st.gen_cfg("user-filled-bad", env={"TEST_ANSWER": "foo"})
    output = st.expect_failure("-i", "status")
    assert "should be 64 characters long" in output

    st.gen_cfg("user-filled-ok", env={"TEST_ANSWER": TEST_TOKEN})
    output = st.expect_success("-i", "status")
    assert st.current_config == {"token": TEST_TOKEN}
    assert "Current IP:" in output
    assert "Last IP:" in output

    # Verify that with an empty config, we properly error out
    st.gen_cfg("empty")
    output = st.expect_failure()
    assert "No token configured" in output

    # Verify that with a valid config file things go as expected
    logfile = os.path.join(tmpdir, "test.log")
    assert not os.path.exists(logfile)
    st.gen_cfg("valid", token=TEST_TOKEN, logfile=logfile, _mock=SAMPLE_MOCK)
    output = st.expect_success("-i", "domains")
    assert "d1.com" in output
    assert "d2.com" in output

    output = st.expect_success("-i", "home.d1.com")
    assert "1/records/3" in output
    assert "2/records/3" not in output

    output = st.expect_failure("-i", "home.example.com")
    assert "No linode DNS records matching" in output

    output = st.expect_success("-i", "home")
    assert "1/records/3" in output
    assert "2/records/3" in output
    assert "Re-run with --commit to save" in output

    output = st.expect_success("-i", "home", "--commit")
    assert st.current_config == {"records": "1/records/3 2/records/3", "token": TEST_TOKEN}
    assert "Contents of" in output
    assert not os.path.exists(logfile)

    st.gen_cfg("invalid", token=TEST_TOKEN, logfile=logfile, _mock=SAMPLE_MOCK)
    output = st.expect_failure()
    assert "Records not configured" in output
    assert "Records not configured" in pop_file(logfile)

    # Simulate headless run
    st.gen_cfg("valid", token=TEST_TOKEN, records="1/records/3", logfile=logfile, _mock=SAMPLE_MOCK)
    output = st.expect_success()
    assert "Would PUT" in output
    logged = pop_file(logfile)
    assert not os.path.exists(logfile)
    assert "Home IP would be updated to 1.2.3.5" in logged
    ipfile_path = os.path.join(st.cfg_folder, "linode-ddns-ip.txt")
    last_ip = pop_file(ipfile_path, delete=False)
    assert "1.2.3.5" in last_ip

    # 2nd run should do nothing
    output = st.expect_success()
    assert not output
    assert not os.path.exists(logfile)
    assert last_ip == pop_file(ipfile_path, delete=False)
