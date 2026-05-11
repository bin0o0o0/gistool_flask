# Agent Notes

## GitHub push through Clash Verge on this machine

If `git push` to GitHub fails from this repository while `pull` or `ls-remote`
sometimes works, do not assume the commit is too large or that credentials are
wrong. On this machine the working solution was to make this repository use
Clash Verge's HTTP proxy endpoint, not the SOCKS/TUN path.

Observed failing symptoms:

```text
OpenSSL SSL_connect: SSL_ERROR_SYSCALL in connection to github.com:443
OpenSSL SSL_read: SSL_ERROR_SYSCALL, errno 0
RPC failed; HTTP 408
send-pack: unexpected disconnect while reading sideband packet
Failed to connect to github.com port 443
```

Important context:

- Clash Verge may be in Global mode with TUN enabled and still fail for Git
  push uploads.
- Low ping latency in Clash does not prove GitHub HTTPS upload stability.
- `git pull` can succeed while `git push` fails because push is a longer HTTPS
  upload request.
- SSH was not reliable here: both `github.com:22` and `ssh.github.com:443`
  timed out in the tested network.

The fix that worked:

```powershell
git -c http.proxy=http://127.0.0.1:7897 `
    -c https.proxy=http://127.0.0.1:7897 `
    -c http.version=HTTP/1.1 `
    -c http.lowSpeedLimit=0 `
    -c http.lowSpeedTime=999999 `
    push --porcelain origin codex/gis-tool
```

After confirming that worked, set the proxy locally for this repository only:

```powershell
git config --local http.proxy http://127.0.0.1:7897
git config --local https.proxy http://127.0.0.1:7897
```

Verify with:

```powershell
git config --local --get-regexp "^http\.proxy$|^https\.proxy$"
git ls-remote origin refs/heads/codex/gis-tool
```

Why local config:

- It avoids changing the user's global Git behavior for other projects.
- VS Code Git commands launched inside this repository will also pick up the
  local proxy configuration.
- It keeps the known-good workaround close to the repo where the issue was
  observed.

Do not remove assets or rewrite application code just to reduce push size before
trying the HTTP proxy endpoint above. In the observed case, a roughly 2 MB PNG
was not the root cause; the failing path was the Git HTTPS upload transport.
