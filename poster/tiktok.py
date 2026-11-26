#!/usr/bin/env python3
"""TikTok Content Posting API — upload a video to the creator's TikTok inbox as a draft.

Runs inside GitHub Actions. Secrets come from environment variables, never from arguments,
and are never printed.

  python3 poster/tiktok.py exchange   # one-time: AUTH_CODE -> refresh token  (authorize.yml)
  python3 poster/tiktok.py upload video.mp4                                  (post.yml)

Env:
  TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET   app credentials (Actions secrets)
  TIKTOK_REFRESH_TOKEN                      current refresh token (Actions secret, rotates)
  AUTH_CODE, REDIRECT_URI, CODE_VERIFIER    only for `exchange`
  GITHUB_OUTPUT                             set by Actions; the new refresh token is written to
                                            the file NEW_REFRESH_TOKEN_FILE, never to stdout

API reference (checked Nov 2026):
  token:   POST https://open.tiktokapis.com/v2/oauth/token/            (form-encoded)
  init:    POST https://open.tiktokapis.com/v2/post/publish/inbox/video/init/   scope video.upload
  upload:  PUT  <upload_url>  Content-Range: bytes a-b/total
  status:  POST https://open.tiktokapis.com/v2/post/publish/status/fetch/
Unaudited apps can only Direct-Post privately; the inbox (draft) flow is used instead, and the
creator finishes the post in the TikTok app (caption, cover, visibility).
"""
import json, math, os, sys, time, urllib.parse, urllib.request

API = os.environ.get("TIKTOK_API_BASE", "https://open.tiktokapis.com")  # override only for tests
MB = 1024 * 1024
TOKEN_FILE = os.environ.get("NEW_REFRESH_TOKEN_FILE", "new_refresh_token.txt")


def _req(method, url, data=None, headers=None, raw=None, timeout=120):
    body = raw if raw is not None else (None if data is None else data)
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(txt) if txt.strip().startswith("{") else txt)
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(txt)
        except ValueError:
            return e.code, txt


def _need(*names):
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        sys.exit(f"Missing environment variables: {', '.join(missing)}")


def _save_refresh(tok):
    with open(TOKEN_FILE, "w") as f:
        f.write(tok["refresh_token"])
    print(f"token ok: access expires in {tok.get('expires_in')}s, "
          f"refresh expires in {tok.get('refresh_expires_in')}s, scope={tok.get('scope')}")


def token_request(params):
    # length/prefix diagnostics only (never the value) to spot copy-paste mistakes
    ck, cs = params.get("client_key", ""), params.get("client_secret", "")
    print(f"client_key: {len(ck)} chars, starts with {ck[:2]!r}; client_secret: {len(cs)} chars")
    form = urllib.parse.urlencode(params).encode()
    code, res = _req("POST", f"{API}/v2/oauth/token/", data=form,
                     headers={"Content-Type": "application/x-www-form-urlencoded",
                              "Cache-Control": "no-cache"})
    if code != 200 or not isinstance(res, dict) or "access_token" not in res:
        # never echo the request; the response holds no secret when it failed
        sys.exit(f"token request failed (HTTP {code}): "
                 f"{res.get('error') if isinstance(res, dict) else res} "
                 f"{res.get('error_description', '') if isinstance(res, dict) else ''}")
    return res


def exchange():
    _need("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "AUTH_CODE", "REDIRECT_URI")
    params = {"client_key": os.environ["TIKTOK_CLIENT_KEY"].strip(),
              "client_secret": os.environ["TIKTOK_CLIENT_SECRET"].strip(),
              "code": urllib.parse.unquote(os.environ["AUTH_CODE"].strip()),
              "grant_type": "authorization_code",
              "redirect_uri": os.environ["REDIRECT_URI"].strip()}
    if os.environ.get("CODE_VERIFIER"):
        params["code_verifier"] = os.environ["CODE_VERIFIER"]
    _save_refresh(token_request(params))


def refresh():
    _need("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN")
    tok = token_request({"client_key": os.environ["TIKTOK_CLIENT_KEY"].strip(),
                         "client_secret": os.environ["TIKTOK_CLIENT_SECRET"].strip(),
                         "grant_type": "refresh_token",
                         "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"].strip()})
    _save_refresh(tok)  # TikTok may rotate the refresh token: always store the newest one
    if "video.upload" not in str(tok.get("scope", "")):
        sys.exit(f"token lacks the video.upload scope (scope={tok.get('scope')}). "
                 "Re-run authorize with scope user.info.basic,video.upload.")
    return tok["access_token"]


def upload(path):
    size = os.path.getsize(path)
    if size < 5 * MB or size <= 64 * MB:
        chunk, count = size, 1                     # whole file in one request
    else:
        chunk = 10 * MB
        count = size // chunk                      # last chunk absorbs the remainder (<=128 MB rule)
    access = refresh()
    auth = {"Authorization": f"Bearer {access}", "Content-Type": "application/json; charset=UTF-8"}
    body = json.dumps({"source_info": {"source": "FILE_UPLOAD", "video_size": size,
                                       "chunk_size": chunk, "total_chunk_count": count}}).encode()
    code, res = _req("POST", f"{API}/v2/post/publish/inbox/video/init/", data=body, headers=auth)
    err = (res.get("error") or {}) if isinstance(res, dict) else {}
    if code != 200 or err.get("code") not in (None, "ok"):
        sys.exit(f"init failed (HTTP {code}): {err.get('code')} {err.get('message')} "
                 f"log_id={err.get('log_id')}")
    publish_id, url = res["data"]["publish_id"], res["data"]["upload_url"]
    print(f"init ok: publish_id={publish_id}, {count} chunk(s), {size/MB:.1f} MB")

    with open(path, "rb") as f:
        for i in range(count):
            start = i * chunk
            end = size - 1 if i == count - 1 else start + chunk - 1
            f.seek(start)
            data = f.read(end - start + 1)
            for attempt in range(4):
                c, r = _req("PUT", url, raw=data, timeout=600, headers={
                    "Content-Type": "video/mp4", "Content-Length": str(len(data)),
                    "Content-Range": f"bytes {start}-{end}/{size}"})
                if c in (200, 201, 206):
                    break
                print(f"chunk {i+1} attempt {attempt+1} failed: HTTP {c} {str(r)[:200]}")
                time.sleep(3 * (attempt + 1))
            else:
                sys.exit("upload failed")
            print(f"chunk {i+1}/{count} uploaded ({c})")

    final = None
    for _ in range(40):                            # up to ~4 minutes
        time.sleep(6)
        c, r = _req("POST", f"{API}/v2/post/publish/status/fetch/",
                    data=json.dumps({"publish_id": publish_id}).encode(), headers=auth)
        st = (r.get("data") or {}) if isinstance(r, dict) else {}
        final = st.get("status")
        print(f"status: {final} {st.get('fail_reason') or ''}")
        if final in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE", "FAILED"):
            break
    if final == "FAILED":
        sys.exit("TikTok reported FAILED")
    if final not in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"):
        print("::warning::status not final yet; check the TikTok app inbox in a few minutes")
    print(f"done: publish_id={publish_id} status={final}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "exchange":
        exchange()
    elif len(sys.argv) >= 3 and sys.argv[1] == "upload":
        upload(sys.argv[2])
    else:
        sys.exit(__doc__)
