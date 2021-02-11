#!/bin/bash
''':'
command -v python  >/dev/null 2>&1 && exec python  "$0" "$@"
command -v python3 >/dev/null 2>&1 && exec python3 "$0" "$@"
command -v python2 >/dev/null 2>&1 && exec python2 "$0" "$@"
>&2 echo "error: cannot find python"
exit 1
'''

# See https://gist.github.com/zsimic/c39dd9686c6d6b0d149a67ff23286b99 for docs on how to use

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.parse
from collections import defaultdict

try:
    from urllib.request import urlopen, Request  # python3

except ImportError:
    from urllib2 import urlopen, Request  # noqa, python2


def get_dt(fmt):
    dt = datetime.datetime.now()
    return dt.strftime(fmt)


def get_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)

    except Exception:
        return {}


def is_root():
    if hasattr(os, "geteuid"):
        return os.geteuid() == 0


class LinodeDDns(object):
    def __init__(self, cfg_folder):
        self.url = "https://api.linode.com/v4"
        self.folder = cfg_folder
        self.cfg_path = os.path.join(self.folder, "linode-ddns.json")
        self.last_ip_path = os.path.join(self.folder, ".linode-ddns-ip")
        self.cfg = get_json(self.cfg_path)
        self._mock = self.cfg.get("_mock", {})
        self.token = self.cfg.get("token")
        self.records = self.cfg.get("records")
        # All settings other than 'token' and 'records' are used for testing
        self.commit = is_root()
        self.logfile = self.cfg.get("logfile", "/var/log/messages")
        self._current_ip = None
        self._headers = None
        self._hostname = None
        self._last_ip = None

    @property
    def current_ip(self):
        if self._current_ip is None:
            default = None
            ips = {}
            output = self.program_output("/bin/ip", "-4", "route")
            if output:
                for line in output.splitlines():
                    if "linkdown" not in line:
                        m = re.search(r" dev (\S+)", line)
                        if m:
                            name = m.group(1)
                            if line.startswith("default"):
                                default = name

                            else:
                                m = re.search(r" src (\S+)", line)
                                if m:
                                    ips[name] = m.group(1)

            self._current_ip = ips.get(default) or ""

        return self._current_ip

    @property
    def headers(self):
        if self._headers is None:
            self._headers = {"Content-type": "application/json", "Authorization": "Bearer %s" % self.token}

        return self._headers

    @property
    def last_ip(self):
        if self._last_ip is None:
            try:
                with open(self.last_ip_path) as fh:
                    line = fh.readline()
                    self._last_ip = line.strip()

            except Exception:
                self._last_ip = ""

        return self._last_ip

    @property
    def hostname(self):
        if self._hostname is None:
            cmd = "/bin/hostname"
            if os.path.exists(cmd):
                self._hostname = self.program_output(cmd)

            else:
                self._hostname = os.environ.get("COMPUTERNAME") or ""

        return self._hostname

    def program_output(self, program, *args, default=""):
        m = self._mock.get(program)
        if m:
            return m

        try:
            p = subprocess.Popen([program] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, _ = p.communicate()
            if isinstance(output, bytes):
                output = output.decode("utf-8")

            return output and output.strip()

        except Exception:
            return default

    def save_ip(self):
        if self.current_ip and (self.commit or os.environ.get("PYTEST_CURRENT_TEST")):
            with open(self.last_ip_path, "w") as fh:
                fh.write("%s\n" % self.current_ip)
                fh.write("# Updated on %s for %s\n" % (get_dt("%Y-%m-%d %H:%M:%S"), self.records))

    def abort(self, message):
        self.log(message)
        sys.exit(1)

    def log(self, message):
        dt = get_dt("%b %d %H:%M:%S")
        message = "%s %s linode-ddns: %s" % (dt, self.hostname, message)
        if self.logfile:
            try:
                with open(self.logfile, "a") as fh:
                    fh.write(message)
                    if not message.endswith("\n"):
                        fh.write("\n")

                    return

            except Exception:
                pass

        print(message)

    def as_json(self):
        result = dict(token=self.token)
        if self.records:
            result["records"] = self.records

        return "%s\n" % json.dumps(result, sort_keys=True, indent=2)

    def save_json(self):
        if self.token:
            with open(self.cfg_path, "w") as fh:
                fh.write(self.as_json())

    def get_url(self, entrypoint):
        return "%s/%s" % (self.url, entrypoint.lstrip("/"))

    def put(self, entrypoint, data):
        url = self.get_url(entrypoint)
        if self.commit:
            self.rest_request(url, data=data, headers=self.headers, method="PUT")

        else:
            self.log("Would PUT %s %s" % (entrypoint, data))

    def get(self, entrypoint, **params):
        url = self.get_url(entrypoint)
        return self.rest_request(url, headers=self.headers, **params)

    def rest_request(self, url, data=None, headers=None, method="GET", **params):
        m = self._mock.get(os.path.basename(url))
        if m:
            return m

        if params:
            query_string = urllib.parse.urlencode(params)
            url = url + "?" + query_string

        request = Request(url, headers=headers)
        if not hasattr(request, "get_method"):
            request.get_method = lambda *_, **__: method

        response = urlopen(request, data=data).read()
        return json.loads(response)

    def get_paginated(self, entrypoint, max_pages=10, **params):
        url = self.get_url(entrypoint)
        result = []
        while max_pages > 0:
            max_pages -= 1
            data = self.rest_request(url, headers=self.headers, method="GET", **params)
            if not isinstance(data, dict) or "ERRORARRAY" in data:
                raise Exception("Linode query failed: %s" % data)

            result.extend(data.get("data", []))
            page = data.get("page")
            pages = data.get("pages")
            if not page or not pages or page >= pages:
                return result

            params["page"] = page + 1

        return result

    def get_domains(self, fatal=True):
        data = self.get_paginated("domains")
        if fatal and not data:
            sys.exit("No domains found")

        return [LinodeDomain(d) for d in data]


class LinodeDomain(object):
    def __init__(self, data):
        self.id = data.get("id")
        self.type = data.get("type")
        self.domain = data.get("domain")
        self.status = data.get("status")
        self.record = None  # Associated record found for the matching name we're looking for, if any

    def __eq__(self, other):
        return self.domain == other.domain

    def __lt__(self, other):
        return self.domain < other.domain


def ask_user(message):
    from_env = os.environ.get("LINODE_DDNS_TOKEN")
    if from_env:
        return from_env

    try:
        compatible_input = raw_input

    except NameError:
        compatible_input = input

    return compatible_input(message)


def main(args=None):
    """
    Update linode dns
    """
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--cfg", "-c", default="~/.ssh", help="Folder to use for config (used for testing).")
    parser.add_argument("--commit", action="store_true", help="Commit config (in interactive mode).")
    parser.add_argument("--interactive", "-i", help="Use for interactive initial setup, or querying/testing.")
    args = parser.parse_args(args=args)
    cfg_path = os.path.abspath(os.path.expanduser(args.cfg))
    if args.interactive and not os.path.isdir(cfg_path):
        os.mkdir(cfg_path, mode=0o700)

    linode = LinodeDDns(cfg_path)

    try:
        if args.interactive and not linode.token:
            token = ask_user("What is your linode token? (will be stored in %s):\n" % linode.cfg_path)
            if token and len(token) == 64:
                linode.token = token
                linode.save_json()

            else:
                linode.abort("Invalid token '%s', should be 64 characters long" % token)

        if not linode.token:
            linode.abort("No token configured in '%s'" % linode.cfg_path)

        if not args.interactive:
            # No args: running scheduled on router
            if not linode.records:
                linode.abort("Records not configured in %s" % linode.cfg_path)

            if not linode.current_ip or linode.current_ip == linode.last_ip:
                # When IP didn't change or couldn't determine IP (for example: internet is down), do nothing
                sys.exit(0)

            data = '{"target": "%s"}' % linode.current_ip
            for record in linode.records.split():
                linode.put("domains/%s" % record, data)

            linode.save_ip()
            action = "updated" if linode.commit else "would be updated"
            linode.log("Home IP %s to %s" % (action, linode.current_ip))
            sys.exit(0)

        if args.interactive == "status":
            print("Current IP: %s, Last IP: %s" % (linode.current_ip, linode.last_ip))
            sys.exit(0)

        if args.interactive == "domains":
            # Show all domains in linode account
            domains = linode.get_domains()
            print("%10s %-9s %-8s %s" % ("ID", "Status", "Type", "Domain"))
            for domain in sorted(domains):
                print("%10s %-9s %-8s %s" % (domain.id, domain.status, domain.type, domain.domain))

            sys.exit(0)

        # Show all records matching given 'args.interactive' host name
        desired_hostname, _, desired_domain = args.interactive.partition(".")
        domains = linode.get_domains()
        records_by_domain = defaultdict(list)
        all_records = []
        for domain in sorted(domains):
            if not desired_domain or desired_domain == domain.domain:
                for entry in linode.get_paginated("domains/%s/records" % domain.id):
                    name = entry.get("name")
                    if name != desired_hostname:
                        continue

                    target = entry.get("target")
                    ep = "%s/records/%s" % (domain.id, entry.get("id"))
                    if target and ":" not in target:
                        records_by_domain[domain.domain].append(ep)
                        all_records.append(ep)

        if not all_records:
            sys.exit("No records matching '%s' found" % args.interactive)

        linode.records = " ".join(all_records)
        print("%s linode DNS records found with hostname '%s':\n" % (len(all_records), desired_hostname))
        print("%-30s %s" % ("Entry point", "Domain"))
        for domain in sorted(records_by_domain.keys()):
            for ep in sorted(records_by_domain[domain]):
                print("%-30s %s" % (ep, domain))

        if args.commit:
            linode.save_json()
            print("\n%s saved, you should be good to go!" % linode.cfg_path)
            msg = "Contents of %s" % linode.cfg_path

        else:
            msg = "Re-run with --commit to save this to '%s':" % linode.cfg_path

        print("\n%s\n" % msg)
        print(linode.as_json())

    except Exception as e:
        linode.abort("FAILED: %s" % e)


if __name__ == "__main__":
    main()
