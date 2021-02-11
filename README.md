[![Tested with Github Actions](https://github.com/zsimic/linode-ddns/workflows/Tests/badge.svg)](https://github.com/zsimic/linode-ddns/actions)

# linode-ddns

Small script allowing to sync one's home IP records to Linode DNS.

Made initially to run periodically on an [Ubiquiti Edge Router Lite](https://www.ui.com/edgemax/edgerouter-lite/).

# TL;DR: quick install

If you're already familiar with this script, or don't care about the details
you can run this to expedite the setup:

```
curl -O https://raw.githubusercontent.com/zsimic/linode-ddns/main/install-linode-ddns.sh

sudo bash install-linode-ddns.sh

rm install-linode-ddns.sh
```

# How to use

Here's a more detailed walk-through, if you're interested to see how the script works.

### 1. Grab the script on the router

ssh to your router, then:

```
sudo curl -s -o/config/scripts/linode-ddns https://raw.githubusercontent.com/zsimic/linode-ddns/main/linode-ddns.py
sudo chmod 0755 /config/scripts/linode-ddns
```

### 2. Configure linode `token` and REST end-point `records`

The config `/root/.ssh/linode-ddns.json` will eventually look like this:

```json
{
  "records": "1234/records/4321",
  "token": "...linode token..."
}
```

This script can help with creating that file, and check that everything works properly
before we create a scheduled job to run it periodically.

First, we'll run the script with argument `domains` in order to:

- have the script ask you for your token (and store it in `/root/.ssh/linode-ddns.json`)
- double-check that things work (linode REST API query to list your domains)

Let's run:

```
sudo /config/scripts/linode-ddns -i domains
```

This will ask you to paste in your token, and will show you your linode domains.
If it works, next step is to add a reference to the linode DNS records to be updated.

If your domain is `example.com`, and you want to make `home.example.com` point to your home IP,
then you need to create an `A` DNS record [on linode](https://cloud.linode.com/domains) 
with hostname `home` (put some IP address manually there just to get the record created).

Next, we check that the script can find that record by running:

```
sudo /config/scripts/linode-ddns -i home.example.com
```

This should show your record.

Note that the script can update several records at the same time, if you have say
`home.domain1.com` and `home.domain2.com`, this script can update them all...

If you would like to update several domains at once, omit the domain part as in: 

```
sudo /config/scripts/linode-ddns -i home
```

Doing so will configure fetch a config that will update all hostnames `home` on all your domains.

Once you see what you expect, either take the output and save it to `/root/.ssh/linode-ddns.json`,
or run this to have the script do that for you:

```
sudo /config/scripts/linode-ddns -i home.example.com --commit
```

### 3. Test that the script works when invoked without arguments

All right, so now you should have an operational script that will update the IP when invoked without arguments.
We can try it out:

```
sudo /config/scripts/linode-ddns

sudo cat /root/.ssh/.linode-ddns-ip  # Should show your IP!

# Should show one log message stating that IP was updated
tail /var/log/messages

# If we run it again, nothing should happen
sudo /config/scripts/linode-ddns

# Only one "IP updated" message still
tail /var/log/messages
```

### 4. Schedule a job to run this script periodically

For example every 30 minutes:

```bash
configure
set system task-scheduler task linode-ddns interval 30m
set system task-scheduler task linode-ddns executable path /config/scripts/linode-ddns
commit
save
```


### 5. Double-check that it works unattended

To double-check that the task is getting triggered, you can do this:

```bash
# Force script to re-run by deleting the file where it remembers which IP it last saw
sudo rm /root/.ssh/.linode-ddns-ip

# Wait 30 minutes (or whatever time you scheduled)

# You should see evidence that the script ran:
sudo cat /root/.ssh/.linode-ddns-ip

# The logs should have a line saying: "... linode-ddns: Home IP updated to ..."
tail -f /var/log/messages
```
